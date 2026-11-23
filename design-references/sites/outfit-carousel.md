---
name: outfit-carousel
use_case: browse complete looks and buy the pieces
type: ecommerce
mood: [light, minimal, editorial]
stack: vanilla (custom element)
weight: heavy
source: https://motionsites.ai/?prompt=outfit-carousel
---

# Outfit Carousel ("Try the Look.")

Full prompt: [../prompts/outfit-carousel.md](../prompts/outfit-carousel.md)

White stage where six full-body models turn on a 3D ring, auto-advancing every
5 s. A right-hand panel lists the pieces with size pickers, a bundle price and
"Add full look to bag". A "View look" popup shows numbered product pins.

## Use this when
- A shop sells outfits, bundles or sets, not single items.
- You want browsing to feel like a runway, with buying one click away.

## Don't use when
- Products aren't photographed as full-body cut-outs on transparent backgrounds.
- The catalogue is large and needs search and filters first.

## Parts worth reusing
- **Progress ticks**: 01–06 bar where the current tick widens and shows its name.
- **Custom cursor**: glass ring reading "Drag", "View", or shrinking to a dot over links.
- **Pin-to-row linking**: hover a product pin and its panel row lights up, and back.
- **Mobile bottom sheet** for size picking; horizontal snap carousel for product rows.
- **Reduced-motion handling**: springs snap, autoplay off, no sweep.

## Tokens
- Fonts: Helvetica/Arial stack at 400; Inter 600 for nav only.
- Colours: white stage, ink `#151413`, muted `#66625c`, accent `#0e0e0e`, hairline `#c8c8c8`.
- Shape: square corners; pills only for size options (30px).
- Motion: `cubic-bezier(.16,1,.3,1)`; critically damped spring; blur-to-sharp entrances.

## Your take
- Like:
- Skip:

## Screenshot
<!-- img/outfit-carousel.png -->
