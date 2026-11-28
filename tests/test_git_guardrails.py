"""The git-guardrails hook (.claude/hooks/git-guardrails.py), against a real temp repo.

The repo's main checkout is on `main`; a linked worktree is on a task branch.
Each test runs the hook on a Bash command and checks it is blocked (exit 2) or
allowed (exit 0). Git config from HOME and the system is ignored.
"""

import importlib.util
import io
import json
import os
import shutil
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path
from types import ModuleType
from typing import Any

import pytest

HOOK = Path(__file__).resolve().parents[1] / ".claude" / "hooks" / "git-guardrails.py"
BLOCK, ALLOW = 2, 0

GIT_ENV = {
    "GIT_CONFIG_GLOBAL": os.devnull,
    "GIT_CONFIG_SYSTEM": os.devnull,
    "GIT_AUTHOR_NAME": "Test",
    "GIT_AUTHOR_EMAIL": "test@example.invalid",
    "GIT_COMMITTER_NAME": "Test",
    "GIT_COMMITTER_EMAIL": "test@example.invalid",
}


def load_hook() -> ModuleType:
    spec = importlib.util.spec_from_file_location("git_guardrails", HOOK)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


hook = load_hook()


@dataclass
class Repo:
    main: Path  # the main checkout, on `main`
    worktree: Path  # a linked worktree on `agent/task`
    plain: Path  # a directory that is not a git work tree


def git(cwd: Path, *args: str) -> None:
    env = {k: v for k, v in os.environ.items() if not k.startswith("GIT_")} | GIT_ENV
    subprocess.run(["git", *args], cwd=cwd, env=env, check=True, capture_output=True)


def make_repo(root: Path, branch: str) -> Repo:
    main = root / "main"
    (main / "src").mkdir(parents=True)
    git(main, "init", "-q", "-b", branch)
    (main / "src" / "file.txt").write_text("hello\n")
    git(main, "add", "src/file.txt")
    git(main, "commit", "-q", "-m", "first")
    worktree = root / "wt"
    git(main, "worktree", "add", "-q", "-b", "agent/task", str(worktree))
    plain = root / "plain"
    plain.mkdir()
    return Repo(main=main, worktree=worktree, plain=plain)


@pytest.fixture
def repo(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Repo:
    for name in ("GIT_DIR", "GIT_WORK_TREE", "CDPATH"):
        monkeypatch.delenv(name, raising=False)
    for name, value in GIT_ENV.items():
        monkeypatch.setenv(name, value)
    return make_repo(tmp_path, "main")


def hook_input(command: str, cwd: Path) -> str:
    return json.dumps({"tool_name": "Bash", "tool_input": {"command": command}, "cwd": str(cwd)})


def run_in_process(command: str, cwd: Path, monkeypatch: pytest.MonkeyPatch) -> int:
    monkeypatch.setattr(sys, "stdin", io.StringIO(hook_input(command, cwd)))
    return hook.main()


def run_subprocess(stdin: str) -> subprocess.CompletedProcess[str]:
    env = {k: v for k, v in os.environ.items() if not k.startswith("GIT_")} | GIT_ENV
    env.pop("CDPATH", None)
    return subprocess.run(
        [sys.executable, str(HOOK)], input=stdin, env=env, capture_output=True, text=True
    )


def check(repo: Repo, mp: pytest.MonkeyPatch, command: str, session: Path | None = None) -> int:
    return run_in_process(command, session or repo.main, mp)


# (1) and (9): no cd or -C judges the session cwd.


def test_commit_in_session_cwd_on_main_is_blocked(repo: Repo, monkeypatch: pytest.MonkeyPatch):
    assert check(repo, monkeypatch, "git commit -m x") == BLOCK


def test_commit_in_session_cwd_on_task_branch_is_allowed(
    repo: Repo, monkeypatch: pytest.MonkeyPatch
):
    assert check(repo, monkeypatch, "git commit -m x", repo.worktree) == ALLOW


def test_detached_head_is_allowed_as_before(
    repo: Repo, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
):
    detached = tmp_path / "detached"
    git(repo.main, "worktree", "add", "-q", "--detach", str(detached))
    assert check(repo, monkeypatch, "git commit -m x", detached) == ALLOW
    assert check(repo, monkeypatch, f"cd {detached} && git commit -m x") == ALLOW


# (2), (3), (4): cd and -C are followed, in both directions.


def test_cd_into_worktree_then_commit_is_allowed(repo: Repo, monkeypatch: pytest.MonkeyPatch):
    assert check(repo, monkeypatch, f"cd {repo.worktree} && git commit -m x") == ALLOW


def test_git_dash_c_worktree_commit_is_allowed(repo: Repo, monkeypatch: pytest.MonkeyPatch):
    assert check(repo, monkeypatch, f"git -C {repo.worktree} commit -m x") == ALLOW


@pytest.mark.parametrize("form", ["git -C {main} commit -m x", "cd {main} && git commit -m x"])
def test_commit_targeting_main_is_blocked_even_from_a_worktree_session(
    repo: Repo, monkeypatch: pytest.MonkeyPatch, form: str
):
    command = form.format(main=repo.main)
    assert check(repo, monkeypatch, command) == BLOCK
    assert check(repo, monkeypatch, command, repo.worktree) == BLOCK


# (5): paths that don't resolve to a git work tree.


@pytest.mark.parametrize(
    "command",
    [
        "cd /nonexistent/guardrail && git commit -m x",
        "git -C /nonexistent/guardrail commit -m x",
        "cd {plain} && git commit -m x",
        "git -C {plain} commit -m x",
        "cd {main}/.git && git commit -m x",
    ],
)
def test_commit_outside_a_work_tree_is_blocked(
    repo: Repo, monkeypatch: pytest.MonkeyPatch, command: str
):
    command = command.format(plain=repo.plain, main=repo.main)
    assert check(repo, monkeypatch, command, repo.worktree) == BLOCK


def test_commit_in_session_cwd_outside_a_work_tree_is_blocked(
    repo: Repo, monkeypatch: pytest.MonkeyPatch
):
    assert check(repo, monkeypatch, "git commit -m x", repo.plain) == BLOCK


# (6): the target can't be worked out statically.


@pytest.mark.parametrize(
    "command",
    [
        "cd && git commit -m x",
        "cd - && git commit -m x",
        "cd ~ && git commit -m x",
        "cd ~/wt && git commit -m x",
        "cd $WT && git commit -m x",
        'cd "$WT" && git commit -m x',
        "cd $(pwd) && git commit -m x",
        "cd `pwd` && git commit -m x",
        "cd {wt}* && git commit -m x",
        "cd {wt} {main} && git commit -m x",
        "git -C $WT commit -m x",
        "git -C ~ commit -m x",
        "(cd {wt} && git commit -m x)",
        "{{ cd {wt}; git commit -m x; }}",
        "bash -c 'cd {wt} && git commit -m x'",
        "sh -c 'git commit -m x'",
        "eval 'git commit -m x'",
        "env git commit -m x",
        "eval cd {main}; git -C {wt} status; git commit -m x",
        "pushd {wt} && git commit -m x",
        "pushd {wt} && popd && git commit -m x",
        "git --git-dir={main}/.git commit -m x",
        "git --work-tree {wt} commit -m x",
        "GIT_DIR={main}/.git git commit -m x",
        "GIT_WORK_TREE={wt} git commit -m x",
        "export GIT_DIR={main}/.git; git commit -m x",
        "git -c alias.ci=commit ci -m x",
        "alias g='git -C {main}'\ng commit -m x",
        'g() {{ git -C {main} "$@"; }}; g commit -m x',
        "$GIT commit -m x",
        "if true; then git commit -m x; fi",
        "cd {main} | true; git commit -m x",
        "git commit -m 'unbalanced",
        'echo "$(cd {main} && git commit -am x)"',
        'git commit -m "$(git commit -am y)"',
        "git commit -F - <<EOF\nmessage\n",
    ],
)
def test_commit_with_an_unknowable_target_is_blocked(
    repo: Repo, monkeypatch: pytest.MonkeyPatch, command: str
):
    command = command.format(wt=repo.worktree, main=repo.main)
    monkeypatch.setenv("WT", str(repo.worktree))
    assert check(repo, monkeypatch, command, repo.worktree) == BLOCK


def test_git_dir_in_the_environment_blocks_commits(repo: Repo, monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("GIT_DIR", str(repo.main / ".git"))
    assert check(repo, monkeypatch, "git commit -m x", repo.worktree) == BLOCK


def test_relative_cd_with_cdpath_set_is_blocked(repo: Repo, monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("CDPATH", str(repo.main.parent))
    assert check(repo, monkeypatch, "cd wt && git commit -m x", repo.main.parent) == BLOCK


# (7): relative paths, trailing slashes, symlinks.


@pytest.mark.parametrize(
    "command",
    [
        "cd wt && git commit -m x",
        "cd ./wt/ && git commit -m x",
        "git -C wt commit -m x",
        "git -C wt/ commit -m x",
        "cd main && git -C ../wt commit -m x",
        "git -C main -C ../wt commit -m x",
        "cd -P wt && git commit -m x",
        "cd -- wt && git commit -m x",
    ],
)
def test_relative_paths_into_the_worktree_are_allowed(
    repo: Repo, monkeypatch: pytest.MonkeyPatch, command: str
):
    assert check(repo, monkeypatch, command, repo.main.parent) == ALLOW


@pytest.mark.parametrize(
    "command",
    [
        "cd ../main && git commit -m x",
        "cd ../main/ && git commit -m x",
        "git -C ../main commit -m x",
        "git -C .. -C main commit -m x",
        "cd .. && git -C main commit -m x",
    ],
)
def test_relative_paths_back_to_main_are_blocked(
    repo: Repo, monkeypatch: pytest.MonkeyPatch, command: str
):
    assert check(repo, monkeypatch, command, repo.worktree) == BLOCK


def test_symlink_to_the_main_checkout_is_judged_as_main(
    repo: Repo, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
):
    link = tmp_path / "link"
    link.symlink_to(repo.main)
    assert check(repo, monkeypatch, f"cd {link} && git commit -m x", repo.worktree) == BLOCK
    assert check(repo, monkeypatch, f"git -C {link} commit -m x", repo.worktree) == BLOCK
    assert check(repo, monkeypatch, "git commit -m x", link) == BLOCK


def test_symlink_to_the_worktree_is_allowed(
    repo: Repo, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
):
    link = tmp_path / "wtlink"
    link.symlink_to(repo.worktree)
    assert check(repo, monkeypatch, f"cd {link} && git commit -m x") == ALLOW


# (8): chains and separators.


@pytest.mark.parametrize(
    ("command", "expected"),
    [
        ("cd {root} && cd wt && git commit -m x", ALLOW),
        ("cd {wt} && cd {main} && git commit -m x", BLOCK),
        ("cd {main} && cd {wt} && git commit -m x", ALLOW),
        ("cd {wt}; git commit -m x", ALLOW),
        ("cd {main}; git commit -m x", BLOCK),
        ("cd {wt}\ngit commit -m x", ALLOW),
        ("cd {main}\ngit commit -m x", BLOCK),
        ("false || git commit -m x", BLOCK),
        ("cd {wt} && git add -A && git commit -m x && git push -u origin agent/task", ALLOW),
        ("cd {wt} && git commit -m x; cd {main} && git commit -m y", BLOCK),
        ("cd {wt} # enter the worktree\ngit commit -m x", ALLOW),
        ("cd {wt} && git commit -m 'fix; cd {main}'", ALLOW),
        ("cd {wt} > /dev/null && git commit -m x", ALLOW),
        ("cd {wt} && \\\ngit commit -m x", ALLOW),
        ("cd $X; git -C {wt} commit -m x", ALLOW),
        ("cd $X; git -C {main} commit -m x", BLOCK),
        ("cd $X; git -C wt commit -m x", BLOCK),
        ("cd {main} && \\\ngit commit -m x", BLOCK),
    ],
)
def test_chains_follow_every_cd(
    repo: Repo, monkeypatch: pytest.MonkeyPatch, command: str, expected: int
):
    command = command.format(root=repo.main.parent, wt=repo.worktree, main=repo.main)
    assert check(repo, monkeypatch, command) == expected


def test_heredoc_commit_message_in_the_worktree_is_allowed(
    repo: Repo, monkeypatch: pytest.MonkeyPatch
):
    message = "Fix the git commit check\n\nDon't block worktrees.\n"
    substitution = f"git commit -m \"$(cat <<'EOF'\n{message}EOF\n)\""
    heredoc = f"git commit -F - <<'EOF'\n{message}EOF"
    for form in (substitution, heredoc):
        assert check(repo, monkeypatch, f"cd {repo.worktree} && {form}") == ALLOW
        assert check(repo, monkeypatch, form) == BLOCK


# (10): the other rules are unchanged and ordinary commands pass.


@pytest.mark.parametrize(
    "command",
    [
        "git push --force origin agent/task",
        "git push -f",
        "git push origin main",
        "git reset --hard HEAD~1",
        "git clean -fd",
        "git checkout .",
        "git restore .",
        "git branch -D main",
    ],
)
def test_existing_rules_still_block(repo: Repo, monkeypatch: pytest.MonkeyPatch, command: str):
    assert check(repo, monkeypatch, command, repo.worktree) == BLOCK
    assert check(repo, monkeypatch, f"cd {repo.worktree} && {command}") == BLOCK


@pytest.mark.parametrize(
    "command",
    [
        "git status",
        "git log --oneline -3",
        "git push --force-with-lease origin agent/task",
        "git log --grep commit",
        "cd ~ && ls",
        "ls 'unbalanced",
    ],
)
def test_ordinary_commands_pass(repo: Repo, monkeypatch: pytest.MonkeyPatch, command: str):
    assert check(repo, monkeypatch, command) == ALLOW


# The hook as Claude Code runs it: JSON on stdin, exit code, message on stderr.


def test_subprocess_blocks_a_commit_on_main_with_a_message(repo: Repo):
    result = run_subprocess(hook_input("git commit -m x", repo.main))
    assert result.returncode == BLOCK
    assert "BLOCKED by git-guardrails: committing on main" in result.stderr


@pytest.mark.parametrize(
    ("form", "expected"),
    [
        ("cd {wt} && git commit -m x", ALLOW),
        ("git -C {wt} commit -m x", ALLOW),
        ("cd {main} && git commit -m x", BLOCK),
        ("git -C /nonexistent/guardrail commit -m x", BLOCK),
        ("git push --force", BLOCK),
        ("git status", ALLOW),
    ],
)
def test_subprocess_decisions(repo: Repo, form: str, expected: int):
    command = form.format(wt=repo.worktree, main=repo.main)
    session = repo.worktree if "main}" in form else repo.main
    assert run_subprocess(hook_input(command, session)).returncode == expected


def test_subprocess_reports_why_an_unresolvable_path_is_blocked(repo: Repo):
    result = run_subprocess(hook_input("cd /nonexistent/guardrail && git commit", repo.main))
    assert result.returncode == BLOCK
    assert "does not exist" in result.stderr


def test_non_bash_tools_and_bad_input(repo: Repo):
    other = json.dumps({"tool_name": "Read", "tool_input": {"file_path": "x"}, "cwd": "/"})
    assert run_subprocess(other).returncode == ALLOW
    assert run_subprocess("not json").returncode == ALLOW
    assert run_subprocess("not json: git commit -m x").returncode == BLOCK


# Here-strings and here-docs: a body is data only for git or a printing `cat`.


@pytest.mark.parametrize(
    ("command", "session", "expected"),
    [
        ("cat <<< x\ngit commit -m y\nx", "main", BLOCK),
        ("cat <<<x\ngit commit -m y\nx", "main", BLOCK),
        ("cd {wt} && git commit -F - <<< 'msg'", "main", ALLOW),
        ("cd {wt} && git commit -F - <<-EOF\n\tmsg\n\tEOF", "main", ALLOW),
        ("git commit -F - <<-EOF\n\tmsg\n\tEOF", "main", BLOCK),
        ('cd {wt} && git commit -F - <<"EOF"\nmsg\nEOF', "main", ALLOW),
        ("cat <<A; cat <<B\na\nA\nb\nB\ngit commit -m x", "main", BLOCK),
        ("cat <<A; cat <<B\na\nA\nb\nB\ngit commit -m x", "wt", ALLOW),
        ("cat <<EOF\ngit commit -m x", "wt", BLOCK),
        ("bash <<'EOF'\ngit commit -m x\nEOF", "main", BLOCK),
        ("sh <<EOF\ngit commit -m x\nEOF", "main", BLOCK),
        ("bash <<'EOF'\ngit -C {main} commit -m x\nEOF", "wt", BLOCK),
        ("python3 <<'EOF'\nimport os; os.system('git commit -m y')\nEOF", "main", BLOCK),
        ("python3 <<'EOF'\nimport os; os.system('git commit -m y')\nEOF", "wt", ALLOW),
        ("cat <<'EOF' | bash\ngit commit -m x\nEOF", "wt", BLOCK),
        ("cat <<'EOF'\ngit commit -m x\nEOF", "main", ALLOW),
        ("eval \"$(cat <<'EOF'\ngit commit -m x\nEOF\n)\"", "wt", BLOCK),
        ("cat <<EOF\n$(git -C {main} commit -am x)\nEOF", "wt", BLOCK),
        ("gh pr create --body \"$(cat <<'EOF'\nRun git commit here\nEOF\n)\"", "wt", ALLOW),
        ("gh pr create --body \"$(cat <<'EOF'\nRun git commit here\nEOF\n)\"", "main", BLOCK),
    ],
)
def test_here_docs_and_here_strings(
    repo: Repo, monkeypatch: pytest.MonkeyPatch, command: str, session: str, expected: int
):
    command = command.format(wt=repo.worktree, main=repo.main)
    where = repo.main if session == "main" else repo.worktree
    assert check(repo, monkeypatch, command, where) == expected


def test_commit_message_that_reads_like_commands_is_data(
    repo: Repo, monkeypatch: pytest.MonkeyPatch
):
    message = "Don't block worktrees\n\ncd ../main; git commit -am oops\n"
    for form in (
        f"git commit -m \"$(cat <<'EOF'\n{message}EOF\n)\"",
        f"git commit -F - <<'EOF'\n{message}EOF",
    ):
        assert check(repo, monkeypatch, f"cd {repo.worktree} && {form}") == ALLOW
        assert check(repo, monkeypatch, form) == BLOCK


# The hook never fails open on a command that says commit.


def test_deep_nesting_blocks_instead_of_crashing(repo: Repo, monkeypatch: pytest.MonkeyPatch):
    command = "echo " + "$(" * 1000 + "git commit -am x" + ")" * 1000
    assert check(repo, monkeypatch, command, repo.worktree) == BLOCK
    result = run_subprocess(hook_input(command, repo.main))
    assert result.returncode == BLOCK
    assert "nested too deeply" in result.stderr


def test_nul_byte_in_a_path_or_the_cwd_blocks(repo: Repo, monkeypatch: pytest.MonkeyPatch):
    assert check(repo, monkeypatch, "cd /tmp/a\x00b && git commit -m x") == BLOCK
    assert check(repo, monkeypatch, "git -C /tmp/a\x00b commit -m x") == BLOCK
    stdin = json.dumps({"tool_input": {"command": "git commit -m x"}, "cwd": "/tmp/a\x00b"})
    monkeypatch.setattr(sys, "stdin", io.StringIO(stdin))
    assert hook.main() == BLOCK


def test_unexpected_error_blocks_a_commit_but_not_other_commands(
    repo: Repo, monkeypatch: pytest.MonkeyPatch
):
    def broken(cmd: str) -> list[tuple[str, bool]]:
        raise RuntimeError("parser bug")

    monkeypatch.setattr(hook, "tokenize", broken)
    assert check(repo, monkeypatch, f"cd {repo.worktree} && git commit -m x") == BLOCK
    assert check(repo, monkeypatch, "git log $REF") == ALLOW


# Cases found by mutation testing.


def test_master_is_protected_like_main(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    for name, value in GIT_ENV.items():
        monkeypatch.setenv(name, value)
    monkeypatch.delenv("GIT_DIR", raising=False)
    master = make_repo(tmp_path, "master")
    assert run_in_process("git commit -m x", master.main, monkeypatch) == BLOCK
    assert run_in_process("git commit -m x", master.worktree, monkeypatch) == ALLOW


def test_dot_dot_after_a_symlink_into_main_is_blocked(repo: Repo, monkeypatch: pytest.MonkeyPatch):
    (repo.worktree / "link").symlink_to(repo.main / "src")
    assert check(repo, monkeypatch, f"git -C {repo.worktree}/link/.. commit -m x") == BLOCK
    assert check(repo, monkeypatch, f"cd {repo.worktree}/link/.. && git commit -m x") == BLOCK
    assert check(repo, monkeypatch, "git -C link/.. commit -m x", repo.worktree) == BLOCK
    assert check(repo, monkeypatch, "cd link/.. && git commit -m x", repo.worktree) == BLOCK


def test_variable_path_is_unresolvable_even_if_it_exists_literally(
    repo: Repo, monkeypatch: pytest.MonkeyPatch
):
    (repo.worktree / "$X").mkdir()  # read literally, `$X/..` would be the worktree
    monkeypatch.setenv("X", str(repo.main / "src"))
    assert check(repo, monkeypatch, "cd $X/.. && git commit -m x", repo.worktree) == BLOCK


def test_unreadable_branch_blocks(repo: Repo, monkeypatch: pytest.MonkeyPatch, tmp_path: Path):
    real_git = shutil.which("git")
    fake = tmp_path / "bin" / "git"
    fake.parent.mkdir()
    fake.write_text(f'#!/bin/sh\n[ "$1" = branch ] && exit 1\nexec {real_git} "$@"\n')
    fake.chmod(0o755)
    monkeypatch.setenv("PATH", f"{fake.parent}{os.pathsep}{os.environ['PATH']}")
    assert check(repo, monkeypatch, "git commit -m x", repo.worktree) == BLOCK


def test_branch_timeout_blocks(repo: Repo, monkeypatch: pytest.MonkeyPatch):
    real_run = subprocess.run

    def slow_branch(args: list[str], **kwargs: Any) -> Any:
        if "branch" in args:
            raise subprocess.TimeoutExpired(args, 5)
        return real_run(args, **kwargs)

    monkeypatch.setattr(hook.subprocess, "run", slow_branch)
    assert check(repo, monkeypatch, "git commit -m x", repo.worktree) == BLOCK


# Wrappers, `command` options, traps and split words.


@pytest.mark.parametrize(
    ("command", "expected"),
    [
        ("setsid git commit -m x", BLOCK),
        ("uv run git commit -m x", BLOCK),
        ("flock /tmp/guardrail.lock git commit -m x", BLOCK),
        ("command -p git -C {main} commit -m x", BLOCK),
        ("command -- cd {main} && git commit -m x", BLOCK),
        ("command -p git -C {wt} commit -m x", ALLOW),
        ("trap 'git -C {main} commit -am x' EXIT; git status", BLOCK),
        ("git -C {main} commi''t -m x", BLOCK),
        ("git -C {main} c\\ommit -m x", BLOCK),
        ('git -C {main} "comm"it -m x', BLOCK),
        ("git -C {wt} commi''t -m x", ALLOW),
        ("c=commit; git $c -m x", BLOCK),
    ],
)
def test_wrappers_and_split_words(
    repo: Repo, monkeypatch: pytest.MonkeyPatch, command: str, expected: int
):
    command = command.format(wt=repo.worktree, main=repo.main)
    assert check(repo, monkeypatch, command, repo.worktree) == expected


# Plausible worker commits stay allowed.


@pytest.mark.parametrize(
    "command",
    [
        "cd {wt} && git add -A && git commit -m x",
        "git -C {wt} add . && git -C {wt} commit -m x",
        "cd {wt} && git commit -m x 2>&1 | tail -3",
        "cd {wt} && git commit -m x || true",
        "cd {wt} && git commit -m x; echo done",
    ],
)
def test_worker_commit_forms_are_allowed(repo: Repo, monkeypatch: pytest.MonkeyPatch, command: str):
    command = command.format(wt=repo.worktree)
    assert check(repo, monkeypatch, command) == ALLOW
