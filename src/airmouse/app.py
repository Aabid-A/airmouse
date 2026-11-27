"""The live Preview: camera in, tracked Hand out, drawn as the Privacy preview.

Two threads. The worker (`pipeline.Worker`) runs the cursor path: camera read,
frame preparation, the Hand tracker, the Controller and the cursor output. It
publishes an immutable `Snapshot` per tracked frame into a latest-value slot. The
main thread owns the window: it draws the latest Snapshot, shows it and checks
for `q` (macOS needs window calls on the main thread). Neither waits for the
other, so a slow window never slows the cursor, and a stalled camera never
freezes the window.

`run_preview` wires the two, written against small adapters (camera, tracker,
window) so tests drive it with fakes. `run_live_preview` wires the real ones.
The controller gets the real Quartz cursor output on macOS and a no-op output
elsewhere (and in tests). In calibrate mode (`--calibrate`) the Preview shows the
Hand and the Active region instead and no controller is built at all, so it can
make no cursor input. In relative control mode (the default) the Preview does not
outline the Active region, since nothing maps through it; absolute mode and
calibrate mode do. With `--debug-gestures` the Preview also draws the Open
palm score, the wrist speed, in relative mode the Fist score and finger curl
against the clutch and hold thresholds, the
worker's stage timings (CAM, PREP, TRACK, CTRL, and FRAME, the camera's delivery
interval), the window's (DRAW, WIN), and the tracking and window rates, plus the
Scroll's two-finger score, state, offset, speed and flick measure, which it also
prints to the terminal once a second (`scroll_line`) so the numbers can be copied.
Frames are rotated and mirrored by `prepare_frame` before tracking.
"""

import math
import sys
import time
from collections.abc import Callable
from typing import TextIO

from airmouse.camera import Camera, CameraError, OpenCvCamera, frame_to_image
from airmouse.config import CameraConfig, Config
from airmouse.controller import Controller, Output
from airmouse.displays import FixedScreen, Screen
from airmouse.mapping import make_cursor_path, mapped_region
from airmouse.output import OutputError, QuartzOutput
from airmouse.pipeline import FpsMeter, LatestSlot, ShutdownOutput, Snapshot, StageTimes, Worker
from airmouse.renderer import DebugReadout, Image, render_calibrate, render_preview
from airmouse.scroll import ScrollReading
from airmouse.tracker import HandLandmarkerTracker, Tracker, TrackerError
from airmouse.window import OpenCvWindow, Window

# With no new Snapshot, the Preview still checks for `q` (and keeps the window alive)
# this often, without spinning.
UI_WAIT_S = 0.03
# How long quitting waits for the worker before it lifts a held button itself.
STOP_TIMEOUT_S = 1.0
# With --debug-gestures, the scroll readout goes to the terminal at most this often.
SCROLL_LINE_S = 1.0

STUCK_MESSAGE = (
    "airmouse: the camera, tracker or cursor output did not stop in time; "
    "the button is up, and the camera is released when airmouse exits."
)

# The display size the mapping assumes when there is no real output (a 16:10 laptop screen).
DEFAULT_DISPLAY = (1440.0, 900.0)


class NoOutput:
    """No cursor input at all: Paused and active still show in the Preview."""

    def move_cursor(self, x: float, y: float) -> None:
        pass

    def press(self, x: float, y: float) -> None:
        pass

    def drag_to(self, x: float, y: float) -> None:
        pass

    def release(self, x: float, y: float) -> None:
        pass

    def release_drag(self) -> None:
        pass

    def scroll(self, pixels: int) -> None:
        pass


def scroll_line(reading: ScrollReading) -> str:
    """One compact line of the Scroll's readout, for the terminal."""

    def number(value: float | None, places: int = 2) -> str:
        return "--" if value is None else f"{value:+.{places}f}"

    score = "--" if reading.score is None else f"{reading.score:.2f}"
    return (
        f"scroll: {reading.mode} {reading.state.value} two={score} "
        f"entry={reading.threshold:.2f} exit={reading.exit_threshold:.2f} "
        f"offset={number(reading.offset)} deadzone={reading.deadzone:.2f} "
        f"speed={reading.speed:+.0f}px/s flick={number(reading.flick)}/"
        f"{reading.flick_speed:.1f}"
    )


def camera_on_line(camera: CameraConfig) -> str:
    return (
        f"camera on: camera {camera.index}, {camera.width}x{camera.height} at {camera.fps} fps. "
        "Press q in the Preview or Ctrl-C to quit."
    )


class PreviewLoop:
    """The main thread: draw the latest Snapshot, show it, check for `q`. Never tracks.

    It draws only Snapshots the worker published, so a stalled worker leaves the
    last known state on screen, and it never invents one.
    """

    def __init__(
        self,
        window: Window,
        slot: LatestSlot[Snapshot],
        *,
        show_camera_image: bool,
        debug_gestures: bool,
        timer: Callable[[], float],
        out: TextIO | None = None,
    ) -> None:
        self._window = window
        self._out = out  # where the once-a-second scroll line goes with --debug-gestures
        self._scroll_line_at: float | None = None
        self._slot = slot
        self._show_camera_image = show_camera_image
        self._debug_gestures = debug_gestures
        self._timer = timer
        self._stages = StageTimes()
        self._meter = FpsMeter()
        self._fps: float | None = None

    def run(self) -> None:
        """Until `q`, a closed window, or the worker ending."""
        drawn = 0
        while True:
            version, snapshot = self._slot.wait_for_newer(drawn, UI_WAIT_S)
            if snapshot is None or version == drawn:
                quit_requested = self._window.quit_requested()
            else:
                drawn = version
                quit_requested = self._draw(snapshot)
            if quit_requested or self._slot.closed:
                return

    def _draw(self, snapshot: Snapshot) -> bool:
        timer = self._timer
        started = timer()
        image = self.render(snapshot)
        rendered = timer()
        self._window.show(image)
        quit_requested = self._window.quit_requested()
        shown = timer()
        self._stages.record("DRAW", rendered - started)
        self._stages.record("WIN", shown - rendered)
        self._fps = self._meter.tick(shown)
        self._print_scroll_line(snapshot, shown)
        return quit_requested

    def _print_scroll_line(self, snapshot: Snapshot, now: float) -> None:
        status = snapshot.controller
        if not self._debug_gestures or self._out is None or status is None:
            return
        if status.scroll is None:
            return
        last = self._scroll_line_at
        if last is not None and now - last < SCROLL_LINE_S:
            return
        self._scroll_line_at = now
        print(scroll_line(status.scroll), file=self._out)

    def render(self, snapshot: Snapshot) -> Image:
        camera_image = (
            frame_to_image(snapshot.camera_frame) if snapshot.camera_frame is not None else None
        )
        status = snapshot.controller
        if status is None:
            return render_calibrate(
                snapshot.view,
                landmarks=snapshot.landmarks,
                camera_on=True,
                fps=snapshot.fps,
                camera_image=camera_image,
                show_camera_image=self._show_camera_image,
            )
        debug = (
            DebugReadout(status.reading, self._readout_rows(snapshot), status.fist, status.scroll)
            if self._debug_gestures
            else None
        )
        return render_preview(
            status.state,
            status.hold_progress,
            landmarks=snapshot.landmarks,
            camera_on=True,
            fps=snapshot.fps,
            camera_image=camera_image,
            show_camera_image=self._show_camera_image,
            debug=debug,
            no_hand=status.no_hand,
            phase=status.phase,
            view=snapshot.view,
            clutch=status.clutch,
            holding=status.holding,
            scrolling=status.scroll is not None and status.scroll.scrolling,
        )

    def _readout_rows(self, snapshot: Snapshot) -> tuple[tuple[str, float], ...]:
        """Worker stages, window stages, then the tracking rate and the window rate."""
        rates = (("TRACK FPS", _or_nan(snapshot.fps)), ("UI FPS", _or_nan(self._fps)))
        return snapshot.timings + self._stages.readings() + rates


def _or_nan(value: float | None) -> float:
    return math.nan if value is None else value  # the readout draws `--`


def run_preview(
    config: Config,
    camera: Camera,
    tracker: Tracker,
    window: Window,
    *,
    show_camera_image: bool = False,
    calibrate: bool = False,
    debug_gestures: bool = False,
    output: Output | None = None,
    display: tuple[float, float] = DEFAULT_DISPLAY,
    screen: Screen | None = None,
    clock: Callable[[], float] = time.monotonic,
    timer: Callable[[], float] = time.perf_counter,
    out: TextIO = sys.stdout,
    stop_timeout_s: float = STOP_TIMEOUT_S,
) -> int:
    """Run until `q` or Ctrl-C, then release everything. Raises CameraError if frames stop.

    `output` takes cursor moves, clicks and drags (default: none); `display` is the main
    display's size in points. `screen` reports the displays and the cursor position for
    relative mode (default: one `display`-sized display, cursor position unknown).
    `debug_gestures` draws the gesture readout and stage timings (`timer` measures them).
    The worker thread's errors are raised here, after everything is released.
    """
    relative = config.control.mode == "relative"
    cursor_output = (
        None
        if calibrate
        else ShutdownOutput(output or NoOutput(), out, screen or FixedScreen(display))
    )
    controller = (
        None
        if cursor_output is None
        else Controller(
            config.timing,
            cursor_output,
            # Relative mode reads the displays and the cursor through the ShutdownOutput,
            # so nothing reaches Quartz after shutdown.
            make_cursor_path(config, display, cursor_output),
            config.open_palm,
            config.pinch,
            config.clutch if relative else None,  # the clutch is relative-mode only
            config.scroll,  # the Scroll works in both control modes
        )
    )
    slot = LatestSlot[Snapshot]()
    worker = Worker(
        config,
        camera,
        tracker,
        slot,
        controller=controller,
        output=cursor_output,
        region=mapped_region(config, display),
        outline_region=not relative,  # absolute mode outlines the region the cursor maps
        show_camera_image=show_camera_image,
        clock=clock,
        timer=timer,
    )
    preview = PreviewLoop(
        window,
        slot,
        show_camera_image=show_camera_image,
        debug_gestures=debug_gestures,
        timer=timer,
        out=out,
    )
    print(camera_on_line(config.camera), file=out)
    if calibrate:
        print(
            "calibrate mode: no cursor input. Adjust rotate and mirror until the "
            "skeleton moves as your hand does.",
            file=out,
        )
    if show_camera_image:
        print("warning: the Preview shows the camera image (--show-camera-image).", file=out)
    worker.start()
    try:
        preview.run()
    except KeyboardInterrupt:
        pass
    finally:
        # The worker lifts a held button and closes the tracker and the camera on its way
        # out. If it is stuck, `stop` lifts the button from here, and the tracker and the
        # camera are left to the worker (if it comes back) or to the process exit, never
        # closed under a call still running on them.
        if not worker.stop(stop_timeout_s):
            print(STUCK_MESSAGE, file=out)
        window.close()
        print("camera off", file=out)
    if worker.error is not None:
        raise worker.error
    return 0


def run_live_preview(
    config: Config,
    *,
    show_camera_image: bool = False,
    calibrate: bool = False,
    debug_gestures: bool = False,
) -> int:
    """The real camera, Hand tracker and window. Returns the exit status."""
    try:
        tracker = HandLandmarkerTracker.open()
    except TrackerError as error:
        print(f"airmouse: {error}", file=sys.stderr)
        return 1
    try:
        camera = OpenCvCamera.open(config.camera)
    except CameraError as error:
        tracker.close()
        print(f"airmouse: {error}", file=sys.stderr)
        return 1
    try:
        output = QuartzOutput.open() if sys.platform == "darwin" and not calibrate else None
    except OutputError as error:
        camera.release()
        tracker.close()
        print(f"airmouse: {error}", file=sys.stderr)
        return 1
    try:
        window = OpenCvWindow()
    except Exception:
        camera.release()
        tracker.close()
        raise
    try:
        return run_preview(
            config,
            camera,
            tracker,
            window,
            show_camera_image=show_camera_image,
            calibrate=calibrate,
            debug_gestures=debug_gestures,
            output=output,
            display=output.display_size if output else DEFAULT_DISPLAY,
            screen=output,
        )
    except (CameraError, OutputError) as error:
        print(f"airmouse: {error}", file=sys.stderr)
        return 1
