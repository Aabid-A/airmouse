---
name: domain-docs
description: Use when a domain term needs defining or is used inconsistently, when writing or editing GLOSSARY.md, or when a hard-to-reverse decision should be recorded as an ADR in docs/adr/.
---

# Domain Docs

Keep humans and agents speaking the same language, and record why the code is
the way it is. Create files lazily: only when there is something to write.

## GLOSSARY.md (repo root)

```md
# <Project name>

<One or two sentences: what this domain is.>

## Language

**Traitor**:
A player secretly working to eliminate faithful players without being voted out.
_Avoid_: Spy, imposter
```

Rules:
- **Be opinionated.** Pick one word per concept; list the rest under `_Avoid_`.
- **One or two sentences.** Say what it is, not how the code does it.
- **Project terms only.** No general programming words (timeout, cache, helper).
- Group under subheadings when clusters appear.
- Use these exact words in code, issues, PRs and UI copy.
- Large repos with several areas: a root `GLOSSARY-MAP.md` linking one glossary per area.

When the user, an issue or the code uses a term differently from the glossary,
say so at once and ask which is right.

## ADRs (docs/adr/0001-slug.md)

Write one only when all three are true:
1. **Hard to reverse.** Changing it later costs real time.
2. **Surprising without context.** A newcomer would ask "why did they do this?"
3. **A real trade-off.** There were genuine alternatives.

Format, usually one paragraph:

```md
# <Short title of the decision>

<Context, what we decided, and why, in one to three sentences.>
```

Add `Status` (proposed, accepted, superseded by 000N), "Considered options" or
"Consequences" only when they add something. Number by taking the highest
existing number plus one.

Good candidates: architecture shape, database or hosting choices with lock-in,
boundaries between areas, deliberate deviations from the obvious path, and
constraints you can't see in the code.

## Rules

- Read `GLOSSARY.md` and the ADRs for the area before planning or reviewing.
- Never put implementation details or task notes in the glossary.
- Don't contradict an accepted ADR silently: propose a new one that supersedes it.

Adapted from Matt Pocock's `domain-modeling` skill (MIT).
