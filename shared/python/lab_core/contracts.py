from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Literal
from uuid import UUID, uuid4

from pydantic import BaseModel, Field


class CorrelationContext(BaseModel):
    run_id: UUID
    task_id: UUID | None = None
    parent_task_id: UUID | None = None
    agent_id: str | None = None
    hop: int = Field(default=0, ge=0)
    request_id: str


class EventDraft(BaseModel):
    event_id: UUID = Field(default_factory=uuid4)
    context: CorrelationContext
    protocol: Literal["a2a", "mcp", "model", "policy", "artifact", "run"]
    operation: str
    direction: Literal["inbound", "outbound", "internal"]
    payload: Any = None
    policy_decision: dict[str, Any] | None = None
    fault_action: dict[str, Any] | None = None
    source_event_key: str | None = None
    occurred_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class ProtocolEvent(EventDraft):
    sequence: int = Field(ge=1)


class ModelRequest(BaseModel):
    provider: str
    model: str
    messages: list[dict[str, Any]]
    metadata: dict[str, Any] = Field(default_factory=dict)
    replay_key: str | None = None


class ModelResponse(BaseModel):
    provider: str
    model: str
    output: dict[str, Any]
    usage: dict[str, Any] = Field(default_factory=dict)
    replay_key: str | None = None
