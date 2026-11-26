# Control mode is a config option, absolute first

v1 maps the Pointer to the screen through the Active region (absolute control mode), because a cursor that follows the finger is the clearest demo. Relative, trackpad-style movement with a clutch is wanted later, and suits lying in bed better. We decided the control mode is selected by config and sits behind one interface, so relative can be added without rewriting the pipeline. The cost is a small abstraction in v1 that only has one implementation.

## Amendment, 2026-11-25: relative is the default

In a real-hand test on the Mac on 2026-11-25, unpausing and pointing worked, but absolute mapping felt discontinuous: the maintainer could not comfortably reach every part of the screen, tracking reset whenever the hand left the Active region, and with several monitors on the desk an absolute map of the main display cannot reach the others at all. So the second implementation behind this interface is now built and is the default. `control.mode` is `relative` by default and `absolute` stays as an option; an unknown value is an error listing both.

Relative mode moves the cursor by the Pointer's movement in the prepared frame, in hand sizes (so the feel does not change with the distance from the camera), times a gain with speed-dependent acceleration and a cap (`[relative]`). The One Euro filter still smooths the Pointer. It starts from the cursor's current position, and the first frame after the start, after a clutch and after the Hand returns moves nothing, so the cursor never jumps.

The clutch is a Fist (all four fingers curled, the index included) held for about 100 ms (`[clutch]`): while it is held the Hand's movement is ignored, no click or drag can start and a held drag is released. The Hand leaving the frame (No hand) also holds the cursor still and resumes without a jump. Because closing a fist moves the index towards the thumb, the clutch has priority over the Pinch, and a Fist is never a Pinch or an Open palm; while the fingers curl towards a Fist the cursor holds still (HOLD). The clutch and these guards belong to relative mode only: in absolute mode the hand's position is the cursor, so there is nothing to clutch, and absolute mode behaves exactly as it did before.

Display scope: relative mode moves across all active displays and keeps the cursor inside the union of their bounds (Quartz global coordinates, in points), whatever their sizes and arrangement, re-reading the display list while running. Absolute mode maps to the main display only.

The interface the Controller sees is a cursor path: a position per frame and a reset. The cost is a second implementation to keep working, and a gesture (the Fist) whose thresholds still need tuning on a real hand.

Status: accepted, amended 2026-11-25
