from __future__ import annotations

import json
from typing import Protocol

import httpx

from shared.python.lab_core.contracts import ModelRequest, ModelResponse


def _decode_decision(content: str) -> dict:
    if not isinstance(content, str):
        raise ValueError("model response content must be text")
    text = content.strip()
    if text.startswith("```"):
        lines = text.splitlines()
        text = "\n".join(lines[1:-1]).strip()
    try:
        output = json.loads(text)
    except json.JSONDecodeError as exc:
        raise ValueError("model response is not valid JSON") from exc
    if not isinstance(output, dict):
        raise ValueError("model response must be a JSON object")
    return output


class ModelAdapter(Protocol):
    async def complete(self, request: ModelRequest) -> ModelResponse: ...


class MockModelAdapter:
    async def complete(self, request: ModelRequest) -> ModelResponse:
        role = request.metadata.get("role")
        hop = int(request.metadata.get("hop", 0))
        if role == "root":
            output = {
                "action": "delegate",
                "target_agent": "worker-agent",
                "summary": "Delegate the fixture inspection to the worker agent.",
            }
        elif role == "worker" and hop <= 1:
            output = {
                "action": "delegate",
                "target_agent": "worker-agent",
                "summary": "Ask the worker hop to inspect the fixture resource.",
            }
        elif role == "worker":
            output = {
                "action": "mcp_call",
                "server_id": "mcp-tools",
                "tool_name": "calculator",
                "arguments": {"a": 1, "b": 2},
                "summary": "Use the calculator fixture and return its result.",
            }
        else:
            output = {"action": "answer", "summary": "Fixture inspection completed."}
        return ModelResponse(provider="mock", model="lab-deterministic", output=output)


class DynamicModelAdapter:
    """Select the provider from the run snapshot without restarting the agent."""

    def __init__(self, remote: "OpenAICompatibleAdapter") -> None:
        self.mock = MockModelAdapter()
        self.remote = remote

    async def complete(self, request: ModelRequest) -> ModelResponse:
        if request.provider == "mock":
            return await self.mock.complete(request)
        return await self.remote.complete(request)


class OpenAICompatibleAdapter:
    def __init__(
        self,
        base_url: str,
        api_key: str,
        *,
        transport: httpx.AsyncBaseTransport | None = None,
        timeout: float = 120.0,
    ):
        self.base_url = base_url.rstrip("/")
        self.api_key = api_key
        self.transport = transport
        self.timeout = timeout

    async def complete(self, request: ModelRequest) -> ModelResponse:
        headers = {"content-type": "application/json"}
        run_id = request.metadata.get("run_id")
        if run_id:
            headers["x-lab-run-id"] = str(run_id)
        agent_id = request.metadata.get("agent_id")
        if agent_id:
            headers["x-lab-agent-id"] = str(agent_id)
        if self.api_key and not run_id:
            headers["authorization"] = f"Bearer {self.api_key}"
        payload = {
            "model": request.model,
            "messages": request.messages,
            "temperature": 0,
            "response_format": {"type": "json_object"},
        }
        async with httpx.AsyncClient(transport=self.transport, timeout=self.timeout) as client:
            response = await client.post(
                f"{self.base_url}/v1/chat/completions", headers=headers, json=payload
            )
        response.raise_for_status()
        body = response.json()
        content = body["choices"][0]["message"]["content"]
        output = _decode_decision(content)
        return ModelResponse(
            provider="openai-compatible",
            model=body.get("model", request.model),
            output=output,
            usage=body.get("usage", {}),
            replay_key=request.replay_key,
        )
