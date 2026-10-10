"""Input checks for activities and completion reports."""

from __future__ import annotations

from typing import Literal

from outmark.categories import ALLOWED_DURATIONS, CATEGORY_INDEX
from outmark.errors import ValidationError

TITLE_LIMIT = 80
INSTRUCTIONS_LIMIT = 400
QUESTION_LIMIT = 200
REFLECTION_LIMIT = 280
Outcome = Literal["kept", "not_kept"]


def require_duration(value: object) -> int:
    if isinstance(value, bool) or value not in ALLOWED_DURATIONS:
        raise ValidationError("duration_minutes must be 5, 10, or 15")
    return int(value)


def require_category(value: object) -> str:
    if not isinstance(value, str) or value not in CATEGORY_INDEX:
        raise ValidationError("category must be one of the eight activity categories")
    return value


def require_text(value: object, field: str, limit: int) -> str:
    text = _stripped(value, field)
    if text is None or text == "":
        raise ValidationError(f"{field} is required")
    _reject_control_chars(text, field)
    if len(text) > limit:
        raise ValidationError(f"{field} must be at most {limit} characters")
    return text


def optional_text(value: object, field: str, limit: int) -> str | None:
    if value is None:
        return None
    text = _stripped(value, field)
    if text is None:
        raise ValidationError(f"{field} must be a string")
    if text == "":
        return None
    _reject_control_chars(text, field)
    if len(text) > limit:
        raise ValidationError(f"{field} must be at most {limit} characters")
    return text


def require_outcome(value: object) -> Outcome:
    if value == "kept":
        return "kept"
    if value == "not_kept":
        return "not_kept"
    raise ValidationError("outcome must be kept or not_kept")


def _stripped(value: object, field: str) -> str | None:
    if value is None:
        return None
    if not isinstance(value, str):
        raise ValidationError(f"{field} must be a string")
    return value.strip()


def _reject_control_chars(text: str, field: str) -> None:
    if any(ord(char) < 32 for char in text):
        raise ValidationError(f"{field} must be a single line of text")
