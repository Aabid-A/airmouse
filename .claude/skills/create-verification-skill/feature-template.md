# Feature file template

One file per user-facing feature in `verify-<app>/features/`. Keep
implementation details out: name only user paths, stable handles, required
state, commands and observable proof.

```markdown
# <Feature name>

<One paragraph: what the user can do and see.>

## Sub-features
- `<id>`: <one behaviour, one line>

## How to get to it (user's view)
- <every entry point: menu, shortcut, command, gesture>

## Driving it
Preconditions: <state needed, starting from the baseline>
- **<user action>**: `<exact command or selector>` → <observable result>

## Human-only
- <what a person must try by hand, if anything>

## Gotchas
- <traps that waste or invalidate a run>
```
