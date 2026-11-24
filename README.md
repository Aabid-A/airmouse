# airmouse

Control your Mac's cursor by moving your hand in the air, using your webcam.
Everything is processed on your laptop.

> Work in progress. See the [issues](https://github.com/Aabid-A/airmouse/issues).

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
