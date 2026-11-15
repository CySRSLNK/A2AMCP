from __future__ import annotations

from typing import Any
from uuid import UUID, uuid4

from pydantic import BaseModel, Field

from shared.python.lab_core.contracts import CorrelationContext, ModelRequest

from .model_proxy import ModelAdapter


class TaskInput(BaseModel):
    run_id: UUID
    prompt: str
    agent_id: str
    task_id: UUID = Field(default_factory=uuid4)
    parent_task_id: UUID | None = None
    hop: int = Field(default=0, ge=0)
    delegation_edges: list[str] = Field(default_factory=list)


class TaskResult(BaseModel):
    status: str
    summary: str
    output: dict[str, Any] = Field(default_factory=dict)
    child_task_id: UUID | None = None


class AgentRuntime:
    def __init__(
        self,
        *,
        agent_id: str,
        model: ModelAdapter,
        a2a_client,
        mcp_client=None,
        max_hop: int = 8,
    ):
        self.agent_id = agent_id
        self.model = model
        self.a2a_client = a2a_client
        self.mcp_client = mcp_client
        self.max_hop = max_hop

    async def handle_task(self, task: TaskInput) -> TaskResult:
        if task.hop >= self.max_hop:
            return TaskResult(status="blocked", summary="maximum delegation depth exceeded")
        if task.delegation_edges.count(f"{self.agent_id}->{self.agent_id}") > 1:
            return TaskResult(status="blocked", summary="repeated delegation edge detected")
        response = await self.model.complete(
            ModelRequest(
                provider="mock",
                model="lab-deterministic",
                messages=[{"role": "user", "content": task.prompt}],
                metadata={
                    "role": "root" if self.agent_id == "root-agent" else "worker",
                    "agent_id": self.agent_id,
                    "hop": task.hop,
                },
            )
        )
        decision = response.output
        action = decision.get("action")
        summary = decision.get("summary", "")
        if action == "answer":
            return TaskResult(status="completed", summary=summary, output=decision)
        if action == "mcp_call":
            if self.mcp_client is None:
                return TaskResult(status="blocked", summary="MCP client is not configured")
            context = CorrelationContext(
                run_id=task.run_id,
                task_id=task.task_id,
                parent_task_id=task.parent_task_id,
                agent_id=self.agent_id,
                hop=task.hop,
                request_id=str(task.task_id),
            )
            result = await self.mcp_client.call_tool(
                context,
                decision["server_id"],
                decision["tool_name"],
                decision.get("arguments", {}),
            )
            return TaskResult(status="completed", summary=summary, output=result)
        if action != "delegate":
            return TaskResult(status="failed", summary="model returned an unsupported action")

        target_agent = decision.get("target_agent")
        edge = f"{self.agent_id}->{target_agent}"
        if edge in task.delegation_edges:
            return TaskResult(status="blocked", summary="repeated delegation edge detected")
        if self.a2a_client is None:
            return TaskResult(status="blocked", summary="A2A client is not configured")

        child = task.model_copy(
            update={
                "agent_id": target_agent,
                "task_id": uuid4(),
                "parent_task_id": task.task_id,
                "hop": task.hop + 1,
                "delegation_edges": [*task.delegation_edges, edge],
            }
        )
        context = CorrelationContext(
            run_id=task.run_id,
            task_id=task.task_id,
            parent_task_id=task.parent_task_id,
            agent_id=self.agent_id,
            hop=task.hop,
            request_id=str(task.task_id),
        )
        child_result = await self.a2a_client.send(context, target_agent, child)
        return TaskResult(
            status=child_result.status,
            summary=summary,
            output=child_result.output,
            child_task_id=child.task_id,
        )
