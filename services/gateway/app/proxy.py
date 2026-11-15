from __future__ import annotations

from collections.abc import AsyncIterator
from collections.abc import Callable
from typing import Any

import httpx

from shared.python.lab_core.contracts import CorrelationContext, EventDraft

from .policies import PolicyEngine
from .transport import HttpTransport


SUPPORTED_OPERATIONS = {
    "message/send": "POST",
    "tasks/get": "POST",
    "tasks/cancel": "POST",
    "message/stream": "POST",
}


class A2AProxy:
    def __init__(
        self,
        registry: dict[str, str],
        *,
        transport: HttpTransport | None = None,
        event_sink: Callable[[EventDraft], None] | None = None,
        policy_engine: PolicyEngine | None = None,
    ):
        self.registry = {key: value.rstrip("/") for key, value in registry.items()}
        self.transport = transport or HttpTransport()
        self.event_sink = event_sink
        self.policy_engine = policy_engine

    async def forward_card(self, agent_id: str) -> httpx.Response:
        return await self.transport.request(
            "GET",
            f"{self._base_url(agent_id)}/.well-known/agent-card.json",
            context=self._card_context(agent_id),
        )

    async def forward_send(
        self, context: CorrelationContext, request: dict[str, Any], agent_id: str
    ) -> httpx.Response:
        return await self.forward(context, request, agent_id)

    async def forward_get(
        self, context: CorrelationContext, request: dict[str, Any], agent_id: str
    ) -> httpx.Response:
        return await self.forward(context, request, agent_id)

    async def forward_cancel(
        self, context: CorrelationContext, request: dict[str, Any], agent_id: str
    ) -> httpx.Response:
        return await self.forward(context, request, agent_id)

    async def forward(
        self, context: CorrelationContext, request: dict[str, Any], agent_id: str
    ) -> httpx.Response:
        operation = request.get("method")
        if operation not in SUPPORTED_OPERATIONS or operation == "message/stream":
            raise ValueError(f"unsupported operation: {operation}")
        self._check_policy(context, operation, agent_id, request)
        self._emit(context, f"{operation}.request", "outbound", request, "request")
        response = await self.transport.request(
            SUPPORTED_OPERATIONS[operation],
            f"{self._base_url(agent_id)}/a2a",
            context=context,
            payload=request,
        )
        response.raise_for_status()
        try:
            response_payload: Any = response.json()
        except ValueError:
            response_payload = response.text
        self._emit(context, f"{operation}.response", "inbound", response_payload, "response")
        return response

    async def forward_stream(
        self, context: CorrelationContext, request: dict[str, Any], agent_id: str
    ) -> AsyncIterator[bytes]:
        if request.get("method") != "message/stream":
            raise ValueError(f"unsupported operation: {request.get('method')}")
        self._check_policy(context, "message/stream", agent_id, request)
        async for chunk in self.transport.stream(
            "POST", f"{self._base_url(agent_id)}/a2a", context=context, payload=request
        ):
            yield chunk

    def _base_url(self, agent_id: str) -> str:
        try:
            return self.registry[agent_id]
        except KeyError as exc:
            raise ValueError(f"unknown agent: {agent_id}") from exc

    def _emit(
        self,
        context: CorrelationContext,
        operation: str,
        direction: str,
        payload: Any,
        suffix: str,
    ) -> None:
        if self.event_sink is None:
            return
        self.event_sink(
            EventDraft(
                context=context,
                protocol="a2a",
                operation=operation,
                direction=direction,
                payload=payload,
                source_event_key=f"{context.request_id}:{operation}:{suffix}",
            )
        )

    def _check_policy(
        self, context: CorrelationContext, operation: str, agent_id: str, payload: Any
    ) -> None:
        if self.policy_engine is None:
            return
        decision = self.policy_engine.evaluate(context, operation, agent_id, payload)
        if decision.outcome != "allow":
            raise PermissionError(decision.reason)

    @staticmethod
    def _card_context(agent_id: str) -> CorrelationContext:
        from uuid import uuid4

        return CorrelationContext(run_id=uuid4(), request_id=f"card-{agent_id}")
