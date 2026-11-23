#!/usr/bin/env bash
# The one command that proves a change is OK. Agents, git hooks and CI all run
# this, so local and CI results match. Exit non-zero on any failure.
#
# Fill in the TODO lines for this project's stack, then delete the guard below.
set -euo pipefail
cd "$(dirname "$0")/.."

echo "== whitespace"
base="${CHECK_BASE:-origin/main}"
if git rev-parse --verify -q "$base" >/dev/null; then
  git diff --check "$base"...HEAD || { echo "whitespace errors"; exit 1; }
fi
git diff --check && git diff --cached --check || { echo "whitespace errors in uncommitted changes"; exit 1; }

# --- guard: remove once real checks are filled in -------------------------
echo "scripts/check.sh has no project checks yet. Fill in install, lint," >&2
echo "typecheck and test below (see the setup issue), then remove this guard." >&2
exit 1
# ---------------------------------------------------------------------------

echo "== install"
# TODO e.g. npm ci  |  pnpm install --frozen-lockfile  |  uv sync

echo "== lint"
# TODO e.g. npm run lint

echo "== typecheck"
# TODO e.g. npx tsc --noEmit

echo "== test"
# TODO e.g. npm test

echo "ALL CHECKS PASSED"
