"""Deterministic activities used when local inference fails."""

from __future__ import annotations

from dataclasses import dataclass

from outmark.records import ActivityDraft


@dataclass(frozen=True)
class _Template:
    title: str
    instructions: str
    reflection_question: str

    def draft(self, duration_minutes: int, category: str) -> ActivityDraft:
        text = self.instructions.format(minutes=duration_minutes)
        return ActivityDraft(
            duration_minutes=duration_minutes,
            category=category,
            title=self.title,
            instructions=text,
            reflection_question=self.reflection_question,
        )


def _pair(first: _Template, second: _Template) -> tuple[_Template, _Template]:
    return (first, second)


CATALOG: dict[str, tuple[_Template, _Template]] = {
    "walking": _pair(
        _Template(
            "Walk a familiar block",
            "Spend {minutes} minutes on a known route. Notice three things at eye level.",
            "Which of the three things had you stopped seeing?",
        ),
        _Template(
            "Feel the ground change",
            "Walk for {minutes} minutes near home. Notice three changes under your feet.",
            "Where did the ground change?",
        ),
    ),
    "nature_observation": _pair(
        _Template(
            "Notice three leaves",
            "Spend {minutes} minutes outside and find three leaf shapes. Do not pick any.",
            "Which shape had you never looked at closely?",
        ),
        _Template(
            "Watch one patch of sky",
            "Stay outside for {minutes} minutes and watch one patch of sky. Count three changes.",
            "What changed while you were looking?",
        ),
    ),
    "quiet_outdoor": _pair(
        _Template(
            "Sit and listen",
            "Sit outside for {minutes} minutes without a screen. Name three sounds.",
            "Which sound was farthest away?",
        ),
        _Template(
            "Feel the air",
            "Stand outside for {minutes} minutes. Name three sensations of the air.",
            "What did the air feel like?",
        ),
    ),
    "social": _pair(
        _Template(
            "Step outside together",
            "Spend {minutes} minutes outside with someone you know. Ask what they hear.",
            "What did they notice that you missed?",
        ),
        _Template(
            "Share one thing you see",
            "Walk for {minutes} minutes with someone you know. Each point out one detail.",
            "What detail did they choose?",
        ),
    ),
    "outdoor_care": _pair(
        _Template(
            "Check one plant",
            "Spend {minutes} minutes with one plant at home. Do not pick it. Notice the soil.",
            "Did the plant look dry, or recently watered?",
        ),
        _Template(
            "Clear three pieces of litter",
            "Spend {minutes} minutes binning three pieces of litter in a public place you may use.",
            "Where did you find them?",
        ),
    ),
    "exploring": _pair(
        _Template(
            "Use a different corner",
            "Walk for {minutes} minutes to a public corner you rarely use, then return.",
            "What was different on that corner?",
        ),
        _Template(
            "Follow a side path",
            "For {minutes} minutes, take one public side path, and turn back if unsure.",
            "What made you choose that path?",
        ),
    ),
    "creative_observation": _pair(
        _Template(
            "Find three repeated shapes",
            "Spend {minutes} minutes outside finding one shape three times. Collect nothing.",
            "Where did the shape repeat?",
        ),
        _Template(
            "Trace a shadow",
            "For {minutes} minutes, follow one shadow and notice three edges it crosses.",
            "Which edge was sharpest?",
        ),
    ),
    "other": _pair(
        _Template(
            "Leave the screen at the door",
            "Spend {minutes} minutes outside the door. Name three things you can see.",
            "What was closest to the door?",
        ),
        _Template(
            "Carry nothing extra",
            "Step outside for {minutes} minutes with empty hands. Notice three details.",
            "What did you leave unphotographed?",
        ),
    ),
}


def choose_fallback(
    duration_minutes: int,
    category: str,
    recent_activities: tuple[str, ...],
) -> ActivityDraft:
    """Pick the next catalog activity whose title is not already in the recent list."""
    options = CATALOG[category]
    used = {item.casefold() for item in recent_activities}
    for option in options:
        if option.title.casefold() not in used:
            return option.draft(duration_minutes, category)
    index = len(recent_activities) % len(options)
    return options[index].draft(duration_minutes, category)
