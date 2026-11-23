# Style

> **Draft.** Written by the agent from what the 13 references have in common.
> It is a starting point, not your taste yet. Edit it, and fill in "Your take"
> in each `sites/` file; this file should follow from those.

Agents use this as the default look unless the project has its own design
system. A project picks one **mode** below and records it in its `AGENTS.md`
Conventions (or a design-tokens issue), then sticks to it.

## Principles (apply to every mode)

1. **Restraint.** A near-neutral background, one ink colour, one accent at most.
   The imagery or product supplies the colour.
2. **Contrast of scale.** One very large display element per screen; everything
   else small. No medium-sized clutter.
3. **Small labels, tracked wide.** Nav, tags and captions in 10–13px,
   uppercase, letter-spacing .12–.2em, often in a mono face.
4. **Two typefaces, clear roles.** A display face with character (condensed,
   serif or wide) and a plain sans for reading. A mono for labels is the
   optional third.
5. **Hairlines over boxes.** Separate with 1px lines and spacing, not borders
   and shadows everywhere.
6. **One easing curve.** Long, soft deceleration, e.g. `cubic-bezier(.16,1,.3,1)`
   or `cubic-bezier(.2,.8,.2,1)`. Durations 200ms for UI, 0.8–1.4s for entrances.
7. **Motion has one source.** Scroll or drag drives one value; everything reads
   from it. Scrolling back reverses cleanly.
8. **Calm first frame.** The page arrives quietly (fade, rise, blur-to-sharp),
   then the interesting thing happens.
9. **Respect reduced motion** everywhere, and never block content on a video or WebGL load.

## Modes

### A. Quiet light (default)
For products, services, studios, shops.
- Background white or warm off-white (`#ffffff`, `#f6f7f4`, `#e9e7df`).
- Ink near-black with a tint (`#151413`, `#16191f`, `#051A24`).
- Muted text 50–60% ink. Hairlines `#c8c8c8`-ish.
- Display: a serif accent (Instrument Serif, Newsreader, PP Mondwest) or a
  wide face (Michroma). Body: Inter, Inter Tight or Helvetica.
- References: vortex-studio-hero, outfit-carousel, vell-lookbook, balloon-drop.

### B. Cinematic dark
For portfolios, launches, immersive heroes.
- Background near-black (`#0a0a0b`, `#0b0b0c`, `#090807`), never pure grey.
- Ink warm off-white (`#f4f1ea`, `#f1efec`, `#f5efe2`).
- Display: tall condensed (Antonio, Aalto) or tight sans (Inter Tight, -.05em).
  Labels: IBM Plex Mono or JetBrains Mono.
- One accent only if any: red `#b3121b`, lime `#c6f35c`, or orange `#E88654`.
- References: vante-ribbon-hero, fernhollow, clothing-rail, fastshot, space-voyage.

## Layout

- Fluid unit for full-screen designs: `--u: min(100vw/1600, 100vh/900)`,
  switching to `1px` at 820px and below.
- Content pages: max width about 1180px, 24px side gutters (16px on phones).
- Generous whitespace between sections; tight grouping within them.
- Every layout works at 375px wide with no horizontal scroll.

## Components

- Buttons: pill (99px radius) with a 1px outline that inverts on hover, or
  solid ink with a soft layered shadow. Square corners elsewhere.
- Tags: small, uppercase, mono, solid accent or outline.
- Glass only over imagery or video (`backdrop-filter: blur`), never on flat colour.

## Imagery and backgrounds

- Full-bleed video or rendered scenes for heroes; a still poster is required.
- Product shots as transparent cut-outs on calm backgrounds.
- Optional film grain at about 6% opacity for warmth.

## Avoid

- Gradients as decoration, drop shadows everywhere, emoji icons.
- More than two typefaces plus a mono.
- Bouncy or fast easing on large elements.
- Centring long paragraphs.
- Heavy 3D or video when the page has to be fast on phones; use a light
  reference instead (see `INDEX.md` weight column).
