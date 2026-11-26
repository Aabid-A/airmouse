---
name: pick-issue
description: Use when starting work from the issue tracker, or when the user says to take the next issue or names one by number. Reads the issue, checks nothing blocks it, marks it in progress and starts the isolate step.
---

# Pick Issue

Work comes from a GitHub issue. One agent, one issue.

## Steps

1. **Choose the issue.** If the user named one, use it. Otherwise list candidates:
   `gh issue list --label ready --state open`. Prefer the one that unblocks the
   most others. Say which you chose and why.
2. **Read it fully:** `gh issue view <n> --comments`. Check:
   - "Blocked by #x" items are all closed (`gh issue view <x>`).
   - Nobody else has it (label `in-progress` or an assignee). If taken, pick another.
   - The acceptance criteria are clear. If not, ask the user, or comment the
     question on the issue; don't guess.
3. **Claim it:** `gh issue edit <n> --add-label in-progress --remove-label ready`
   and, if you can, assign it to the current user.
4. **Start the isolate step** with the issue number: use the `new-feature`
   skill; the branch is `agent/<n>-<slug>`.
5. Keep the acceptance criteria open while you build. `prove` and `ship` check
   against them.

## Rules

- Never take two issues in one branch. Split or finish one first.
- If the work turns out bigger than the issue says, stop and comment on the
  issue; propose splitting with `to-issues`. Don't quietly widen the scope.
- If you must stop, remove `in-progress`, add `ready` or `blocked`, and leave a
  comment with where you got to.
