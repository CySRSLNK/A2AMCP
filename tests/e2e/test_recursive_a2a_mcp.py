import asyncio
from uuid import uuid4

from services.agent_runtime.app.model_proxy import MockModelAdapter
from services.agent_runtime.app.planner import AgentRuntime, TaskInput


class RecordingMcpClient:
    def __init__(self, events):
        self.events = events

    async def call_tool(self, context, server_id, name, arguments):
        self.events.append(("mcp", context, server_id, name))
        return {"content": [{"type": "text", "text": "3"}]}


class RecordingA2AClient:
    def __init__(self, runtimes, events):
        self.runtimes = runtimes
        self.events = events

    async def send(self, context, target_agent, task):
        self.events.append(("a2a", context, target_agent, task.hop))
        return await self.runtimes[target_agent].handle_task(task)


def test_mock_run_contains_recursive_a2a_and_mcp_hops():
    events = []
    worker = AgentRuntime(
        agent_id="worker-agent",
        model=MockModelAdapter(),
        a2a_client=None,
        mcp_client=RecordingMcpClient(events),
        max_hop=3,
    )
    root = AgentRuntime(
        agent_id="root-agent",
        model=MockModelAdapter(),
        a2a_client=None,
        mcp_client=RecordingMcpClient(events),
        max_hop=3,
    )
    client = RecordingA2AClient({"root-agent": root, "worker-agent": worker}, events)
    root.a2a_client = client
    worker.a2a_client = client

    result = asyncio.run(
        root.handle_task(
            TaskInput(run_id=uuid4(), prompt="inspect fixture", agent_id="root-agent")
        )
    )

    assert result.status == "completed"
    assert [event[0] for event in events] == ["a2a", "a2a", "mcp"]
    assert events[0][2] == "worker-agent"
    assert events[1][3] == 2
    assert events[2][2:] == ("mcp-tools", "calculator")
