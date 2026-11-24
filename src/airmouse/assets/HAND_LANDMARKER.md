# Hand model: `hand_landmarker.task`

The MediaPipe Hand Landmarker "full" model bundle (float16), vendored unchanged.
The tracker loads it from this folder, so airmouse never downloads it (ADR 0001,
ADR 0003).

| | |
|---|---|
| File | `hand_landmarker.task` |
| Size | 7,819,105 bytes |
| SHA-256 | `fbc2a30080c3c557093b5ddfc334698132eb341044ccee322ccf8bcf3607cde1` |
| Contents | `hand_detector.tflite` (palm detector) and `hand_landmarks_detector.tflite` (21 landmarks) |
| Modifications | None. It is a byte-for-byte copy. |

## Source

- Download used: <https://storage.googleapis.com/mediapipe-models/hand_landmarker/hand_landmarker/float16/latest/hand_landmarker.task>.
  The `float16/1/` object at the same path holds the same bytes. Google's object was last modified on 26 April 2023.
- Google's guide: <https://developers.google.com/edge/mediapipe/solutions/vision/hand_landmarker>.
  Its "Model card" link and its download link point to the Hugging Face repo
  <https://huggingface.co/litert-community/MediaPipe-HandLandmarker-Full>, which
  records the same size and SHA-256 and states the file is byte-identical to
  Google's.
- Checked on 2026-11-24: the Google storage file and the SHA-256 Hugging Face records for its copy match this file.

## Licence

Apache License, Version 2.0 (full text in `LICENSE-Apache-2.0.txt`).

Evidence, from Google's own model card ("Model Card Hand Tracking (Lite_Full)
with Fairness Oct 2021", 358,044 bytes, SHA-256
`43127ff8a92e22717f0d8c30dab3efef4641a29cbf50b15ae3de001be94ab76b`,
<https://storage.googleapis.com/mediapipe-assets/Model%20Card%20Hand%20Tracking%20(Lite_Full)%20with%20Fairness%20Oct%202021.pdf>):
"LICENSED UNDER Apache License, Version 2.0". The Hugging Face model card also
declares `license: apache-2.0`.

## Attribution

Created by the MediaPipe team at Google. Cite: F. Zhang, V. Bazarevsky, A. Vakunov,
A. Tkachenka, G. Sung, C.-L. Chang, M. Grundmann, "MediaPipe Hands: On-device
Real-time Hand Tracking", 2020, <https://arxiv.org/abs/2006.10214>. The model
card also credits the GHUM hand model (Xu et al., CVPR 2020). No separate
copyright notice or NOTICE file is published for the model.

## Check it

```bash
cd src/airmouse/assets
shasum -a 256 -c hand_landmarker.task.sha256     # macOS
sha256sum -c hand_landmarker.task.sha256          # Linux
```

`tests/test_assets.py` runs the same check in CI. To replace the file, change
the checksum file, this note and ADR 0003 together, and say why in the PR.
