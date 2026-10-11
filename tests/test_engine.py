"""Acceptance, rejection, expiry, persistence, and restart recovery."""

from __future__ import annotations

from datetime import date, datetime, timedelta, timezone
from pathlib import Path

import pytest

from outmark.clock import FakeClock
from outmark.engine import SessionEngine
from outmark.errors import StorageError, TransitionError, ValidationError
from outmark.records import ActivityDraft, CompletionReport, ProposalStatus, SessionStatus
from outmark.storage import JsonStore

ZONE = timezone(timedelta(hours=5, minutes=45))
START = datetime(2026, 10, 10, 12, 0, tzinfo=ZONE)


def test_reject_does_not_start_a_timer(tmp_path: Path) -> None:
    engine, clock, path = _engine(tmp_path)
    proposal = engine.propose(_draft())

    rejected = engine.reject(proposal.id)
    clock.advance(30 * 60)

    assert rejected.status is ProposalStatus.REJECTED
    assert engine.sessions() == ()
    assert engine.active_session() is None
    assert '"sessions": []' in path.read_text(encoding="utf-8")


def test_accept_persists_an_active_session(tmp_path: Path) -> None:
    engine, _clock, path = _engine(tmp_path)
    proposal = engine.propose(_draft())

    session = engine.accept(proposal.id)

    assert session.status is SessionStatus.ACTIVE
    assert session.started_at == START
    assert session.quest == "Walk a familiar block and notice three doorways."
    assert engine.active_session() is not None
    assert engine.active_session().deadline_passed is False
    stored = path.read_text(encoding="utf-8")
    assert '"status": "active"' in stored
    assert '"started_at": "2026-10-10T12:00:00+05:45"' in stored


def test_duplicate_reject_and_accept_leave_the_file_unchanged(tmp_path: Path) -> None:
    engine, _clock, path = _engine(tmp_path)
    proposal = engine.propose(_draft())
    engine.reject(proposal.id)
    before = path.read_text(encoding="utf-8")

    with pytest.raises(TransitionError):
        engine.reject(proposal.id)
    with pytest.raises(TransitionError):
        engine.accept(proposal.id)

    assert path.read_text(encoding="utf-8") == before
    assert engine.sessions() == ()


def test_duplicate_accept_and_report_leave_the_file_unchanged(tmp_path: Path) -> None:
    engine, clock, path = _engine(tmp_path)
    proposal = engine.propose(_draft())
    session = engine.accept(proposal.id)
    before_second_accept = path.read_text(encoding="utf-8")

    with pytest.raises(TransitionError):
        engine.accept(proposal.id)
    assert path.read_text(encoding="utf-8") == before_second_accept

    clock.advance(session.duration_minutes * 60)
    engine.report(session.id, CompletionReport("kept", "A sparrow on the wall."))
    before_second_report = path.read_text(encoding="utf-8")
    with pytest.raises(TransitionError):
        engine.report(session.id, CompletionReport("not_kept"))

    assert path.read_text(encoding="utf-8") == before_second_report
    assert engine.sessions()[0].status is SessionStatus.KEPT


def test_expiry_does_not_mark_the_session_kept(tmp_path: Path) -> None:
    engine, clock, path = _engine(tmp_path)
    proposal = engine.propose(_draft(duration_minutes=10))
    engine.accept(proposal.id)
    clock.advance(11 * 60)
    before = path.read_text(encoding="utf-8")

    view = engine.active_session()

    assert view is not None
    assert view.deadline_passed is True
    assert view.progress_segments == 13
    assert view.session.status is SessionStatus.ACTIVE
    assert path.read_text(encoding="utf-8") == before
    assert engine.history().cells[0] == (False,) * 13


def test_live_elapsed_time_follows_the_monotonic_clock(tmp_path: Path) -> None:
    engine, clock, _path = _engine(tmp_path)
    engine.accept(engine.propose(_draft(duration_minutes=10)).id)
    clock.advance(300, wall=False)

    assert engine.active_session().elapsed_seconds == 300
    assert engine.active_session().progress_segments == 6

    clock.advance(3600, monotonic=False)
    assert engine.active_session().elapsed_seconds == 300


def test_restart_restores_the_active_session_from_wall_time(tmp_path: Path) -> None:
    engine, _clock, path = _engine(tmp_path)
    session = engine.accept(engine.propose(_draft(duration_minutes=10)).id)
    restored_clock = FakeClock(START + timedelta(minutes=4), monotonic=0.0)
    restored = SessionEngine(JsonStore(path), restored_clock)

    view = restored.active_session()

    assert view is not None
    assert view.session.id == session.id
    assert view.session.status is SessionStatus.ACTIVE
    assert view.elapsed_seconds == 4 * 60
    assert view.deadline_passed is False
    restored_clock.advance(50, wall=False)
    assert restored.active_session().elapsed_seconds == 4 * 60 + 50

    expired_clock = FakeClock(START + timedelta(minutes=11), monotonic=0.0)
    expired = SessionEngine(JsonStore(path), expired_clock)
    before = path.read_text(encoding="utf-8")
    expired_view = expired.active_session()
    assert expired_view is not None
    assert expired_view.session.status is SessionStatus.ACTIVE
    assert expired_view.deadline_passed is True
    assert expired_view.elapsed_seconds == 10 * 60
    assert path.read_text(encoding="utf-8") == before

    expired.report(session.id, CompletionReport("not_kept"))
    reloaded = SessionEngine(JsonStore(path), expired_clock)
    assert reloaded.sessions()[0].status is SessionStatus.NOT_KEPT
    assert reloaded.active_session() is None


def test_not_kept_report_preserves_older_kept_cells(tmp_path: Path) -> None:
    engine, clock, _path = _engine(tmp_path, START.replace(month=9, day=28))
    _close(engine, clock, "walking", "kept", "The long way around the block.")
    clock.set_wall(datetime(2026, 10, 9, 12, 0, tzinfo=ZONE))
    _close(engine, clock, "nature_observation", "kept", None)
    clock.set_wall(datetime(2026, 10, 10, 12, 0, tzinfo=ZONE))
    _close(engine, clock, "walking", "not_kept", "I stayed at the desk.")

    grid = engine.history()

    assert grid.start_date == date(2026, 9, 28)
    assert grid.end_date == date(2026, 10, 10)
    assert grid.cells[0][0] is True
    assert grid.cells[0][12] is False
    assert grid.cells[1][11] is True
    assert grid.row_mask(0) == 1
    assert len(engine.sessions()) == 3


def test_days_outside_the_window_stay_in_the_file(tmp_path: Path) -> None:
    engine, clock, _path = _engine(tmp_path, datetime(2026, 9, 27, 12, 0, tzinfo=ZONE))
    _close(engine, clock, "walking", "kept", None)
    clock.set_wall(START)

    grid = engine.history()

    assert all(not lit for row in grid.cells for lit in row)
    assert engine.sessions()[0].status is SessionStatus.KEPT


def test_two_kept_activities_on_one_day_light_one_cell(tmp_path: Path) -> None:
    engine, clock, _path = _engine(tmp_path)
    _close(engine, clock, "walking", "kept", None)
    _close(engine, clock, "walking", "kept", "Second loop.")

    assert engine.history().cells[0][12] is True
    assert sum(session.status is SessionStatus.KEPT for session in engine.sessions()) == 2


def test_invalid_activity_does_not_create_a_file(tmp_path: Path) -> None:
    engine, _clock, path = _engine(tmp_path)

    with pytest.raises(ValidationError):
        engine.propose(_draft(duration_minutes=7))

    assert not path.exists()


def test_corrupt_history_is_not_replaced(tmp_path: Path) -> None:
    path = tmp_path / "outmark.json"
    path.write_text("{not json", encoding="utf-8")

    with pytest.raises(StorageError):
        SessionEngine(JsonStore(path), FakeClock(START))

    assert path.read_text(encoding="utf-8") == "{not json"


def test_a_report_before_the_deadline_is_refused(tmp_path: Path) -> None:
    engine, clock, path = _engine(tmp_path)
    session = engine.accept(engine.propose(_draft(duration_minutes=5)).id)
    clock.advance(299)
    before = path.read_text(encoding="utf-8")

    with pytest.raises(TransitionError, match="after the timer ends") as caught:
        engine.report(session.id, CompletionReport("kept"))

    assert caught.value.remaining_seconds == 1
    assert path.read_text(encoding="utf-8") == before
    assert engine.sessions()[0].status is SessionStatus.ACTIVE

    clock.advance(1)
    reported = engine.report(session.id, CompletionReport("kept", "The full five minutes."))

    assert reported.status is SessionStatus.KEPT
    with pytest.raises(TransitionError, match="only an active session"):
        engine.report(session.id, CompletionReport("kept"))
    assert len(engine.sessions()) == 1


def test_not_kept_is_also_refused_before_the_deadline(tmp_path: Path) -> None:
    engine, clock, path = _engine(tmp_path)
    session = engine.accept(engine.propose(_draft(duration_minutes=5)).id)
    clock.advance(299)
    before = path.read_text(encoding="utf-8")

    with pytest.raises(TransitionError, match="after the timer ends"):
        engine.report(session.id, CompletionReport("not_kept"))

    assert path.read_text(encoding="utf-8") == before


def test_another_suggestion_is_allowed_after_rejection(tmp_path: Path) -> None:
    engine, _clock, _path = _engine(tmp_path)
    first = engine.propose(_draft(title="First"))
    engine.reject(first.id)

    second = engine.propose(_draft(title="Second"))

    assert second.status is ProposalStatus.PROPOSED
    assert engine.open_proposal() == second
    assert engine.sessions() == ()


def _engine(tmp_path: Path, wall: datetime = START) -> tuple[SessionEngine, FakeClock, Path]:
    path = tmp_path / "outmark.json"
    clock = FakeClock(wall)
    return SessionEngine(JsonStore(path), clock), clock, path


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
        duration_minutes=values["duration_minutes"],  # type: ignore[arg-type]
        category=values["category"],  # type: ignore[arg-type]
        title=values["title"],  # type: ignore[arg-type]
        instructions=values["instructions"],  # type: ignore[arg-type]
        reflection_question=values["reflection_question"],  # type: ignore[arg-type]
    )


def _close(
    engine: SessionEngine,
    clock: FakeClock,
    category: str,
    outcome: str,
    reflection: str | None,
) -> None:
    proposal = engine.propose(_draft(category=category))
    session = engine.accept(proposal.id)
    clock.advance(session.duration_minutes * 60)
    engine.report(session.id, CompletionReport(outcome, reflection))  # type: ignore[arg-type]
