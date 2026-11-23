---
name: new-project
description: Use when the user wants to start a new project. Creates a private GitHub repo with gh, installs the code factory into it, and opens the setup issues so the agent can build the foundations through the normal flow.
---

# New Project

Start a project the factory can run on.

## Before anything

1. Check `gh auth status`, or that the GitHub MCP tools are available. If
   neither works, stop and tell the user.
2. Confirm with the user, in one message: **repo name**, **owner** (default: the
   logged-in account), **visibility** (default: private), **stack**, and
   **one line on what it is**. Creating a repo is visible outside this machine,
   so don't create it until they say yes.
3. Find the factory folder (the repo containing `install.sh`). If you can't,
   ask where it is.

## Steps

1. **Create and clone:**
   `gh repo create <owner>/<name> --private --clone --description "<one line>"`
   (use `--public` only if the user asked).
2. **Install the factory:** `<factory>/install.sh repo <project> --target <t>`
   for the user's harness (`claude`, `agents`, `cursor`, `all`). It adds
   `AGENTS.md`, skills, `design-references/`, `.github/` templates and CI,
   `CODING_STANDARDS.md`, `scripts/check.sh` and the git hooks.
3. **Write a short `README.md`** (one-line description, stack, how to run) and
   a `.gitignore` for the stack. This first scaffold is the only commit on
   `main`; the hooks block it, so use the one-off override and tell the user:
   `ALLOW_MAIN=1 git commit ...` and `ALLOW_MAIN=1 SKIP_CHECKS=1 git push`.
   Every later change goes through a branch and PR.
4. **Create labels:** `spec`, `ready`, `in-progress`, `needs-review`, `blocked`,
   `human-verified` (`gh label create`; ignore "already exists").
5. **Open the setup issues** with the `to-issues` skill, after the user confirms
   the list. Defaults, in order:
   - Fill in `scripts/check.sh` (install, lint, typecheck, test) and remove its
     guard; add the runtime to `.github/workflows/checks.yml`. Until this
     lands, push with `SKIP_CHECKS=1` and expect CI to fail.
   - Choose the stack, record it as the first ADR, and write `skills/code-structure`.
   - Start `GLOSSARY.md` with the core domain terms (`domain-docs`).
   - Once the app runs: `create-verification-skill` to script launching and
     driving it.
   - First project rules in `CODING_STANDARDS.md`.
   - If there is a UI: choose the `STYLE.md` mode and main references (record
     both in `AGENTS.md` Conventions), then build design tokens and base styles.
   - First vertical slice of the product (better: `grill`, then `to-spec`).
6. **Push and report:** the repo URL, the issue list, and which issue to take
   first with `pick-issue`.

## Rules

- Private by default. Never push secrets; add `.gitignore` for the stack first.
- Don't create anything the user didn't confirm (repo, labels, issues).
- Don't build features in this skill. Setup only; the work goes through issues.
