"""Activity-generation prompt text. This module does not change session state."""

from __future__ import annotations

import json

from outmark.generator_types import GenerationRequest

SYSTEM_PROMPT = "\n".join(
    (
        "You are Outmark, a practical outdoor activity generator.",
        "",
        "Generate one small, safe, realistic screen-free activity from the user's",
        "available time, preferred category, and recent history.",
        "",
        "Activities should be possible near home or in a familiar public outdoor",
        "space. They should not require equipment, money, internet access,",
        "photography, or contact with strangers.",
        "",
        "Avoid dangerous routes, trespassing, disturbing wildlife, collecting",
        "plants, or entering private property.",
        "",
        "Prefer movement, noticing the environment, a quiet break, or a meaningful",
        "interaction with someone the user already knows.",
        "",
        "Avoid repeating the user's recent activities.",
        "",
        "Return valid JSON with these fields only:",
        "title, instructions, reflection_question, category.",
        "",
        "Keep the title short and the instructions concise. Match the chosen",
        "duration. Do not claim that the user has completed the activity.",
    )
)


def user_message(request: GenerationRequest) -> str:
    """The user turn sent to the local model."""
    payload = {
        "duration_minutes": request.duration_minutes,
        "preferred_category": request.preferred_category,
        "recent_activities": list(request.recent_activities),
        "recent_reflections": list(request.recent_reflections),
    }
    return json.dumps(payload, ensure_ascii=True)
