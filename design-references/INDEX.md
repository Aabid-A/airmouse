# Index

Read this and `STYLE.md` first, then open only the summaries that match the
task. Each summary links its full prompt in `prompts/`. Open a full prompt only
when you need exact values. They are long (5–78 KB).

**Weight** is build and performance cost: light (fast, simple), medium, heavy
(WebGL, many videos or scroll-scrubbing; needs a performance plan and a fallback).

## By use case

| Use case | Reference | Mood | Stack | Weight |
|---|---|---|---|---|
| **Hero: AI or dev tool with a prompt box** | [fastshot](sites/fastshot.md) | dark, sleek | vanilla | light |
| **Hero: portfolio or agency, work on scroll** | [vante-ribbon-hero](sites/vante-ribbon-hero.md) | dark, technical | three.js | heavy |
| **Hero: immersive brand moment** | [fernhollow](sites/fernhollow.md) | dark, nature, glow | 3D engine | heavy |
| **Hero: explore destinations or chapters** | [space-voyage](sites/space-voyage.md) | dark, sci-fi | canvas + video | heavy |
| **Landing: person or small studio selling a service** | [vortex-studio-hero](sites/vortex-studio-hero.md) | light, clean | React + Tailwind | light |
| **Landing: friendly consumer product** | [balloon-drop](sites/balloon-drop.md) | light, warm | vanilla | medium |
| **Landing: luxury or fashion series** | [vell-lookbook](sites/vell-lookbook.md) | light, airy | vanilla | medium |
| **Landing: editorial catalogue or archive** | [building-atlas](sites/building-atlas.md) | dark, editorial | vanilla | heavy |
| **Story: long scroll with data moments** | [moss-island](sites/moss-island.md) | light, misty | scroll video | heavy |
| **Shop: complete looks and bundles** | [outfit-carousel](sites/outfit-carousel.md) | light, minimal | vanilla | heavy |
| **Shop: bold streetwear hero** | [clothing-rail](sites/clothing-rail.md) | dark, edgy | CSS 3D | medium |
| **Footer: glass over video** | [lumina-footer](sites/lumina-footer.md) | dark, glass | React + Tailwind | light |
| **Footer: story moment** | [offline-footer](sites/offline-footer.md) | cinematic | one video | medium |

## Reusable parts, by kind

Where to look when you need one piece rather than a whole page.

| Need | Look at |
|---|---|
| Navigation | balloon-drop (rounded nav, mega-menu), vante-ribbon-hero (pills, hanging pager), fernhollow (minimal tracked links + pill) |
| Primary call to action | fastshot (prompt composer), vortex-studio-hero (layered-shadow button), fernhollow (round arrow) |
| Scroll-driven motion | vante-ribbon-hero, moss-island, vell-lookbook (one variable drives everything) |
| Cards and galleries | building-atlas (book-cards, shelf), clothing-rail (CSS 3D hover), vante-ribbon-hero (grid landing) |
| Product and commerce | outfit-carousel (panel, size sheet, bundle), clothing-rail (detail view) |
| Data display | moss-island (count-up, sparkline, glass card, hotspots), space-voyage (fact list) |
| Footers | lumina-footer, offline-footer, building-atlas (giant outline wordmark) |
| Texture and finish | building-atlas (film grain), lumina-footer (liquid glass), clothing-rail (chrome gradient) |
| Custom cursor | outfit-carousel, vell-lookbook |
| Marquee | clothing-rail, vortex-studio-hero |

## Adding one

1. Save the full prompt as `prompts/<slug>.md`.
2. Copy `_template.md` to `sites/<slug>.md` and fill it in.
3. Add a row to both tables above.
4. Fill in **Your take**, and update `STYLE.md` if it shows a trait you want everywhere.
