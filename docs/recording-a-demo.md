# Recording a demo

The Preview is built to be screen-recorded. It is a fixed 16:9 window shown at 1280x720,
and by default it shows only the Hand skeleton on a plain dark background, so a recording
contains no face and no room.

## Steps

1. Start airmouse: `uv run airmouse`. Check that the Preview window is open and shows
   the Camera-on indicator. Do not use `--show-camera-image` for a demo.
2. Press Cmd-Shift-5. The macOS screenshot toolbar appears.
3. Choose **Record Selected Portion**.
4. Drag the selection frame over the Preview window, so the window fills it.
5. Click **Record**. The toolbar turns into a stop button in the menu bar.
6. Show the sequence you want to demonstrate. A good take is: Paused, hold an Open palm
   until the Hold ring fills, move the Pointer around the Active region, Pinch to click,
   Pinch and move to drag, then show an Open palm to pause again.
7. Click the stop button in the menu bar. macOS saves the recording as a file.

The cursor airmouse moves is outside the Preview window, so a recording of only the
window shows the skeleton and the state but not the cursor. To show the cursor as well,
select a larger portion, or the whole screen, with the Preview window in it. The
Options menu in the same toolbar has the save location and other recording settings.

## Before you share it

- Watch the clip once for anything else on screen: other windows, notifications, file
  names.
- Keep the clip short. A few seconds per Gesture is enough.
- The README has a placeholder where the demo goes. Add the file to `docs/` and replace
  the placeholder line in `README.md`. Avoid committing large files: a short, small clip
  is best.
