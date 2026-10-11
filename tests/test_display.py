"""Display modes, mask mapping, and a bridge stand-in. No physical LEDs are checked."""

from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from outmark.app import create_app
from outmark.clock import FakeClock
from outmark.config import Settings
from outmark.display import (
    MODE_ACTIVE,
    MODE_DONE,
    MODE_GRID,
    MODE_PENDING,
    MODE_REST,
    PROGRESS_ROW,
    BridgeDisplay,
    DisplayTracker,
    DisplayView,
    RecordingDisplay,
    publish,
    render_frame,
    send,
)
from outmark.engine import SessionEngine
from outmark.errors import DisplayError
from outmark.frames import EVENT_KEPT, EVENT_NOT_KEPT, EVENT_STARTUP, VIEW_CHART
from outmark.records import ActivityDraft, CompletionReport, SessionStatus
from outmark.storage import JsonStore

ZONE = timezone(timedelta(hours=5, minutes=45))
START = datetime(2026, 10, 10, 12, 0, tzinfo=ZONE)


def test_idle_engine_selects_rest_and_does_not_create_a_file(tmp_path: Path) -> None:
    engine, _clock, path = _engine(tmp_path)
    display = RecordingDisplay()

    publish(engine, display)

    assert not path.exists()
    assert _mode(display) == MODE_REST
    assert _masks(display) == (0,) * 8
    assert display.calls[-1] == ("set_mode", MODE_REST)


def test_grid_puts_the_oldest_day_in_column_zero(tmp_path: Path) -> None:
    engine, clock, _path = _engine(tmp_path, START - timedelta(days=12))
    _close(engine, clock, "walking", "kept")
    clock.set_wall(START)
    display = RecordingDisplay()

    publish(engine, display)

    assert _mode(display) == MODE_GRID
    assert _masks(display)[0] == 1
    frame = render_frame(MODE_GRID, 0, _masks(display))
    assert frame[0] == 1
    assert frame[13] == 0
    assert sum(frame) == 1


def test_pending_active_and_done_are_distinct_from_a_kept_cell(tmp_path: Path) -> None:
    engine, clock, path = _engine(tmp_path)
    _close(engine, clock, "nature_observation", "kept")
    proposal = engine.propose(_draft(duration_minutes=10))
    engine.accept(proposal.id)
    before = path.read_text(encoding="utf-8")
    display = RecordingDisplay()

    publish(engine, display)
    assert _mode(display) == MODE_PENDING
    assert render_frame(MODE_PENDING, 0, (0,) * 8) != render_frame(MODE_GRID, 0, _masks(display))

    clock.advance(300, wall=False)
    display.calls.clear()
    publish(engine, display)
    assert _mode(display) == MODE_ACTIVE
    assert ("set_progress", 6) in display.calls
    active = render_frame(MODE_ACTIVE, 6, (0,) * 8)
    assert active[PROGRESS_ROW * 13 : PROGRESS_ROW * 13 + 6] == (1, 1, 1, 1, 1, 1)
    assert sum(active) == 6

    clock.advance(400, wall=False)
    display.calls.clear()
    publish(engine, display)
    assert _mode(display) == MODE_DONE
    assert path.read_text(encoding="utf-8") == before
    assert engine.sessions()[-1].status is SessionStatus.ACTIVE
    done = render_frame(MODE_DONE, 13, (0,) * 8)
    assert done != active
    assert done != render_frame(MODE_REST, 0, (0,) * 8)
    assert done != render_frame(MODE_PENDING, 0, (0,) * 8)


def test_not_kept_leaves_the_older_cell_on_the_grid(tmp_path: Path) -> None:
    engine, clock, _path = _engine(tmp_path, START - timedelta(days=1))
    _close(engine, clock, "walking", "kept")
    clock.set_wall(START)
    _close(engine, clock, "walking", "not_kept")
    display = RecordingDisplay()

    publish(engine, display)

    assert _mode(display) == MODE_GRID
    assert _masks(display)[0] == 1 << 11
    assert engine.sessions()[-1].status is SessionStatus.NOT_KEPT


def test_invalid_mask_is_rejected_before_any_call() -> None:
    display = RecordingDisplay()

    with pytest.raises(DisplayError):
        send(display, DisplayView(MODE_GRID, 0, (1 << 13,) + (0,) * 7))

    assert display.calls == []


def test_a_failed_display_call_does_not_change_the_history_file(tmp_path: Path) -> None:
    engine, clock, path = _engine(tmp_path)
    _close(engine, clock, "walking", "kept")
    before = path.read_text(encoding="utf-8")

    with pytest.raises(RuntimeError, match="bridge down"):
        publish(engine, _BrokenDisplay())

    assert path.read_text(encoding="utf-8") == before
    assert engine.sessions()[0].status is SessionStatus.KEPT


def test_startup_publish_uses_the_stored_grid(tmp_path: Path) -> None:
    clock = FakeClock(START)
    engine, stored_clock, _path = _engine(tmp_path / "data")
    _close(engine, stored_clock, "walking", "kept")
    display = RecordingDisplay()

    app = create_app(_settings(tmp_path), display=display, clock=clock)
    client = app.test_client()

    assert client.get("/health").status_code == 200
    assert _mode(display) == MODE_GRID
    assert _masks(display)[0] == 1 << 12
    assert app.config["OUTMARK_ENGINE"] is not None


def test_a_corrupt_history_file_does_not_stop_the_web_server(tmp_path: Path) -> None:
    path = tmp_path / "data" / "outmark.json"
    path.parent.mkdir()
    path.write_text("{not json", encoding="utf-8")
    display = RecordingDisplay()

    app = create_app(_settings(tmp_path), display=display, clock=FakeClock(START))

    assert app.test_client().get("/health").status_code == 200
    assert path.read_text(encoding="utf-8") == "{not json"
    assert display.calls == []
    assert app.config["OUTMARK_ENGINE"] is None


def test_the_page_does_not_offer_a_plant(tmp_path: Path) -> None:
    display = RecordingDisplay()
    client = create_app(_settings(tmp_path), display=display, clock=FakeClock(START)).test_client()
    page = client.get("/").get_data(as_text=True)

    assert "Plant growth" not in page
    assert "plant-drawing" not in page
    assert client.post("/api/display-mode", json={"display_mode": "plant"}).status_code == 404
    assert ("set_view", VIEW_CHART) in display.calls


def test_kept_growth_is_sent_once_and_a_restart_does_not_repeat_it(tmp_path: Path) -> None:
    engine, clock, path = _engine(tmp_path)
    tracker = DisplayTracker()
    display = RecordingDisplay()
    publish(engine, display, tracker.observe(engine))
    proposal = engine.propose(_draft())
    tracker.observe(engine)
    session = engine.accept(proposal.id)
    tracker.observe(engine)
    clock.advance(session.duration_minutes * 60)
    tracker.observe(engine)
    engine.report(session.id, CompletionReport("kept", None))
    event = tracker.observe(engine)
    display.calls.clear()
    publish(engine, display, event)

    assert event is not None
    assert event[0] == EVENT_KEPT
    assert display.calls[0] == ("set_event", EVENT_KEPT, event[1])
    assert ("set_view", VIEW_CHART) in display.calls
    assert not any(call[0] == "set_plant" for call in display.calls)
    assert tracker.observe(engine) is None

    restarted = RecordingDisplay()
    restarted_tracker = DisplayTracker()
    restarted_engine = SessionEngine(JsonStore(path), FakeClock(clock.wall()))
    publish(restarted_engine, restarted, restarted_tracker.observe(restarted_engine))
    assert ("set_view", VIEW_CHART) in restarted.calls
    assert [call[1] for call in restarted.calls if call[0] == "set_event"] == [EVENT_STARTUP]
    assert restarted_tracker.observe(restarted_engine) is None


def test_not_kept_does_not_send_growth(tmp_path: Path) -> None:
    engine, clock, _path = _engine(tmp_path)
    tracker = DisplayTracker()
    tracker.observe(engine)
    proposal = engine.propose(_draft())
    tracker.observe(engine)
    session = engine.accept(proposal.id)
    tracker.observe(engine)
    clock.advance(session.duration_minutes * 60)
    tracker.observe(engine)
    engine.report(session.id, CompletionReport("not_kept", None))
    event = tracker.observe(engine)
    display = RecordingDisplay()
    publish(engine, display, event)

    assert event is not None
    assert event[0] == EVENT_NOT_KEPT
    assert ("set_view", VIEW_CHART) in display.calls
    assert not any(call[0] == "set_plant" for call in display.calls)
    assert not any(call[1] == EVENT_KEPT for call in display.calls if call[0] == "set_event")


def test_an_older_file_without_display_mode_opens_on_the_chart(tmp_path: Path) -> None:
    path = tmp_path / "outmark.json"
    path.write_text(
        json.dumps(
            {
                "version": 1,
                "settings": {"default_duration": 10},
                "proposals": [],
                "sessions": [],
            }
        ),
        encoding="utf-8",
    )

    engine = SessionEngine(JsonStore(path), FakeClock(START))

    assert engine.display_mode() == "chart"


def test_bridge_display_imports_only_when_the_runtime_exists() -> None:
    try:
        import arduino.app_utils  # noqa: F401
    except ImportError:
        with pytest.raises(ImportError):
            BridgeDisplay()
    else:
        pytest.skip("arduino.app_utils is installed on this machine")


def _engine(tmp_path: Path, wall: datetime = START) -> tuple[SessionEngine, FakeClock, Path]:
    path = tmp_path / "outmark.json"
    clock = FakeClock(wall)
    return SessionEngine(JsonStore(path), clock), clock, path


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
        duration_minutes=values["duration_minutes"],  # type: ignore[arg-type]
        category=str(values["category"]),
        title=str(values["title"]),
        instructions=str(values["instructions"]),
        reflection_question=str(values["reflection_question"]),
    )


def _close(engine: SessionEngine, clock: FakeClock, category: str, outcome: str) -> None:
    proposal = engine.propose(_draft(category=category))
    session = engine.accept(proposal.id)
    clock.advance(session.duration_minutes * 60)
    report = CompletionReport(outcome, None)  # type: ignore[arg-type]
    engine.report(session.id, report)


def _masks(display: RecordingDisplay) -> tuple[int, ...]:
    return tuple(call[2] for call in display.calls if call[0] == "set_grid_row")  # type: ignore[misc]


def _mode(display: RecordingDisplay) -> int:
    return next(call[1] for call in reversed(display.calls) if call[0] == "set_mode")  # type: ignore[return-value]


class _BrokenDisplay:
    def set_mode(self, mode: int) -> None:
        raise RuntimeError("bridge down")

    def set_progress(self, segments: int) -> None:
        raise RuntimeError("bridge down")

    def set_grid_row(self, row: int, mask: int) -> None:
        raise RuntimeError("bridge down")

    def set_view(self, view: int) -> None:
        raise RuntimeError("bridge down")

    def set_plant(self, stage: int) -> None:
        raise RuntimeError("bridge down")

    def set_event(self, code: int, generation: int) -> None:
        raise RuntimeError("bridge down")
