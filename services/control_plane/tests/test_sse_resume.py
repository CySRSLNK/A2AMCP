from uuid import uuid4

import asyncio

from shared.python.lab_core.contracts import CorrelationContext, EventDraft
from services.control_plane.app.events import EventStore
from services.control_plane.app.main import event_stream


def test_sse_stream_resumes_after_last_event_id(tmp_path):
    store = EventStore(f"sqlite:///{tmp_path / 'events.db'}")
    run_id = uuid4()

    for index in range(3):
        store.append(
            EventDraft(
                context=CorrelationContext(
                    run_id=run_id,
                    task_id=None,
                    parent_task_id=None,
                    agent_id="test-agent",
                    hop=0,
                    request_id=f"request-{index}",
                ),
                protocol="mcp",
                operation="tools/list",
                direction="inbound",
                payload={"index": index},
            )
        )

    async def collect():
        return [chunk async for chunk in event_stream(store, run_id, 1)]

    text = "\n".join(asyncio.run(collect()))
    assert "id: 2" in text
    assert "id: 3" in text
    assert "id: 1" not in text
