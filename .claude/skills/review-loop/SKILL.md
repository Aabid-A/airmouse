---
name: review-loop
description: Use after opening a PR to review it and iterate on the findings until the gate passes, within an iteration cap. Reviews on two separate axes (standards and spec) so one can't hide the other.
---

# Review Loop

Success: the current commit passes the gate with no unresolved actionable
findings, and `scripts/check.sh` (or the repo's checks) passes. Default cap:
**5 iterations**. The user can set another.

Reviewing is where standards are enforced. The builder had the most context
pressure; the reviewer gets a clean diff and a clean head.

## Choose a gate

Set in `AGENTS.md` under Conventions. Default is **A**.

### A. Two-axis review (no paid tools)

Pin the diff: `git diff origin/main...HEAD` and `git log origin/main..HEAD --oneline`.
Fail early if the diff is empty.

Run **two reviews, each in a fresh context that did not write the code**, and
keep their findings separate. Best: two reviewer agents or subagents in
parallel. Otherwise a second session or another model from the command line.
Last resort: do them yourself one after the other, re-reading only the diff.

**Standards review.** Give it the diff, `CODING_STANDARDS.md` (including its
baseline smells), `GLOSSARY.md` if present, and for UI diffs the `ui-design`
skill. Brief: "For each problem, cite the rule (file and rule) and quote the
hunk. Mark hard violations of a project rule separately from judgement calls.
Baseline smells are always judgement calls. Skip what tooling enforces. Under
400 words."

**Spec review.** Give it the diff and the spec: the issue named in `Closes #n`
or `Refs #n` (`gh issue view <n>`), a linked spec issue, or a spec file. For a
`human-verified` issue, criteria marked "(needs you)" are not findings; the
reviewer checks everything else. Brief: "Report
(a) acceptance criteria missing or partial, (b) behaviour nobody asked for
(scope creep), (c) criteria that look done but are wrong. Quote the criterion
for each. Under 400 words." If there is no spec, skip it and say so.

Report both under `## Standards` and `## Spec`. Don't merge or rerank them.

**Bugs need proof.** A finding that says the code is *wrong* (crashes, wrong
result, broken criterion, security hole) counts only with a run that shows it:
a failing test, a repro script, or command output, run against the real code in
the reviewer's own worktree. Unproven bug claims are listed separately as
"unproven" and don't block. Standards findings and smells are judgement calls
and need no run, but are labelled as such.

**Risky diffs get a safety check.** When the PR's merge danger is a one-way
door or a wide blast radius (data, schemas, public APIs, shared state), the
reviewer also: finds the one fact the change is safe because of (for example
"this only drops entries that are already dead"), proves it by running real
code, and lists what else could break beyond the diff (other callers, stored
data, wire formats, timing). Report how far the proof got: said, pointed at the
line, reasoned through, ran it, or reproduced it in the app.

### B. Review bot (e.g. Greptile)

Trigger the bot on the PR, wait for a result tied to the **current** commit
(ignore stale ones), read findings via `gh pr view` / `gh api`. Run gate A's
spec review as well; bots rarely know the spec.

## Cycle

1. Run the gate on the current commit.
2. If it passes, stop and report.
3. Fix each real finding in your branch. If a finding is wrong, reply on the PR
   with the reason; don't silently ignore it.
4. Rerun checks, commit, push (`--force-with-lease` only if you rebased).
5. Repeat until it passes or you hit the cap.

## After it passes

Post the result as a comment on the PR: the head commit, each axis (standards,
spec) with pass or fail, and any "unproven" findings. A merge under the
`AGENTS.md` Merging rules needs this comment on the current head. A new push
makes it stale.

If a finding was something a tool could have caught, say so in the PR and
suggest a check (see the `retro` skill). That is how the brakes improve.

## Stopping honestly

At the cap, a timeout, or a missing integration: stop and report the real
result, the open findings and what is left. Don't raise the cap or claim success.

Two-axis review adapted from Matt Pocock's `code-review` skill (MIT). Proof rule and
safety check adapted from pstack's `interrogate` and `blast-radius` skills by
Lauren Tan (MIT).
