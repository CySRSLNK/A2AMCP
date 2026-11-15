from datetime import datetime, timedelta, timezone
from uuid import uuid4

import pytest

from services.control_plane.app.approvals import ApprovalManager
from services.control_plane.app.policies import freeze_policy


def test_policy_snapshot_is_immutable_after_run_start():
    source = {"max_hop": 2, "allowed_tools": ["calculator"]}
    snapshot = freeze_policy(source)
    source["max_hop"] = 99
    source["allowed_tools"].append("fixture_http_get")

    assert snapshot.max_hop == 2
    assert snapshot.allowed_tools == ["calculator"]


def test_approval_can_be_decided_once_and_times_out():
    manager = ApprovalManager()
    run_id = uuid4()
    approval = manager.request(run_id, "tools/call:calculator", expires_in=timedelta(seconds=1))

    approved = manager.decide(approval.id, "approve")
    assert approved.status == "approved"

    with pytest.raises(ValueError, match="already decided"):
        manager.decide(approval.id, "deny")

    expired = manager.request(
        run_id,
        "tools/call:fixture_http_get",
        expires_in=timedelta(seconds=1),
        now=datetime.now(timezone.utc) - timedelta(seconds=2),
    )
    manager.timeout(now=datetime.now(timezone.utc))
    assert manager.get(expired.id).status == "denied"
