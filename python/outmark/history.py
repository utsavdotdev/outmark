"""The rolling 13-day grid. Only kept sessions light a cell."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, timedelta

from outmark.categories import CATEGORIES, CATEGORY_INDEX, WINDOW_DAYS
from outmark.records import Session, SessionStatus


@dataclass(frozen=True)
class HistoryGrid:
    """Eight category rows and thirteen day columns. Column 0 is the oldest day."""

    start_date: date
    end_date: date
    cells: tuple[tuple[bool, ...], ...]

    def row_mask(self, row: int) -> int:
        if not 0 <= row < len(self.cells):
            raise ValueError("row must be between 0 and 7")
        mask = 0
        for column, lit in enumerate(self.cells[row]):
            if lit:
                mask |= 1 << column
        return mask


def build_grid(sessions: tuple[Session, ...] | list[Session], today: date) -> HistoryGrid:
    """Collapse kept sessions into the window that ends on `today`."""
    start = today - timedelta(days=WINDOW_DAYS - 1)
    rows = [[False] * WINDOW_DAYS for _ in CATEGORIES]
    for session in sessions:
        if session.status is not SessionStatus.KEPT:
            continue
        column = (session.started_at.date() - start).days
        if not 0 <= column < WINDOW_DAYS:
            continue
        rows[CATEGORY_INDEX[session.category]][column] = True
    return HistoryGrid(
        start_date=start,
        end_date=today,
        cells=tuple(tuple(row) for row in rows),
    )
