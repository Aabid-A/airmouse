# airmouse

Control your Mac's cursor by moving your hand in the air, using your webcam.
Everything is processed on your laptop.

airmouse tracks one Hand with the webcam, turns the index fingertip (the Pointer) into a
cursor position, and turns a Pinch into a click or a drag. It runs on macOS on Apple
Silicon, from a terminal. It saves no video, makes no network calls and, by default, shows
no camera image anywhere, so its Preview is safe to screen-record and share.

<!-- Placeholder until the demo is recorded. Do not commit a fake GIF.
     Record one as described in docs/recording-a-demo.md, then replace the line below with:
     ![airmouse demo](docs/demo.gif) -->
> Demo coming soon. This is a placeholder until a demo is recorded
> ([how to record one](docs/recording-a-demo.md)).

**Contents:**
[How it works](#how-it-works) ·
[Install and run](#install-and-run) ·
[Config reference](#config-reference) ·
[Permissions troubleshooting](#permissions-troubleshooting) ·
[Privacy](#privacy) ·
[Style](#style) ·
[Recording a demo](#recording-a-demo) ·
[Known limits](#known-limits-and-not-built-yet) ·
[Development](#development) ·
[Third-party notices](#third-party-notices) ·
[Licence](#licence)

## How it works

Each camera frame goes through these steps:

1. **Camera.** OpenCV reads a frame. The frame is rotated and mirrored as the config says,
   so a hand moved right moves right in the picture.
2. **Tracker.** MediaPipe's HandLandmarker finds one Hand as 21 landmarks, using the
   vendored Hand model (`hand_landmarker.task`, see [ADR 0003](docs/adr/0003-vendor-the-hand-model.md)).
3. **Gestures.** The landmarks are scored for the Open palm and the Fist, and measured
   for the Pinch.
4. **Controller.** A small state machine decides what the Hand means (below).
5. **Control mode.** While active, a One Euro filter smooths the Pointer, and the control
   mode turns it into a cursor position
   ([ADR 0002](docs/adr/0002-control-mode-is-pluggable.md)). Relative mode (the default)
   moves the cursor by the Pointer's movement, across all your displays; absolute mode
   maps the Active region to the main display. See [Control mode](#control-mode).
6. **Output.** Quartz posts the cursor moves and left-button events, and reports the
   displays and where the cursor is.
7. **Renderer.** The Preview draws the Hand skeleton, the state label and the Camera-on
   indicator on a plain dark background (and, in absolute mode, the Active region
   outline).
8. **Config.** Every number below comes from `~/.config/airmouse/config.toml`, with
   command-line flags on top.

Steps 1 to 6 are the cursor path. They run on a worker thread, and the Renderer runs on
the main thread, which owns the window (macOS needs window calls there). After each frame
the worker publishes a Snapshot, an immutable copy of the latest state, into a slot that
keeps only the newest one. The main thread draws the latest Snapshot, shows it and checks
for `q`. Neither waits for the other: a slow window never slows the cursor, and a stalled
camera never freezes the window, which keeps showing the last state the worker reported.
On `q` or Ctrl-C the main thread stops the worker and waits up to a second. The worker
lifts any held mouse button, closes the tracker and releases the camera on its way out.
If it is stuck (in a camera read, the tracker or the output), the main thread lifts the
button itself and shuts the output, so nothing the worker does later reaches the Mac; the
tracker and the camera are never closed under a call still running on them, and are
released when the worker comes back or when airmouse exits. See
[ADR 0004](docs/adr/0004-cursor-path-on-a-worker-thread.md).

Terms used in this document are defined in [GLOSSARY.md](GLOSSARY.md).

### Control mode

`[control] mode` (or `--control-mode`) picks how the Pointer moves the cursor.

**Relative** (the default) works like a mouse or trackpad. The cursor moves by how far
the Pointer moves, from wherever the cursor is when airmouse starts following. Movement
is measured in hand sizes, so it feels the same near or far from the camera, and
`[relative]` sets the gain, the acceleration and a cap. Bending or straightening the
index finger alone does not move the cursor; moving the hand, or swinging the finger
sideways, does. Slow movements add up, so even a tiny one moves the cursor. The cursor moves
across all your displays, of any size and arrangement, and stops at the outer edges of
the whole desk: a move off an edge slides along it. airmouse reads the display list about
once a second, so plugging a display in or out while it runs is fine; if the display
under the cursor goes away, the cursor moves to the nearest one left. Display
coordinates are in points, so Retina displays need nothing special.

To reach further, use the **clutch**: make a Fist (all four fingers curled), move your
hand back, and point again. While the Fist is held the cursor stays put and the Preview
says CLUTCH. Taking your hand out of the camera's view also stops the cursor (shown as
NO HAND). The cursor never jumps when you point again.

While your fingers are curling towards a Fist (the finger curl at `[clutch]
hold_threshold` or more) the cursor holds still and the Preview says HOLD, so closing
the fist never drags the cursor. Straighten the index (the Pointer pose) and it follows
again. A Pointer held at an angle to the camera, or with the index a little bent, is
not curled and never holds.

**Absolute** maps the Active region to the main display only: the cursor goes where the
Pointer is in the region. It works exactly as before relative mode existed: there is no
clutch and no HOLD, because the hand's position is the cursor.

### Active region

Absolute mode only. The Active region is a rectangle in the middle of the camera frame,
with the same shape as your screen. The Pointer inside it maps to the whole main display,
so your arm does not have to travel far. A Pointer outside it clamps to the nearest
screen edge. Its width is `[active_region] width_fraction` of the frame (default 0.6),
and in absolute mode the Preview outlines it. Calibrate mode always shows it.

### Gestures

| Gesture | What it is | What it does |
| --- | --- | --- |
| Pointer | The index fingertip | Moves the cursor while airmouse is active. |
| Pinch | Thumb tip and index tip brought together, measured against hand size | A short Pinch is a click. A Pinch held while the Pointer moves is a drag. |
| Open palm | The four fingers held upright and extended, together or spread | Pauses at once. Held steady, it unpauses. |
| Fist | All four fingers curled, the index included; the thumb is free (beside the fingers or tucked over them) | Relative mode: held for 100 ms (`[clutch] debounce_ms`), the clutch: the cursor stops following and any drag is released. |

Details that matter in use:

- The cursor freezes when a Pinch starts to form, so the click lands where you aimed.
- A Pinch released within 300 ms without the Pointer moving is a click. If the Pointer
  moves further while the Pinch is closed, it becomes a drag until the Pinch opens.
- A closed Pinch never counts as an Open palm.
- In relative mode a Fist is never a Pinch or an Open palm. Closing a fist moves the
  index towards the thumb, so while the fingers curl the cursor holds still (HOLD), a
  Pinch that closes on the way is cancelled without a click once the index folds back
  towards the palm, and a drag only starts when the whole hand moves. After the clutch
  the fingers must open (the finger curl below `hold_threshold`) before the cursor
  follows, and a Pinch in the first 0.3 s after the clutch is ignored, since that is the
  index passing the thumb as the hand opens.
- After a held Open palm unpauses airmouse, the Open palm is ignored until the Hand
  leaves that shape, so the same palm cannot pause it again at once.

### State machine

airmouse starts **Paused**: Hand movement produces no input.

| From | To | When |
| --- | --- | --- |
| Paused | active | An Open palm is held steady for 0.8 s (`unpause_hold_s`). The Hold ring fills while you hold it. |
| active | Paused | An Open palm lasts 150 ms (`pause_debounce_ms`). Any drag is released. |
| active | No hand | No Hand has been seen for 250 ms (`no_hand_timeout_ms`). |
| No hand | active | The Hand returns. |
| active | clutch | Relative mode: a Fist lasts 100 ms (`[clutch] debounce_ms`). Any drag is released. |
| clutch | active | The fingers open again (HOLD until the finger curl is below `hold_threshold`). |

In No hand the cursor freezes and any drag is released. airmouse stays unpaused. When the
Hand returns, the cursor follows the Pointer again from its new position. A Hand that
returns still pinched must open its Pinch before a click or drag can start, so losing the
Hand never presses the button. A dropout shorter than 250 ms changes nothing. Paused shows
as Paused whether or not a Hand is visible.

In relative mode the cursor then carries on from where it is, so it never jumps.

The Preview labels each state: PAUSED, ACTIVE, PINCH, DRAG, NO HAND, CLUTCH and HOLD. The
label is always text, never only a colour.

## Install and run

You need a Mac with Apple Silicon, a webcam, [uv](https://docs.astral.sh/uv/) and a
terminal app. uv installs Python 3.12 (pinned in `.python-version`) if you do not have it.

```bash
git clone https://github.com/Aabid-A/airmouse.git
cd airmouse
uv sync
uv run airmouse
```

The first run checks the Accessibility and Camera permissions (see
[Permissions troubleshooting](#permissions-troubleshooting)). Then it prints a
Camera-on indicator line in the terminal, such as:

```text
camera on: camera 0, 640x480 at 30 fps. Press q in the Preview or Ctrl-C to quit.
```

and opens the Preview, a 1280x720 window. Show one Hand to the camera and hold an Open
palm steady for about 0.8 s. The Hold ring fills and airmouse becomes active. Move the
Pointer to move the cursor, Pinch to click, Pinch and move to drag, and show an Open palm
to pause. Press `q` in the Preview, or Ctrl-C, to quit. On exit airmouse lifts the mouse
button if it was down and prints `camera off`.

### Command-line flags

```text
$ uv run airmouse --help
usage: airmouse [-h] [--version] [--config PATH] [--print-config] [--camera N]
                [--width WIDTH] [--height HEIGHT] [--fps FPS]
                [--rotate {0,90,180,270}] [--mirror | --no-mirror]
                [--active-region-width FRACTION] [--control-mode MODE]
                [--show-camera-image] [--calibrate] [--debug-gestures]
```

| Flag | Meaning |
| --- | --- |
| `--config PATH` | Read this config file instead of `~/.config/airmouse/config.toml`. The file must exist. |
| `--print-config` | Print every effective setting as TOML and exit. |
| `--camera N`, `--width`, `--height`, `--fps` | Override the `[camera]` settings. |
| `--rotate {0,90,180,270}`, `--mirror` / `--no-mirror` | Override `[camera] rotate` and `mirror`. |
| `--active-region-width FRACTION` | Override `[active_region] width_fraction`. |
| `--control-mode MODE` | Override `[control] mode`: `relative` (the default) or `absolute`. |
| `--calibrate` | Calibrate mode: see the Hand and the Active region, with no cursor input. |
| `--debug-gestures` | Draw the Open palm score, the wrist speed, per-stage timings and the tracking and window rates in the Preview. |
| `--show-camera-image` | Debugging only. Draw the camera image behind the skeleton. See [Privacy](#privacy). |
| `--version` | Print the version and exit. |

### Calibrate mode

If your camera sits somewhere unusual, such as above you pointing down, run:

```bash
uv run airmouse --calibrate
```

Calibrate mode shows the Hand and the Active region, labelled CALIBRATE, and makes no
cursor input. Change `--rotate` (0, 90, 180 or 270) and `--mirror` or `--no-mirror` until
the skeleton moves the way your hand does, for example `uv run airmouse --calibrate
--rotate 90`. Then save the values in the config file. Rotate and mirror are applied
before the Active region is placed.

### Tuning the Open palm and the Fist

The Open palm and Fist thresholds were tuned on synthetic landmarks only, not on a real
Hand. If either triggers too easily or not at all on your Hand, run:

```bash
uv run airmouse --debug-gestures
```

The Preview then draws the Open palm score against its threshold, the wrist speed against
the steadiness tolerance, in relative mode the Fist score against the clutch threshold
(FIST) and the finger curl against the hold threshold (CURL), and a column of readings
on the right:

- The cursor path (worker thread), in ms: CAM is the wait for the camera, PREP frame
  preparation, TRACK the Hand tracker, CTRL the Controller and cursor output, and FRAME
  the time between two frames from the camera. A slow camera shows as a large CAM and
  FRAME while the other stages stay small.
- The window (main thread), in ms: DRAW the Preview render, WIN showing it and checking
  for `q`.
- TRACK FPS, frames tracked per second (the camera's rate when the tracker keeps up; the
  FPS in the Preview's corner is the same number), and UI FPS, images the window shows
  per second.

Adjust the `[open_palm]` and `[clutch]` settings below. While you point, the CURL bar
must stay below its tick (`hold_threshold`), or the cursor holds still and the Preview
says HOLD. If your pointing pose reads curled, lower `[clutch] tip_open` and
`tip_curled` (how far back the fingertip must fold), or raise `hold_threshold`. If a
Fist does not clutch, check the FIST bar reaches its tick; raise `tip_open` or lower
`score_threshold`.

## Config reference

airmouse reads `~/.config/airmouse/config.toml` if it exists. Every key is optional. A
flag beats the file, and the file beats the default. An unknown key, a wrong type or an
out-of-range value stops airmouse with an error that names the key.

To see the effective settings, or to start a config file:

```bash
uv run airmouse --print-config > ~/.config/airmouse/config.toml
```

(Create the folder first with `mkdir -p ~/.config/airmouse`.)

| Section and key | Default | Meaning |
| --- | --- | --- |
| `[camera] index` | `0` | Which camera to use (0 or more). Flag `--camera`. |
| `[camera] width` | `640` | Camera frame width in pixels. Flag `--width`. |
| `[camera] height` | `480` | Camera frame height in pixels. Flag `--height`. |
| `[camera] fps` | `30` | Camera frames per second. Flag `--fps`. |
| `[camera] rotate` | `0` | Rotate the frame clockwise by 0, 90, 180 or 270 degrees. Flag `--rotate`. |
| `[camera] mirror` | `true` | Mirror the frame left to right. Flag `--mirror` or `--no-mirror`. |
| `[active_region] width_fraction` | `0.6` | Active region width as a fraction of the frame width, from 0 to 1. The region keeps the screen's shape and stays inside the frame. Flag `--active-region-width`. |
| `[control] mode` | `"relative"` | `"relative"` (moves by the Pointer's movement, across all displays) or `"absolute"` (Active region to the main display). Flag `--control-mode`. |
| `[filter] min_cutoff` | `1.0` | One Euro filter: lower is smoother when the Pointer is slow, higher is more responsive. |
| `[filter] beta` | `0.007` | One Euro filter: how quickly the smoothing relaxes when the Pointer moves fast. Higher means less lag in fast moves. |
| `[pinch] close_threshold` | `0.25` | The Pinch closes when the thumb-to-index distance, in hand sizes, falls below this. Must be below `open_threshold`. |
| `[pinch] open_threshold` | `0.4` | The Pinch opens again when the distance rises above this. |
| `[pinch] click_window_ms` | `300.0` | A Pinch released within this time without the Pointer moving is a click. |
| `[timing] unpause_hold_s` | `0.8` | Seconds an Open palm is held steady to unpause. |
| `[timing] pause_debounce_ms` | `150.0` | Milliseconds an Open palm must last, while active, to pause. |
| `[timing] no_hand_timeout_ms` | `250.0` | Milliseconds without a Hand before the No hand state. |
| `[open_palm] score_threshold` | `0.6` | The Open palm counts when its score, from 0 to 1, reaches this. |
| `[open_palm] finger_curled` | `1.1` | A finger tip this many hand sizes from the wrist or closer scores 0. Must be below `finger_extended`. |
| `[open_palm] finger_extended` | `1.6` | A finger tip this many hand sizes from the wrist or farther scores 1. |
| `[open_palm] thumb_weight` | `0.1` | How much an extended thumb adds to the score. |
| `[open_palm] spread_weight` | `0.05` | How much spread fingertips add to the score. With `thumb_weight`, the total must stay below 1. |
| `[open_palm] pinch_gap` | `0.2` | A thumb tip closer than this many hand sizes to the index tip is a Pinch, never an Open palm. |
| `[open_palm] steady_max_speed` | `2.5` | How fast the wrist may move, in hand sizes per second, for the Hold ring to keep filling. |
| `[relative] gain` | `800.0` | Relative mode: display points the cursor moves per hand size of Pointer movement, 1 to 20000. |
| `[relative] acceleration` | `0.5` | Relative mode: extra gain with speed. The gain is `gain * (1 + acceleration * speed)`, speed in hand sizes per second; 0 means none. 0 to 10. |
| `[relative] max_gain` | `3000.0` | Relative mode: the gain never goes above this, however fast the hand moves. At least `gain`. |
| `[clutch] score_threshold` | `0.6` | Relative mode: the Fist counts when its score, from 0 to 1, reaches this. |
| `[clutch] hold_threshold` | `0.3` | The cursor holds still (HOLD) while the finger curl, from 0 to 1, is at this or more. At most `score_threshold`. |
| `[clutch] tip_curled` | `-0.15` | Each finger's tip is measured along the hand's axis (wrist to the middle finger's base), past its own base, in hand sizes: this or less is fully curled. Must be below `tip_open`. |
| `[clutch] tip_open` | `0.0` | This or more is an open finger. A finger aimed at the camera looks short, but its tip still lies past its base. |
| `[clutch] finger_curled` | `1.0` | Each finger is also measured as wrist-to-tip over wrist-to-base distance; this ratio or less is fully curled. A finger counts as curled only when both measures agree. Must be below `finger_open`. |
| `[clutch] finger_open` | `1.4` | This ratio or more is an open finger. The finger curl is the least curled finger. |
| `[clutch] pinch_gap` | `0.1` | A thumb tip closer than this many hand sizes to the index tip is a Pinch, never a Fist. A thumb tucked over the fingers further away is still a Fist. |
| `[clutch] debounce_ms` | `100.0` | Milliseconds a Fist must last to become the clutch. |

Example `config.toml` for an overhead camera and a smaller Active region:

```toml
[camera]
rotate = 90

[active_region]
width_fraction = 0.5
```

## Permissions troubleshooting

macOS grants the Accessibility and Camera permissions to the **terminal app** that runs
airmouse (Terminal, iTerm and so on), not to airmouse itself. At start, airmouse reads
both permission statuses without opening the camera. If one is missing, it prints a
message and exits with status 1:

```text
airmouse needs the Accessibility permission.
It is granted to your terminal app (Terminal, iTerm, ...), not to airmouse.
Open System Settings > Privacy & Security > Accessibility, turn on your terminal app, then restart the terminal and run airmouse again.
```

For the camera, the message says `Camera` and ends with `Open System Settings > Privacy &
Security > Camera, ...`. To fix either one:

1. Open System Settings > Privacy & Security, then Accessibility (or Camera).
2. Turn on your terminal app.
3. Quit the terminal app completely and open it again, then run `uv run airmouse`.

Accessibility lets airmouse move the cursor and click. Camera lets it read frames. If the
Camera permission has never been decided, airmouse lets the start go ahead and macOS asks
your terminal app for it when the camera first opens.

If airmouse cannot read the status at all, it says so instead of claiming a permission is
missing:

```text
airmouse could not check the Camera permission: <reason>
This is a problem reading macOS, not a missing permission.
```

Other messages start with `airmouse:`, for example when the camera cannot be opened or
stops delivering frames. Try `--camera 1` if you have more than one camera.

## Privacy

airmouse watches a webcam, and its Preview is meant to be screen-recorded and shared, so
privacy is a design rule, recorded in
[ADR 0001](docs/adr/0001-privacy-by-design.md):

- **The Preview shows no camera pixels by default.** It is the Privacy preview: the Hand
  skeleton and the state on a plain background. A face or a room never appears in it.
- **No frame is saved.** airmouse writes no video or image to disk.
- **No network calls.** airmouse does not use the network when it runs. The Hand model is
  vendored in the repository ([ADR 0003](docs/adr/0003-vendor-the-hand-model.md)), so
  there is nothing to download at first run.
- **The camera is never hidden.** The Camera-on indicator is always visible, as a line in
  the terminal and as a red dot with CAMERA ON in the Preview.
- **Showing the camera image is opt-in.** `--show-camera-image` draws it behind the
  skeleton, for debugging only, and airmouse prints a warning when it is on.
- **Test fixtures are synthetic landmarks**, never recorded video.

## Style

The Preview is dark and cinematic (style mode B): a glowing skeleton on a near-black
background, a thin Active region outline in absolute and calibrate mode, and small
tracked monospace labels. State
colours always come with a text label. The canvas is a fixed 16:9, drawn at 640x360 and
shown at 1280x720, so a screen recording of the window is a standard video shape.

## Recording a demo

On the Mac, press Cmd-Shift-5, choose **Record Selected Portion**, drag the selection over
the 1280x720 Preview window, and click Record. Stop from the menu bar. Because the
Preview shows only the skeleton, the recording shows no face or room. The steps in full
are in [docs/recording-a-demo.md](docs/recording-a-demo.md).

## Known limits and not built yet

Not built yet (planned):

- Scroll and right-click Gestures.

Known limits:

- macOS on Apple Silicon only.
- The Open palm, Fist and relative-mode values were tuned on synthetic landmarks. Tune
  them on your Hand with `--debug-gestures`, `[open_palm]`, `[clutch]` and `[relative]`.
- Absolute mode maps to the main display only; relative mode reaches every display.
- A Pointer aimed steeply at the camera with the index well bent (on synthetic hands:
  about 70 degrees of bend at 60 degrees of tilt) looks like a curled finger, because its
  tip folds back past its base in the picture. The cursor then holds (HOLD).
- One Hand is tracked.
- Camera, cursor output and permission checks have only been exercised in tests with
  fakes unless you have run them on your own Mac. Report problems on the
  [issues page](https://github.com/Aabid-A/airmouse/issues).

## Development

Needs [uv](https://docs.astral.sh/uv/) and Python 3.12.

```bash
uv sync
uv run airmouse --help
scripts/check.sh
```

`scripts/check.sh` is the one command that proves a change works: whitespace, `uv sync
--locked`, `ruff check`, `ruff format --check`, `pyright` and `pytest`. Contributors and
coding agents should read [AGENTS.md](AGENTS.md), [CODING_STANDARDS.md](CODING_STANDARDS.md)
and [GLOSSARY.md](GLOSSARY.md). Decisions are in [docs/adr](docs/adr/).

## Third-party notices

The hand model (`hand_landmarker.task`) is Google's MediaPipe model, licensed under
Apache-2.0. Its source, checksum and licence text are in `src/airmouse/assets/`.

## Licence

MIT. See [LICENSE](LICENSE).
