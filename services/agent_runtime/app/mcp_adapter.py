from __future__ import annotations

from typing import Any

import httpx

from shared.python.lab_core.correlation import context_headers
from shared.python.lab_core.contracts import CorrelationContext


class GatewayMcpClient:
    def __init__(
        self,
        gateway_base_url: str,
        *,
        transport: httpx.AsyncBaseTransport | None = None,
        timeout: float = 60.0,
    ):
        self.gateway_base_url = gateway_base_url.rstrip("/")
        self.transport = transport
        self.timeout = timeout
        self._request_id = 0

    async def call_tool(
        self, context: CorrelationContext, server_id: str, name: str, arguments: dict[str, Any]
    ) -> dict[str, Any]:
        return await self._request(
            context, server_id, "tools/call", {"name": name, "arguments": arguments}
        )

    async def read_resource(
        self, context: CorrelationContext, server_id: str, uri: str
    ) -> dict[str, Any]:
        return await self._request(context, server_id, "resources/read", {"uri": uri})

    async def _request(
        self, context: CorrelationContext, server_id: str, method: str, params: dict[str, Any]
    ) -> dict[str, Any]:
        self._request_id += 1
        body = {"jsonrpc": "2.0", "id": self._request_id, "method": method, "params": params}
        async with httpx.AsyncClient(transport=self.transport, timeout=self.timeout) as client:
            response = await client.post(
                f"{self.gateway_base_url}/mcp/{server_id}",
                headers=context_headers(context),
                json=body,
            )
        response.raise_for_status()
        result = response.json()
        if "error" in result:
            raise RuntimeError(result["error"].get("message", "MCP request failed"))
        return result["result"]
