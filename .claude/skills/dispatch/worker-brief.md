# Worker brief template

Fill in one per issue. This is the worker's whole prompt. Paste the relevant
lines; don't just name files the worker would have to go and read.

```markdown
You are a worker on <repo>. Do one issue and stop at an open PR.

## Your issue: #<n> <title>
<issue body: why, acceptance criteria, how it will be proven>
Part of spec #<s>: <the 3–10 spec lines that matter for this issue, or "none">

## Words to use (from GLOSSARY.md)
- **<Term>**: <definition>

## Decisions to respect (from docs/adr)
- ADR <000N> <title>: <one line>

## Where to start
- Files likely to change: <paths>
- Related code to read first: <paths>
- Don't touch: <paths other workers own in this batch>

## Look and feel (UI only)
- Style mode: <A quiet light | B cinematic dark> (design-references/STYLE.md)
- References: <sites/x.md: the parts to reuse>

## How to work
Follow AGENTS.md. Skills, in order: <from the dispatch table>.
Branch: agent/<n>-<slug> in its own worktree, from origin/main.
Checks: scripts/check.sh must pass. Evidence goes in the PR (pr skill).

## Stop when
- The PR is open with "Closes #<n>" (or "Refs #<n>" if the issue is labelled
  `human-verified`, with the user's checks left unticked and marked "(needs you)"),
  checks pass, and the issue is labelled `needs-review`. Never close the issue.
- Or you are blocked or the work is bigger than the issue: stop, comment on the
  issue with what you found, and report back. Don't widen the scope.

Report back: PR URL, check result, and anything unfinished.
```
