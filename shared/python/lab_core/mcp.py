from typing import Any


class McpRpcError(RuntimeError):
    """Keep an MCP error intact while passing through the gateway and agent."""

    def __init__(self, error: dict[str, Any]):
        self.error = error
        super().__init__(error.get("message", "MCP request failed"))
