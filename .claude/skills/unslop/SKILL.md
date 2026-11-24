---
name: unslop
description: Use before committing, posting or sending text a person will read - commit messages, PR titles and bodies, issues, docs, READMEs, code comments, reports. Cuts AI tells and filler while keeping the meaning and tone.
---

# Unslop

Edit the text, then rewrite what fails. Keep the meaning. Apply it to text you
wrote or changed, not to prose you didn't touch. Rule numbers are stable so
other files can cite them.

## Words
1. No AI vocabulary: additionally, crucial, delve, enhance, foster, landscape,
   pivotal, showcase, testament, underscore, vibrant, seamless, robust.
2. Plain words: "use", not "utilize" or "leverage"; "is" or "has", not "serves
   as", "boasts" or "features".
3. No abstract metaphor nouns: substrate, vector, nexus, primitive, paradigm,
   flywheel, north star. Use the concrete word.
4. Cut filler: "in order to" is "to"; delete "it is important to note that".
5. Cut adverbs, or use a stronger verb. Give the number.
6. One name per thing. Repeat it; don't vary it for style.

## Sentences
7. One idea per sentence. Split any sentence the reader has to reread.
8. Active voice. Name who does it unless it doesn't matter.
9. Say what it does, not how it feels. Name the mechanism or the number.
10. No trailing "-ing" phrases that add nothing ("..., ensuring quality").
11. No "not just X, but Y". State the point.
12. Don't force ideas into threes.
13. No vague sources ("experts say"). Name the source or delete it.
14. One hedge at most ("may"). No generic closing lines; end on a fact or a plan.

## Punctuation and format
15. No em or en dashes as pauses. Use a full stop or a comma.
16. A colon comes before a list or an example, not mid-sentence.
17. Sentence-case headings. Straight quotes. No decorative emoji.
18. Don't bold every name. No bold label that repeats its own line
    ("**Speed:** Speed improved").
19. Whole sentences with their articles and verbs; spell out arrows and
    abbreviations in prose.

## Tone
20. No praise or agreement openers, no chatbot lines ("I hope this helps").
    Start with the point.

Check: could a sentence appear unchanged in another project's docs? Rewrite or
cut it.

Adapted from pstack's `unslop` skill by Lauren Tan (MIT).
