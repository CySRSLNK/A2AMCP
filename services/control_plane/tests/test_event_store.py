import asyncio
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from uuid import uuid4

from shared.python.lab_core.contracts import CorrelationContext, EventDraft
from shared.python.lab_core.redaction import redact_payload
from services.control_plane.app.events import EventStore


def make_draft(run_id, index: int, source_key: str | None = None) -> EventDraft:
    return EventDraft(
        context=CorrelationContext(
            run_id=run_id,
            task_id=None,
            parent_task_id=None,
            agent_id="test-agent",
            hop=0,
            request_id=f"request-{index}",
        ),
        protocol="a2a",
        operation="message/send",
        direction="outbound",
        payload={"index": index, "authorization": "Bearer test-secret"},
        source_event_key=source_key,
    )


def test_event_store_assigns_strict_sequences_under_concurrent_appends(tmp_path: Path):
    store = EventStore(f"sqlite:///{tmp_path / 'events.db'}")
    run_id = uuid4()

    def append(index: int):
        return store.append(make_draft(run_id, index)).sequence

    with ThreadPoolExecutor(max_workers=8) as executor:
        sequences = list(executor.map(append, range(40)))

    assert sorted(sequences) == list(range(1, 41))


def test_event_store_deduplicates_source_event_keys(tmp_path: Path):
    store = EventStore(f"sqlite:///{tmp_path / 'events.db'}")
    run_id = uuid4()

    first = store.append(make_draft(run_id, 1, source_key="same-request"))
    duplicate = store.append(make_draft(run_id, 2, source_key="same-request"))

    assert duplicate.event_id == first.event_id
    assert duplicate.sequence == first.sequence


def test_redaction_removes_credentials_without_changing_safe_payload():
    payload = {
        "authorization": "Bearer very-secret",
        "nested": {"api_key": "key-secret", "value": "keep"},
        "text": "Authorization: Bearer inline-secret",
    }

    assert redact_payload(payload) == {
        "authorization": "[REDACTED]",
        "nested": {"api_key": "[REDACTED]", "value": "keep"},
        "text": "Authorization: Bearer [REDACTED]",
    }


def test_iter_after_is_an_async_resume_cursor(tmp_path: Path):
    store = EventStore(f"sqlite:///{tmp_path / 'events.db'}")
    run_id = uuid4()
    for index in range(3):
        store.append(make_draft(run_id, index))

    async def collect():
        return [event.sequence async for event in store.iter_after(run_id, 1)]

    assert asyncio.run(collect()) == [2, 3]
