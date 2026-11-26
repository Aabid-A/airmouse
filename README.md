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
is measured in hand sizes, so it feels the same near or far from the camera. Like
pointer acceleration on a mouse, a slow hand moves the cursor a little, for fine
aiming, and a fast hand moves it a lot, to cross the screen (see *Tuning relative mode*
below). Bending or straightening the
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

#### Tuning relative mode

The gain is how many display points the cursor moves for one hand size of Pointer
movement (a hand size is the wrist to the middle finger's base, roughly 9 cm). Below
`[relative] slow_speed` (hand sizes per second) the gain is `gain`; above `fast_speed`
it is `max_gain`; in between it rises smoothly, with no steps. With the defaults, a slow
careful move of a tenth of a hand size moves the cursor about 40 points, and one hand
size moved quickly (in a third of a second or less) moves it about 2400 points.

The Pointer is smoothed first, hardest when the hand is slow so a shaky hand does not
shake the cursor, and less as it speeds up so a fast move does not lag. The smoothing
cutoff is `min_cutoff + beta * speed` (Hz, speed in hand sizes per second). This is
relative mode's own One Euro filter; `[filter]` applies to absolute mode only.

- Fine aiming too slow, or small moves need too much hand travel: raise `gain`.
- Fine aiming still jumpy: lower `gain`, or raise `slow_speed` so more of your careful
  movement gets the low gain.
- Crossing the screen takes too much arm: raise `max_gain`, or lower `fast_speed` so the
  full gain comes sooner.
- The cursor shakes while you hold still: lower `min_cutoff`. It feels sluggish on small
  moves: raise `min_cutoff`.
- Fast moves trail behind the hand: raise `beta`. Fast moves feel twitchy: lower it.

`slow_speed` must be below `fast_speed`, and `max_gain` at least `gain`. An older config
with `acceleration` is rejected with a message naming these keys: remove it, and set the
new ones if the defaults do not suit you.

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
| Scroll | Index and middle fingers raised together, ring and pinky curled, thumb relaxed; then the Hand moved up or down | Held for 120 ms (`[scroll] debounce_ms`), it scrolls: hold the Hand above or below where the pose started to scroll steadily (further is faster), or flick it quickly up or down for one big step, as for Reels or Shorts. Both control modes. |

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
- The Scroll has two motions (`[scroll] mode`, default `"auto"`):
  - **Continuous**, like a joystick. Where the knuckles of the two fingers are when
    scrolling starts is the anchor, and distances are in the hand size at that moment.
    Within 0.15 hand sizes of it (`deadzone`) nothing scrolls; past it the speed eases
    in smoothly and grows with the distance, up to 1500 pixels per second
    (`max_speed`). Back at the anchor it stops. The distance is smoothed, so a shaky
    hand does not make the speed wobble.
  - **Flick**: a quick move up or down from the anchor (3 hand sizes per second over
    0.3 hand sizes or more) scrolls one step of 600 pixels at once, then nothing scrolls
    for 0.5 s (`flick_cooldown_ms`), so the hand can come back without scrolling the
    other way. The next flick needs the Hand back at the anchor and still for a moment.
  - In `"auto"`, one motion is one or the other, never both: a slow move gives a
    continuous scroll (it starts 150 ms after leaving the deadzone, the time a flick has
    to happen) and a quick one a single step. `mode = "continuous"` turns the flick off;
    `mode = "flick"` turns the continuous scroll off.
- Hand up scrolls up (content above comes into view); `[scroll] invert = true` flips
  both motions. With the default direction a flick **down** shows the next item in a
  feed such as Reels or Shorts. It is vertical only.
- While a scroll is on the cursor holds still, a Pinch cannot start and the mouse button
  is never pressed. A Pinch and an Open palm (which also pauses) end it at once; in
  relative mode a Fist ends it through the clutch, once it has lasted 100 ms
  (`[clutch] debounce_ms`). A Pinch that closed while scrolling must open before it can
  click.
- Starting needs a clear two-finger pose (`score_threshold`), but staying needs less
  (`exit_threshold`), and a pose that reads poorly for up to 250 ms (`grace_ms`), as
  when the two fingers point at the camera and overlap, only fades the scroll out
  instead of ending it. Relaxing to a Pointer pose or another shape ends it once the
  grace period is over. While a scroll is on, two fingers that still read as the pose
  never count as an Open palm; with no scroll on, the Open palm and pausing work exactly
  as before.
- No hand ends the scroll. A Hand that comes back in the two-finger pose does not scroll:
  form the pose again to start a new scroll from a new anchor.

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
| active | scroll | The two-finger pose lasts 120 ms (`[scroll] debounce_ms`). Any drag is released. |
| scroll | active | The pose has read below `exit_threshold` for 250 ms (`grace_ms`), or at once for a Pinch, the clutch (relative mode) or an Open palm. No hand ends it too. |

In No hand the cursor freezes and any drag is released. airmouse stays unpaused. When the
Hand returns, the cursor follows the Pointer again from its new position. A Hand that
returns still pinched must open its Pinch before a click or drag can start, so losing the
Hand never presses the button. A dropout shorter than 250 ms changes nothing. Paused shows
as Paused whether or not a Hand is visible.

In relative mode the cursor then carries on from where it is, so it never jumps.

The Preview labels each state: PAUSED, ACTIVE, PINCH, DRAG, NO HAND, CLUTCH, HOLD and
SCROLL. The label is always text, never only a colour.

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
Pointer to move the cursor, Pinch to click, Pinch and move to drag, raise two fingers and
move the Hand up or down to scroll (or flick it for one step), and show an Open palm to
pause. Press `q` in the Preview, or Ctrl-C, to quit. On exit airmouse lifts the mouse
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
| `--debug-gestures` | Draw the Open palm score, the wrist speed, the Fist and two-finger scores, the scroll state, offset, speed and flick measure, per-stage timings and the tracking and window rates in the Preview, and print a one-line scroll readout to the terminal once a second. |
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

### Tuning the Scroll

The two-finger pose was also tuned on synthetic landmarks only, so its defaults are
loose. With `--debug-gestures` the Preview adds these under the Fist's place, in both
control modes:

- TWO: the two-finger score against `score_threshold` (the tick; while scrolling the tick
  moves to `exit_threshold`, shown as OUT).
- SCROLL and a state: IDLE (not in the pose), ARMING (in the pose, waiting for the
  debounce), SCROLLING, GRACE (the pose reads poorly; fading out), COOLDOWN (after a
  flick) or BLOCKED (after No hand, until the pose is formed again).
- OFFSET: the smoothed distance of the two knuckles above (UP) or below (DOWN) the
  anchor, in hand sizes, against the deadzone tick.
- RATE: the scroll speed in pixels per second against `max_speed`.
- FLICK: how fast the knuckles moved over the last flick window, in hand sizes per
  second, against `flick_speed`.

The terminal also gets one line a second with the same numbers, to copy into an issue:

```text
scroll: auto scrolling two=0.97 entry=0.50 exit=0.30 offset=+0.35 deadzone=0.15 speed=+500px/s flick=+0.02/3.0
```

What to change:

- The pose does not start: TWO stays under its tick. Lower `score_threshold`. If the
  score drops when the fingers point at the camera, lower `exit_threshold` or raise
  `grace_ms`. If a Pointer pose or a half-open hand starts scrolling, raise
  `score_threshold` or `separation` (how much further out the two fingertips must be
  than ring and pinky, in hand sizes).
- `separation` is 0.7 so a steeply tilted open palm stays clear of the pose. The cost:
  a very relaxed two-finger pose, or one with the thumb out, drops out earlier when
  tilted towards the camera (on synthetic hands, a relaxed pose with the thumb out
  scores 0.58 at 55 degrees and 0.31 at 60, so it can no longer start there, where 0.5
  gave 1.0 and 0.83). If that is your pose, lower `separation` towards 0.5, at the cost
  of a smaller margin against a tilted open palm.
- Raised fingers read folded: lower `tip_curled` or `finger_curled`. Curled ring and
  pinky read open: raise `tip_open` or `finger_open`. `pair_gap` is how close the two
  fingertips must be to count as one pair.
- The speed: `deadzone` is the still zone, `ease` how gently the speed starts past it,
  `gain` the pixels per second for each hand size past the deadzone and `max_speed` the
  cap. If the speed still wobbles, lower `min_cutoff` (steadier) or `beta`; if it lags
  when you stop, raise them.
- The flick: if quick moves do not flick, lower `flick_speed` or `flick_min_travel`; if
  ordinary moves flick, raise them, or set `mode = "continuous"`. `flick_pixels` is the
  size of one step (see the limits below), `flick_window_ms` the time a flick is measured
  over, `flick_cooldown_ms` the pause after it.
- The direction is the wrong way round on your Mac: set `invert = true`.

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
| `[filter] min_cutoff` | `1.0` | Absolute mode's One Euro filter: lower is smoother when the Pointer is slow, higher is more responsive. Relative mode uses `[relative] min_cutoff`. |
| `[filter] beta` | `0.007` | Absolute mode's One Euro filter: how quickly the smoothing relaxes when the Pointer moves fast. Higher means less lag in fast moves. Relative mode uses `[relative] beta`. |
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
| `[relative] gain` | `400.0` | Relative mode: display points the cursor moves per hand size of Pointer movement when the hand is slow (at `slow_speed` or below), for fine aiming. 1 to 20000. |
| `[relative] max_gain` | `2500.0` | Relative mode: the gain when the hand is fast (at `fast_speed` or above), and the cap. At least `gain`; equal to `gain` turns acceleration off. Up to 50000. |
| `[relative] slow_speed` | `0.2` | Relative mode: hand speed, in hand sizes per second, up to which the gain stays at `gain`. 0 to 50, below `fast_speed`. |
| `[relative] fast_speed` | `3.0` | Relative mode: hand speed, in hand sizes per second, from which the gain is `max_gain`. Between the two speeds the gain rises smoothly. 0.01 to 50. |
| `[relative] min_cutoff` | `0.5` | Relative mode's One Euro filter: smoothing cutoff in Hz when the hand is still. Lower is steadier, higher is more responsive. 0.01 to 30. |
| `[relative] beta` | `5.0` | Relative mode's One Euro filter: Hz added to the cutoff per hand size per second of speed, so the smoothing relaxes as the hand speeds up. Higher means less lag in fast moves. 0 to 100. |
| `[clutch] score_threshold` | `0.6` | Relative mode: the Fist counts when its score, from 0 to 1, reaches this. |
| `[clutch] hold_threshold` | `0.3` | The cursor holds still (HOLD) while the finger curl, from 0 to 1, is at this or more. At most `score_threshold`. |
| `[clutch] tip_curled` | `-0.15` | Each finger's tip is measured along the hand's axis (wrist to the middle finger's base), past its own base, in hand sizes: this or less is fully curled. Must be below `tip_open`. |
| `[clutch] tip_open` | `0.0` | This or more is an open finger. A finger aimed at the camera looks short, but its tip still lies past its base. |
| `[clutch] finger_curled` | `1.0` | Each finger is also measured as wrist-to-tip over wrist-to-base distance; this ratio or less is fully curled. A finger counts as curled only when both measures agree. Must be below `finger_open`. |
| `[clutch] finger_open` | `1.4` | This ratio or more is an open finger. The finger curl is the least curled finger. |
| `[clutch] pinch_gap` | `0.1` | A thumb tip closer than this many hand sizes to the index tip is a Pinch, never a Fist. A thumb tucked over the fingers further away is still a Fist. |
| `[clutch] debounce_ms` | `100.0` | Milliseconds a Fist must last to become the clutch. |
| `[scroll] mode` | `"auto"` | `"auto"`: a held offset scrolls continuously and a quick flick scrolls one step, never both for one motion. `"continuous"`: no flick. `"flick"`: only flicks. |
| `[scroll] invert` | `false` | `false`: Hand up scrolls up (content above comes into view). `true`: the other way, for both motions. |
| `[scroll] deadzone` | `0.15` | Hand sizes of offset from the anchor that do not scroll. 0 to 2. |
| `[scroll] ease` | `0.15` | Hand sizes past the deadzone over which the speed eases in (a smoothstep) to the linear rate; 0 for none. 0 to 2. |
| `[scroll] gain` | `2500.0` | Pixels per second for each hand size past the deadzone. 1 to 50000. |
| `[scroll] max_speed` | `1500.0` | The continuous speed cap, in pixels per second. 1 to 20000. |
| `[scroll] min_cutoff` | `0.5` | The Scroll's own One Euro filter on the offset: cutoff in Hz when the hand is still. Lower is steadier, higher responds faster. 0.01 to 30. |
| `[scroll] beta` | `0.3` | Hz added to that cutoff per hand size per second, so fast moves lag less. 0 to 100. |
| `[scroll] score_threshold` | `0.5` | The two-finger score, from 0 to 1, needed to start a scroll. 0.01 to 1. |
| `[scroll] exit_threshold` | `0.3` | The score needed to keep a scroll going. 0.01 to 1, at most `score_threshold`. |
| `[scroll] debounce_ms` | `120.0` | Milliseconds the pose must last before a scroll starts, so passing through it does not scroll. 0 to 2000. |
| `[scroll] grace_ms` | `250.0` | Milliseconds the score may stay under `exit_threshold` (the scroll fades out meanwhile) before the scroll ends. 0 to 2000. |
| `[scroll] tip_curled` | `-0.5` | Hand sizes a fingertip lies past its own base along the hand's axis: this or less is fully curled. Must be below `tip_open`. -2 to 2. |
| `[scroll] tip_open` | `0.0` | This or more is fully open. Index and middle count as raised if this or the ratio says so; ring and pinky count as curled if this or the ratio says so. -2 to 2. |
| `[scroll] finger_curled` | `1.0` | Wrist-to-tip over wrist-to-base ratio at or below which a finger is fully curled. Must be below `finger_open`. 0 to 3. |
| `[scroll] finger_open` | `1.4` | The ratio at or above which a finger is fully open. 0 to 3. |
| `[scroll] pair_gap` | `0.3` | Hand sizes: index and middle tips closer than this are read as one pair (the better of the two counts), so overlapping fingers still count. 0 to 2. |
| `[scroll] separation` | `0.7` | Hand sizes the pair's tips must lie further out along the hand than ring and pinky for full marks (none at half of it). 0.01 to 3. |
| `[scroll] flick_speed` | `3.0` | Hand sizes per second over the flick window that make a flick. 0.1 to 50. |
| `[scroll] flick_min_travel` | `0.3` | Hand sizes the knuckles must also travel within the window. 0.01 to 3. |
| `[scroll] flick_window_ms` | `150.0` | Milliseconds a flick is measured over; also how long `"auto"` waits before a continuous scroll starts. 10 to 1000. |
| `[scroll] flick_pixels` | `600` | Pixels one flick scrolls, as one scroll wheel event. 1 to 10000. |
| `[scroll] flick_cooldown_ms` | `500.0` | Milliseconds after a flick in which nothing scrolls. 0 to 5000. |

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

- A right-click Gesture. Horizontal scroll.

Known limits:

- macOS on Apple Silicon only.
- The Open palm, Fist and relative-mode values were tuned on synthetic landmarks. Tune
  them on your Hand with `--debug-gestures`, `[open_palm]`, `[clutch]` and `[relative]`.
- The Scroll's pose thresholds and speeds were tuned on synthetic landmarks too, and its
  scroll events have only been tested with fakes. Tune it with `--debug-gestures` and
  `[scroll]`.
- Two fingers tilted towards the camera at a fixed height still move the knuckles down
  in the picture, so tilting while scrolling scrolls down a little (on synthetic hands, a
  sweep to 75 degrees and back at the anchor scrolled about 1000 pixels down, half of
  what following the fingertips did). Keep the wrist height steady, or widen `deadzone`.
- The Scroll follows the knuckles because they move less than the fingertips when the
  fingers tilt. How steady the knuckle landmarks are under real jitter and lighting is
  not known yet: the synthetic jitter is the same for every landmark.
- In relative mode, relaxed two fingers tilted to about 70 degrees read as a Fist. A dip
  shorter than 100 ms is ignored, but held there the clutch takes over and ends the
  scroll. If that happens, raise `[clutch] score_threshold` or lower `[clutch] tip_curled`
  (a finger then has to fold back further to count as curled).
- Whether one 600-pixel scroll event moves exactly one item in Instagram Reels or YouTube
  Shorts in Safari or Chrome has not been tried. Feeds that snap each item to the
  window move one item for a step of more than half and less than one and a half
  windows; feeds that count wheel gestures in JavaScript may move one item per event
  or ignore events below a threshold. If a flick moves two items, lower `flick_pixels`;
  if it moves none, raise it.
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
