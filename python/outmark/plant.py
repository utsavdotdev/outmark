"""Plant stages derived from kept commitments.

The stage is not stored separately. It is the count of kept sessions, limited
to five. A restart rebuilds the same stage from those sessions, and a repeated
report cannot add a second kept row.
"""

from outmark.records import SessionStatus

STAGE_LABELS = (
    "Seed",
    "Split seed",
    "Sprout",
    "Two leaves",
    "Growing plant",
    "Flowering plant",
)


def plant_state(sessions) -> dict[str, int | str]:
    kept = sum(1 for session in sessions if session.status is SessionStatus.KEPT)
    stage = min(len(STAGE_LABELS) - 1, kept)
    return {"kept_sessions": kept, "stage": stage, "label": STAGE_LABELS[stage]}
