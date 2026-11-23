---
name: balloon-drop
use_case: friendly product landing for a consumer brand
type: landing
mood: [light, warm, playful]
stack: vanilla, single file
weight: medium
source: motionsites.ai (slug not recorded)
---

# olla - Kitchenware Landing (Balloon-Drop Grill)

Full prompt: [../prompts/balloon-drop.md](../prompts/balloon-drop.md)

Warm beige page for a kitchenware brand. A fixed white rounded nav with a "Shop"
mega-menu that wipes open into a strip of line icons. The hero is two rounded
panels: a wide night-sky panel with lilac clouds and a narrow yellow product card
playing a looping video of cookware nesting together.

## Use this when
- A physical consumer product needs a hero that feels friendly and crafted.
- You have a product video loop to show off.

## Don't use when
- The brand is serious, technical or enterprise.

## Parts worth reusing
- **Rounded floating nav** with a mega-menu that wipes downward.
- **Two-panel hero**: wide scene panel beside a narrow product card, both rounded, with a shared gutter.
- **Card colour sampled from the video** at runtime, so the card always matches the footage.
- **One easing for everything**: `cubic-bezier(.2,.8,.2,1)`.
- **Shared container width** (`87vw`) for nav, hero and following panels.

## Tokens
- Fonts: Jost 400/500/600 (fallback Futura, Century Gothic).
- Colours: page `#e9e7df`, ink `#16193a`, navy `#141a4a`, card yellow `#f7d23a`.
- Spacing: gutter `1.19vw`, container `87vw`.

## Your take
- Like:
- Skip:

## Screenshot
<!-- img/balloon-drop.png -->
