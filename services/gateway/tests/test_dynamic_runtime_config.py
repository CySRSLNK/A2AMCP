import asyncio

import httpx

from shared.python.lab_core.contracts import CorrelationContext
from services.gateway.app.mcp import McpProxy
from services.gateway.app.routes.model import ModelProxy
from services.gateway.app.transport import HttpTransport


class SnapshotClient:
    async def get_snapshot(self, run_id: str) -> dict:
        return {
            "model": {"base_url": "https://dynamic-model", "request_timeout": 20},
            "mcp_servers": [
                {
                    "id": "dynamic-tools",
                    "endpoint": "http://dynamic-mcp:8200",
                    "enabled": True,
                    "capabilities": ["tools/call"],
                    "allowed_tools": ["calculator"],
                }
            ],
        }


def test_model_proxy_uses_snapshot_credentials_without_static_key():
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url == httpx.URL("https://dynamic-model/v1/chat/completions")
        assert request.headers["authorization"] == "Bearer snapshot-key"
        assert "x-lab-run-id" not in request.headers
        return httpx.Response(200, json={"choices": []})

    class Client(SnapshotClient):
        async def get_snapshot(self, run_id: str) -> dict:
            snapshot = await super().get_snapshot(run_id)
            snapshot["api_key"] = "snapshot-key"
            return snapshot

    response = asyncio.run(
        ModelProxy(
            "https://static-model",
            "static-key",
            transport=httpx.MockTransport(handler),
            runtime_config_client=Client(),
        ).forward({}, "run-1")
    )
    assert response.status_code == 200


def test_mcp_proxy_uses_snapshot_server_and_rejects_unlisted_tools():
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url == httpx.URL("http://dynamic-mcp:8200/mcp")
        payload = httpx.Response(200, content=request.read()).json()
        return httpx.Response(
            200,
            json={"jsonrpc": "2.0", "id": payload["id"], "result": {"content": [{"text": "3"}]}},
        )

    proxy = McpProxy(
        {},
        transport=HttpTransport(httpx.MockTransport(handler)),
        runtime_config_client=SnapshotClient(),
    )
    context = CorrelationContext(run_id="00000000-0000-0000-0000-000000000001", request_id="r1")
    result = asyncio.run(proxy.call_tool(context, "dynamic-tools", "calculator", {"a": 1, "b": 2}))
    assert result["content"][0]["text"] == "3"

    try:
        asyncio.run(proxy.call_tool(context, "dynamic-tools", "shell", {}))
    except PermissionError as exc:
        assert "not allowed" in str(exc)
    else:
        raise AssertionError("unlisted dynamic tool was forwarded")
