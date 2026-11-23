---
name: dispatch
description: Use when the user wants several issues worked on, or asks to run the board, dispatch work, or assign agents. Acts as the orchestrator - picks a batch of unblocked issues that won't collide, builds a focused context packet for each, launches one worker per issue, tracks them to PR and review, and reports back. Never merges.
---

# Dispatch

You are the **orchestrator**. You don't write feature code. You choose work,
give each worker exactly the context it needs, launch it, and keep the board honest.

## 1. Read the board

```bash
python3 <skills-dir>/dispatch/board.py --batch 3
```

It prints JSON: `batch` (unblocked `ready` issues ranked by how much they
unblock, with no overlapping `Files:`), `held`, `blocked` and `in_progress`. It
changes nothing. Default batch is 3; start with 1–2 on a new project.

Check each candidate quickly: are the acceptance criteria clear? Is the
`## Context` section filled in? If not, fix the issue (with the user's yes) or
leave it out. An issue with no `Files:` is treated as touching everything, so
it runs alone.

## 2. Propose the plan and wait

Show the user one line per issue: number, title, type, worker model, files.
Also list what is held or blocked and why. **Launch nothing until they say yes.**

## 3. Build a context packet per issue

Fill in [worker-brief.md](worker-brief.md) for each issue. Include only:
- the issue text and acceptance criteria, and the spec it is part of, if any
- the `GLOSSARY.md` terms and ADRs it names (paste the relevant lines, not whole files)
- the files to start from, and the checks to run
- for UI: the style mode, the named `design-references/sites/*.md`, and the `ui-design` skill
- the skills for its type (table below)

Leave out everything else: other issues, this conversation, unrelated docs.
A focused worker makes fewer mistakes and costs less.

| Type | Skills to name | Model |
|---|---|---|
| `feature` | pick-issue, new-feature, code-structure, prove, ship | standard |
| `ui` | the above + ui-design, design-review | strongest available |
| `bug` | prove (failing test first), then the feature skills | standard |
| `refactor` | code-structure, prove (behaviour unchanged) | strongest available |
| `docs` | new-feature, ship (no review loop) | cheapest available |

"Model" is a hint. Use what the harness and the user allow.

## 4. Claim and launch

For each approved issue: claim it
(`gh issue edit <n> --add-label in-progress --remove-label ready --remove-label blocked`), then launch
one worker with its packet as the whole prompt. Use the best option you have:
1. **Subagents** in this harness, in the background, one per issue.
2. **Headless CLI** in its own worktree: `claude -p "<packet>"`,
   `codex exec "<packet>"`, or your harness's equivalent.
3. **Separate sessions** the user opens, each pasted one packet.
4. **No parallelism**: work the batch yourself, one issue at a time, with a fresh
   context for each where possible.

Workers follow the normal workflow (isolate, build, prove, ship) and stop at an
open PR with `needs-review`.

## 5. Track and gate

- Keep a short ledger: issue, worker, branch, PR, state.
- When a PR opens, run `review-loop` on it **from a context that is not the
  worker**: a separate reviewer, not the one that wrote it.
- If a worker is stuck or widens scope, stop it, comment on the issue, and put
  the label back to `ready` or `blocked`.
- When the batch is done, run `board.py` again: merged work may unblock more.

## 6. Report

For each issue: PR link, check result, review result, and anything open.
Then suggest the next batch. Run `retro` if a worker went wrong.

## Never

- Merge, or launch workers without the user's yes for that batch.
- Give two workers overlapping files.
- Hand a worker the whole conversation; give it the packet.
- Report a PR as done when checks or review haven't passed.
