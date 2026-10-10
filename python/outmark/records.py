"""Stored proposals, sessions, and completion reports."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum
from typing import Any, TypeVar

from outmark.errors import StorageError
from outmark.validation import Outcome


class ProposalStatus(StrEnum):
    PROPOSED = "proposed"
    REJECTED = "rejected"
    ACCEPTED = "accepted"


class SessionStatus(StrEnum):
    ACTIVE = "active"
    KEPT = "kept"
    NOT_KEPT = "not_kept"


@dataclass(frozen=True)
class ActivityDraft:
    """A validated activity waiting to become a proposal. The model does not build this."""

    duration_minutes: int
    category: str
    title: str
    instructions: str
    reflection_question: str


@dataclass(frozen=True)
class CompletionReport:
    """An explicit user report. Timer expiry never creates one of these."""

    outcome: Outcome
    reflection: str | None = None


@dataclass(frozen=True)
class Proposal:
    id: str
    created_at: datetime
    duration_minutes: int
    category: str
    title: str
    instructions: str
    reflection_question: str
    status: ProposalStatus

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "created_at": _dump_dt(self.created_at),
            "duration_minutes": self.duration_minutes,
            "category": self.category,
            "title": self.title,
            "instructions": self.instructions,
            "reflection_question": self.reflection_question,
            "status": self.status.value,
        }

    @classmethod
    def from_dict(cls, raw: object) -> Proposal:
        data = _object(
            raw,
            "proposal",
            {
                "id",
                "created_at",
                "duration_minutes",
                "category",
                "title",
                "instructions",
                "reflection_question",
                "status",
            },
        )
        return cls(
            id=_id(data, "proposal"),
            created_at=_load_dt(data.get("created_at"), "proposal.created_at"),
            duration_minutes=_stored_duration(data.get("duration_minutes")),
            category=_stored_category(data.get("category")),
            title=_stored_text(data.get("title"), "proposal.title"),
            instructions=_stored_text(data.get("instructions"), "proposal.instructions"),
            reflection_question=_stored_text(
                data.get("reflection_question"), "proposal.reflection_question"
            ),
            status=_enum(ProposalStatus, data.get("status"), "proposal.status"),
        )


@dataclass(frozen=True)
class Session:
    id: str
    proposal_id: str
    started_at: datetime
    duration_minutes: int
    category: str
    title: str
    quest: str
    reflection_question: str
    status: SessionStatus
    reflection: str | None
    reported_at: datetime | None

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "proposal_id": self.proposal_id,
            "started_at": _dump_dt(self.started_at),
            "duration_minutes": self.duration_minutes,
            "category": self.category,
            "title": self.title,
            "quest": self.quest,
            "reflection_question": self.reflection_question,
            "status": self.status.value,
            "reflection": self.reflection,
            "reported_at": None if self.reported_at is None else _dump_dt(self.reported_at),
        }

    @classmethod
    def from_dict(cls, raw: object) -> Session:
        data = _object(
            raw,
            "session",
            {
                "id",
                "proposal_id",
                "started_at",
                "duration_minutes",
                "category",
                "title",
                "quest",
                "reflection_question",
                "status",
                "reflection",
                "reported_at",
            },
        )
        status = _enum(SessionStatus, data.get("status"), "session.status")
        reported_at = data.get("reported_at")
        reflection = data.get("reflection")
        if status is SessionStatus.ACTIVE:
            if reported_at is not None or reflection is not None:
                raise StorageError("an active session cannot contain a completion report")
        elif reported_at is None:
            raise StorageError("a reported session needs reported_at")
        return cls(
            id=_id(data, "session"),
            proposal_id=_id(data, "session", key="proposal_id"),
            started_at=_load_dt(data.get("started_at"), "session.started_at"),
            duration_minutes=_stored_duration(data.get("duration_minutes")),
            category=_stored_category(data.get("category")),
            title=_stored_text(data.get("title"), "session.title"),
            quest=_stored_text(data.get("quest"), "session.quest"),
            reflection_question=_stored_text(
                data.get("reflection_question"), "session.reflection_question"
            ),
            status=status,
            reflection=_optional_stored_text(reflection, "session.reflection"),
            reported_at=(
                None if reported_at is None else _load_dt(reported_at, "session.reported_at")
            ),
        )


@dataclass(frozen=True)
class SessionSnapshot:
    """A live view. `deadline_passed` is derived and is not a stored status."""

    session: Session
    elapsed_seconds: float
    deadline_passed: bool
    progress_segments: int


def _dump_dt(value: datetime) -> str:
    return value.isoformat(timespec="seconds")


def _load_dt(value: object, field: str) -> datetime:
    if not isinstance(value, str):
        raise StorageError(f"{field} must be a string")
    try:
        parsed = datetime.fromisoformat(value)
    except ValueError as exc:
        raise StorageError(f"{field} must be an ISO 8601 timestamp") from exc
    if parsed.tzinfo is None:
        raise StorageError(f"{field} must include a timezone")
    return parsed


def _object(raw: object, label: str, keys: set[str]) -> dict[str, Any]:
    if not isinstance(raw, dict):
        raise StorageError(f"{label} must be an object")
    if set(raw) != keys:
        raise StorageError(f"{label} has missing or unexpected fields")
    return raw


def _id(data: dict[str, Any], label: str, key: str = "id") -> str:
    value = data.get(key)
    if not isinstance(value, str) or not value.strip():
        raise StorageError(f"{label}.{key} must be a non-empty string")
    return value


def _stored_duration(value: object) -> int:
    if isinstance(value, bool) or value not in (5, 10, 15):
        raise StorageError("duration_minutes must be 5, 10, or 15")
    return int(value)


def _stored_category(value: object) -> str:
    from outmark.categories import CATEGORY_INDEX

    if not isinstance(value, str) or value not in CATEGORY_INDEX:
        raise StorageError("category must be one of the eight activity categories")
    return value


def _stored_text(value: object, field: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise StorageError(f"{field} must be a non-empty string")
    return value


def _optional_stored_text(value: object, field: str) -> str | None:
    if value is None:
        return None
    if not isinstance(value, str) or not value.strip():
        raise StorageError(f"{field} must be a string or null")
    return value


_EnumT = TypeVar("_EnumT", bound=StrEnum)


def _enum(kind: type[_EnumT], value: object, field: str) -> _EnumT:
    try:
        return kind(value)
    except ValueError as exc:
        raise StorageError(f"{field} is not a known state") from exc
