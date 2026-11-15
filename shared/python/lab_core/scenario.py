from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class AgentSpec(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str
    role: str = "worker"
    endpoint: str | None = None
    capabilities: list[str] = Field(default_factory=list)


class McpServerSpec(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str
    endpoint: str | None = None
    capabilities: list[str] = Field(default_factory=list)


class Scenario(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str
    version: int = Field(default=1, ge=1)
    description: str | None = None
    agents: list[AgentSpec]
    mcp_servers: list[McpServerSpec] = Field(default_factory=list)
    policy_profile: dict[str, Any] = Field(default_factory=dict)
    model_provider: dict[str, Any] = Field(default_factory=dict)
    fault_profile: dict[str, Any] = Field(default_factory=dict)


class ScenarioLoader:
    def __init__(
        self,
        *,
        allowed_agents: set[str] | None = None,
        allowed_mcp_servers: set[str] | None = None,
    ) -> None:
        self.allowed_agents = allowed_agents
        self.allowed_mcp_servers = allowed_mcp_servers

    def load(self, document: dict[str, Any]) -> Scenario:
        try:
            scenario = Scenario.model_validate(document)
        except Exception as exc:
            message = str(exc)
            if "Extra inputs are not permitted" in message:
                raise ValueError(f"unknown field in scenario: {message}") from exc
            raise ValueError(f"invalid scenario: {message}") from exc

        agent_ids = [agent.id for agent in scenario.agents]
        if len(agent_ids) != len(set(agent_ids)):
            raise ValueError("duplicate agent registration")
        mcp_ids = [server.id for server in scenario.mcp_servers]
        if len(mcp_ids) != len(set(mcp_ids)):
            raise ValueError("duplicate MCP registration")
        if self.allowed_agents is not None:
            unknown = set(agent_ids) - self.allowed_agents
            if unknown:
                raise ValueError(f"unknown agent registration: {sorted(unknown)}")
        if self.allowed_mcp_servers is not None:
            unknown = set(mcp_ids) - self.allowed_mcp_servers
            if unknown:
                raise ValueError(f"unknown MCP registration: {sorted(unknown)}")
        return scenario
