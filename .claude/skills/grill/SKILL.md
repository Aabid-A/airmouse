---
name: grill
description: Use before planning work that is big, vague or risky, or when the user asks to be grilled on an idea. Interviews the user in rounds until every decision is settled, records terms in GLOSSARY.md and lasting decisions as ADRs, and only then hands off to to-spec.
---

# Grill

Reach a shared understanding before anything is built. Treat the plan as a
**decision tree**: each decision opens the ones that hang off it.

## Rounds

The **frontier** is every open decision whose prerequisites are already
settled. Ask the whole frontier in one round, numbered, each with your
recommended answer, worded so "yes" accepts it:

```
Q1 - <title>: <question, with the options if there are any>
-> Recommended: <your answer and the one-line reason>
```

Then wait. Each answer moves the frontier; recompute and ask the next round.
A question that depends on another open question waits for a later round.

## Facts vs decisions

- **Facts are your job.** Anything you can find in the code, docs or tools,
  look up yourself (a helper agent if you have one). Don't ask the user.
- **Decisions are the user's.** Put each one to them and wait.

## Write things down as you go

Use the `domain-docs` skill while grilling:
- When a term is settled, add it to `GLOSSARY.md` right away.
- When a decision is hard to reverse, surprising, and a real trade-off, offer an ADR.
- Point out when the user's words conflict with the glossary or the code.

## Done

The frontier is empty: every branch visited, nothing silently assumed. Summarise
the decisions, ask the user to confirm, then offer `to-spec`. Don't build anything.

Adapted from Matt Pocock's `grilling` and `grill-with-docs` skills (MIT).
