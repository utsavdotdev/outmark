"""Atomic JSON storage for proposals and sessions."""

from __future__ import annotations

import json
import os
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Any, TypeVar

from outmark.errors import StorageError
from outmark.records import Proposal, Session

STORE_FILENAME = "outmark.json"
DOCUMENT_VERSION = 1
_SETTING_KEYS = frozenset({"default_duration"})
_DOCUMENT_KEYS = frozenset({"version", "settings", "proposals", "sessions"})


@dataclass(frozen=True)
class Document:
    default_duration: int
    proposals: tuple[Proposal, ...]
    sessions: tuple[Session, ...]

    def to_dict(self) -> dict[str, Any]:
        return {
            "version": DOCUMENT_VERSION,
            "settings": {"default_duration": self.default_duration},
            "proposals": [proposal.to_dict() for proposal in self.proposals],
            "sessions": [session.to_dict() for session in self.sessions],
        }


def empty_document() -> Document:
    return Document(default_duration=10, proposals=(), sessions=())


class JsonStore:
    """Load and replace one JSON file. A failed load does not write."""

    def __init__(self, path: Path) -> None:
        self.path = path

    def load(self) -> Document:
        if not self.path.exists():
            return empty_document()
        try:
            raw = json.loads(self.path.read_text(encoding="utf-8"))
        except (OSError, UnicodeError, json.JSONDecodeError) as exc:
            raise StorageError("activity history could not be read") from exc
        return _document(raw)

    def save(self, document: Document) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        payload = json.dumps(document.to_dict(), indent=2, sort_keys=True) + "\n"
        temporary = self.path.with_name(self.path.name + ".tmp")
        try:
            with temporary.open("w", encoding="utf-8") as handle:
                handle.write(payload)
                handle.flush()
                os.fsync(handle.fileno())
            os.replace(temporary, self.path)
        except OSError as exc:
            raise StorageError("activity history could not be saved") from exc


def _document(raw: object) -> Document:
    if not isinstance(raw, dict):
        raise StorageError("activity history must be a JSON object")
    if set(raw) != _DOCUMENT_KEYS:
        raise StorageError("activity history has missing or unexpected fields")
    if raw.get("version") != DOCUMENT_VERSION:
        raise StorageError("activity history version is not supported")
    settings = raw.get("settings")
    if not isinstance(settings, dict) or set(settings) != _SETTING_KEYS:
        raise StorageError("settings are missing or unexpected")
    default_duration = settings.get("default_duration")
    if isinstance(default_duration, bool) or default_duration not in (5, 10, 15):
        raise StorageError("default_duration must be 5, 10, or 15")
    proposals = _list(raw.get("proposals"), "proposals", Proposal.from_dict)
    sessions = _list(raw.get("sessions"), "sessions", Session.from_dict)
    _unique([item.id for item in proposals], "proposal id")
    _unique([item.id for item in sessions], "session id")
    active = [session for session in sessions if session.status.value == "active"]
    if len(active) > 1:
        raise StorageError("more than one session is active")
    open_proposals = [item for item in proposals if item.status.value == "proposed"]
    if len(open_proposals) > 1:
        raise StorageError("more than one proposal is open")
    return Document(
        default_duration=int(default_duration),
        proposals=tuple(proposals),
        sessions=tuple(sessions),
    )


_ItemT = TypeVar("_ItemT")


def _list(raw: object, field: str, parse: Callable[[object], _ItemT]) -> list[_ItemT]:
    if not isinstance(raw, list):
        raise StorageError(f"{field} must be a list")
    return [parse(item) for item in raw]


def _unique(values: list[str], label: str) -> None:
    if len(values) != len(set(values)):
        raise StorageError(f"duplicate {label}")
