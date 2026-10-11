"""Activity-generation prompt text. This module does not change session state."""

from __future__ import annotations

from outmark.categories import CATEGORIES
from outmark.generator_types import GenerationRequest

# The words that follow "Spend N minutes". The model is told to copy this,
# and the parser writes it again so a wrong duration cannot survive.
CATEGORY_TASK: dict[str, str] = {
    "walking": "walking outside near home",
    "nature_observation": "outside noticing plants, sky, or the ground",
    "quiet_outdoor": "outside in quiet, without a screen",
    "social": "outside with someone you already know",
    "outdoor_care": "on one small act of care for an outdoor place",
    "exploring": "in one public place you rarely use",
    "creative_observation": "outside looking for a repeated shape, color, or shadow",
    "other": "just outside, away from the screen",
}

# Phrases that mean the model switched to a different category.
MISFIT: dict[str, tuple[str, ...]] = {
    "walking": ("bird", "birds", "leaf", "leaves", "litter", "shadow"),
    "nature_observation": ("litter", "doorway", "doorways"),
    "quiet_outdoor": ("bird", "birds", "litter"),
    "social": ("bird", "birds", "litter", "leaf", "leaves"),
    "outdoor_care": ("bird", "birds", "doorway", "doorways"),
    "exploring": ("bird", "birds", "litter", "leaf", "leaves"),
    "creative_observation": ("bird", "birds", "litter", "doorway", "doorways"),
    "other": ("bird", "birds", "litter"),
}

SYSTEM_PROMPT = "\n".join(
    (
        "You write one short outdoor activity as JSON.",
        "Use only the duration and category the user gives you.",
        "Do not invent a different category, a different number of minutes,",
        "equipment, money, photos, or strangers.",
        "Do not say the activity is already finished.",
        "JSON keys: title, instructions, reflection_question, category.",
    )
)


def opening_line(duration_minutes: int, category: str) -> str:
    """The sentence that states the user's duration and category."""
    return f"Spend {duration_minutes} minutes {CATEGORY_TASK[category]}."


def user_message(request: GenerationRequest) -> str:
    """The user turn sent to the local model."""
    opening = opening_line(request.duration_minutes, request.preferred_category)
    lines = [
        f"Minutes: {request.duration_minutes}.",
        f"Category id: {request.preferred_category}.",
        f"Category: {_category_label(request.preferred_category)}.",
        f'The instructions must begin with exactly: "{opening}"',
        f'The category field must be exactly "{request.preferred_category}".',
        "Stay inside this category. Do not switch to a different kind of activity.",
    ]
    if request.recent_activities:
        lines.append("Do not repeat:")
        lines.extend(f"- {item}" for item in request.recent_activities)
    if request.recent_reflections:
        lines.append("Recent reflections:")
        lines.extend(f"- {item}" for item in request.recent_reflections)
    lines.append("Return JSON only.")
    return "\n".join(lines)


def _category_label(category_id: str) -> str:
    for key, label in CATEGORIES:
        if key == category_id:
            return label
    return category_id
