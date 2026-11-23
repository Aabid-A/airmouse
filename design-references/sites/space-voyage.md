---
name: space-voyage
use_case: immersive explorer where each section is a destination
type: hero
mood: [dark, cinematic, sci-fi]
stack: vanilla, single file, canvas + videos
weight: heavy
source: motionsites.ai (slug not recorded)
---

# Planet Jumping - Space Portal Experience

Full prompt: [../prompts/space-voyage.md](../prompts/space-voyage.md)

A full-viewport space experience. A giant condensed planet title (e.g. "MARS")
with facts, a planet list, and a round canvas-driven "portal" showing the next
destination. Clicking the portal plays a travel video and jumps to that planet.
A video preloader runs first.

## Use this when
- The content is a set of places, products or chapters you "travel" between.
- You want a game-like, cinematic first impression.

## Don't use when
- Speed, SEO or accessibility of content is the priority.

## Parts worth reusing
- **Portal button** that previews the next destination and plays a transition video on click.
- **One data object drives the page** (`render()` sets title, next, facts, list from the current planet).
- **Giant condensed display title** with thin and regular sans for everything else.
- **Fact list** as a `dl` of label/value pairs.

## Tokens
- Fonts: SF Pro 400/700, SF Pro Thin 100, Aalto (condensed, titles only); Arial fallbacks.
- Colours: background `#090807`, white text.

## Your take
- Like:
- Skip:

## Screenshot
<!-- img/space-voyage.png -->
