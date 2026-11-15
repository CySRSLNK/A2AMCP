from __future__ import annotations

import re
from collections.abc import Iterator
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator


ProtocolPath = Literal["cross-mcp", "a2a-mcp"]
ObservableProtocol = Literal["a2a", "mcp"]
Direction = Literal["inbound", "outbound"]
ExpectedDecision = Literal["allow", "deny", "approval_required", "descriptive"]

_UNSAFE_TEXT_PATTERNS = (
    re.compile(r"\b[a-z][a-z0-9+.-]{1,31}://", re.IGNORECASE),
    re.compile(r"\b[a-z][a-z0-9+.-]{1,31}%3a%2f%2f", re.IGNORECASE),
    re.compile(r"\b(?:\d{1,3}\.){3}\d{1,3}(?::\d{1,5})?\b"),
    re.compile(r"\b(?:rm\s+-rf|curl\s|wget\s|bash\s+-c|sh\s+-c|powershell(?:\.exe)?\s)", re.IGNORECASE),
    re.compile(r"\b(?:python(?:3)?|node)\s+-c\b", re.IGNORECASE),
    re.compile(r"\b(?:nc|netcat)\s+(?:\d{1,3}\.){3}\d{1,3}\b", re.IGNORECASE),
    re.compile(r"\b(?:javascript|data):", re.IGNORECASE),
    re.compile(r"\bBearer\s+[A-Za-z0-9._-]+", re.IGNORECASE),
    re.compile(r"\b(?:api[_-]?key|password|secret)\s*[:=]", re.IGNORECASE),
)
_A2A_EVENT_OPERATION = re.compile(
    r"^(?:message/send|tasks/get|tasks/cancel)\.(?:request|response)$"
)
_MCP_EVENT_OPERATION = re.compile(
    r"^(?:tools/list|resources/read|tools/call:[A-Za-z0-9][A-Za-z0-9._-]{0,63})$"
)


def _iter_text(value: Any) -> Iterator[str]:
    if isinstance(value, str):
        yield value
        return
    if isinstance(value, dict):
        for key, item in value.items():
            yield from _iter_text(key)
            yield from _iter_text(item)
        return
    if isinstance(value, list):
        for item in value:
            yield from _iter_text(item)


class SourceRef(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str = Field(min_length=1, max_length=96)
    kind: Literal["taxonomy", "benchmark", "research", "advisory", "scanner"]


class Preconditions(BaseModel):
    model_config = ConfigDict(extra="forbid")

    required_agents: list[str] = Field(default_factory=list)
    required_mcp_servers: list[str] = Field(default_factory=list)
    required_capabilities: list[str] = Field(default_factory=list)
    required_policy: dict[str, Any] = Field(default_factory=dict)


class InjectionPoint(BaseModel):
    model_config = ConfigDict(extra="forbid")

    component: Literal[
        "agent_card",
        "a2a_message",
        "a2a_artifact",
        "mcp_tool_description",
        "mcp_tool_result",
        "mcp_resource",
        "credential",
        "task_state",
    ]
    trust_boundary: str = Field(min_length=1, max_length=120)
    input_kind: Literal[
        "metadata",
        "message",
        "artifact",
        "tool_description",
        "tool_result",
        "resource",
        "credential",
        "task_state",
    ]


class EventExpectation(BaseModel):
    model_config = ConfigDict(extra="forbid")

    protocol: ObservableProtocol
    operation: str = Field(min_length=1, max_length=128)
    direction: Direction
    actor: str | None = Field(default=None, max_length=64)
    target: str | None = Field(default=None, max_length=128)
    relation: Literal["required", "optional"] = "required"
    min_count: int = Field(default=1, ge=0, le=100)

    @model_validator(mode="after")
    def validate_operation(self) -> "EventExpectation":
        pattern = _A2A_EVENT_OPERATION if self.protocol == "a2a" else _MCP_EVENT_OPERATION
        if pattern.fullmatch(self.operation) is None:
            raise ValueError(
                f"unsupported observable {self.protocol} event operation: {self.operation}"
            )
        return self


class Oracle(BaseModel):
    model_config = ConfigDict(extra="forbid")

    observable: list[str] = Field(min_length=1)
    expected_decision: ExpectedDecision = "descriptive"


class AttackCase(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str = Field(pattern=r"^[A-Z0-9][A-Z0-9-]+$", max_length=64)
    version: int = Field(ge=1)
    protocol_path: ProtocolPath
    runnable: bool = False
    fixture_scenario_id: str | None = None
    category: str = Field(min_length=1, max_length=96)
    title: str = Field(min_length=1, max_length=160)
    summary: str = Field(min_length=1, max_length=500)
    sources: list[SourceRef] = Field(min_length=1)
    preconditions: Preconditions = Field(default_factory=Preconditions)
    injection_point: InjectionPoint
    expected_events: list[EventExpectation] = Field(min_length=1)
    impact: str = Field(min_length=1, max_length=160)
    oracle: Oracle
    safe_fixture: Literal["local-only"]
    dry_run_prompt: str = Field(min_length=1, max_length=500)
    mitigations: list[str] = Field(default_factory=list)
    notes: list[str] = Field(default_factory=list)

    @model_validator(mode="after")
    def validate_fixture_reference(self) -> "AttackCase":
        if self.runnable and not self.fixture_scenario_id:
            raise ValueError("runnable attack case requires fixture_scenario_id")
        if not self.runnable and self.fixture_scenario_id:
            raise ValueError("descriptive attack case cannot declare fixture_scenario_id")
        return self


class AttackCatalog(BaseModel):
    model_config = ConfigDict(extra="forbid")

    version: int = Field(ge=1)
    cases: list[AttackCase] = Field(min_length=1)


class AttackCatalogLoader:
    def load(self, document: dict[str, Any]) -> AttackCatalog:
        try:
            catalog = AttackCatalog.model_validate(document)
        except Exception as exc:
            raise ValueError(f"invalid attack catalog: {exc}") from exc

        seen: set[tuple[str, int]] = set()
        for case in catalog.cases:
            key = (case.id, case.version)
            if key in seen:
                raise ValueError(f"duplicate attack case: {case.id} v{case.version}")
            seen.add(key)
            self._validate_text(case)
        return catalog

    def _validate_text(self, case: AttackCase) -> None:
        for value in _iter_text(case.model_dump(mode="json")):
            if any(pattern.search(value) for pattern in _UNSAFE_TEXT_PATTERNS):
                raise ValueError(f"unsafe attack catalog text in {case.id}")

