---
name: ship
description: Use when a code change is done and proven and the task calls for a pull request. Commits, rebases, pushes, opens the PR with evidence, runs the review loop, and ends by giving the PR URL. Never merges.
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
8. **Apply the merge policy** (`AGENTS.md`). Check the PR is safe: review
   passed with no open bug findings, two-way door, issue not `human-verified`,
   no path from `.github/CODEOWNERS` in `gh pr diff <n> --name-only`, and
   Auto-merge is `on`.
   - Safe: `gh pr merge <n> --auto --squash`. GitHub merges it when the
     ruleset's checks pass.
   - Not safe: label the issue `parked` and comment on the PR with the reason.
9. Present the PR URL, the review result, and whether auto-merge is on or why
   it was parked.

## Never

- Merge by hand (`gh pr merge` without `--auto`), or turn on auto-merge for a
  PR the policy parks, unless the user explicitly asks.
- Push to `main` or use plain `--force`.
- Report a review pass that didn't happen.
