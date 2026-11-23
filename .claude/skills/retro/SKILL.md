---
name: retro
description: Use when the user asks for a retro, or after a task that went badly (a missed bug, a long detour, a failed review). Finds changes to the factory and repo setup - checks, standards, docs, skills - so the same problem doesn't happen again. Improves the system, not just the code.
---

# Retro

Suggest improvements to the agent's **environment** so future runs go better.
Don't fix code here; propose changes to how the work is set up.

## Steps

1. Read what happened: the task's issue, PR, review comments, commits, and
   the session log or transcript if available. Default to the current task.
2. Look for candidates in these areas:
   - **Automated checks.** Could a check have caught a mistake the agent made?
     Read `scripts/check.sh` and the CI workflow first: an existing check that
     is unwired or broken is the finding. A repo with no CI or hooks running
     its checks is itself a finding.
   - **Standards.** Did review miss something? If the rule is mechanical (a
     banned API, an import shape, a file location, a naming pattern), propose a
     check: a lint rule, test or line in `scripts/check.sh`. Only judgement
     calls go into `CODING_STANDARDS.md`.
   - **Navigation.** Did the agent take long to find something? Propose a
     pointer (in `AGENTS.md`, a README, or `GLOSSARY.md`) or a structure change.
   - **Domain language.** Did a term cause confusion? Propose a `GLOSSARY.md` entry.
   - **Decisions.** Did the agent undo something deliberate? Propose an ADR.
   - **Steering bloat.** Is `AGENTS.md` growing? Move rules into checks,
     standards or skills; delete instructions that change nothing.
   - **Tool cost.** Expensive or repeated tool calls that a script could replace.
   - **Information access.** Missing logs, data or docs the agent needed.
   - **Factory skills.** A skill step that was wrong, missing or ignored.
3. Present the candidates to the user, most severe first, each with the exact
   change (file and text, or the check to add).
4. On a yes, make the changes. Changes to the factory itself go to the factory
   repo through its normal flow, then `install.sh --update` into projects.

## Rules

- Prefer a check over a rule, and a rule over a sentence in `AGENTS.md`.
- `AGENTS.md` is loaded into every session: keep it to pointers and essentials.
- Don't change anything without the user's yes.

Adapted from Matt Pocock's `retro` skill (MIT).
