#!/usr/bin/env bash
# The one command that proves a change is OK. Agents, git hooks and CI all run
# this, so local and CI results match. Exit non-zero on any failure.
set -euo pipefail
cd "$(dirname "$0")/.."

echo "== whitespace"
base="${CHECK_BASE:-origin/main}"
if git rev-parse --verify -q "$base" >/dev/null; then
  git diff --check "$base"...HEAD || { echo "whitespace errors"; exit 1; }
fi
git diff --check && git diff --cached --check || { echo "whitespace errors in uncommitted changes"; exit 1; }

command -v uv >/dev/null || { echo "uv is required: https://docs.astral.sh/uv/" >&2; exit 1; }

echo "== install"
uv sync --locked

echo "== lint"
uv run ruff check .
uv run ruff format --check .

echo "== typecheck"
uv run pyright

echo "== test"
uv run pytest

echo "ALL CHECKS PASSED"
