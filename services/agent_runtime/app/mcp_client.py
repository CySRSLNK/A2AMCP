from __future__ import annotations

from typing import Any


class McpClient:
    async def call_tool(self, server_id: str, name: str, arguments: dict[str, Any]) -> dict[str, Any]:
        raise NotImplementedError("MCP adapter is added in Task 5")

    async def read_resource(self, server_id: str, uri: str) -> dict[str, Any]:
        raise NotImplementedError("MCP adapter is added in Task 5")
