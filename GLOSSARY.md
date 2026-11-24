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
The smaller rectangle of the camera frame that is mapped to the whole screen, so the arm does not have to travel far.
_Avoid_: ROI, zone, box

**Control mode**:
How hand position becomes cursor movement. v1 ships **absolute** (the pointer maps to a screen point through the active region). **Relative** (trackpad-style, with a clutch) is planned and is selected by config.
_Avoid_: Input mode, tracking mode

**Gesture**:
A recognised hand shape. v1: **pinch** and **open palm**. Later: scroll, right-click.
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
The window that shows what airmouse sees: hand skeleton, active region and gesture state. It is the footage used in demos.
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
