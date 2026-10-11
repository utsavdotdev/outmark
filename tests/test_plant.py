"""Plant growth follows kept sessions and nothing else."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from outmark.app import create_app
from outmark.clock import FakeClock
from outmark.config import Settings
from outmark.display import RecordingDisplay
from outmark.engine import SessionEngine
from outmark.errors import TransitionError
from outmark.generator_types import GenerationResult
from outmark.plant import STAGE_LABELS, plant_state
from outmark.records import ActivityDraft, CompletionReport
from outmark.storage import JsonStore

ZONE = timezone(timedelta(hours=5, minutes=45))
START = datetime(2026, 10, 10, 12, 0, tzinfo=ZONE)


def test_an_empty_history_is_a_seed(tmp_path: Path) -> None:
    engine, _, _ = _engine(tmp_path)

    assert plant_state(engine.sessions()) == {
        "kept_sessions": 0,
        "stage": 0,
        "label": "Seed",
    }


def test_rejecting_or_starting_does_not_grow_the_plant(tmp_path: Path) -> None:
    engine, clock, _ = _engine(tmp_path)
    rejected = engine.propose(_draft(title="Left behind"))
    engine.reject(rejected.id)

    proposal = engine.propose(_draft())
    engine.accept(proposal.id)
    clock.advance(10 * 60)

    assert plant_state(engine.sessions())["stage"] == 0
    assert engine.active_session() is not None
    assert engine.active_session().deadline_passed is True


def test_not_kept_does_not_grow_or_remove_an_earlier_stage(tmp_path: Path) -> None:
    engine, clock, _ = _engine(tmp_path)
    _close(engine, clock, "kept", "First")
    assert plant_state(engine.sessions())["stage"] == 1

    _close(engine, clock, "not_kept", None)

    state = plant_state(engine.sessions())
    assert state["kept_sessions"] == 1
    assert state["stage"] == 1


def test_a_kept_report_grows_one_stage_and_a_repeat_does_not(tmp_path: Path) -> None:
    engine, clock, path = _engine(tmp_path)
    proposal = engine.propose(_draft())
    session = engine.accept(proposal.id)
    clock.advance(session.duration_minutes * 60 - 1)
    with pytest.raises(TransitionError):
        engine.report(session.id, CompletionReport("kept", None))
    assert plant_state(engine.sessions())["stage"] == 0

    clock.advance(1)
    engine.report(session.id, CompletionReport("kept", "A sparrow."))
    with pytest.raises(TransitionError):
        engine.report(session.id, CompletionReport("kept", "A sparrow."))

    assert plant_state(engine.sessions()) == {
        "kept_sessions": 1,
        "stage": 1,
        "label": "Split seed",
    }
    restored = SessionEngine(JsonStore(path), FakeClock(clock.wall()))
    assert plant_state(restored.sessions())["stage"] == 1


def test_later_kept_sessions_stop_at_the_flower(tmp_path: Path) -> None:
    engine, clock, _ = _engine(tmp_path)
    for index in range(6):
        _close(engine, clock, "kept", None, title=f"Walk {index}")

    state = plant_state(engine.sessions())
    assert state["kept_sessions"] == 6
    assert state["stage"] == len(STAGE_LABELS) - 1
    assert state["label"] == "Flowering plant"


def test_the_page_and_history_share_the_kept_stage(tmp_path: Path) -> None:
    clock = FakeClock(START)
    client = create_app(
        _settings(tmp_path),
        display=RecordingDisplay(),
        clock=clock,
        source=_Source([_draft(), _draft(title="Second walk")]),
    ).test_client()
    page = client.get("/").get_data(as_text=True)
    assert 'id="plant-drawing"' in page
    assert client.get("/api/session").get_json()["plant"]["stage"] == 0

    proposed = client.post("/api/quest", json={"duration_minutes": 5, "category": "walking"})
    started = client.post(
        "/api/session/start",
        json={"proposal_id": proposed.get_json()["proposal"]["id"]},
    )
    session_id = started.get_json()["session"]["id"]
    clock.advance(5 * 60)
    reported = client.post(
        "/api/session/report",
        json={"session_id": session_id, "outcome": "kept", "reflection": "Quiet street."},
    )

    assert reported.get_json()["plant"]["stage"] == 1
    assert client.get("/api/history").get_json()["plant"]["stage"] == 1
    assert client.get("/api/session").get_json()["plant"]["label"] == "Split seed"


def _engine(tmp_path: Path) -> tuple[SessionEngine, FakeClock, Path]:
    path = tmp_path / "outmark.json"
    clock = FakeClock(START)
    return SessionEngine(JsonStore(path), clock), clock, path


def _close(
    engine: SessionEngine,
    clock: FakeClock,
    outcome: str,
    reflection: str | None,
    title: str = "Walk the block",
) -> None:
    proposal = engine.propose(_draft(title=title))
    session = engine.accept(proposal.id)
    clock.advance(session.duration_minutes * 60)
    engine.report(session.id, CompletionReport(outcome, reflection))  # type: ignore[arg-type]


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
        duration_minutes=int(values["duration_minutes"]),  # type: ignore[arg-type]
        category=str(values["category"]),
        title=str(values["title"]),
        instructions=str(values["instructions"]),
        reflection_question=str(values["reflection_question"]),
    )


def _settings(tmp_path: Path) -> Settings:
    return Settings(
        host="127.0.0.1",
        port=8765,
        data_dir=tmp_path / "data",
        model_dir=tmp_path / "models",
        log_level="INFO",
    )


class _Source:
    def __init__(self, drafts: list[ActivityDraft]) -> None:
        self._drafts = drafts

    def generate(self, request: object) -> GenerationResult:
        return GenerationResult(activity=self._drafts.pop(0), source="model")
