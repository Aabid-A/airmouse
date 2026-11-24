---
name: retro
description: Use when the user asks for a retro, after a task that went badly (a missed bug, a long detour, a failed review), or when the user corrects an agent for a mistake it has made before. Makes repeated mistakes impossible - structure first, then types, lint, tests, and docs last - and keeps the rule table in AGENTS.md honest. Improves the system, not just the code.
---

# Retro

Change the repo and the factory so the next agent can't make the same mistake.
Assume every agent sees only the files it opened, copies the nearest example,
and takes the shortest path that passes the checks.

## 1. Find the mistake classes

Read what happened: the issue, PR, review comments, reverts, commits, the
session log if available, and comments that explain workarounds. Group the
mistakes into classes. A class counts once it has happened twice; a first-time
mistake gets noted, not a new rule.

Also check:
- **Checks:** read `scripts/check.sh` and CI. A check that exists but is
  unwired or broken is a finding. No CI or hooks running checks is a finding.
- **Rule table:** a rule in `AGENTS.md` whose enforcer is "nothing", broken again.
- **Navigation, language, decisions:** slow searches (add a pointer), confused
  terms (`GLOSSARY.md`), undone decisions (ADR).
- **Verification:** `verify-<app>` missing or out of date.
- **Cost and bloat:** expensive repeated tool calls a script could replace;
  `AGENTS.md` lines that change nothing.
- **Factory skills:** a step that was wrong, missing or ignored.

## 2. Fix each class at the highest level that works

1. **Structure.** One owner per piece of state, one supported way per task.
   Hide internals so the wrong import fails. One source of truth instead of
   lists kept in sync by hand. Delete old ways an agent would copy.
2. **Types.** Make the bad state impossible to write.
3. **A check whose error names the fix** (lint rule, script in
   `scripts/check.sh`, CI job): "use `X` from `Y` instead". If the bad pattern
   is already common, fail only on new occurrences.
4. **A test of behaviour.** Fix or delete tests that pass when the behaviour
   breaks or fail when only internals change.
5. **Docs last**, only for judgement calls: `CODING_STANDARDS.md` (read in
   review), a skill step, or a line in `AGENTS.md`. Nothing fails when an agent
   skips these.

## 3. Prove each check

Every new check must fail on a real past mistake (revert to it, or replay it in
a scratch branch) and pass on the fix. Run the same command locally and in CI.
An exception goes on the offending line with a reason, an expiry date, and the
user's approval.

## 4. Keep the rule table

`AGENTS.md` has a "Rules and what enforces them" table. Each rule names its
enforcer: a check, type, test, review, or "nothing yet". When the user corrects
an agent, fix the mistake and add or update the row. If the rule was already
there with nothing enforcing it, that's a repeat: fix it at a higher level now.
Drop a row once the structure makes the mistake impossible.

## 5. Propose, then act

Present the classes, most frequent first: the evidence, the level you chose,
and why a higher level didn't work. On the user's yes, make one commit per
class through the normal workflow. Factory changes go to the factory repo, then
into projects with `install.sh --update`.

## Rules

- Prefer structure over a check, a check over a rule, a rule over a sentence.
- `AGENTS.md` loads into every session: pointers, essentials and the table only.
- Don't change anything without the user's yes.

Adapted from Matt Pocock's `retro` skill (MIT) and pstack's `correct` skill by
Lauren Tan (MIT).
