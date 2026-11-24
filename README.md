# airmouse

Control your Mac's cursor by moving your hand in the air, using your webcam.
Everything is processed on your laptop.

> Work in progress. See the [issues](https://github.com/Aabid-A/airmouse/issues).

## Run

```bash
uv run airmouse
```

This opens the Preview: your Hand as a skeleton on a plain dark background, with a
"camera on" indicator and the frame rate. The camera image is never shown and no frame
is saved. It does not move the cursor yet. Press `q` in the Preview or Ctrl-C to quit.
Use `--camera N` to pick a camera. For debugging only, `--show-camera-image` draws the
camera image behind the skeleton.

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
