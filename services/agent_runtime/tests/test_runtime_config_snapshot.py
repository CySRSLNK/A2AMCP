import asyncio
from uuid import uuid4

from shared.python.lab_core.contracts import ModelResponse
from services.agent_runtime.app.planner import AgentRuntime, TaskInput


class CapturingModel:
    def __init__(self):
        self.requests = []

    async def complete(self, request):
        self.requests.append(request)
        return ModelResponse(provider="test", model=request.model, output={"action": "answer", "summary": "ok"})


def test_agent_uses_snapshot_model_and_never_receives_api_key():
    model = CapturingModel()
    runtime = AgentRuntime(agent_id="worker-agent", model=model, a2a_client=None)
    task = TaskInput(
        run_id=uuid4(),
        prompt="answer",
        agent_id="worker-agent",
        runtime_config={
            "config_version": 7,
            "model": {"provider": "openai-compatible", "model_name": "snapshot-model"},
            "agents": {"worker-agent": {"max_hop": 3, "allowed_targets": [], "allowed_mcp_servers": [], "allowed_tools": []}},
            "mcp_servers": [],
        },
    )

    result = asyncio.run(runtime.handle_task(task))

    assert result.status == "completed"
    assert model.requests[0].model == "snapshot-model"
    assert model.requests[0].metadata["runtime_config_version"] == 7
    assert "api_key" not in task.model_dump(mode="json")
