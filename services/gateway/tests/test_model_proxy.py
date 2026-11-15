import asyncio

import httpx

from services.gateway.app.routes.model import ModelProxy


def test_model_proxy_forwards_to_configured_provider():
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url == httpx.URL("https://model.local/v1/chat/completions")
        assert request.headers["authorization"] == "Bearer secret"
        return httpx.Response(200, json={"choices": [{"message": {"content": "ok"}}]})

    proxy = ModelProxy(
        "https://model.local",
        "secret",
        transport=httpx.MockTransport(handler),
    )

    response = asyncio.run(proxy.forward({"model": "test", "messages": []}))

    assert response.status_code == 200
    assert response.json()["choices"][0]["message"]["content"] == "ok"
