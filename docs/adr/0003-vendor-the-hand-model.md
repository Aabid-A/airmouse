# Vendor the hand model in the repo

mediapipe 1.2.3 ships only the Tasks API and no hand model, so `HandLandmarker` needs the 7.8 MB `hand_landmarker.task` file at run time. We decided to commit that file unmodified in `src/airmouse/assets/`, with the Apache-2.0 licence text, a note giving its source, licence and SHA-256, and a test that fails if it changes, so airmouse needs no network call to run and ADR 0001 stays literally true. We considered a documented one-time manual download (an extra step and a failure on first run) and a download at first run (breaks ADR 0001). The cost is that the repository history carries 7.8 MB for good, each model update adds another 7.8 MB, and reviewers cannot read a binary, so the note and the checksum test stand in for review.

Status: accepted
