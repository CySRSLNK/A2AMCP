from __future__ import annotations

from copy import deepcopy
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class PolicySnapshot(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    version: int = Field(default=1, ge=1)
    max_hop: int = Field(default=3, ge=0)
    allowed_tools: list[str] = Field(default_factory=list)
    allowed_targets: list[str] = Field(default_factory=list)
    approval_required: list[str] = Field(default_factory=list)
    payload_limit: int = Field(default=1_048_576, ge=1)


def freeze_policy(source: dict[str, Any] | PolicySnapshot) -> PolicySnapshot:
    if isinstance(source, PolicySnapshot):
        return source.model_copy(deep=True)
    return PolicySnapshot.model_validate(deepcopy(source))
