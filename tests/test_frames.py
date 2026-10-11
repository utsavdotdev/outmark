"""Frame sequences for the matrix. These tests do not light a physical board."""

from __future__ import annotations

from pathlib import Path

from outmark.display import MODE_ACTIVE, MODE_DONE, MODE_GRID, MODE_PENDING, render_frame
from outmark.frames import (
    ACCEPT_FRAMES,
    EXPIRED_FRAMES,
    FRAME_LENGTH,
    FRAME_MS,
    NOT_KEPT_FRAMES,
    PLANT_ROWS,
    PROPOSAL_FRAMES,
    REVEAL_FRAMES,
    EventGate,
    FramePlayer,
    accept_frames,
    breathe_frame,
    chart_timer_frame,
    column_reveal,
    done_frame,
    expired_frames,
    growth_count,
    growth_frames,
    not_kept_frames,
    pending_frame,
    plant_frame,
    plant_timer_frame,
    proposal_frames,
)

SKETCH = Path(__file__).resolve().parents[1] / "sketch" / "sketch.ino"


def test_plant_stages_are_distinct_and_leave_the_timer_row_empty() -> None:
    frames = [plant_frame(stage) for stage in range(6)]
    assert len(set(frames)) == 6
    for frame in frames:
        assert len(frame) == FRAME_LENGTH
        assert set(frame) <= {0, 1}
        assert frame[7 * 13 : 8 * 13] == (0,) * 13
        assert sum(frame) >= 1
    assert plant_frame(0)[6 * 13 + 6] == 1


def test_growth_starts_at_the_old_stage_and_ends_at_the_new_one() -> None:
    frames = growth_frames(0, 1)
    assert frames[0] == plant_frame(0)
    assert frames[-1] == plant_frame(1)
    assert len(frames) == growth_count(0, 1)
    assert growth_frames(5, 5)[0] == plant_frame(5)
    assert growth_frames(5, 5)[-1] == plant_frame(5)
    assert growth_frames(5, 5)[1] != plant_frame(5)
    assert len(growth_frames(5, 5)) == 3
    assert growth_frames(4, 1)[-1] == plant_frame(4)


def test_other_events_do_not_use_the_growth_ending() -> None:
    assert len(proposal_frames()) == PROPOSAL_FRAMES
    assert proposal_frames()[-1] == pending_frame()
    assert proposal_frames()[-1] != plant_frame(1)
    assert len(accept_frames()) == ACCEPT_FRAMES
    assert accept_frames()[-1] == pending_frame()
    assert len(expired_frames()) == EXPIRED_FRAMES
    assert expired_frames()[-1] == done_frame()
    assert expired_frames()[-1] not in {plant_frame(stage) for stage in range(6)}
    assert len(not_kept_frames(3)) == NOT_KEPT_FRAMES
    assert not_kept_frames(3)[-1] == plant_frame(3)
    assert sum(not_kept_frames(3)[-1]) == sum(plant_frame(3))


def test_a_reveal_never_lights_a_pixel_outside_the_destination() -> None:
    masks = (1 << 12, 0, 0, 0, 0, 0, 0, 0)
    destination = render_frame(MODE_GRID, 0, masks)
    frames = column_reveal(destination)
    assert len(frames) == REVEAL_FRAMES
    assert frames[-1] == destination
    for frame in frames:
        for index, pixel in enumerate(frame):
            if pixel:
                assert destination[index] == 1


def test_timer_frames_follow_the_segment_count() -> None:
    assert chart_timer_frame(4) == render_frame(MODE_ACTIVE, 4, (1 << 12,) + (0,) * 7)
    assert sum(chart_timer_frame(4)) == 4
    planted = plant_timer_frame(3, 4)
    assert planted[7 * 13 : 7 * 13 + 4] == (1, 1, 1, 1)
    for index, pixel in enumerate(plant_frame(3)):
        if pixel:
            assert planted[index] == 1


def test_idle_breathing_keeps_the_plant_pixels() -> None:
    base = plant_frame(2)
    moved = breathe_frame(2, 1)
    assert breathe_frame(2, 0) == base
    assert moved[0] == 1
    for index, pixel in enumerate(base):
        if pixel:
            assert moved[index] == 1


def test_pending_and_done_match_the_existing_renderer() -> None:
    assert pending_frame() == render_frame(MODE_PENDING, 0, (0,) * 8)
    assert done_frame() == render_frame(MODE_DONE, 0, (0,) * 8)


def test_a_new_event_replaces_the_one_that_is_playing() -> None:
    player = FramePlayer()
    player.steady = done_frame()
    player.play(proposal_frames(), 0)
    assert player.current(0) == proposal_frames()[0]
    player.play(expired_frames(), 50)
    assert player.current(50) == expired_frames()[0]
    assert player.current(50 + FRAME_MS * EXPIRED_FRAMES) == done_frame()


def test_a_repeated_generation_is_ignored() -> None:
    gate = EventGate()
    assert gate.accept(1, 1) is True
    assert gate.accept(5, 1) is False
    assert gate.accept(5, 2) is True
    assert gate.accept(0, 3) is False
    assert gate.accept(8, 4) is False


def test_the_sketch_uses_the_same_plant_rows_and_does_not_block() -> None:
    text = SKETCH.read_text(encoding="utf-8")
    for rows in PLANT_ROWS:
        assert ", ".join(str(value) for value in rows) in text
    assert "delay(" not in text
    assert "playSequence" not in text
    assert "loadSequence" not in text
    assert "millis()" in text
    assert "set_event" in text
    assert "PROPOSAL_FRAMES = 4" in text
    assert "ACCEPT_FRAMES = 3" in text
    assert "EXPIRED_FRAMES = 14" in text
    assert "NOT_KEPT_FRAMES = 3" in text
    assert "REVEAL_FRAMES = 13" in text
    assert "(to - from) + 4" in text
