---
name: create-verification-skill
description: Use when a project has no scripted way to run the real app and prove behaviour (a new project's setup issue, or prove and design-review keep improvising how to launch and drive it). Generates a project-local verify-<app> skill - launch, doctor, drive, evidence, cleanup - plus a feature map, and proves it works once.
---

# Create a verification skill

Every project needs one scripted way to drive the real app the way a user does
and capture proof. This skill writes that as a skill inside the project, so
`prove` and `design-review` stop improvising.

## 1. Study the repo, not the user

Answer from the code; ask the user only what you can't observe.

- **Surface:** what does a user touch? Web UI, CLI, desktop app, API, mobile,
  hardware input? Pick the main one; note the others.
- **Run:** how does it start locally? Prefer the repo's own dev command. Note
  ports, env vars, seed data, auth, permissions (camera, accessibility).
- **Drive:** how can an agent use it from a script? Existing harnesses first
  (Playwright specs, test fixtures, a CLI, HTTP endpoints, a debug flag).
  Otherwise: Playwright for web, a PTY or `expect` script for CLI/TUI, `curl`
  for services.
- **Observe:** what proof can be captured? Screenshots, terminal transcripts,
  response bodies, logs, exit codes, stored data.
- **Isolate:** can two instances run side by side (ports, data dirs)? If not,
  say so in the generated skill.
- **Human-only:** which behaviour can only a person check (hand movement,
  feel, a physical device)? List it; those criteria stay `human-verified`.

If the app doesn't build or start, fix that or report it first.

## 2. Write the skill

Create `<skills-dir>/verify-<app>/SKILL.md` (the same folder the factory
skills are installed in), with frontmatter `name: verify-<app>` and a
`description` that starts "Use when proving <app> behaviour...". Sections,
each filled from what you found, no placeholders:

- **Launch:** the exact command, and how to tell it's ready to use (not just
  that a process answered). Starts from an empty data dir, migrations and seed included.
- **Doctor:** one read-only check: process up, right build, port owned by
  this run, permissions granted. Run it first whenever anything looks off.
- **Drive:** real commands and selectors from this repo. Prefer stable
  handles (accessible names, data attributes, CLI flags, routes) over coordinates.
- **Evidence:** what to capture and where (`.artifacts/<task>/`). Use the real
  user path, not test-only shortcuts. Capture the action and the resulting
  state. Check side effects (files, rows, messages).
- **Cleanup:** stop only what this run started (never kill by process name).
  Keep the evidence.
- **Human-only checks:** the behaviours from step 1, with what the user should try.
- **Helpers:** any script you add is executable and its usage is shown.

## 3. Seed the feature map

Create `verify-<app>/features/README.md` (baseline preconditions, driving
conventions, proof rules, an index) and one file per main user-facing feature,
three to five to start. Use [feature-template.md](feature-template.md).

## 4. Prove it before handing over

Follow the new skill end to end once: launch, doctor, drive one feature,
capture evidence, clean up. Confirm the evidence still exists after cleanup.
If any step fails, fix the skill and run again. Report what you ran and the
evidence path.

## 5. Keep it honest

When a feature changes, its feature file changes in the same PR. `retro`
flags a stale map. Ship the skill itself through the normal workflow.

Adapted from pstack's `create-verification-skill` by Lauren Tan (MIT).
