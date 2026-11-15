import asyncio

import httpx

from shared.python.lab_core.contracts import CorrelationContext
from services.gateway.app.policies import PolicyEngine
from services.gateway.app.proxy import A2AProxy
from services.gateway.app.transport import HttpTransport


def test_proxy_preserves_json_rpc_and_correlation_headers():
    seen = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["url"] = str(request.url)
        seen["headers"] = dict(request.headers)
        seen["json"] = httpx.Response(200, content=request.content).json()
        return httpx.Response(200, json={"jsonrpc": "2.0", "id": 7, "result": {"ok": True}})

    transport = HttpTransport(httpx.MockTransport(handler))
    proxy = A2AProxy({"worker": "http://worker:8100"}, transport=transport)
    ctx = CorrelationContext(run_id="00000000-0000-0000-0000-000000000001", request_id="req-1")
    request = {"jsonrpc": "2.0", "id": 7, "method": "message/send", "params": {"text": "hi"}}

    response = asyncio.run(proxy.forward_send(ctx, request, "worker"))

    assert response.status_code == 200
    assert seen["json"] == request
    assert seen["headers"]["x-lab-run-id"] == str(ctx.run_id)
    assert seen["headers"]["x-lab-request-id"] == "req-1"


def test_policy_engine_denies_unknown_target_and_excessive_hop():
    engine = PolicyEngine(allowed_targets={"worker"}, max_hop=1)
    ctx = CorrelationContext(run_id="00000000-0000-0000-0000-000000000001", request_id="req-1", hop=2)

    unknown = engine.evaluate(ctx, "message/send", "unknown", {})
    deep = engine.evaluate(ctx, "message/send", "worker", {})

    assert unknown.outcome == "deny"
    assert deep.outcome == "deny"


def test_proxy_emits_before_and_after_events():
    events = []

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"jsonrpc": "2.0", "id": 1, "result": {"ok": True}})

    proxy = A2AProxy(
        {"worker": "http://worker:8100"},
        transport=HttpTransport(httpx.MockTransport(handler)),
        event_sink=events.append,
    )
    ctx = CorrelationContext(run_id="00000000-0000-0000-0000-000000000001", request_id="req-1")

    asyncio.run(proxy.forward_send(ctx, {"jsonrpc": "2.0", "id": 1, "method": "message/send"}, "worker"))

    assert [event.operation for event in events] == ["message/send.request", "message/send.response"]
    assert all(event.context.request_id == "req-1" for event in events)


def test_proxy_rejects_unsupported_operation():
    proxy = A2AProxy({"worker": "http://worker:8100"}, transport=HttpTransport(httpx.MockTransport(lambda _: None)))
    ctx = CorrelationContext(run_id="00000000-0000-0000-0000-000000000001", request_id="req-1")

    try:
        asyncio.run(proxy.forward(ctx, {"jsonrpc": "2.0", "id": 1, "method": "unknown"}, "worker"))
    except ValueError as exc:
        assert "unsupported" in str(exc)
    else:
        raise AssertionError("unsupported operation was accepted")
