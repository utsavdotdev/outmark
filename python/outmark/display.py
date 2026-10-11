"""Matrix modes and the Linux side of the Arduino Bridge.

The sketch in sketch/sketch.ino draws the same frames. Tests use RecordingDisplay.
A passing test here does not mean a physical LED turned on.
"""

from __future__ import annotations

import logging
import threading
import time
from dataclasses import dataclass
from typing import Protocol

from outmark.engine import SessionEngine
from outmark.errors import DisplayError
from outmark.frames import (
    EVENT_ACCEPT,
    EVENT_EXPIRED,
    EVENT_KEPT,
    EVENT_MODE,
    EVENT_NOT_KEPT,
    EVENT_PROPOSAL,
    EVENT_STARTUP,
    VIEW_CHART,
)
from outmark.records import SessionStatus

logger = logging.getLogger(__name__)

MODE_REST = 0
MODE_GRID = 1
MODE_PENDING = 2
MODE_ACTIVE = 3
MODE_DONE = 4

ROWS = 8
COLS = 13
FRAME_LENGTH = ROWS * COLS
MASK_MAX = (1 << COLS) - 1
PROGRESS_ROW = 3
CENTER_COL = 6
REST_PIXEL = (PROGRESS_ROW, CENTER_COL)
DONE_PIXELS = (
    (4, 2),
    (4, 4),
    (5, 3),
    (5, 5),
    (6, 6),
)
REFRESH_SECONDS = 5


class MatrixDisplay(Protocol):
    """The three calls the sketch exposes. Implementations must not store sessions."""

    def set_mode(self, mode: int) -> None:
        """Select one display mode."""

    def set_progress(self, segments: int) -> None:
        """Set the active-session bar length, from 0 through 13."""

    def set_grid_row(self, row: int, mask: int) -> None:
        """Set one history row. Bit 0 is the oldest day."""

    def set_view(self, view: int) -> None:
        """Select the chart or the plant. 0 is the chart and 1 is the plant."""

    def set_plant(self, stage: int) -> None:
        """Store the plant stage. This does not by itself play a growth animation."""

    def set_event(self, code: int, generation: int) -> None:
        """Play one animation. The same generation is ignored by the sketch."""


@dataclass(frozen=True)
class DisplayView:
    mode: int
    progress: int
    masks: tuple[int, ...]


class RecordingDisplay:
    """In-memory stand-in used by tests."""

    def __init__(self) -> None:
        self.calls: list[tuple[object, ...]] = []

    def set_mode(self, mode: int) -> None:
        self.calls.append(("set_mode", mode))

    def set_progress(self, segments: int) -> None:
        self.calls.append(("set_progress", segments))

    def set_grid_row(self, row: int, mask: int) -> None:
        self.calls.append(("set_grid_row", row, mask))

    def set_view(self, view: int) -> None:
        self.calls.append(("set_view", view))

    def set_plant(self, stage: int) -> None:
        self.calls.append(("set_plant", stage))

    def set_event(self, code: int, generation: int) -> None:
        self.calls.append(("set_event", code, generation))


class BridgeDisplay:
    """Call the sketch through arduino.app_utils.Bridge. Import happens on construction."""

    def __init__(self) -> None:
        from arduino.app_utils import Bridge

        self._call = Bridge.call

    def set_mode(self, mode: int) -> None:
        self._call("set_mode", mode)

    def set_progress(self, segments: int) -> None:
        self._call("set_progress", segments)

    def set_grid_row(self, row: int, mask: int) -> None:
        self._call("set_grid_row", row, mask)

    def set_view(self, view: int) -> None:
        self._call("set_view", view)

    def set_plant(self, stage: int) -> None:
        self._call("set_plant", stage)

    def set_event(self, code: int, generation: int) -> None:
        self._call("set_event", code, generation)


def open_bridge_display() -> BridgeDisplay | None:
    """Return a board display, or None when the App Lab bridge is not installed."""
    try:
        return BridgeDisplay()
    except ImportError:
        logger.info("Arduino Bridge is not installed. The matrix will not update.")
        return None


def describe(engine: SessionEngine) -> DisplayView:
    """Choose one mode from the stored session. This does not write the JSON file."""
    snapshot = engine.active_session()
    masks = tuple(engine.history().row_mask(row) for row in range(ROWS))
    if snapshot is None:
        if engine.open_proposal() is not None:
            return DisplayView(MODE_PENDING, 0, masks)
        mode = MODE_GRID if any(masks) else MODE_REST
        return DisplayView(mode, 0, masks)
    if snapshot.deadline_passed:
        return DisplayView(MODE_DONE, snapshot.progress_segments, masks)
    if snapshot.progress_segments == 0:
        return DisplayView(MODE_PENDING, 0, masks)
    return DisplayView(MODE_ACTIVE, snapshot.progress_segments, masks)


def publish(
    engine: SessionEngine,
    display: MatrixDisplay,
    event: tuple[int, int] | None = None,
) -> None:
    """Send the activity chart. A failure here must not be treated as a session change.

    Refresh calls omit the event, so a growth-style replay cannot happen.
    The matrix stays on the chart.
    """
    if event is not None:
        display.set_event(event[0], event[1])
    display.set_view(VIEW_CHART)
    send(display, describe(engine))


def send(display: MatrixDisplay, view: DisplayView) -> None:
    """Validate, then send rows, progress, and the mode last."""
    _require_int(view.mode, MODE_REST, MODE_DONE, "mode")
    _require_int(view.progress, 0, COLS, "progress")
    if len(view.masks) != ROWS:
        raise DisplayError("the matrix needs eight row masks")
    masks = tuple(_require_int(mask, 0, MASK_MAX, "mask") for mask in view.masks)
    for row, mask in enumerate(masks):
        display.set_grid_row(row, mask)
    display.set_progress(view.progress)
    display.set_mode(view.mode)


def render_frame(mode: int, progress: int, masks: tuple[int, ...]) -> tuple[int, ...]:
    """Build the 104-pixel frame the sketch draws for this mode."""
    _require_int(mode, MODE_REST, MODE_DONE, "mode")
    _require_int(progress, 0, COLS, "progress")
    if len(masks) != ROWS:
        raise DisplayError("the matrix needs eight row masks")
    checked = tuple(_require_int(mask, 0, MASK_MAX, "mask") for mask in masks)
    frame = [0] * FRAME_LENGTH
    if mode == MODE_GRID:
        for row, mask in enumerate(checked):
            for column in range(COLS):
                if mask & (1 << column):
                    frame[row * COLS + column] = 1
    elif mode == MODE_ACTIVE:
        for column in range(progress):
            frame[PROGRESS_ROW * COLS + column] = 1
    elif mode == MODE_PENDING:
        for row in range(ROWS):
            frame[row * COLS + CENTER_COL] = 1
    elif mode == MODE_DONE:
        for row, column in DONE_PIXELS:
            frame[row * COLS + column] = 1
    else:
        row, column = REST_PIXEL
        frame[row * COLS + column] = 1
    return tuple(frame)


class DisplayTracker:
    """Remember the last phase so a refresh does not replay an animation."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._generation = 0
        self._seen = False
        self._phase = "idle"
        self._kept = 0
        self._mode = "chart"

    def observe(self, engine: SessionEngine) -> tuple[int, int] | None:
        with self._lock:
            return self._observe(engine)

    def _observe(self, engine: SessionEngine) -> tuple[int, int] | None:
        phase = _phase(engine)
        kept = _kept_count(engine)
        mode = "chart"
        code: int | None = None
        if not self._seen:
            code = EVENT_STARTUP
        elif mode != self._mode:
            code = EVENT_MODE
        elif phase == "proposed" and self._phase != "proposed":
            code = EVENT_PROPOSAL
        elif phase == "active" and self._phase == "proposed":
            code = EVENT_ACCEPT
        elif phase == "awaiting_report" and self._phase == "active":
            code = EVENT_EXPIRED
        elif self._phase == "awaiting_report" and phase == "idle":
            code = EVENT_KEPT if kept > self._kept else EVENT_NOT_KEPT
        self._seen = True
        self._phase = phase
        self._kept = kept
        self._mode = mode
        if code is None:
            return None
        self._generation += 1
        return (code, self._generation)


def _kept_count(engine: SessionEngine) -> int:
    return sum(1 for session in engine.sessions() if session.status is SessionStatus.KEPT)


def _phase(engine: SessionEngine) -> str:
    snapshot = engine.active_session()
    if snapshot is not None:
        return "awaiting_report" if snapshot.deadline_passed else "active"
    if engine.open_proposal() is not None:
        return "proposed"
    return "idle"


def start_refresh(
    engine: SessionEngine,
    display: MatrixDisplay,
    tracker: DisplayTracker,
    interval: float = REFRESH_SECONDS,
) -> None:
    """Refresh progress from the engine without blocking the web server.

    The tracker emits an event only when the phase or mode changes, so the
    five-second refresh does not replay a growth animation.
    """

    def _loop() -> None:
        while True:
            time.sleep(interval)
            try:
                publish(engine, display, tracker.observe(engine))
            except Exception:
                logger.exception("Matrix update failed. Stored sessions were left unchanged.")

    threading.Thread(target=_loop, name="outmark-display", daemon=True).start()


def _require_int(value: object, low: int, high: int, field: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise DisplayError(f"{field} must be an integer")
    if not low <= value <= high:
        raise DisplayError(f"{field} must be between {low} and {high}")
    return value
