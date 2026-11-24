# Agent workflow (code factory)

This file is the factory. It tells any coding agent how to take work from an
idea to a reviewed pull request. Skills hold the detail; this file decides
which skill runs when. Keep it short: rules that a tool can check belong in
`scripts/check.sh`, and review rules belong in `CODING_STANDARDS.md`.

## How to read this file

Works with any model and harness. Skills are named like `/new-feature`. If your
harness has slash commands, run them. If not, load the skill of that name from
the skills folder (`.claude/skills`, `.agents/skills`, `.cursor/skills`, or
wherever your harness keeps them) and follow it. Where a skill mentions a
capability your harness lacks (subagents, a browser, computer use), use the
fallback it names, and say in the PR what you could not do.

## Where to look

- `GLOSSARY.md`: the project's words. Use them exactly in code, issues and PRs.
- `docs/adr/`: decisions and why. Don't undo one silently.
- `CODING_STANDARDS.md`: judgement-call rules, applied in review.
- `scripts/check.sh`: the one command that proves a change works.
- `design-references/`: the look to match for UI work.

## Pick the parts that fit the task

- Read-only reviews, explanations and investigations: no branch, commit or PR.
- Big, vague or risky work: plan it first (below).
- Code changes: all four workflow steps.
- Small docs edits: own branch plus content checks; no evidence or review loop.
- A request for a plan, review or experiment does not imply publishing it.

## Plan, then track it in issues

Needs `gh` logged in, or the GitHub MCP tools: wherever a skill says `gh`, use
the matching MCP tool if `gh` isn't available. One issue, one branch, one PR.

1. `/grill` the idea until every decision is settled; `/domain-docs` records
   terms in `GLOSSARY.md` and lasting decisions as ADRs.
2. `/to-spec` writes the spec as an issue labelled `spec`.
3. `/to-issues` splits it into small issues with acceptance criteria and blockers.
4. `/pick-issue` takes one and starts the workflow. To run several at once,
   `/dispatch` is the orchestrator: it picks a batch that won't collide, gives
   each worker a focused brief, launches them after the user's yes, and gets
   each PR reviewed by a separate context.

New project: `/new-project`. Labels: `spec`, `ready`, `in-progress`,
`needs-review`, `blocked`, `human-verified`. Never create repos, issues or labels
the user didn't confirm. Private by default. Small ad-hoc tasks can skip issues.

**Human-verified issues** (label `human-verified`) need the user to check
something by hand, such as hardware, feel or a live demo. For these the PR says
`Refs #<n>`, never `Closes`, so merging doesn't close the issue. Criteria that
need the human stay unticked, marked "(needs you)". Only the user closes the
issue. Every other issue uses `Closes #<n>`.

**Blockers.** `Blocked by #n` is a hard gate: it holds until issue n is closed.
A human-verified issue stays open until the user closes it, so it is not listed
under `Blocked by` unless the user names it as a gate. List it as `Builds on #n`
instead: start once its PR is merged to `main`, whether or not the issue is closed.

## Workflow

1. **Isolate.** `/new-feature`: own worktree and branch from `origin/main`.
   Never build on `main`.
2. **Build.** Follow `/code-structure` and the repo's existing architecture.
   Reuse before writing new. For user-facing UI, follow `/ui-design`.
3. **Prove.** Run `scripts/check.sh`. For changed behaviour, `/prove`: the
   failure before the fix and the success after. For UI, `/design-review`.
4. **Ship.** `/ship`: commit, rebase, push, open the PR (`/pr` writes the body),
   then `/review-loop` until the gate passes. Merge if the Merging rules below
   allow it; either way end with the PR URL.

When a task went badly, or every few PRs, run `/retro` to improve the setup.

## Brakes

- `scripts/check.sh` runs locally, in the git `pre-push` hook and in CI. A
  failing check is a stop, not a suggestion.
- Git hooks (`.githooks/`) and, in Claude Code, a guardrail hook block commits
  on `main`, pushes to `main`, plain force-push, `reset --hard` and `clean -f`.
  Don't work around them; if one blocks you, stop and say why you needed it.
- Review runs on two axes (standards and spec) in `/review-loop`.

## Merging

An agent may merge its own PR (squash, pinned to the reviewed head commit) once
all of these hold on that commit:

- Every CI job is green on that head commit (a skipped or cancelled job is not
  green), and there is no merge conflict.
- The review gate passed from an independent context (a subagent, another
  session or a review bot; not the agent that wrote the code), and its result is
  a comment on the PR that names that head commit. A self-review never counts:
  hand the PR to the user.
- The PR links no `human-verified` issue, whether by `Closes` or `Refs`. For
  those the user merges, and closes the issue after trying it.
- The PR does not change the rules or brakes: `AGENTS.md`, `CLAUDE.md`,
  `.claude/`, `.githooks/`, `.github/`, `CODING_STANDARDS.md`, `scripts/`, or the
  dependencies and the build, lint, type and test settings in `pyproject.toml`
  and `uv.lock`. The user merges those.
- The PR's merge danger is a two-way door (a one-way door is a destructive
  action; see below).

Never merge on red, stale or missing CI or review, and never use an override
(`SKIP_CHECKS`, `ALLOW_MAIN`, plain force-push) to get there.

## When to ask the user

Beyond the confirmations this file already requires (creating repos, issues or
labels; launching `/dispatch` workers; stopping when a brake blocks you), stop
and ask only for:

1. the same failure twice (same cause, after a real attempt to fix it);
2. adding a new dependency;
3. anything that touches secrets;
4. a destructive or one-way action (deleting data or branches that hold unmerged
   work, plain force-push, a one-way-door merge).

For everything else, decide, write the assumption in the PR, and carry on. The
Never rules in this file still apply.

Before escalating a CI or tooling failure, search the web and the GitHub
changelog (https://github.blog/changelog/) for the cause, and say what you found.

## Multi-agent rules

- One worktree and branch per task and per agent. Never touch another agent's
  worktree, branch or uncommitted work.
- Only `--force-with-lease`, only on your own task branch.
- Scope check before starting: skim open PRs' changed files. Stop and ask only
  when changes conflict in behaviour or ownership is unclear.
- Worktrees don't isolate ports or databases. Confirm a port answers your
  process; no schema experiments on a shared database.
- Regenerate lockfiles on conflict; never hand-merge them.
- Merge only as the Merging rules allow. Keep the worktree until it is merged or closed.

## Periodic: untangle the codebase

`/untangle-codebase` is optional and not bundled. If you have it, run it only
when asked, or suggest it when the repo has grown messy or after about ten
merged PRs: from green checks, in its own branch and PR, behaviour unchanged,
and ask before it removes comments or tests.

## Done means

- Changes stay inside the task's scope.
- `scripts/check.sh` passes on the final commit, and CI is green.
- The PR follows `/pr`: sketch, evidence, criteria, merge danger.
- For UI changes, `/design-review` screenshots are in the PR.
- The review gate passed, or you report the real result and what is open.
  Never claim success you didn't get.
- The PR is merged under the Merging rules, or handed to the user with its URL.

## Conventions

<!-- Fill in per project: language/runtime, architecture, anything unusual. -->
- Branch prefix: `agent/`
- Review gate: A (two-axis review). See `skills/review-loop/SKILL.md`.
- Style mode: <!-- A quiet light | B cinematic dark; see design-references/STYLE.md -->
- Main references: <!-- e.g. vortex-studio-hero, fastshot; see design-references/INDEX.md -->

## Checks in this repo

- `scripts/check.sh`: whitespace, `uv sync --locked`, `ruff check`, `ruff format --check`, `pyright`, `pytest`.
