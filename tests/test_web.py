"""Webpage workflow. Display checks use an in-memory stand-in, not the board."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from pathlib import Path

from outmark.app import create_app
from outmark.clock import FakeClock
from outmark.config import Settings
from outmark.display import (
    MODE_ACTIVE,
    MODE_DONE,
    MODE_GRID,
    MODE_PENDING,
    MODE_REST,
    RecordingDisplay,
)
from outmark.generator_types import GenerationResult
from outmark.records import ActivityDraft

ZONE = timezone(timedelta(hours=5, minutes=45))
START = datetime(2026, 10, 10, 12, 0, tzinfo=ZONE)


def test_home_page_offers_the_commitment_flow(tmp_path: Path) -> None:
    client = create_app(_settings(tmp_path)).test_client()
    page = client.get("/").get_data(as_text=True)
    script = client.get("/static/app.js").get_data(as_text=True)

    assert "Suggest an activity" in page
    assert "Accept and start" in page
    assert "Another suggestion" in page
    assert "I kept it" in page
    assert "I did not keep it" in page
    assert "Reflection" in page
    assert "History" in page
    assert "Writing a suggestion" in script
    assert "The local model did not answer" in script
    assert "No model file is installed" in script
    assert "The local service did not respond." in script


def test_quest_shows_one_proposal_and_leaves_the_matrix_idle(tmp_path: Path) -> None:
    display = RecordingDisplay()
    source = _Source([_draft()])
    client = _client(tmp_path, display, source)

    response = client.post("/api/quest", json={"duration_minutes": 10, "category": "walking"})

    assert response.status_code == 200
    body = response.get_json()
    assert body["phase"] == "proposed"
    assert body["source"] == "model"
    assert body["model_present"] is False
    assert body["proposal"]["title"] == "Walk the block"
    assert body["proposal"]["duration_minutes"] == 10
    assert body["session"] is None
    assert len(source.calls) == 1
    assert _mode(display) == MODE_REST
    assert client.get("/api/session").get_json()["phase"] == "proposed"


def test_a_second_quest_is_refused_until_the_first_is_rejected(tmp_path: Path) -> None:
    display = RecordingDisplay()
    source = _Source([_draft(), _draft(title="Sit and listen")])
    client = _client(tmp_path, display, source)
    client.post("/api/quest", json={"duration_minutes": 10, "category": "walking"})

    refused = client.post("/api/quest", json={"duration_minutes": 5, "category": "quiet_outdoor"})

    assert refused.status_code == 409
    assert len(source.calls) == 1
    assert _mode(display) == MODE_REST
    proposal_id = client.get("/api/session").get_json()["proposal"]["id"]
    rejected = client.post("/api/proposal/reject", json={"id": proposal_id})
    assert rejected.status_code == 200
    assert rejected.get_json()["phase"] == "idle"
    assert rejected.get_json()["session"] is None

    again = client.post("/api/quest", json={"duration_minutes": 5, "category": "quiet_outdoor"})
    assert again.status_code == 200
    assert again.get_json()["proposal"]["title"] == "Sit and listen"
    assert again.get_json()["proposal"]["duration_minutes"] == 5
    assert _mode(display) == MODE_REST


def test_accept_starts_the_timer_and_a_reload_follows_it(tmp_path: Path) -> None:
    clock = FakeClock(START)
    display = RecordingDisplay()
    client = _client(tmp_path, display, _Source([_draft()]), clock)
    proposal_id = _propose(client)

    started = client.post("/api/session/start", json={"proposal_id": proposal_id})

    assert started.status_code == 200
    assert started.get_json()["phase"] == "active"
    assert started.get_json()["session"]["status"] == "active"
    assert started.get_json()["session"]["elapsed_seconds"] == 0
    assert started.get_json()["session"]["deadline_passed"] is False
    assert _mode(display) == MODE_PENDING

    clock.advance(60)
    running = client.get("/api/session")
    assert running.get_json()["session"]["elapsed_seconds"] == 60
    assert running.get_json()["session"]["progress_segments"] == 1
    assert running.get_json()["session"]["status"] == "active"
    assert _mode(display) == MODE_ACTIVE

    restored = create_app(
        _settings(tmp_path),
        display=RecordingDisplay(),
        clock=FakeClock(START + timedelta(minutes=4)),
        source=_Source([]),
    ).test_client()
    restored_body = restored.get("/api/session").get_json()
    assert restored_body["phase"] == "active"
    assert restored_body["session"]["elapsed_seconds"] == 240
    assert restored_body["session"]["deadline_passed"] is False


def test_deadline_asks_for_a_report_and_does_not_mark_kept(tmp_path: Path) -> None:
    clock = FakeClock(START)
    display = RecordingDisplay()
    client = _client(tmp_path, display, _Source([_draft()]), clock)
    client.post("/api/session/start", json={"proposal_id": _propose(client)})
    clock.advance(600)

    body = client.get("/api/session").get_json()

    assert body["session"]["status"] == "active"
    assert body["session"]["deadline_passed"] is True
    assert _mode(display) == MODE_DONE


def test_kept_report_lights_a_cell_and_shows_the_reflection(tmp_path: Path) -> None:
    display = RecordingDisplay()
    client = _client(tmp_path, display, _Source([_draft()]))
    session_id = _start(client)

    reported = client.post(
        "/api/session/report",
        json={"session_id": session_id, "outcome": "kept", "reflection": "A sparrow on the wall."},
    )

    assert reported.status_code == 200
    assert reported.get_json()["phase"] == "idle"
    assert _mode(display) == MODE_GRID
    history = client.get("/api/history").get_json()
    assert history["end_date"] == "2026-10-10"
    assert history["rows"][0]["cells"][12] is True
    assert history["sessions"][0]["reflection"] == "A sparrow on the wall."
    assert history["sessions"][0]["status"] == "kept"


def test_not_kept_is_listed_and_does_not_light_a_cell(tmp_path: Path) -> None:
    display = RecordingDisplay()
    client = _client(tmp_path, display, _Source([_draft()]))
    session_id = _start(client)

    reported = client.post(
        "/api/session/report",
        json={"session_id": session_id, "outcome": "not_kept", "reflection": None},
    )

    assert reported.status_code == 200
    assert _mode(display) == MODE_REST
    history = client.get("/api/history").get_json()
    assert all(cell is False for row in history["rows"] for cell in row["cells"])
    assert history["sessions"][0]["status"] == "not_kept"


def test_invalid_input_does_not_store_a_session(tmp_path: Path) -> None:
    display = RecordingDisplay()
    source = _Source([_draft()])
    client = _client(tmp_path, display, source)

    before = len(display.calls)
    response = client.post("/api/quest", json={"duration_minutes": 7, "category": "walking"})

    assert response.status_code == 400
    assert source.calls == []
    assert len(display.calls) == before
    assert not (tmp_path / "data" / "outmark.json").exists()


def test_a_failed_matrix_update_keeps_the_accepted_session(tmp_path: Path) -> None:
    client = _client(tmp_path, _BrokenDisplay(), _Source([_draft()]))

    started = client.post("/api/session/start", json={"proposal_id": _propose(client)})

    assert started.status_code == 200
    assert started.get_json()["session"]["status"] == "active"
    assert client.get("/api/session").get_json()["phase"] == "active"


def test_a_corrupt_store_is_not_rewritten(tmp_path: Path) -> None:
    path = tmp_path / "data" / "outmark.json"
    path.parent.mkdir()
    path.write_text("{not json", encoding="utf-8")
    client = create_app(_settings(tmp_path), display=RecordingDisplay()).test_client()

    response = client.get("/api/session")

    assert response.status_code == 503
    assert path.read_text(encoding="utf-8") == "{not json"
    refused = client.post("/api/quest", json={"duration_minutes": 10, "category": "walking"})
    assert refused.status_code == 503


def test_catalog_source_is_reported_when_the_model_is_absent(tmp_path: Path) -> None:
    source = _Source([_draft()], source="fallback")
    client = _client(tmp_path, RecordingDisplay(), source)

    response = client.post("/api/quest", json={"duration_minutes": 10, "category": "walking"})
    body = response.get_json()

    assert body["source"] == "fallback"
    assert body["model_present"] is False
    assert body["proposal"]["title"] == "Walk the block"


def _client(tmp_path: Path, display: object, source: _Source, clock: FakeClock | None = None):
    app = create_app(
        _settings(tmp_path),
        display=display,  # type: ignore[arg-type]
        clock=clock or FakeClock(START),
        source=source,
    )
    return app.test_client()


def _propose(client) -> str:
    response = client.post("/api/quest", json={"duration_minutes": 10, "category": "walking"})
    return response.get_json()["proposal"]["id"]


def _start(client) -> str:
    started = client.post("/api/session/start", json={"proposal_id": _propose(client)})
    return started.get_json()["session"]["id"]


def _settings(tmp_path: Path) -> Settings:
    return Settings(
        host="127.0.0.1",
        port=8080,
        data_dir=tmp_path / "data",
        model_dir=tmp_path / "models",
        log_level="INFO",
    )


def _draft(**overrides: object) -> ActivityDraft:
    values: dict[str, object] = {
        "duration_minutes": 10,
        "category": "walking",
        "title": "Walk the block",
        "instructions": "Walk a familiar block and notice three doorways.",
        "reflection_question": "Which doorway had you stopped seeing?",
    }
    values.update(overrides)
    return ActivityDraft(
        duration_minutes=10,
        category=str(values["category"]),
        title=str(values["title"]),
        instructions=str(values["instructions"]),
        reflection_question=str(values["reflection_question"]),
    )


def _mode(display: RecordingDisplay) -> int:
    return next(call[1] for call in reversed(display.calls) if call[0] == "set_mode")  # type: ignore[return-value]


class _Source:
    def __init__(self, drafts: list[ActivityDraft], source: str = "model") -> None:
        self._drafts = drafts
        self.calls: list[object] = []
        self._source = source

    def generate(self, request: object) -> GenerationResult:
        self.calls.append(request)
        return GenerationResult(activity=self._drafts.pop(0), source=self._source)  # type: ignore[arg-type]


class _BrokenDisplay:
    def set_mode(self, mode: int) -> None:
        raise RuntimeError("bridge down")

    def set_progress(self, segments: int) -> None:
        raise RuntimeError("bridge down")

    def set_grid_row(self, row: int, mask: int) -> None:
        raise RuntimeError("bridge down")
