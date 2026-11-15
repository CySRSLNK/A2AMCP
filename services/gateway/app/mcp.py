from __future__ import annotations

from collections.abc import Callable
from itertools import count
from typing import Any

import httpx

from shared.python.lab_core.contracts import CorrelationContext, EventDraft
from shared.python.lab_core.mcp import McpRpcError

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
        runtime_config_client=None,
    ):
        self.registry = {key: value.rstrip("/") for key, value in registry.items()}
        self.transport = transport or HttpTransport()
        self.policy_engine = policy_engine
        self.event_sink = event_sink
        self.runtime_config_client = runtime_config_client
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
        base_url = self.registry.get(server_id)
        if base_url is None and self.runtime_config_client is None:
            raise ValueError(f"unknown MCP server: {server_id}")
        server_config = None
        if self.runtime_config_client is not None:
            snapshot = await self.runtime_config_client.get_snapshot(str(context.run_id))
            server_config = next(
                (item for item in snapshot.get("mcp_servers", []) if item.get("id") == server_id),
                None,
            )
            if server_config is None or not server_config.get("enabled", False):
                raise ValueError(f"MCP server is not enabled: {server_id}")
            capabilities = set(server_config.get("capabilities", []))
            if method != "initialize" and method not in capabilities:
                raise PermissionError(f"MCP operation is not allowed: {method}")
            if method == "tools/call" and server_config.get("allowed_tools"):
                tool_name = params.get("name")
                if tool_name not in set(server_config["allowed_tools"]):
                    raise PermissionError(f"MCP tool is not allowed: {tool_name}")
            base_url = str(server_config["endpoint"]).rstrip("/")
        operation = policy_operation or method
        if self.policy_engine is not None:
            decision = self.policy_engine.evaluate(context, operation, server_id, params)
            if decision.outcome != "allow":
                raise PermissionError(decision.reason)
        rpc_id = next(self._ids)
        payload = {"jsonrpc": "2.0", "id": rpc_id, "method": method, "params": params}
        self._emit(context, operation, "outbound", payload, f"rpc-{rpc_id}:request")
        response = await self.transport.request(
            "POST", f"{base_url}/mcp", context=context, payload=payload
        )
        response.raise_for_status()
        body = response.json()
        self._emit(
            context,
            operation,
            "inbound",
            body.get("result", body),
            f"rpc-{rpc_id}:response",
        )
        if "error" in body:
            raise McpRpcError(body["error"])
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
