# Privacy by design: no camera pixels shown by default, nothing saved, no network

airmouse watches a webcam in a bedroom, and its Preview is meant to be screen-recorded and shared. We decided that the Preview shows only the hand skeleton and gesture state on a plain background by default (the Privacy preview), that no frame is ever written to disk, and that the app makes no network calls. Showing the raw camera image is an explicit opt-in for debugging. Repo fixtures are synthetic landmarks only, never recorded video. The cost is a less obviously "real" looking demo and harder debugging of tracking problems, which we accept so a face or room can never leak into a shared clip.

Status: accepted
