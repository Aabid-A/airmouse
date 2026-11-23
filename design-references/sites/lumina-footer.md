---
name: lumina-footer
use_case: footer over a full-screen video background
type: footer
mood: [dark, glass, cinematic]
stack: react + tailwind v4 + motion + lucide-react
weight: light
source: motionsites.ai (slug not recorded)
---

# Lumina - Liquid Glass Footer

Full prompt: [../prompts/lumina-footer.md](../prompts/lumina-footer.md)

A fixed full-screen video background with a rounded "liquid glass" footer that
fades and rises in. Logo and a short description on the left, three link columns
on the right, and a bottom bar with credits and social icons.

## Use this when
- The site already has a video or image backdrop and needs a footer that sits on it.
- You're building in React and Tailwind.

## Don't use when
- The background is plain or light; the glass effect needs something behind it.

## Parts worth reusing
- **`.liquid-glass` class**: near-transparent fill, `backdrop-filter: blur(4px)`, a 1px inset top highlight, and a masked gradient border via `::before`.
- **Footer grid**: 12 columns, brand in 5, links in 7 split into 3 lists.
- **Bottom bar**: tiny uppercase wide-tracked labels at 50% opacity.
- **Entrance**: fade and rise 40px over 1 s, 0.4 s delay.

## Tokens
- Fonts: Helvetica (web font) as the root sans.
- Colours: white text at 70%, borders white at 10%.
- Shape: `rounded-3xl`, padding 6/10.

## Your take
- Like:
- Skip:

## Screenshot
<!-- img/lumina-footer.png -->
