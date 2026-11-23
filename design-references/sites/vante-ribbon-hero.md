---
name: vante-ribbon-hero
use_case: portfolio or agency hero that reveals a body of work on scroll
type: hero
mood: [dark, technical, quiet]
stack: vanilla + three.js 0.170
weight: heavy
source: https://motionsites.ai/?prompt=vante-ribbon-hero
---

# Vante - Video Ribbon Scroll Portfolio Hero

Full prompt: [../prompts/vante-ribbon-hero.md](../prompts/vante-ribbon-hero.md)

"CRAFT IN / MOTION" slides across in opposite directions while a ribbon of live
video cards spirals through 3D, then six cards land in a 3x2 grid with hover
name pills. One scroll value drives it all, so scrolling back reverses cleanly.

## Use this when
- Showing a portfolio, showreel or set of case studies.
- You have short video clips of the work.

## Don't use when
- Mobile performance matters most (eight video textures plus WebGL).
- The work is text-led, not visual.

## Parts worth reusing
- **Opposing headline lines** that pass like trains on scroll.
- **Almost-empty first frame**: glow, hairline with a "+", only the end of the headline.
- **Pill buttons** with 1px outlines that invert on hover; boxed pager arrows hanging from the top edge.
- **Mono label system**: IBM Plex Mono for every small label.
- **Smoothed scroll**: `p += (target - p) * .09`.

## Tokens
- Fonts: Inter Tight 400 (`clamp(40px,6.7vw,130px)`, -.055em); IBM Plex Mono.
- Colours: bg `#0a0a0b`, ink `#f4f1ea`, mid `#8d8b86`, line 14% ink.
- Motion: `1-(1-t)^3` landings; smoothstep rule draw.

## Your take
- Like:
- Skip:

## Screenshot
<!-- img/vante-ribbon-hero.png -->
