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
        mode = MODE_GRID if any(masks) else MODE_REST
        return DisplayView(mode, 0, masks)
    if snapshot.deadline_passed:
        return DisplayView(MODE_DONE, snapshot.progress_segments, masks)
    if snapshot.progress_segments == 0:
        return DisplayView(MODE_PENDING, 0, masks)
    return DisplayView(MODE_ACTIVE, snapshot.progress_segments, masks)


def publish(engine: SessionEngine, display: MatrixDisplay) -> None:
    """Send the current view. A failure here must not be treated as a session change."""
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


def start_refresh(
    engine: SessionEngine,
    display: MatrixDisplay,
    interval: float = REFRESH_SECONDS,
) -> None:
    """Refresh progress from the engine without blocking the web server."""

    def _loop() -> None:
        while True:
            time.sleep(interval)
            try:
                publish(engine, display)
            except Exception:
                logger.exception("Matrix update failed. Stored sessions were left unchanged.")

    threading.Thread(target=_loop, name="outmark-display", daemon=True).start()


def _require_int(value: object, low: int, high: int, field: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise DisplayError(f"{field} must be an integer")
    if not low <= value <= high:
        raise DisplayError(f"{field} must be between {low} and {high}")
    return value
