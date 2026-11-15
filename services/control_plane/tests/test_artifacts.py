from uuid import uuid4

import pytest

from services.control_plane.app.artifacts import ArtifactStore, CrossTaskAccessError, RunDestroyer
from services.control_plane.app.events import EventStore
from shared.python.lab_core.contracts import CorrelationContext, EventDraft


def test_artifact_store_uses_inline_and_content_addressed_bodies(tmp_path):
    store = ArtifactStore(tmp_path / "blobs", inline_limit=8)
    run_id = uuid4()
    task_id = uuid4()

    small = store.put(run_id, task_id, b"small", "text/plain")
    large = store.put(run_id, task_id, b"0123456789", "application/octet-stream")

    assert small.inline is True
    assert large.inline is False
    assert store.get(small, run_id, task_id) == b"small"
    assert store.get(large, run_id, task_id) == b"0123456789"
    assert large.sha256


def test_cross_task_access_requires_explicit_opt_in(tmp_path):
    store = ArtifactStore(tmp_path / "blobs")
    ref = store.put(uuid4(), uuid4(), b"secret", "text/plain")

    with pytest.raises(CrossTaskAccessError):
        store.get(ref, ref.run_id, uuid4())
    assert store.get(ref, ref.run_id, uuid4(), allow_cross_task=True) == b"secret"


def test_destroy_run_removes_events_and_artifacts(tmp_path):
    database = tmp_path / "events.db"
    event_store = EventStore(f"sqlite:///{database}")
    artifacts = ArtifactStore(tmp_path / "blobs")
    run_id = uuid4()
    task_id = uuid4()
    event_store.append(
        EventDraft(
            context=CorrelationContext(run_id=run_id, task_id=task_id, request_id="r1"),
            protocol="artifact",
            operation="put",
            direction="internal",
            payload={"artifact": "x"},
        )
    )
    artifacts.put(run_id, task_id, b"payload", "text/plain")

    report = RunDestroyer(event_store, artifacts).destroy(run_id)

    assert report.deleted_events == 1
    assert report.deleted_artifacts == 1
    assert event_store.list_events(str(run_id)) == []
