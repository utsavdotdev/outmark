"""Values passed into an activity generator. The model never builds these itself."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

from outmark.records import ActivityDraft


@dataclass(frozen=True)
class GenerationRequest:
    duration_minutes: int
    preferred_category: str
    recent_activities: tuple[str, ...] = ()
    recent_reflections: tuple[str, ...] = ()


@dataclass(frozen=True)
class GenerationResult:
    activity: ActivityDraft
    source: Literal["model", "fallback"]
