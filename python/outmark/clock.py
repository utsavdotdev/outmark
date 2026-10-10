"""Wall-clock timestamps for storage, and a monotonic clock for live elapsed time."""

from __future__ import annotations

import time
from datetime import datetime, timedelta
from typing import Protocol


class Clock(Protocol):
    """A pair of clocks. Tests supply a controllable stand-in."""

    def wall(self) -> datetime:
        """Timezone-aware local time, stored with each session."""

    def monotonic(self) -> float:
        """Seconds that move only forward inside one process."""


class SystemClock:
    """Clocks used by the running application."""

    def wall(self) -> datetime:
        return datetime.now().astimezone()

    def monotonic(self) -> float:
        return time.monotonic()


class FakeClock:
    """A clock whose wall time and monotonic time advance independently."""

    def __init__(self, wall: datetime, monotonic: float = 0.0) -> None:
        if wall.tzinfo is None:
            raise ValueError("wall clock must be timezone-aware")
        self._wall = wall
        self._monotonic = monotonic

    def wall(self) -> datetime:
        return self._wall

    def monotonic(self) -> float:
        return self._monotonic

    def set_wall(self, wall: datetime) -> None:
        if wall.tzinfo is None:
            raise ValueError("wall clock must be timezone-aware")
        self._wall = wall

    def advance(self, seconds: float, *, wall: bool = True, monotonic: bool = True) -> None:
        if seconds < 0:
            raise ValueError("seconds must be zero or greater")
        if wall:
            self._wall += timedelta(seconds=seconds)
        if monotonic:
            self._monotonic += seconds
