import pytest
from uuid import uuid4

from services.control_plane.app.replay import NonReplayableError, ReplayEngine
from services.gateway.app.policies import PolicyEngine
from shared.python.lab_core.contracts import CorrelationContext


def test_depth_policy_denies_before_forwarding():
    decision = PolicyEngine(allowed_targets={"worker-agent"}, max_hop=1).evaluate(
        CorrelationContext(run_id=uuid4(), hop=2, request_id="r1"),
        "message/send",
        "worker-agent",
        {"prompt": "loop"},
    )
    assert decision.outcome == "deny"
    assert decision.rule_id == "max-hop"


def test_replay_requires_retained_response_bodies():
    engine = ReplayEngine()
    plan = engine.create_plan("run-1", [{"event_id": "e1", "payload": {"answer": "3"}}])
    assert plan.event_count == 1
    with pytest.raises(NonReplayableError):
        engine.create_plan("run-1", [{"event_id": "e2", "payload": {"_redacted": True}}])
