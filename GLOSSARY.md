# airmouse

Control a Mac's cursor by moving a hand in the air in front of the webcam. All
processing stays on the laptop.

## Language

**Hand**:
The single hand airmouse tracks, as 21 landmarks from MediaPipe's HandLandmarker (Tasks API).
_Avoid_: Palm (only the open palm gesture), user

**Hand model**:
The vendored `hand_landmarker.task` file (a palm detector plus a 21-landmark model) that the HandLandmarker loads. It ships inside the package, so airmouse never downloads it.
_Avoid_: Model file, weights

**Pointer**:
The index fingertip landmark, which drives the cursor.
_Avoid_: Finger, tip, cursor (the cursor is the on-screen result, not the landmark)

**Active region**:
The smaller rectangle of the camera frame that absolute control mode maps to the whole main display, so the arm does not have to travel far.
_Avoid_: ROI, zone, box

**Control mode**:
How hand position becomes cursor movement, selected by `control.mode`. **Relative**, the default: the cursor moves by the Pointer's movement (in hand sizes, times a gain), from where it is, across all displays, with the Fist as the clutch. **Absolute**: the Pointer maps to a point on the main display through the Active region (ADR 0002).
_Avoid_: Input mode, tracking mode

**Clutch**:
Relative mode: the state in which the Hand's movement is ignored, so the hand can be moved back without moving the cursor, like lifting a mouse. Entered by holding a Fist for about 100 ms; a held drag is released, and the Preview says CLUTCH. No hand also holds the cursor still and resumes without a jump, but it is its own state and the Preview says NO HAND. While the fingers are only curling towards a Fist the cursor also holds still, and the Preview says HOLD. The cursor never jumps when following resumes.
_Avoid_: Freeze, hold-off

**Fist**:
All four fingers curled into the palm, the index included: each fingertip folded back past its own base along the hand's axis. The thumb is free (beside the fingers or tucked over them), but a thumb tip right on the index tip is a Pinch, never a Fist. Scored from 0 to 1 against a threshold (`[clutch]`). Held, it is the clutch (relative mode only).
_Avoid_: Grab

**Gesture**:
A recognised hand shape. v1: **pinch**, **open palm** and **fist**. Later: scroll, right-click.
_Avoid_: Pose, sign

**Pinch**:
Thumb tip and index tip brought together, measured relative to hand size. A short pinch is a click. A held pinch while moving is a drag.
_Avoid_: Tap, grab

**Open palm**:
The four fingers held upright and extended, together or spread, scored from 0 to 1 against a threshold (`[open_palm]` in the config). The thumb and the spread only add a little, so a normal open hand counts; a fist, a Pointer pose and a Pinch never do. Pauses at once; held steady for about 0.8 s (configurable) it also unpauses, so it acts as a toggle.
_Avoid_: Stop sign, high five

**Hold ring**:
The progress ring in the Preview that fills while an open palm is held toward unpausing, so it never triggers by accident.
_Avoid_: Spinner, countdown

**Paused**:
State in which hand movement produces no input. airmouse starts Paused. Entered with the open palm, left by holding it.
_Avoid_: Idle, disabled, locked

**Preview**:
The window that shows what airmouse sees: hand skeleton, gesture state and, in absolute mode, the active region. It is the footage used in demos.
_Avoid_: Debug window, viewer

**Privacy preview**:
The Preview with the camera image replaced by a plain background, so only the skeleton and gesture state show. The default. A face or room never appears in it.
_Avoid_: Anonymous mode, blur mode

**Camera-on indicator**:
The always-visible status in the CLI (and Preview) that the camera is capturing.
_Avoid_: Recording light

**No hand**:
The state after the Hand has been lost for about 250 ms. The cursor freezes, any drag is released, airmouse stays unpaused, and the Preview says so.
_Avoid_: Lost, tracking failure

**Calibrate mode**:
`--calibrate`, a view of the Hand and the Active region used to set rotate, mirror and the region for the camera's position. Applied before the Active region is placed.
_Avoid_: Setup wizard

**Cursor path**:
Everything from the camera to the cursor: camera read, frame preparation, the Hand tracker, the Controller and the cursor output. It runs on its own worker thread and never waits for the Preview (ADR 0004). In code it lives in `airmouse.pipeline`.
_Avoid_: Pipeline (ambiguous), backend

**Snapshot**:
The cursor path's latest state, copied and immutable, that the Preview draws: the Hand, the Controller's state, phase and Hold ring, No hand, the clutch and the hold, the debug readings and timings. Only the newest one is kept.
_Avoid_: Frame (a camera image), message, event
