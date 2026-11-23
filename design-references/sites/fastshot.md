---
name: fastshot
use_case: hero for an AI or dev tool with a prompt box as the main action
type: hero
mood: [dark, sleek, product]
stack: vanilla, single file
weight: light
source: motionsites.ai (slug not recorded)
---

# Fastshot - "Describe an app. We'll build it."

Full prompt: [../prompts/fastshot.md](../prompts/fastshot.md)

Single full-viewport hero over a background video, for an AI app builder. The
centrepiece is a prompt composer card: a text area, a row of chips, the model
name, a paperclip and an orange send button. The prompt measures everything
against a 1560x1008 frame and warns about the usual layout mistakes.

## Use this when
- The product's main action is typing a prompt or a request (AI tools, search, builders).
- You want an Apple-precise, calm product hero.

## Don't use when
- The page needs several sections; this is one screen only.

## Parts worth reusing
- **Prompt composer card**: chips left, model picker and send right; the send circle is taller than the chips and not centred on them.
- **Measured-frame layout**: every position derived from one reference frame via a `--u` unit.
- **Inter with optical sizing** (`opsz` 32 for display) and precise per-role weights (400, 410, 480, 500, 520).
- **Warm gradient send button**: `#FBBC94` to `#E88654`.
- **Glassy chips**: stacked white gradients at 4–9% over dark.

## Tokens
- Fonts: Inter variable (opsz 14–32).
- Colours: stage `#0a0d12`, card `rgba(41,41,43,.955)`, text greys `#98999C`, `#909093`.
- Accent: orange gradient `#FBBC94` → `#F49D70` → `#E88654`.

## Your take
- Like:
- Skip:

## Screenshot
<!-- img/fastshot.png -->
