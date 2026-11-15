import asyncio

import httpx

from shared.python.lab_core.contracts import EventDraft, ModelResponse
from services.agent_runtime.app.planner import AgentRuntime, TaskInput


class ScriptedModel:
    async def complete(self, request):
        return ModelResponse(
            provider="test-provider",
            model="test-model",
            output={"action": "answer", "summary": "done"},
            usage={"total_tokens": 4},
        )


class TimeoutModel:
    async def complete(self, request):
        raise httpx.ReadTimeout("upstream timeout")


def test_model_decision_emits_correlated_request_and_response_events():
    events: list[EventDraft] = []
    runtime = AgentRuntime(
        agent_id="worker-agent",
        model=ScriptedModel(),
        a2a_client=None,
        model_provider="test",
        model_name="test-model",
        event_sink=events.append,
    )
    task = TaskInput(
        run_id="11111111-1111-1111-1111-111111111111",
        prompt="answer",
        agent_id="worker-agent",
        hop=2,
    )

    result = asyncio.run(runtime.handle_task(task))

    assert result.status == "completed"
    assert [(event.operation, event.direction) for event in events] == [
        ("completion.request", "outbound"),
        ("completion.response", "inbound"),
    ]
    for event in events:
        assert event.context.run_id == task.run_id
        assert event.context.task_id == task.task_id
        assert event.context.agent_id == "worker-agent"
        assert event.context.hop == 2
    assert events[0].payload["provider"] == "test"
    assert "messages" not in events[0].payload
    assert "api_key" not in events[0].payload
    assert events[1].payload == {
        "provider": "test-provider",
        "model": "test-model",
        "output": {"action": "answer", "summary": "done"},
        "usage": {"total_tokens": 4},
    }


def test_model_timeout_emits_error_event_and_fails_closed():
    events: list[EventDraft] = []
    runtime = AgentRuntime(
        agent_id="worker-agent",
        model=TimeoutModel(),
        a2a_client=None,
        event_sink=events.append,
    )

    result = asyncio.run(
        runtime.handle_task(
            TaskInput(
                run_id="22222222-2222-2222-2222-222222222222",
                prompt="answer",
                agent_id="worker-agent",
            )
        )
    )

    assert result.status == "failed"
    assert result.summary == "model request timed out"
    assert events[-1].operation == "completion.error"
    assert events[-1].direction == "inbound"
    assert events[-1].payload == {"error": "model request timed out"}
