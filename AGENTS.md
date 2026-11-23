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

Needs `gh` logged in. One issue, one branch, one PR.

1. `/grill` the idea until every decision is settled; `/domain-docs` records
   terms in `GLOSSARY.md` and lasting decisions as ADRs.
2. `/to-spec` writes the spec as an issue labelled `spec`.
3. `/to-issues` splits it into small issues with acceptance criteria and blockers.
4. `/pick-issue` takes one and starts the workflow.

New project: `/new-project`. Labels: `spec`, `ready`, `in-progress`,
`needs-review`, `blocked`. Never create repos, issues or labels the user didn't
confirm. Private by default. Small ad-hoc tasks can skip issues.

## Workflow

1. **Isolate.** `/new-feature`: own worktree and branch from `origin/main`.
   Never build on `main`.
2. **Build.** Follow `/code-structure` and the repo's existing architecture.
   Reuse before writing new. For user-facing UI, follow `/ui-design`.
3. **Prove.** Run `scripts/check.sh`. For changed behaviour, `/prove`: the
   failure before the fix and the success after. For UI, `/design-review`.
4. **Ship.** `/ship`: commit, rebase, push, open the PR (`/pr` writes the body),
   then `/review-loop` until the gate passes. End with the PR URL.

When a task went badly, or every few PRs, run `/retro` to improve the setup.

## Brakes

- `scripts/check.sh` runs locally, in the git `pre-push` hook and in CI. A
  failing check is a stop, not a suggestion.
- Git hooks (`.githooks/`) and, in Claude Code, a guardrail hook block commits
  on `main`, pushes to `main`, plain force-push, `reset --hard` and `clean -f`.
  Don't work around them; if one blocks you, stop and say why you needed it.
- Review runs on two axes (standards and spec) in `/review-loop`.

## Multi-agent rules

- One worktree and branch per task and per agent. Never touch another agent's
  worktree, branch or uncommitted work.
- Only `--force-with-lease`, only on your own task branch.
- Scope check before starting: skim open PRs' changed files. Stop and ask only
  when changes conflict in behaviour or ownership is unclear.
- Worktrees don't isolate ports or databases. Confirm a port answers your
  process; no schema experiments on a shared database.
- Regenerate lockfiles on conflict; never hand-merge them.
- Don't merge a PR unless asked. Keep the worktree until it is merged or closed.

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

## Conventions

<!-- Fill in per project: language/runtime, architecture, anything unusual. -->
- Branch prefix: `agent/`
- Review gate: A (two-axis review). See `skills/review-loop/SKILL.md`.
- Style mode: <!-- A quiet light | B cinematic dark; see design-references/STYLE.md -->
- Main references: <!-- e.g. vortex-studio-hero, fastshot; see design-references/INDEX.md -->

## Checks in this repo

- `scripts/check.sh` (fill in its install, lint, typecheck and test lines)
