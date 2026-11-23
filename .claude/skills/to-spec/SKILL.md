---
name: to-spec
description: Use when a feature or chunk of work has been discussed (ideally after grill) and needs a written spec before it is split into issues. Writes the spec from what is already known, without re-interviewing, and posts it as a GitHub issue labelled spec after the user confirms.
---

# To Spec

Turn what's been decided into one spec that `to-issues` can split. Don't
re-interview the user; synthesise what you already know. If big questions
are still open, stop and suggest `grill` first.

## Steps

1. Read the relevant code, `GLOSSARY.md` and any ADRs for the area. Use the
   glossary's words throughout.
2. Choose the **test seams**: the highest public interface where the feature
   can be tested from the outside. Prefer existing seams; fewer is better.
   Check them with the user.
3. Write the spec with the template below and show it to the user.
4. On a yes, post it: `gh issue create --label spec --title "Spec: <name>"`
   (create the `spec` label if missing). Then offer `to-issues` to split it.

## Template

```markdown
## Problem
<the user's problem, from their point of view>

## Solution
<what changes for the user>

## User stories
1. As a <who>, I want <what>, so that <why>
<a long list covering the whole feature, edge cases included>

## Decisions
<modules to build or change, their interfaces, data/schema changes, API
contracts, architecture choices. No file paths or code; they go stale.
Exception: a type shape or state machine from a prototype, trimmed.>

## Testing
<the seams, what each test proves (behaviour, not internals), prior art>

## Out of scope
<what this spec deliberately does not cover>

## Notes
<open risks, links to ADRs and design references>
```

## Rules

- Nothing gets built from a spec directly. It becomes issues first.
- Don't create the issue without the user's yes.

Adapted from Matt Pocock's `to-spec` skill (MIT).
