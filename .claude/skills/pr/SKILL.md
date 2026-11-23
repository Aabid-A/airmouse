---
name: pr
description: Use when writing or updating a pull request title and body. Produces a short, scannable PR a human can review in minutes - a sketch of the change, before/after evidence, the issue's criteria, and how risky the merge is.
---

# PR

The reader is a busy human deciding whether to merge. Make the review fast.
Skip preambles. Use the domain words from `GLOSSARY.md`.

## Title

Imperative and specific: "Add vote counting to the game engine". No prefixes
like "feat:" unless the repo uses them.

## Body

```markdown
Closes #<n>

## Summary
<the smallest sketch that makes the change clear: pseudocode, a call tree,
a component tree, or a shallow file tree. Two to ten lines.>

## Evidence
- **Before:** <failing test / output / screenshot>
  **After:** <passing test / output / screenshot>

## Acceptance criteria
- [x] <criterion you proved>
- [ ] <criterion not done, with why>

## Merge danger
**Door:** one-way | two-way   <one-way = hard to undo: data, schemas, public APIs>
**Blast radius:** <one word: local, module, app, data, users>
<one or two lines on what could break, only if not obvious>
```

## Rules

- Tick a criterion only if the evidence shows it.
- Pick the sketch type that fits: logic as pseudocode, runtime flow as a call
  tree, UI as a component tree, a refactor as a file tree.
- UI changes: before/after screenshots at mobile and desktop (from `design-review`).
- No marketing words, no "This PR...", no restating the diff line by line.
- Keep it under about 40 lines. Link to `.artifacts/` for detail.

Adapted from Matt Pocock's `pr` skill (MIT), itself based on Dex Horthy's
`show-me` skill (HumanLayer).
