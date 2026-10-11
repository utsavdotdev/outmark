"""Offline and restart checks. The display stand-in is not a lit LED."""

from __future__ import annotations

import socket
from datetime import datetime, timedelta, timezone
from pathlib import Path

from outmark.app import create_app
from outmark.clock import FakeClock
from outmark.config import Settings
from outmark.display import MODE_DONE, MODE_GRID, MODE_REST, RecordingDisplay
from outmark.generator import LlamaServerSource
from outmark.records import SessionStatus
from outmark.storage import JsonStore

ZONE = timezone(timedelta(hours=5, minutes=45))
START = datetime(2026, 10, 10, 12, 0, tzinfo=ZONE)


def test_inference_failure_uses_the_catalog_and_reject_starts_no_timer(tmp_path: Path) -> None:
    display = RecordingDisplay()
    source = LlamaServerSource(
        chat_url=f"http://127.0.0.1:{_closed_port()}/v1/chat/completions",
        timeout=1,
    )
    client = _client(tmp_path, display, source, FakeClock(START))

    suggested = client.post("/api/quest", json={"duration_minutes": 10, "category": "walking"})

    assert suggested.status_code == 200
    assert suggested.get_json()["source"] == "fallback"
    assert suggested.get_json()["proposal"]["title"] == "Walk a familiar block"
    assert suggested.get_json()["session"] is None
    assert _mode(display) == MODE_REST
    proposal_id = suggested.get_json()["proposal"]["id"]

    rejected = client.post("/api/proposal/reject", json={"id": proposal_id})

    assert rejected.status_code == 200
    assert rejected.get_json()["phase"] == "idle"
    stored = _store(tmp_path).load()
    assert stored.sessions == ()
    assert stored.proposals[0].status.value == "rejected"
    assert _mode(display) == MODE_REST


def test_malformed_model_output_uses_the_catalog(tmp_path: Path) -> None:
    client = _client(tmp_path, RecordingDisplay(), _source(_Garbage()), FakeClock(START))

    response = client.post("/api/quest", json={"duration_minutes": 5, "category": "walking"})

    assert response.status_code == 200
    body = response.get_json()
    assert body["source"] == "fallback"
    assert body["proposal"]["title"] == "Walk a familiar block"
    assert body["proposal"]["duration_minutes"] == 5
    assert "not json" not in body["proposal"]["instructions"]


def test_a_public_model_url_is_not_contacted(tmp_path: Path) -> None:
    client_double = _Counting()
    source = LlamaServerSource("https://api.openai.com/v1/chat/completions", client=client_double)
    client = _client(tmp_path, RecordingDisplay(), source, FakeClock(START))

    response = client.post("/api/quest", json={"duration_minutes": 10, "category": "quiet_outdoor"})

    assert response.status_code == 200
    assert client_double.calls == 0
    assert response.get_json()["source"] == "fallback"
    assert response.get_json()["proposal"]["title"] == "Sit and listen"


def test_restart_after_the_deadline_does_not_mark_the_session_kept(tmp_path: Path) -> None:
    client = _client(tmp_path, RecordingDisplay(), _source(_Garbage()), FakeClock(START))
    started = client.post("/api/session/start", json={"proposal_id": _propose(client)})
    assert started.get_json()["session"]["status"] == "active"
    before = (tmp_path / "data" / "outmark.json").read_text(encoding="utf-8")

    display = RecordingDisplay()
    restored = create_app(
        _settings(tmp_path),
        display=display,
        clock=FakeClock(START + timedelta(minutes=11)),
        source=_source(_Garbage()),
    ).test_client()
    body = restored.get("/api/session").get_json()

    assert body["phase"] == "awaiting_report"
    assert body["session"]["status"] == "active"
    assert body["session"]["deadline_passed"] is True
    assert (tmp_path / "data" / "outmark.json").read_text(encoding="utf-8") == before
    assert _mode(display) == MODE_DONE
    assert _store(tmp_path).load().sessions[0].status is SessionStatus.ACTIVE


def test_the_window_rolls_forward_without_deleting_the_session(tmp_path: Path) -> None:
    clock = FakeClock(START)
    client = _client(tmp_path, RecordingDisplay(), _source(_Garbage()), clock)
    started = client.post("/api/session/start", json={"proposal_id": _propose(client)})
    clock.advance(600)
    reported = client.post(
        "/api/session/report",
        json={
            "session_id": started.get_json()["session"]["id"],
            "outcome": "kept",
            "reflection": "A gate.",
        },
    )
    assert reported.status_code == 200

    display = RecordingDisplay()
    later = create_app(
        _settings(tmp_path),
        display=display,
        clock=FakeClock(START + timedelta(days=14)),
        source=_source(_Garbage()),
    ).test_client()
    history = later.get("/api/history").get_json()

    assert history["end_date"] == "2026-10-24"
    assert history["sessions"] == []
    assert all(cell is False for row in history["rows"] for cell in row["cells"])
    assert _mode(display) == MODE_REST
    stored = _store(tmp_path).load()
    assert len(stored.sessions) == 1
    assert stored.sessions[0].status is SessionStatus.KEPT
    assert stored.sessions[0].reflection == "A gate."


def test_a_failed_display_update_during_report_keeps_the_file(tmp_path: Path) -> None:
    clock = FakeClock(START)
    client = _client(tmp_path, _BrokenDisplay(), _source(_Garbage()), clock)
    started = client.post("/api/session/start", json={"proposal_id": _propose(client)})
    clock.advance(600)
    reported = client.post(
        "/api/session/report",
        json={
            "session_id": started.get_json()["session"]["id"],
            "outcome": "kept",
            "reflection": "Still on disk.",
        },
    )

    assert reported.status_code == 200
    stored = _store(tmp_path).load()
    assert stored.sessions[0].status is SessionStatus.KEPT
    assert stored.sessions[0].reflection == "Still on disk."

    display = RecordingDisplay()
    create_app(
        _settings(tmp_path),
        display=display,
        clock=FakeClock(START),
        source=_source(_Garbage()),
    )
    assert _mode(display) == MODE_GRID


def _client(tmp_path: Path, display: object, source: LlamaServerSource, clock: FakeClock):
    app = create_app(
        _settings(tmp_path),
        display=display,  # type: ignore[arg-type]
        clock=clock,
        source=source,
    )
    return app.test_client()


def _propose(client) -> str:
    response = client.post("/api/quest", json={"duration_minutes": 10, "category": "walking"})
    return response.get_json()["proposal"]["id"]


def _settings(tmp_path: Path) -> Settings:
    return Settings(
        host="127.0.0.1",
        port=8080,
        data_dir=tmp_path / "data",
        model_dir=tmp_path / "models",
        log_level="INFO",
    )


def _store(tmp_path: Path) -> JsonStore:
    return JsonStore(tmp_path / "data" / "outmark.json")


def _source(client: _Garbage) -> LlamaServerSource:
    return LlamaServerSource(client=client, timeout=1)


def _closed_port() -> int:
    probe = socket.socket()
    probe.bind(("127.0.0.1", 0))
    port = probe.getsockname()[1]
    probe.close()
    return port


def _mode(display: RecordingDisplay) -> int:
    return next(call[1] for call in reversed(display.calls) if call[0] == "set_mode")  # type: ignore[return-value]


class _Garbage:
    def complete(self, url: str, payload: dict[str, object], timeout: float) -> str:
        return "not json"


class _Counting:
    def __init__(self) -> None:
        self.calls = 0

    def complete(self, url: str, payload: dict[str, object], timeout: float) -> str:
        self.calls += 1
        return "should not be sent"


class _BrokenDisplay:
    def set_mode(self, mode: int) -> None:
        raise RuntimeError("bridge down")

    def set_progress(self, segments: int) -> None:
        raise RuntimeError("bridge down")

    def set_grid_row(self, row: int, mask: int) -> None:
        raise RuntimeError("bridge down")
