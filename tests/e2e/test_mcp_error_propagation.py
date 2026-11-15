import asyncio
import json
from uuid import uuid4

import httpx
import pytest
from fastapi import FastAPI

from services.agent_runtime.app.a2a_client import A2AClient
from services.agent_runtime.app.mcp_adapter import GatewayMcpClient
from services.agent_runtime.app.planner import AgentRuntime, TaskInput
from services.gateway.app.mcp import McpProxy
from services.gateway.app.proxy import A2AProxy
from services.gateway.app.routes.a2a import build_router as a2a_router
from services.gateway.app.routes.mcp import build_router as mcp_router
from services.gateway.app.transport import HttpTransport
from services.mcp_fixtures.app.server import create_app
from shared.python.lab_core.contracts import CorrelationContext, ModelResponse


class ScriptedModel:
    def __init__(self, actions):
        self.actions = iter(actions)
        self.requests = []

    async def complete(self, request):
        self.requests.append(request)
        return ModelResponse(provider="test", model="scripted", output=next(self.actions))


def agent_app(runtime):
    app = FastAPI()

    @app.post("/a2a")
    async def send(request: dict):
        result = await runtime.handle_task(TaskInput.model_validate(request["params"]))
        return {"jsonrpc": "2.0", "id": request["id"], "result": result.model_dump(mode="json")}

    return app


@pytest.fixture
def run_chain(tmp_path, monkeypatch):
    monkeypatch.setenv("MCP_FILE_ROOT", str(tmp_path))
    (tmp_path / "example.txt").write_text("example file contents", encoding="utf-8")

    def run(worker_actions):
        apps = {}
        events = []

        async def dispatch(request):
            return await httpx.ASGITransport(
                app=apps[request.url.host], raise_app_exceptions=False
            ).handle_async_request(request)

        network = httpx.MockTransport(dispatch)
        worker_model = ScriptedModel(worker_actions)
        root = AgentRuntime(
            agent_id="root-agent",
            model=ScriptedModel([
                {"action": "delegate", "target_agent": "worker-agent", "summary": "delegate the read"}
            ]),
            a2a_client=A2AClient("http://gateway", transport=network),
            allowed_tools=set(),
        )
        worker = AgentRuntime(
            agent_id="worker-agent",
            model=worker_model,
            a2a_client=None,
            mcp_client=GatewayMcpClient("http://gateway", transport=network),
        )
        gateway = FastAPI()
        gateway.include_router(a2a_router(A2AProxy(
            {"root-agent": "http://root-agent", "worker-agent": "http://worker-agent"},
            transport=HttpTransport(network),
            event_sink=events.append,
        )))
        gateway.include_router(mcp_router(McpProxy(
            {"mcp-file-reader": "http://mcp-file-reader"},
            transport=HttpTransport(network),
            event_sink=events.append,
        )))
        apps.update({
            "gateway": gateway,
            "root-agent": agent_app(root),
            "worker-agent": agent_app(worker),
            "mcp-file-reader": create_app("file-tools"),
        })
        task = TaskInput(run_id=uuid4(), agent_id="root-agent", prompt="读取 missing.txt")
        context = CorrelationContext(
            run_id=task.run_id, task_id=task.task_id,
            agent_id="control-plane", request_id=str(uuid4()),
        )
        result = asyncio.run(A2AClient("http://gateway", transport=network).send(
            context, "root-agent", task
        ))
        return result, worker_model.requests, events

    return run


def read_file(path):
    return {
        "action": "mcp_call", "server_id": "mcp-file-reader", "tool_name": "read_file",
        "arguments": {"path": path},
    }


def test_missing_file_error_reaches_worker_model_and_outer_a2a_result(run_chain):
    result, requests, events = run_chain([
        read_file("missing.txt"),
        {"action": "answer", "summary": "无法读取 missing.txt：文件不存在。"},
    ])

    assert result.status == "completed"
    assert result.summary == "无法读取 missing.txt：文件不存在。"
    assert result.output["summary"] == "无法读取 missing.txt：文件不存在。"
    assert len(requests) == 2
    observation = requests[1].messages[-1]["content"]
    assert "file does not exist" in observation
    assert '"code": -32602' in observation
    outer = [event for event in events if event.context.agent_id == "control-plane"][-1]
    assert outer.operation == "message/send.response"
    assert outer.payload["result"]["output"]["summary"] == "无法读取 missing.txt：文件不存在。"


def test_worker_can_choose_a_new_path_after_mcp_error(run_chain):
    result, requests, events = run_chain([
        read_file("missing.txt"),
        read_file("example.txt"),
        {"action": "answer", "summary": "example file contents"},
    ])

    assert result.output["summary"] == "example file contents"
    assert len(requests) == 3
    assert "file does not exist" in requests[1].messages[-1]["content"]
    assert "example file contents" in requests[2].messages[-1]["content"]
    calls = [event for event in events if event.protocol == "mcp" and event.direction == "outbound"]
    assert [event.payload["params"]["arguments"]["path"] for event in calls] == [
        "missing.txt", "example.txt"
    ]


def test_child_failure_reason_reaches_root_instead_of_delegation_summary(run_chain):
    result, _, events = run_chain([{"action": "delegate", "summary": "missing target"}])

    assert result.status == "failed"
    assert "invalid model decision" in result.summary
    outer = [event for event in events if event.context.agent_id == "control-plane"][-1]
    assert outer.payload["result"]["status"] == "failed"
    assert "invalid model decision" in outer.payload["result"]["summary"]


def test_repeated_mcp_errors_remain_bounded_and_return_to_root(run_chain):
    result, requests, events = run_chain([read_file("missing.txt")] * 9)

    assert result.status == "blocked"
    assert result.summary == "maximum MCP tool steps exceeded"
    assert len(requests) == 9
    calls = [event for event in events if event.protocol == "mcp" and event.direction == "outbound"]
    assert len(calls) == 8


@pytest.mark.parametrize("operation", ["tools/call", "resources/read"])
def test_gateway_preserves_rpc_error_details_and_caller_id(operation):
    async def run():
        def upstream(request):
            payload = json.loads(request.content)
            return httpx.Response(200, json={
                "jsonrpc": "2.0", "id": payload["id"],
                "error": {"code": -32602, "message": "file does not exist", "data": {"path": "missing.txt"}},
            })

        gateway = FastAPI()
        gateway.include_router(mcp_router(McpProxy(
            {"files": "http://files"}, transport=HttpTransport(httpx.MockTransport(upstream))
        )))
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=gateway, raise_app_exceptions=False), base_url="http://gateway"
        ) as client:
            return await client.post("/mcp/files", headers={
                "x-lab-run-id": str(uuid4()), "x-lab-request-id": "read-request"
            }, json={
                "jsonrpc": "2.0", "id": "caller-17", "method": operation,
                "params": {"name": "read_file", "arguments": {"path": "missing.txt"}, "uri": "fixture://missing"},
            })

    response = asyncio.run(run())

    assert response.status_code == 200
    assert response.json() == {
        "jsonrpc": "2.0", "id": "caller-17",
        "error": {"code": -32602, "message": "file does not exist", "data": {"path": "missing.txt"}},
    }


@pytest.mark.parametrize("protocol", ["mcp", "a2a"])
@pytest.mark.parametrize("failure", ["http", "connection", "timeout"])
def test_transport_failure_returns_failed_task_instead_of_raising(protocol, failure):
    def upstream(request):
        if failure == "connection":
            raise httpx.ConnectError("connection refused", request=request)
        if failure == "timeout":
            raise httpx.ReadTimeout("timed out", request=request)
        return httpx.Response(503, text="upstream unavailable")

    network = httpx.MockTransport(upstream)
    decision = read_file("missing.txt") if protocol == "mcp" else {
        "action": "delegate", "target_agent": "worker-agent", "summary": "delegate the read"
    }
    runtime = AgentRuntime(
        agent_id="root-agent", model=ScriptedModel([decision]),
        a2a_client=A2AClient("http://gateway", transport=network),
        mcp_client=GatewayMcpClient("http://gateway", transport=network),
    )

    result = asyncio.run(runtime.handle_task(TaskInput(
        run_id=uuid4(), agent_id="root-agent", prompt="read a file"
    )))

    assert result.status == "failed"
    assert ("MCP" if protocol == "mcp" else "A2A") in result.summary
    assert ("timed out" if failure == "timeout" else "failed") in result.summary
