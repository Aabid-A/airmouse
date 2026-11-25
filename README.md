# airmouse

Control your Mac's cursor by moving your hand in the air, using your webcam.
Everything is processed on your laptop.

> Work in progress. See the [issues](https://github.com/Aabid-A/airmouse/issues).

## Run

```bash
uv run airmouse
```

This opens the Preview: your Hand as a glowing skeleton on a plain dark background, in a
fixed 16:9 window (1280x720, ready to screen-record), with the Active region outline, the
state (Paused, active, Pinch, drag, No hand), a "camera on" indicator and the frame rate. The camera image is never shown and no frame
is saved. It does not move the cursor yet. Press `q` in the Preview or Ctrl-C to quit.
Use `--camera N` to pick a camera. For debugging only, `--show-camera-image` draws the
camera image behind the skeleton. To tune the Open palm on your own hand, run with
`--debug-gestures`: the Preview then draws the Open palm score against its threshold, the
wrist speed against the steadiness tolerance, and per-stage timings in ms (CAM is the wait
for the camera, PREP frame preparation, TRACK the Hand tracker, DRAW the Preview render,
WIN the window). The thresholds are under `[open_palm]` in the config; see `--print-config`.

## Third-party notices

The hand model (`hand_landmarker.task`) is Google's MediaPipe model, licensed under
Apache-2.0. Its source, checksum and licence text are in `src/airmouse/assets/`.

## Development

Needs [uv](https://docs.astral.sh/uv/) and Python 3.12.

```bash
uv sync
uv run airmouse --help
scripts/check.sh
```
