---
name: fernhollow
use_case: immersive brand hero for a studio or agency
type: hero
mood: [dark, cinematic, nature, glow]
stack: vanilla UI over a compiled three.js engine
weight: heavy
source: motionsites.ai (flower valley; exact slug not recorded)
---

# Fernhollow - Night Flower Valley Hero

Full prompt: [../prompts/fernhollow.md](../prompts/fernhollow.md)

A cream headline "Grown, not built." over an interactive 3D night valley of
glowing flowers. Scroll flies the camera; the mouse pushes flowers away; hovering
the arrow slows the flight and muffles ambient sound.

## Use this when
- One big brand moment matters more than content density.
- The audience is on desktop with decent hardware.

## Don't use when
- The page has to load fast on phones, or carry lots of content.
- You can't ship the third-party engine it depends on (it runs gladeye.com's compiled code).

## Parts worth reusing
- **Interface layer only**: tall condensed headline, tiny tracked nav, one cream pill CTA.
- **UI fades in after the scene is ready** (loader is a single pulsing dot).
- **CTA hover changes the world** (scene slows and dims): ties UI to the backdrop.
- **Sound starts muted** with a clear speaker toggle.

## Tokens
- Fonts: Antonio 400 (headline, line-height .92); Manrope 400/500.
- Colours: black, cream `#f5efe2`, dark-on-cream `#151510`.
- Unit: `--u: min(100vw/1600, 100vh/900)`.

## Your take
- Like:
- Skip:

## Screenshot
<!-- img/fernhollow.png -->
