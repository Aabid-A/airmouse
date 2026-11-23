#!/usr/bin/env python3
"""Claude Code PreToolUse hook: block dangerous git commands before they run.

Reads the tool call as JSON on stdin. Exit code 2 blocks the call and shows the
message to the agent. Mirrors the rules in .githooks/ (which work for any tool)
and AGENTS.md. Idea from Matt Pocock's git-guardrails-claude-code skill (MIT).
"""
import json
import re
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


def current_branch(cwd):
    try:
        out = subprocess.run(["git", "branch", "--show-current"], cwd=cwd,
                             capture_output=True, text=True, timeout=5)
        return out.stdout.strip()
    except Exception:
        return ""


def main():
    try:
        data = json.load(sys.stdin)
    except Exception:
        return 0
    if data.get("tool_name") not in (None, "Bash"):
        return 0
    cmd = (data.get("tool_input") or {}).get("command", "") or ""
    for part in re.split(r"&&|\|\||;|\n", cmd):
        for pattern, why in RULES:
            if re.search(pattern, part):
                print(f"BLOCKED by git-guardrails: {why}\nCommand: {part.strip()}", file=sys.stderr)
                return 2
        if re.search(r"\bgit\b.*\bcommit(\s|$)", part) and current_branch(data.get("cwd")) in ("main", "master"):
            print("BLOCKED by git-guardrails: committing on main. Use /new-feature "
                  "to make a task branch first.", file=sys.stderr)
            return 2
    return 0


if __name__ == "__main__":
    sys.exit(main())
