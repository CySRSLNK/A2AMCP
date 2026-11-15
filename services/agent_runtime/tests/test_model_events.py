import asyncio

import httpx

from shared.python.lab_core.contracts import EventDraft, ModelResponse
from services.agent_runtime.app.planner import AgentRuntime, TaskInput


class ScriptedModel:
    def __init__(self):
        self.requests = []

    async def complete(self, request):
        self.requests.append(request)
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


def test_toolless_agent_prompt_requires_delegation_for_tool_requests():
    model = ScriptedModel()
    runtime = AgentRuntime(
        agent_id="root-agent",
        model=model,
        a2a_client=None,
        allowed_targets={"worker-agent"},
        allowed_tools=set(),
    )

    result = asyncio.run(
        runtime.handle_task(
            TaskInput(
                run_id="33333333-3333-3333-3333-333333333333",
                prompt="委派 worker agent 使用 read_file 读取 example.txt",
                agent_id="root-agent",
            )
        )
    )

    assert result.status == "completed"
    system_message = model.requests[0].messages[0]["content"]
    assert "choose mcp_call instead of answering" in system_message
    assert "delegate the original task" in system_message


def test_agent_prompt_uses_allowed_tools_before_delegating_unavailable_work():
    model = ScriptedModel()
    runtime = AgentRuntime(
        agent_id="root-agent",
        model=model,
        a2a_client=None,
        allowed_targets={"worker-agent"},
        allowed_tools={"calculator"},
    )

    asyncio.run(
        runtime.handle_task(
            TaskInput(
                run_id="44444444-4444-4444-4444-444444444444",
                prompt="调用 calculator 计算 6*8，并读取 example.txt",
                agent_id="root-agent",
            )
        )
    )

    system_message = model.requests[0].messages[0]["content"]
    assert "Use an allowed tool directly" in system_message
    assert "Do not delegate an operation merely because another agent also has it" in system_message
    assert "delegate only the remaining unsupported work" in system_message
    assert "root agent should delegate file and tool requests" not in system_message
