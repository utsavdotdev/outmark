"""The eight matrix rows, in frame order from row 0."""

from __future__ import annotations

CATEGORIES: tuple[tuple[str, str], ...] = (
    ("walking", "Walking and movement"),
    ("nature_observation", "Nature observation"),
    ("quiet_outdoor", "Quiet outdoor time"),
    ("social", "Social connection"),
    ("outdoor_care", "Outdoor care or helping"),
    ("exploring", "Exploring a new place"),
    ("creative_observation", "Creative observation"),
    ("other", "Other offline experiences"),
)

CATEGORY_INDEX: dict[str, int] = {
    category_id: index for index, (category_id, _label) in enumerate(CATEGORIES)
}

ALLOWED_DURATIONS: frozenset[int] = frozenset({5, 10, 15})

WINDOW_DAYS = 13
