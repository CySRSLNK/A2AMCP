import asyncio

import httpx

from services.gateway.app.runtime_config_client import RuntimeConfigClient


def test_runtime_config_client_uses_internal_token():
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.headers["x-control-plane-internal-token"] == "internal"
        assert request.url.path.endswith("/runtime-config")
        return httpx.Response(200, json={"config_version": 4})

    client = RuntimeConfigClient(
        "http://control-plane:8000",
        "internal",
        transport=httpx.MockTransport(handler),
    )
    snapshot = asyncio.run(client.get_snapshot("run-1"))
    assert snapshot["config_version"] == 4
