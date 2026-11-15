import asyncio
from uuid import uuid4

from shared.python.lab_core.contracts import ModelResponse
from services.agent_runtime.app.agent_card import AgentCard
from services.agent_runtime.app.planner import AgentRuntime, TaskInput


class ScriptedModel:
    def __init__(self, actions):
        self.actions = iter(actions)

    async def complete(self, request):
        return ModelResponse(
            provider="test",
            model="scripted",
            output=next(self.actions),
        )


class FakeA2AClient:
    def __init__(self, runtimes):
        self.runtimes = runtimes
        self.calls = []

    async def send(self, context, target_agent, task):
        self.calls.append((target_agent, task))
        return await self.runtimes[target_agent].handle_task(task)


class FakeMcpClient:
    def __init__(self):
        self.contexts = []

    async def call_tool(self, context, server_id, name, arguments):
        self.contexts.append((context, server_id, name, arguments))
        return {"content": [{"type": "text", "text": "3"}]}


def test_agent_card_declares_task_and_stream_capabilities():
    card = AgentCard(
        agent_id="worker-agent",
        name="Worker Agent",
        description="Performs fixture inspection",
        url="http://worker-agent:8100",
    )

    document = card.model_dump(mode="json")

    assert document["id"] == "worker-agent"
    assert "message/send" in document["capabilities"]["operations"]
    assert "message/stream" in document["capabilities"]["operations"]


def test_root_can_delegate_recursively_to_worker():
    run_id = uuid4()
    worker = AgentRuntime(
        agent_id="worker-agent",
        model=ScriptedModel(
            [
                {"action": "delegate", "target_agent": "worker-agent", "summary": "delegate once"},
                {"action": "answer", "summary": "worker result"},
            ]
        ),
        a2a_client=None,
        max_hop=3,
    )
    root = AgentRuntime(
        agent_id="root-agent",
        model=ScriptedModel(
            [{"action": "delegate", "target_agent": "worker-agent", "summary": "delegate root"}]
        ),
        a2a_client=None,
        max_hop=3,
    )
    client = FakeA2AClient({"root-agent": root, "worker-agent": worker})
    root.a2a_client = client
    worker.a2a_client = client

    result = asyncio.run(
        root.handle_task(
            TaskInput(run_id=run_id, prompt="inspect fixture", agent_id="root-agent")
        )
    )

    assert result.status == "completed"
    assert len(client.calls) == 2
    assert client.calls[0][0] == "worker-agent"
    assert client.calls[1][1].hop == 2


def test_recursion_stops_at_depth_and_repeated_edge():
    runtime = AgentRuntime(
        agent_id="worker-agent",
        model=ScriptedModel(
            [{"action": "delegate", "target_agent": "worker-agent", "summary": "loop"}]
        ),
        a2a_client=None,
        max_hop=1,
    )
    runtime.a2a_client = FakeA2AClient({"worker-agent": runtime})

    depth_result = asyncio.run(
        runtime.handle_task(
            TaskInput(run_id=uuid4(), prompt="loop", agent_id="worker-agent", hop=1)
        )
    )
    repeated_result = asyncio.run(
        runtime.handle_task(
            TaskInput(
                run_id=uuid4(),
                prompt="loop",
                agent_id="worker-agent",
                delegation_edges=["worker-agent->worker-agent", "worker-agent->worker-agent"],
            )
        )
    )

    assert depth_result.status == "blocked"
    assert repeated_result.status == "blocked"


def test_mcp_call_inherits_task_correlation_context():
    mcp = FakeMcpClient()
    runtime = AgentRuntime(
        agent_id="worker-agent",
        model=ScriptedModel(
            [{
                "action": "mcp_call",
                "server_id": "mcp-tools",
                "tool_name": "calculator",
                "arguments": {"a": 1, "b": 2},
                "summary": "calculate",
            }]
        ),
        a2a_client=None,
        mcp_client=mcp,
    )
    task = TaskInput(run_id=uuid4(), prompt="calculate", agent_id="worker-agent", hop=2)

    result = asyncio.run(runtime.handle_task(task))

    assert result.status == "completed"
    context, server_id, name, arguments = mcp.contexts[0]
    assert context.task_id == task.task_id
    assert context.hop == 2
    assert (server_id, name, arguments) == ("mcp-tools", "calculator", {"a": 1, "b": 2})


def test_model_decision_cannot_delegate_to_unapproved_target():
    runtime = AgentRuntime(
        agent_id="root-agent",
        model=ScriptedModel(
            [{"action": "delegate", "target_agent": "untrusted-agent", "summary": "delegate"}]
        ),
        a2a_client=FakeA2AClient({}),
        allowed_targets={"worker-agent"},
    )

    result = asyncio.run(
        runtime.handle_task(TaskInput(run_id=uuid4(), prompt="delegate", agent_id="root-agent"))
    )

    assert result.status == "blocked"
    assert result.summary == "target agent is not allowed"


def test_model_decision_cannot_call_unapproved_tool():
    runtime = AgentRuntime(
        agent_id="worker-agent",
        model=ScriptedModel(
            [{
                "action": "mcp_call",
                "server_id": "mcp-tools",
                "tool_name": "shell",
                "summary": "call tool",
            }]
        ),
        a2a_client=None,
        mcp_client=FakeMcpClient(),
        allowed_mcp_servers={"mcp-tools"},
        allowed_tools={"calculator"},
    )

    result = asyncio.run(
        runtime.handle_task(TaskInput(run_id=uuid4(), prompt="call", agent_id="worker-agent"))
    )

    assert result.status == "blocked"
    assert result.summary == "MCP tool is not allowed"


def test_model_decision_schema_failure_is_fail_closed():
    runtime = AgentRuntime(
        agent_id="root-agent",
        model=ScriptedModel([{"action": "delegate", "summary": "missing target"}]),
        a2a_client=None,
    )

    result = asyncio.run(
        runtime.handle_task(TaskInput(run_id=uuid4(), prompt="delegate", agent_id="root-agent"))
    )

    assert result.status == "failed"
    assert result.summary.startswith("invalid model decision:")
