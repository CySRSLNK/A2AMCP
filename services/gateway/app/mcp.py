from __future__ import annotations

from collections.abc import Callable
from itertools import count
from typing import Any

import httpx

from shared.python.lab_core.contracts import CorrelationContext, EventDraft

from .policies import PolicyEngine
from .transport import HttpTransport


class McpProxy:
    def __init__(
        self,
        registry: dict[str, str],
        *,
        transport: HttpTransport | None = None,
        policy_engine: PolicyEngine | None = None,
        event_sink: Callable[[EventDraft], None] | None = None,
    ):
        self.registry = {key: value.rstrip("/") for key, value in registry.items()}
        self.transport = transport or HttpTransport()
        self.policy_engine = policy_engine
        self.event_sink = event_sink
        self._ids = count(1)

    async def initialize(self, context: CorrelationContext, server_id: str) -> dict[str, Any]:
        return await self._rpc(context, server_id, "initialize", {})

    async def list_tools(self, context: CorrelationContext, server_id: str) -> dict[str, Any]:
        await self.initialize(context, server_id)
        return await self._rpc(context, server_id, "tools/list", {})

    async def call_tool(
        self, context: CorrelationContext, server_id: str, name: str, arguments: dict[str, Any]
    ) -> dict[str, Any]:
        return await self._rpc(
            context,
            server_id,
            "tools/call",
            {"name": name, "arguments": arguments},
            policy_operation=f"tools/call:{name}",
        )

    async def read_resource(
        self, context: CorrelationContext, server_id: str, uri: str
    ) -> dict[str, Any]:
        return await self._rpc(context, server_id, "resources/read", {"uri": uri})

    async def _rpc(
        self,
        context: CorrelationContext,
        server_id: str,
        method: str,
        params: dict[str, Any],
        *,
        policy_operation: str | None = None,
    ) -> dict[str, Any]:
        try:
            base_url = self.registry[server_id]
        except KeyError as exc:
            raise ValueError(f"unknown MCP server: {server_id}") from exc
        operation = policy_operation or method
        if self.policy_engine is not None:
            decision = self.policy_engine.evaluate(context, operation, server_id, params)
            if decision.outcome != "allow":
                raise PermissionError(decision.reason)
        payload = {"jsonrpc": "2.0", "id": next(self._ids), "method": method, "params": params}
        self._emit(context, operation, "outbound", payload, "request")
        response = await self.transport.request(
            "POST", f"{base_url}/mcp", context=context, payload=payload
        )
        response.raise_for_status()
        body = response.json()
        self._emit(context, operation, "inbound", body.get("result", body), "response")
        if "error" in body:
            raise RuntimeError(body["error"].get("message", "MCP request failed"))
        return body["result"]

    def _emit(
        self,
        context: CorrelationContext,
        operation: str,
        direction: str,
        payload: Any,
        suffix: str,
    ) -> None:
        if self.event_sink is not None:
            self.event_sink(
                EventDraft(
                    context=context,
                    protocol="mcp",
                    operation=operation,
                    direction=direction,
                    payload=payload,
                    source_event_key=f"{context.request_id}:{operation}:{suffix}",
                )
            )
