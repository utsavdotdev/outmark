"""8×13 frames for the UNO Q matrix.

Row 0 is the same buffer edge as the walking row of the history grid. Which
physical edge that is was not checked on the glass. Values are 0 or 1. The
sketch plays these sequences with millis() and matrix.draw. It does not use
delay, loadSequence, or playSequence.

A kept report must call the growth event before the new plant stage is stored
on the MCU, so the animation still has the previous silhouette.
"""

from __future__ import annotations

ROWS = 8
COLS = 13
FRAME_LENGTH = ROWS * COLS

EVENT_STARTUP = 1
EVENT_PROPOSAL = 2
EVENT_ACCEPT = 3
EVENT_EXPIRED = 4
EVENT_KEPT = 5
EVENT_NOT_KEPT = 6
EVENT_MODE = 7

PROPOSAL_FRAMES = 4
ACCEPT_FRAMES = 3
EXPIRED_FRAMES = 14
NOT_KEPT_FRAMES = 3
REVEAL_FRAMES = 13
FRAME_MS = 160

VIEW_CHART = 0
VIEW_PLANT = 1


def _bits(*columns: int) -> int:
    mask = 0
    for column in columns:
        mask |= 1 << column
    return mask


# Distinct silhouettes. Row 7 stays empty so a timer can use it.
PLANT_ROWS: tuple[tuple[int, ...], ...] = (
    (0, 0, 0, 0, 0, 0, _bits(6), 0),
    (0, 0, 0, 0, 0, _bits(6), _bits(5, 7), 0),
    (0, 0, 0, 0, _bits(6), _bits(6), _bits(6), 0),
    (0, 0, 0, _bits(6), _bits(4, 6, 8), _bits(6), _bits(6), 0),
    (0, 0, _bits(6), _bits(3, 6, 9), _bits(6), _bits(5, 6, 7), _bits(6), 0),
    (0, _bits(5, 6, 7), _bits(4, 6, 8), _bits(6), _bits(4, 6, 8), _bits(6), _bits(6), 0),
)


def rows_to_frame(rows: tuple[int, ...]) -> tuple[int, ...]:
    if len(rows) != ROWS:
        raise ValueError("a frame needs eight rows")
    frame: list[int] = []
    for mask in rows:
        for column in range(COLS):
            frame.append(1 if mask & (1 << column) else 0)
    return tuple(frame)


def plant_frame(stage: int) -> tuple[int, ...]:
    return rows_to_frame(PLANT_ROWS[_stage(stage)])


def breathe_frame(stage: int, phase: int) -> tuple[int, ...]:
    """The plant plus, on odd phases, one corner pixel that is not part of it."""
    frame = list(plant_frame(stage))
    if phase % 2 == 1:
        frame[0] = 1
    return tuple(frame)


def plant_timer_frame(stage: int, segments: int) -> tuple[int, ...]:
    """Keep the plant and fill row 7 from the left. Row 7 is not part of a stage."""
    frame = list(plant_frame(stage))
    count = _segments(segments)
    for column in range(count):
        frame[7 * COLS + column] = 1
    return tuple(frame)


def chart_timer_frame(segments: int) -> tuple[int, ...]:
    """Progress on row 3 only. History masks are not drawn, so they cannot change."""
    frame = [0] * FRAME_LENGTH
    for column in range(_segments(segments)):
        frame[3 * COLS + column] = 1
    return tuple(frame)


def pending_frame() -> tuple[int, ...]:
    frame = [0] * FRAME_LENGTH
    for row in range(ROWS):
        frame[row * COLS + 6] = 1
    return tuple(frame)


def done_frame() -> tuple[int, ...]:
    frame = [0] * FRAME_LENGTH
    for row, column in ((4, 2), (4, 4), (5, 3), (5, 5), (6, 6)):
        frame[row * COLS + column] = 1
    return tuple(frame)


def column_reveal(destination: tuple[int, ...]) -> tuple[tuple[int, ...], ...]:
    _require_frame(destination)
    frames: list[tuple[int, ...]] = []
    for step in range(COLS):
        frame = []
        for index, pixel in enumerate(destination):
            frame.append(pixel if index % COLS <= step else 0)
        frames.append(tuple(frame))
    return tuple(frames)


def proposal_frames() -> tuple[tuple[int, ...], ...]:
    seed = plant_frame(0)
    blank = tuple(0 for _ in range(FRAME_LENGTH))
    return (blank, seed, seed, pending_frame())


def accept_frames() -> tuple[tuple[int, ...], ...]:
    pending = pending_frame()
    marked = list(pending)
    marked[3 * COLS] = 1
    return (pending, tuple(marked), pending)


def expired_frames() -> tuple[tuple[int, ...], ...]:
    frames: list[tuple[int, ...]] = []
    for column in range(COLS):
        frame = [0] * FRAME_LENGTH
        for row in range(ROWS):
            frame[row * COLS + column] = 1
        frames.append(tuple(frame))
    frames.append(done_frame())
    return tuple(frames)


def not_kept_frames(stage: int) -> tuple[tuple[int, ...], ...]:
    plant = plant_frame(stage)
    wink = list(plant)
    wink[COLS - 1] = 1
    return (plant, tuple(wink), plant)


def growth_frames(previous: int, current: int) -> tuple[tuple[int, ...], ...]:
    start = _stage(previous)
    end = _stage(current)
    if end < start:
        end = start
    if start == end:
        base = plant_frame(end)
        shimmer = list(base)
        shimmer[0] = 1
        return (base, tuple(shimmer), base)
    frames = [plant_frame(start), plant_frame(start)]
    for stage in range(start + 1, end + 1):
        frames.append(plant_frame(stage))
    shimmer = list(plant_frame(end))
    shimmer[0] = 1
    frames.append(tuple(shimmer))
    frames.append(plant_frame(end))
    return tuple(frames)


def growth_count(previous: int, current: int) -> int:
    start = _stage(previous)
    end = _stage(max(start, _stage(current)))
    if start == end:
        return 3
    return (end - start) + 4


class FramePlayer:
    """Play a sequence from a supplied clock. Calling play again replaces it."""

    def __init__(self) -> None:
        self.steady: tuple[int, ...] = tuple(0 for _ in range(FRAME_LENGTH))
        self._sequence: tuple[tuple[int, ...], ...] = ()
        self._started = 0
        self._playing = False

    def play(self, frames: tuple[tuple[int, ...], ...], now: int) -> None:
        if not frames:
            raise ValueError("an animation needs a frame")
        for frame in frames:
            _require_frame(frame)
        self._sequence = frames
        self._started = now
        self._playing = True

    def current(self, now: int) -> tuple[int, ...]:
        if not self._playing:
            return self.steady
        elapsed = now - self._started
        if elapsed >= FRAME_MS * len(self._sequence):
            self._playing = False
            return self.steady
        index = min(len(self._sequence) - 1, elapsed // FRAME_MS)
        return self._sequence[index]


class EventGate:
    """Ignore a generation that already played. A new generation may interrupt."""

    def __init__(self) -> None:
        self.last: int | None = None

    def accept(self, code: int, generation: int) -> bool:
        if code < EVENT_STARTUP or code > EVENT_MODE:
            return False
        if generation == self.last:
            return False
        self.last = generation
        return True


def _stage(stage: int) -> int:
    if isinstance(stage, bool) or not isinstance(stage, int):
        raise ValueError("stage must be an integer")
    if not 0 <= stage < len(PLANT_ROWS):
        raise ValueError("stage must be between 0 and 5")
    return stage


def _segments(segments: int) -> int:
    if isinstance(segments, bool) or not isinstance(segments, int):
        raise ValueError("segments must be an integer")
    if not 0 <= segments <= COLS:
        raise ValueError("segments must be between 0 and 13")
    return segments


def _require_frame(frame: tuple[int, ...]) -> None:
    if len(frame) != FRAME_LENGTH or any(pixel not in (0, 1) for pixel in frame):
        raise ValueError("a frame must be 104 pixels of 0 or 1")
