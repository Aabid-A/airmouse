#!/usr/bin/env python3
"""Claude Code PreToolUse hook: block dangerous git commands before they run.

Reads the tool call as JSON on stdin. Exit code 2 blocks the call and shows the
message to the agent. Mirrors the rules in .githooks/ (which work for any tool)
and AGENTS.md. Idea from Matt Pocock's git-guardrails-claude-code skill (MIT).

A `git commit` is judged in the directory it will run in: the session cwd, as
changed by `cd` parts earlier in the same command and by `git -C`. It is
blocked when that directory is on main or master, and also when the directory
cannot be worked out from the command text alone (fail closed).
"""

from __future__ import annotations  # runs on the system python3, which may be old

import json
import os
import re
import shlex
import subprocess
import sys

RULES = [
    (r"\bgit\b.*\bpush\b.*(\s--force(?!-with-lease)\b|\s-f\b)",
     "plain force-push. Use --force-with-lease on your own task branch."),
    (r"\bgit\b.*\bpush\b.*(\s|:)(main|master)(\s|$)",
     "pushing to main. Push your task branch and open a PR."),
    (r"\bgit\b.*\breset\b.*--hard\b", "git reset --hard discards work."),
    (r"\bgit\b.*\bclean\b.*(\s-[a-zA-Z]*f|\s--force)", "git clean -f deletes untracked files."),
    (r"\bgit\b.*\b(checkout|restore)\b.*\s(--\s+)?\.(\s|$)", "discarding all local changes."),
    (r"\bgit\b.*\bbranch\b.*\s-D\s+(main|master)(\s|$)", "deleting main."),
]

PROTECTED_BRANCHES = ("main", "master")
COMMIT_MENTION = re.compile(r"\bgit\b.*\bcommit(\s|$)")
SUBST = "$__guardrail_subst__"  # stands in for a $(...) or `...` span

# Shell control flow, and commands that run another command. A git commit
# behind one of these cannot be judged statically.
SHELL_KEYWORDS = {
    "if", "then", "else", "elif", "fi", "do", "done", "while", "until", "for",
    "case", "esac", "select", "function", "!", "{", "}", "[[", "]]", "coproc",
}
COMMAND_RUNNERS = {
    "bash", "sh", "zsh", "dash", "ksh", "mksh", "fish", "eval", "exec", "env",
    "sudo", "doas", "su", "xargs", "nice", "nohup", "time", "timeout", "stdbuf",
    "watch", "parallel", "find", "source", ".",
}
# Commands that may change the shell's directory in ways the hook can't follow.
DIR_CHANGERS = {"pushd", "popd", "eval", "source", "."}
GIT_OPTS_WITH_ARG = {"-c", "--namespace", "--config-env", "--attr-source"}
GIT_FLAGS = {
    "-p", "--paginate", "-P", "--no-pager", "--no-replace-objects", "--no-lazy-fetch",
    "--literal-pathspecs", "--glob-pathspecs", "--noglob-pathspecs", "--icase-pathspecs",
    "--no-optional-locks", "--no-advice", "--html-path", "--man-path", "--info-path",
    "--exec-path", "-v", "--version", "-h", "--help",
}
GIT_FLAG_PREFIXES = (
    "--exec-path=", "--namespace=", "--config-env=", "--list-cmds=", "--super-prefix=",
    "--attr-source=",
)
OPERATOR = re.compile(r"&&|\|\||;;|\|&|&>>|&>|>>|<<<|<<-|<<|>&|<&|>\||[;&|()<>\n]")
REDIRECTS = {">", ">>", "<", "<<", "<<-", "<<<", ">&", "<&", "&>", "&>>", ">|"}


class Blocked(Exception):
    """The command must not run; the message says why."""


class Unknown:
    """A working directory the hook cannot work out from the command text."""

    def __init__(self, why: str) -> None:
        self.why = why


class Part:
    """One simple command: its words and how it is joined to its neighbours."""

    def __init__(self, words: list[str], before: str, after: str) -> None:
        self.words = words
        self.before = before
        self.after = after

    @property
    def in_pipeline_or_background(self) -> bool:
        return self.before in ("|", "|&") or self.after in ("|", "|&", "&")


# --- Text pre-pass: comments, here-documents and command substitutions ------


def _find_subst_end(s: str, i: int) -> int:
    """Index just past the `)` closing the `$(` that ends at s[i-1]."""
    depth = 1
    quote = ""
    heredocs: list[tuple[str, bool]] = []
    while i < len(s):
        c = s[i]
        if quote == "'":
            if c == "'":
                quote = ""
        elif c == "\\":
            i += 1
        elif quote == '"':
            if c == '"':
                quote = ""
        elif c in "'\"":
            quote = c
        elif s.startswith("<<", i) and not s.startswith("<<<", i):
            word, strip_tabs, i = _read_heredoc_word(s, i + 2)
            heredocs.append((word, strip_tabs))
            continue
        elif c == "\n" and heredocs:
            i += 1
            for word, strip_tabs in heredocs:
                i = _skip_heredoc(s, i, word, strip_tabs)
            heredocs = []
            continue
        elif c == "(":
            depth += 1
        elif c == ")":
            depth -= 1
            if depth == 0:
                return i + 1
        i += 1
    raise Blocked("unbalanced $( in the command.")


def _read_heredoc_word(s: str, i: int) -> tuple[str, bool, int]:
    """Parse the delimiter after `<<`. Returns (word, strip_tabs, end index)."""
    strip_tabs = s.startswith("-", i)
    if strip_tabs:
        i += 1
    while i < len(s) and s[i] in " \t":
        i += 1
    word = []
    while i < len(s) and s[i] not in " \t\n;&|()<>":
        c = s[i]
        if c in "'\"":
            end = s.find(c, i + 1)
            if end < 0:
                raise Blocked("unbalanced quotes in a here-document delimiter.")
            word.append(s[i + 1:end])
            i = end + 1
        elif c == "\\" and i + 1 < len(s):
            word.append(s[i + 1])
            i += 2
        else:
            word.append(c)
            i += 1
    if not word:
        raise Blocked("a here-document with no delimiter.")
    return "".join(word), strip_tabs, i


def _skip_heredoc(s: str, i: int, word: str, strip_tabs: bool) -> int:
    """From the start of a body line, index of the line after the delimiter line."""
    while i <= len(s):
        end = s.find("\n", i)
        line = s[i:] if end < 0 else s[i:end]
        if (line.lstrip("\t") if strip_tabs else line) == word:
            return len(s) if end < 0 else end + 1
        if end < 0:
            break
        i = end + 1
    raise Blocked(f"a here-document with no closing {word!r} line.")


def preprocess(cmd: str) -> tuple[str, list[str]]:
    """Drop comments and here-document bodies; cut out command substitutions.

    Returns the cleaned command, with each substitution replaced by SUBST, and
    the bodies of the substitutions.
    """
    out: list[str] = []
    bodies: list[str] = []
    heredocs: list[tuple[str, bool]] = []
    quote = ""
    i = 0
    while i < len(cmd):
        c = cmd[i]
        if quote == "'":
            out.append(c)
            if c == "'":
                quote = ""
            i += 1
            continue
        if c == "\\":
            if not cmd.startswith("\\\n", i):  # backslash-newline joins lines
                out.append(cmd[i:i + 2])
            i += 2
            continue
        if c == "`":
            end = cmd.find("`", i + 1)
            while end > 0 and cmd[end - 1] == "\\":
                end = cmd.find("`", end + 1)
            if end < 0:
                raise Blocked("unbalanced backtick in the command.")
            bodies.append(cmd[i + 1:end])
            out.append(SUBST)
            i = end + 1
            continue
        if cmd.startswith("$(", i):
            end = _find_subst_end(cmd, i + 2)
            bodies.append(cmd[i + 2:end - 1])
            out.append(SUBST)
            i = end
            continue
        if quote == '"':
            out.append(c)
            if c == '"':
                quote = ""
            i += 1
            continue
        if c in "'\"":
            quote = c
            out.append(c)
            i += 1
            continue
        if c == "#" and (i == 0 or cmd[i - 1] in " \t\n;&|()<>"):
            end = cmd.find("\n", i)
            i = len(cmd) if end < 0 else end
            continue
        if cmd.startswith("<<", i) and not cmd.startswith("<<<", i):
            word, strip_tabs, end = _read_heredoc_word(cmd, i + 2)
            heredocs.append((word, strip_tabs))
            out.append("<< " + shlex.quote(word))
            i = end
            continue
        if c == "\n" and heredocs:
            out.append(c)
            i += 1
            for word, strip_tabs in heredocs:
                i = _skip_heredoc(cmd, i, word, strip_tabs)
            heredocs = []
            continue
        out.append(c)
        i += 1
    if quote:
        raise Blocked("unbalanced quotes in the command.")
    if heredocs:
        raise Blocked("a here-document with no body.")
    return "".join(out), bodies


# --- Splitting into simple commands ------------------------------------------


def tokenize(cmd: str) -> list[tuple[str, bool]]:
    """Shell words and operators, as (text, is_operator)."""
    lexer = shlex.shlex(cmd, posix=True, punctuation_chars=";&|()<>\n")
    lexer.whitespace = " \t\r"
    lexer.commenters = ""
    lexer.whitespace_split = True
    try:
        raw = list(lexer)
    except ValueError as e:
        raise Blocked(f"the command could not be parsed ({e}).") from e
    tokens: list[tuple[str, bool]] = []
    for tok in raw:
        if tok and all(ch in ";&|()<>\n" for ch in tok):
            tokens.extend((op, True) for op in OPERATOR.findall(tok))
        else:
            tokens.append((tok, False))
    return tokens


def split_parts(tokens: list[tuple[str, bool]]) -> tuple[list[Part], bool]:
    """Simple commands in order, and whether the command uses ( ) grouping."""
    parts: list[Part] = []
    grouped = False
    words: list[str] = []
    before = ""
    skip_next = False
    for text, is_op in tokens:
        if skip_next and not is_op:
            skip_next = False
            continue
        skip_next = False
        if not is_op:
            words.append(text)
        elif text in REDIRECTS:
            skip_next = True
        elif text in ("(", ")"):
            grouped = True
            parts.append(Part(words, before, text))
            words, before = [], text
        else:  # a separator, a pipe or a background &
            parts.append(Part(words, before, text))
            words, before = [], text
    parts.append(Part(words, before, ""))
    return [p for p in parts if p.words], grouped


def command_words(words: list[str]) -> tuple[list[str], list[str]]:
    """Split leading VAR=value assignments off; drop `command`/`builtin`."""
    i = 0
    while i < len(words) and re.match(r"[A-Za-z_][A-Za-z0-9_]*=", words[i]):
        i += 1
    assigns = [w.split("=", 1)[0] for w in words[:i]]
    rest = words[i:]
    while rest and rest[0] in ("command", "builtin"):
        rest = rest[1:]
    return assigns, rest


def is_git(word: str) -> bool:
    return os.path.basename(word) == "git"


def has_expansion(word: str) -> bool:
    return "$" in word or "`" in word


# --- Working directory -------------------------------------------------------


def unresolvable(path: str) -> str | None:
    """Why `path` can't be resolved statically, or None if it can."""
    if path == "":
        return "an empty path"
    if path == "-":
        return "`cd -`"
    if path.startswith("~"):
        return f"a path starting with ~ ({path})"
    if has_expansion(path):
        return f"a path with a $ or ` expansion ({path})"
    if any(ch in path for ch in "*?[{"):
        return f"a path with a glob or brace pattern ({path})"
    return None


def apply_cd(args: list[str], cwd: str | Unknown) -> str | Unknown:
    """The directory after `cd <args>` run in `cwd`."""
    physical = False
    while args and args[0].startswith("-") and args[0] != "-":
        if args[0] == "--":
            args = args[1:]
            break
        if args[0] not in ("-L", "-P", "-e", "-LP", "-PL"):
            return Unknown(f"`cd {args[0]}` (unrecognised option)")
        physical = physical or "P" in args[0]
        args = args[1:]
    if not args:
        return Unknown("`cd` with no directory (goes to $HOME)")
    if len(args) > 1:
        return Unknown("`cd` with more than one argument")
    path = args[0]
    why = unresolvable(path)
    if why:
        return Unknown(why)
    if isinstance(cwd, Unknown):
        return cwd
    if os.environ.get("CDPATH") and not path.startswith(("/", "./", "../")) and path not in (
        ".", "..",
    ):
        return Unknown("a relative `cd` while CDPATH is set")
    joined = os.path.join(cwd, path)
    return os.path.realpath(joined) if physical else os.path.normpath(joined)


def git_commit_target(
    assigns: list[str], args: list[str], cwd: str | Unknown
) -> str | Unknown | None:
    """For `git <args>`: the directory a commit runs in, or None if not a commit."""
    if any(a in ("GIT_DIR", "GIT_WORK_TREE") for a in assigns):
        raise Blocked("GIT_DIR or GIT_WORK_TREE set on a git command next to a commit.")
    target = cwd
    i = 0
    while i < len(args):
        a = args[i]
        if a == "-C":
            if i + 1 >= len(args):
                raise Blocked("`git -C` with no directory.")
            path = args[i + 1]
            why = unresolvable(path) if path != "-" else None
            if why:
                target = Unknown(f"`git -C` with {why}")
            elif os.path.isabs(path):
                target = os.path.realpath(path)
            elif not isinstance(target, Unknown) and path:
                target = os.path.realpath(os.path.join(target, path))
            i += 2
        elif a in ("--git-dir", "--work-tree", "--bare") or a.startswith(
            ("--git-dir=", "--work-tree=")
        ):
            raise Blocked(f"`git {a}` redirects git away from the working directory.")
        elif a in GIT_OPTS_WITH_ARG:
            if a == "-c" and i + 1 < len(args) and args[i + 1].lower().startswith("alias."):
                raise Blocked("`git -c alias.…` next to a commit.")
            i += 2
        elif a in GIT_FLAGS or a.startswith(GIT_FLAG_PREFIXES):
            i += 1
        elif a.startswith("-"):
            raise Blocked(f"unrecognised git option {a!r} before the subcommand.")
        elif has_expansion(a):
            raise Blocked(f"the git subcommand is an expansion ({a}).")
        else:
            return target if a == "commit" else None
    return None


def run_git(cwd: str, *args: str) -> str | None:
    try:
        out = subprocess.run(["git", *args], cwd=cwd, capture_output=True, text=True,
                             timeout=5)
    except Exception:
        return None
    return out.stdout.strip() if out.returncode == 0 else None


def judge(cwd: str | Unknown) -> None:
    """Block a commit that would run in `cwd` unless it is a task branch."""
    if isinstance(cwd, Unknown):
        raise Blocked(f"can't tell where this commit runs: {cwd.why}. "
                      "Run `cd <worktree> && git commit ...` with a plain path.")
    real = os.path.realpath(cwd)
    if not os.path.isdir(real):
        raise Blocked(f"the commit would run in {cwd}, which does not exist.")
    if run_git(real, "rev-parse", "--is-inside-work-tree") != "true":
        raise Blocked(f"the commit would run in {cwd}, which is not a git work tree.")
    branch = run_git(real, "branch", "--show-current")
    if branch is None:
        raise Blocked(f"could not read the branch of {cwd}.")
    if branch in PROTECTED_BRANCHES:
        raise Blocked(f"committing on {branch} (in {real}). Use /new-feature to make "
                      "a task branch first, and commit inside its worktree.")


# --- The commit check --------------------------------------------------------


def mentions_commit(cmd: str) -> bool:
    """Cheap filter: only a command with the word `commit` can hold a git commit."""
    return bool(re.search(r"\bcommit\b", cmd))


def contains_commit(cmd: str) -> bool:
    """Whether a command (e.g. a substitution body) has a git commit in it."""
    if not mentions_commit(cmd):
        return False
    try:
        cleaned, bodies = preprocess(cmd)
        parts, _ = split_parts(tokenize(cleaned))
    except Blocked:
        return True
    for part in parts:
        _, words = command_words(part.words)
        if COMMIT_MENTION.search(" ".join(part.words)) or (
            words and has_expansion(words[0]) and "commit" in words
        ):
            return True
    return any(contains_commit(b) for b in bodies)


def check_commits(cmd: str, session_cwd: str) -> None:
    """Raise Blocked if any git commit in `cmd` targets main or can't be judged."""
    if not mentions_commit(cmd):
        return
    cleaned, bodies = preprocess(cmd)
    if any(contains_commit(b) for b in bodies):
        raise Blocked("git commit inside a $(...) or `...` substitution. "
                      "Run the commit as its own command.")
    parts, grouped = split_parts(tokenize(cleaned))

    plans: list[tuple[Part, list[str], list[str]]] = []
    commit_seen = False
    for part in parts:
        assigns, words = command_words(part.words)
        plans.append((part, assigns, words))
        if COMMIT_MENTION.search(" ".join(part.words)) or (
            words and has_expansion(words[0]) and "commit" in words
        ):
            commit_seen = True
    # These can hide a commit behind a name that doesn't say git (a function,
    # an alias), so they block whenever the command says `commit` at all.
    if grouped:
        raise Blocked("a ( ) subshell, group or function in a command that says commit. "
                      "Run `cd <worktree> && git commit ...` on its own.")
    if any(words and words[0] in SHELL_KEYWORDS | {"alias"} for _, _, words in plans):
        raise Blocked("shell control flow or an alias in a command that says commit. "
                      "Run `cd <worktree> && git commit ...` on its own.")
    if not commit_seen:
        return
    if re.search(r"\bGIT_(DIR|WORK_TREE)\b|\bCDPATH\b", cleaned):
        raise Blocked("GIT_DIR, GIT_WORK_TREE or CDPATH in a command with a git commit.")
    if os.environ.get("GIT_DIR") or os.environ.get("GIT_WORK_TREE"):
        raise Blocked("GIT_DIR or GIT_WORK_TREE is set in the environment.")

    cwd: str | Unknown = session_cwd
    for part, assigns, words in plans:
        if not words:
            continue
        name = words[0]
        if name == "cd":
            if part.in_pipeline_or_background:
                cwd = Unknown("`cd` in a pipeline or background job")
            elif assigns:
                cwd = Unknown("`cd` with a variable assignment")
            else:
                cwd = apply_cd(words[1:], cwd)
        elif is_git(name):
            target = git_commit_target(assigns, words[1:], cwd)
            if target is not None:
                judge(target)
        elif COMMIT_MENTION.search(" ".join(part.words)):
            if name in COMMAND_RUNNERS:
                raise Blocked(f"a git commit run through `{name}`. "
                              "Run `cd <worktree> && git commit ...` directly.")
            judge(cwd)  # some other program mentions git commit: judge as before
        elif has_expansion(name) and "commit" in words:
            raise Blocked(f"the command name is an expansion ({name}) next to `commit`.")
        if name in DIR_CHANGERS:
            cwd = Unknown(f"`{name}` can change the directory")


def main() -> int:
    raw = sys.stdin.read()
    try:
        data = json.loads(raw)
    except Exception:
        if mentions_commit(raw):
            print("BLOCKED by git-guardrails: hook input is not JSON, so a git commit "
                  "can't be checked.", file=sys.stderr)
            return 2
        return 0
    if not isinstance(data, dict) or data.get("tool_name") not in (None, "Bash"):
        return 0
    tool_input = data.get("tool_input")
    cmd = tool_input.get("command") if isinstance(tool_input, dict) else None
    if not isinstance(cmd, str):
        cmd = ""
    for part in re.split(r"&&|\|\||;|\n", cmd):
        for pattern, why in RULES:
            if re.search(pattern, part):
                print(f"BLOCKED by git-guardrails: {why}\nCommand: {part.strip()}", file=sys.stderr)
                return 2
    session_cwd = data.get("cwd")
    if not isinstance(session_cwd, str) or not session_cwd:
        session_cwd = os.getcwd()
    try:
        check_commits(cmd, session_cwd)
    except Blocked as e:
        print(f"BLOCKED by git-guardrails: {e}\nCommand: {cmd.strip()}", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main())
