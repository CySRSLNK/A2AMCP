import pytest

from services.control_plane.app.replay import NonReplayableError, ReplayEngine


def test_replay_creates_new_logical_run_from_retained_events():
    plan = ReplayEngine().create_plan(
        "run-original",
        [
            {"event_id": "e1", "payload": {"model": "answer"}},
            {"event_id": "e2", "payload": {"tool": "calculator", "result": "3"}},
        ],
    )

    assert plan.source_run_id == "run-original"
    assert plan.replay_run_id != "run-original"
    assert plan.event_count == 2
    assert plan.event_id_map["e1"]


def test_replay_refuses_missing_or_redacted_bodies():
    with pytest.raises(NonReplayableError, match="not replayable"):
        ReplayEngine().create_plan("run-original", [{"event_id": "e1", "payload": None}])

    with pytest.raises(NonReplayableError, match="not replayable"):
        ReplayEngine().create_plan(
            "run-original", [{"event_id": "e1", "payload": {"_redacted": True}}]
        )
