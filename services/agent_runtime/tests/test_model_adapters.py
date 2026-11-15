import asyncio

import httpx

from shared.python.lab_core.contracts import ModelRequest
from services.agent_runtime.app.model_proxy import MockModelAdapter, OpenAICompatibleAdapter


def test_mock_model_returns_structured_delegate_decision():
    adapter = MockModelAdapter()
    request = ModelRequest(
        provider="mock",
        model="lab-deterministic",
        messages=[{"role": "user", "content": "inspect the fixture"}],
        metadata={"role": "root", "hop": 0},
    )

    response = asyncio.run(adapter.complete(request))

    assert response.output == {
        "action": "delegate",
        "target_agent": "worker-agent",
        "summary": "Delegate the fixture inspection to the worker agent.",
    }


def test_openai_compatible_adapter_maps_chat_completion_response():
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/v1/chat/completions"
        return httpx.Response(
            200,
            json={
                "model": "test-model",
                "choices": [{"message": {"content": '{"action":"answer","summary":"ok"}'}}],
                "usage": {"total_tokens": 3},
            },
        )

    adapter = OpenAICompatibleAdapter(
        "https://model.local",
        "test-key",
        transport=httpx.MockTransport(handler),
    )
    response = asyncio.run(
        adapter.complete(
            ModelRequest(
                provider="openai-compatible",
                model="test-model",
                messages=[{"role": "user", "content": "hello"}],
            )
        )
    )

    assert response.output == {"action": "answer", "summary": "ok"}
    assert response.usage == {"total_tokens": 3}
