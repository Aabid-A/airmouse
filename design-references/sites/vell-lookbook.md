---
name: vell-lookbook
use_case: luxury or fashion landing that walks through a series
type: landing
mood: [light, soft, airy, luxury]
stack: vanilla, single file
weight: medium
source: https://motionsites.ai/?prompt=vell-lookbook
---

# Maison Vell - Runway Depth Lookbook

Full prompt: [../prompts/vell-lookbook.md](../prompts/vell-lookbook.md)

Six models stand in a line receding into blurred haze. Drag, wheel or arrow keys
walk the line forward; a product rail on the right scrolls in sync and a big
look number rolls over. Loops forever.

## Use this when
- You have a sequence (collections, chapters, steps) and want it to feel physical.
- The brand is quiet and premium.

## Don't use when
- The content isn't a series, or people need to jump around freely.

## Parts worth reusing
- **One variable drives everything**: a single float `p` positions models, rail and number.
- **Depth table**: seven stops (x, y, height, blur, opacity) interpolated linearly. Designed, not computed.
- **Rolling number**: a stacked list of numbers slid by `-p * line-height`.
- **Fluid unit**: `--u: min(100vw/1600, 100vh/900)` so the layout scales as one piece.
- **Sprite sheets cropped with SVG viewBox**: one image for all models.

## Tokens
- Fonts: Michroma (wide, uppercase, tracked .14–.2em) for display and labels; Inter for body.
- Colours: ink `#16191f`, mid `#737b86`, dim `#a4adb8`, rail `#f3f6fa`, pale blue gradient stage.
- Motion: exponential ease `p += (target-p)*(1-exp(-dt*.0072))`; snap on release.

## Your take
- Like:
- Skip:

## Screenshot
<!-- img/vell-lookbook.png -->
