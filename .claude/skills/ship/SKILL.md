---
name: ship
description: Use when a code change is done and proven and the task calls for a pull request. Commits, rebases, pushes, opens the PR with evidence, runs the review loop, and ends by giving the PR URL. Merges only under the AGENTS.md Merging rules.
---

# Ship

Only ship when the task calls for a PR. A plan, review or local experiment does
not imply publishing.

## Steps

1. Confirm you're on your task branch, not `main` (`git branch --show-current`).
2. Review your own diff (`git diff origin/main...`). Remove debug code and
   unrelated edits.
3. Commit with a clear message: imperative, explain why, checked with `unslop`.
   Write it to a file and use `git commit -F <file>`, so the shell can't mangle it.
4. `git fetch origin && git rebase origin/main`, then rerun the checks
   (`scripts/check.sh` if the repo has it). Don't ship on red.
5. `git push -u origin <branch>`. After a rebase of an already-pushed branch,
   `--force-with-lease` only.
6. **Open the PR** (`gh pr create`). If the work came from an issue, the body
   says `Closes #<n>` and the issue's acceptance criteria are copied in as a
   checklist, ticked only for what you proved. If the issue is labelled
   `human-verified`, write `Refs #<n>` instead, leave the criteria that need the
   user unticked and marked "(needs you)", and never close the issue yourself.
   After opening, swap the issue's
   label: `gh issue edit <n> --add-label needs-review --remove-label in-progress`.
   Write the title and body with the `pr` skill: a sketch of the change, the
   before/after evidence from `prove`, the criteria, and the merge danger.
7. Run `/review-loop` for code or executable-workflow changes.
8. If the Merging rules in `AGENTS.md` allow it, merge (squash, pinned to the
   reviewed head commit), confirm a `Closes` issue closed, and remove the
   worktree. A `human-verified` issue stays open (the PR and the squash commit
   message say `Refs`, never `Closes`): label it
   `needs-review` and comment what the user must try and how. Otherwise stop.
   Either way, end with the PR URL and the real review result.

## Never

- Merge outside the `AGENTS.md` Merging rules, or use any override.
- Push to `main` or use plain `--force`.
- Report a review pass that didn't happen.
