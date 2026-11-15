from __future__ import annotations

from typing import Any, Literal
from uuid import UUID, uuid4

import httpx
from pydantic import BaseModel, ConfigDict, Field, ValidationError, model_validator

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
    policy: dict[str, Any] = Field(default_factory=dict)


class AgentDecision(BaseModel):
    model_config = ConfigDict(extra="forbid")

    action: Literal["answer", "delegate", "mcp_call"]
    summary: str = Field(default="", max_length=2000)
    target_agent: str | None = Field(default=None, max_length=64)
    server_id: str | None = Field(default=None, max_length=64)
    tool_name: str | None = Field(default=None, max_length=96)
    arguments: dict[str, Any] = Field(default_factory=dict)

    @model_validator(mode="after")
    def validate_action_fields(self) -> "AgentDecision":
        if self.action == "delegate" and not self.target_agent:
            raise ValueError("delegate action requires target_agent")
        if self.action == "mcp_call" and not self.server_id:
            raise ValueError("mcp_call action requires server_id")
        if self.action == "mcp_call" and not self.tool_name:
            raise ValueError("mcp_call action requires tool_name")
        return self


def _normalize_model_decision(output: dict[str, Any]) -> dict[str, Any]:
    """Accept common provider aliases while validating one canonical action schema."""
    normalized = dict(output)
    aliases = {
        "action": "type",
        "target_agent": "target",
        "server_id": "server",
        "tool_name": "tool",
    }
    for canonical, alias in aliases.items():
        if canonical not in normalized and alias in normalized:
            normalized[canonical] = normalized.pop(alias)
    return normalized


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
        model_provider: str = "mock",
        model_name: str = "lab-agent",
        allowed_targets: set[str] | None = None,
        allowed_mcp_servers: set[str] | None = None,
        allowed_tools: set[str] | None = None,
    ):
        self.agent_id = agent_id
        self.model = model
        self.a2a_client = a2a_client
        self.mcp_client = mcp_client
        self.max_hop = max_hop
        self.model_provider = model_provider
        self.model_name = model_name
        self.allowed_targets = (
            {"root-agent", "worker-agent"} if allowed_targets is None else set(allowed_targets)
        )
        self.allowed_mcp_servers = (
            {"mcp-tools", "mcp-resources"}
            if allowed_mcp_servers is None
            else set(allowed_mcp_servers)
        )
        self.allowed_tools = (
            {"calculator", "fixture_http_get"} if allowed_tools is None else set(allowed_tools)
        )

    async def handle_task(self, task: TaskInput) -> TaskResult:
        effective_max_hop = min(self.max_hop, int(task.policy.get("max_hop", self.max_hop)))
        if task.hop >= effective_max_hop:
            return TaskResult(status="blocked", summary="maximum delegation depth exceeded")
        if task.delegation_edges.count(f"{self.agent_id}->{self.agent_id}") > 1:
            return TaskResult(status="blocked", summary="repeated delegation edge detected")
        try:
            response = await self.model.complete(
                ModelRequest(
                    provider=self.model_provider,
                    model=self.model_name,
                    messages=self._messages(task),
                    metadata={
                        "role": "root" if self.agent_id == "root-agent" else "worker",
                        "agent_id": self.agent_id,
                        "hop": task.hop,
                        "allowed_targets": sorted(self._allowed_targets(task)),
                        "allowed_mcp_servers": sorted(self.allowed_mcp_servers),
                        "allowed_tools": sorted(self._allowed_tools(task)),
                    },
                )
            )
            decision = AgentDecision.model_validate(_normalize_model_decision(response.output))
        except httpx.TimeoutException:
            return TaskResult(status="failed", summary="model request timed out")
        except (ValidationError, ValueError) as exc:
            return TaskResult(status="failed", summary=f"invalid model decision: {exc}")

        if decision.action == "answer":
            return TaskResult(
                status="completed",
                summary=decision.summary,
                output=decision.model_dump(mode="json"),
            )
        if decision.action == "mcp_call":
            if self.mcp_client is None:
                return TaskResult(status="blocked", summary="MCP client is not configured")
            if decision.server_id not in self.allowed_mcp_servers:
                return TaskResult(status="blocked", summary="MCP server is not allowed")
            if decision.tool_name not in self._allowed_tools(task):
                return TaskResult(status="blocked", summary="MCP tool is not allowed")
            context = CorrelationContext(
                run_id=task.run_id,
                task_id=task.task_id,
                parent_task_id=task.parent_task_id,
                agent_id=self.agent_id,
                hop=task.hop,
                request_id=str(task.task_id),
            )
            try:
                result = await self.mcp_client.call_tool(
                    context,
                    decision.server_id,
                    decision.tool_name,
                    decision.arguments,
                )
            except httpx.TimeoutException:
                return TaskResult(status="failed", summary="MCP request timed out")
            return TaskResult(status="completed", summary=decision.summary, output=result)

        target_agent = decision.target_agent
        if target_agent not in self._allowed_targets(task):
            return TaskResult(status="blocked", summary="target agent is not allowed")
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
        try:
            child_result = await self.a2a_client.send(context, target_agent, child)
        except httpx.TimeoutException:
            return TaskResult(status="failed", summary="A2A delegation request timed out")
        return TaskResult(
            status=child_result.status,
            summary=decision.summary,
            output=child_result.output,
            child_task_id=child.task_id,
        )

    def _allowed_targets(self, task: TaskInput) -> set[str]:
        configured = set(task.policy.get("allowed_targets", []))
        return self.allowed_targets & configured if configured else set(self.allowed_targets)

    def _allowed_tools(self, task: TaskInput) -> set[str]:
        configured = set(task.policy.get("allowed_tools", []))
        return self.allowed_tools & configured if configured else set(self.allowed_tools)

    def _messages(self, task: TaskInput) -> list[dict[str, str]]:
        targets = ", ".join(sorted(self._allowed_targets(task))) or "none"
        servers = ", ".join(sorted(self.allowed_mcp_servers)) or "none"
        tools = ", ".join(sorted(self._allowed_tools(task))) or "none"
        tool_contracts = []
        if "calculator" in self._allowed_tools(task):
            tool_contracts.append(
                'calculator arguments: {"operation":"add|multiply","a":number,"b":number}'
            )
        if "fixture_http_get" in self._allowed_tools(task):
            tool_contracts.append(
                'fixture_http_get arguments: {"url":"fixture://..."}'
            )
        contracts = " ".join(tool_contracts) or "none"
        chain = " -> ".join([*task.delegation_edges, self.agent_id]) or self.agent_id
        system = (
            "You are an agent in a mediated A2A/MCP security lab. "
            "Analyze the task and return exactly one JSON object, with no markdown. "
            "Allowed actions are answer, delegate, and mcp_call. "
            f"Your agent id is {self.agent_id}; current hop is {task.hop}. "
            f"Current delegation chain is {chain}. "
            f"Allowed target agents: {targets}. Allowed MCP servers: {servers}. "
            f"Allowed MCP tools: {tools}. Tool contracts: {contracts}. "
            "Use exactly these field names: action, summary, target_agent, server_id, tool_name, arguments. "
            "For delegate use target_agent. For mcp_call use server_id, tool_name, and arguments. "
            "Do not use aliases such as type, server, or tool. "
            "Never invent targets, servers, tools, credentials, or network destinations. "
            "Return a concise summary in the summary field."
        )
        return [
            {"role": "system", "content": system},
            {"role": "user", "content": task.prompt},
        ]
