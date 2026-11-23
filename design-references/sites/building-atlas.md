---
name: building-atlas
use_case: editorial catalogue or archive of many items
type: landing
mood: [dark, editorial, bookish, light-mode option]
stack: vanilla, single file
weight: heavy
source: motionsites.ai (slug not recorded)
---

# Plinth - "Shared Interiors" Building Atlas

Full prompt: [../prompts/building-atlas.md](../prompts/building-atlas.md)

Dark editorial atlas of invented buildings. A huge two-line serif headline and a
search field over a drifting 3D ribbon of paper "book-cards"; a bookshelf of 3D
spines with one turned face-out; a footer with a giant hatched outline wordmark.
Clicking a card flies it to the centre, spins it, and zooms into a reading view.
Browser Back flies it home.

## Use this when
- You have a collection (articles, case studies, places, products) to browse.
- The tone is editorial, calm and a bit literary.

## Don't use when
- Users need dense lists, sorting and filters more than browsing for pleasure.

## Parts worth reusing
- **Dark and light themes from one token set**, with `color-mix` for muted, subtle and border shades.
- **Film grain overlay**: fixed SVG `feTurbulence` at 6% opacity with `mix-blend-mode: overlay`.
- **Bookshelf of spines** as a navigation idea.
- **Click-to-fly transition** into a detail view, reversed by browser Back.
- **Giant outline wordmark** in the footer.
- **Photo sheets cropped with background-position**: one image file, four photos.

## Tokens
- Fonts: Newsreader (serif display, 300–500), Geist (UI), Geist Mono (labels).
- Colours: dark bg `#111111`, fg `#ededed`; light bg `#ffffff`, fg `#0a0a0a`; card ink `#171614`.
- Layout: `.wrap` max 1180px; scene height `clamp(640px, 80svh - 48px, 900px)`.

## Your take
- Like:
- Skip:

## Screenshot
<!-- img/building-atlas.png -->
