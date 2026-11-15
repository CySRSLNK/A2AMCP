from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel

from shared.python.lab_core.contracts import CorrelationContext


class PolicyDecision(BaseModel):
    outcome: Literal["allow", "deny", "approval_required"]
    rule_id: str
    reason: str


class PolicyEngine:
    def __init__(
        self,
        *,
        allowed_targets: set[str] | None = None,
        max_hop: int = 8,
        max_payload_bytes: int = 256 * 1024,
        approval_operations: set[str] | None = None,
        allow_dynamic_targets: bool = False,
    ):
        self.allowed_targets = allowed_targets or set()
        self.max_hop = max_hop
        self.max_payload_bytes = max_payload_bytes
        self.approval_operations = approval_operations or set()
        self.allow_dynamic_targets = allow_dynamic_targets

    def evaluate(
        self,
        context: CorrelationContext,
        operation: str,
        target: str,
        payload_summary: Any,
    ) -> PolicyDecision:
        if target not in self.allowed_targets and not self.allow_dynamic_targets:
            return PolicyDecision(outcome="deny", rule_id="target-allowlist", reason="target is not allowed")
        if context.hop > self.max_hop:
            return PolicyDecision(outcome="deny", rule_id="max-hop", reason="delegation depth exceeded")
        if len(repr(payload_summary).encode("utf-8")) > self.max_payload_bytes:
            return PolicyDecision(outcome="deny", rule_id="payload-limit", reason="payload too large")
        if operation in self.approval_operations:
            return PolicyDecision(
                outcome="approval_required",
                rule_id="operator-approval",
                reason="operation requires operator approval",
            )
        return PolicyDecision(outcome="allow", rule_id="default-allow", reason="policy allows operation")
