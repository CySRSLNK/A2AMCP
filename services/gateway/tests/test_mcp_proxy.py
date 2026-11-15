import asyncio

import httpx

from shared.python.lab_core.contracts import CorrelationContext
from services.gateway.app.mcp import McpProxy
from services.gateway.app.policies import PolicyEngine
from services.gateway.app.transport import HttpTransport


def proxy_for(handler, policy=None):
    return McpProxy(
        {"mcp-tools": "http://mcp-tools:8200"},
        transport=HttpTransport(httpx.MockTransport(handler)),
        policy_engine=policy,
    )


def context():
    return CorrelationContext(run_id="00000000-0000-0000-0000-000000000001", request_id="mcp-1")


def test_mcp_proxy_initializes_lists_tools_and_calls_tool():
    methods = []

    def handler(request: httpx.Request) -> httpx.Response:
        body = request.read()
        payload = httpx.Response(200, content=body).json()
        methods.append(payload["method"])
        if payload["method"] == "initialize":
            result = {"protocolVersion": "2025-06-18", "capabilities": {"tools": {}}}
        elif payload["method"] == "tools/list":
            result = {"tools": [{"name": "add", "description": "Add", "inputSchema": {}}]}
        else:
            result = {"content": [{"type": "text", "text": "3"}]}
        return httpx.Response(200, json={"jsonrpc": "2.0", "id": payload["id"], "result": result})

    proxy = proxy_for(handler)
    tools = asyncio.run(proxy.list_tools(context(), "mcp-tools"))
    result = asyncio.run(proxy.call_tool(context(), "mcp-tools", "add", {"a": 1, "b": 2}))

    assert methods == ["initialize", "tools/list", "tools/call"]
    assert tools["tools"][0]["name"] == "add"
    assert result["content"][0]["text"] == "3"


def test_mcp_proxy_reads_resources_and_applies_tool_policy():
    def handler(request: httpx.Request) -> httpx.Response:
        payload = httpx.Response(200, content=request.read()).json()
        return httpx.Response(
            200,
            json={
                "jsonrpc": "2.0",
                "id": payload["id"],
                "result": {"contents": [{"uri": "fixture://notes", "text": "safe"}]},
            },
        )

    policy = PolicyEngine(allowed_targets={"mcp-tools"}, approval_operations={"tools/call:add"})
    proxy = proxy_for(handler, policy=policy)

    resource = asyncio.run(proxy.read_resource(context(), "mcp-tools", "fixture://notes"))

    assert resource["contents"][0]["text"] == "safe"
    try:
        asyncio.run(proxy.call_tool(context(), "mcp-tools", "add", {"a": 1, "b": 2}))
    except PermissionError as exc:
        assert "approval" in str(exc)
    else:
        raise AssertionError("approval-required tool call was forwarded")
