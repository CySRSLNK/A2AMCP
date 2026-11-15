from __future__ import annotations

from typing import Any

import httpx

from shared.python.lab_core.correlation import context_headers
from shared.python.lab_core.contracts import CorrelationContext

from .planner import TaskInput, TaskResult


class A2AClient:
    def __init__(
        self,
        gateway_base_url: str,
        *,
        transport: httpx.AsyncBaseTransport | None = None,
        timeout: float = 300.0,
    ):
        self.gateway_base_url = gateway_base_url.rstrip("/")
        self.transport = transport
        self.timeout = timeout

    async def send(
        self, context: CorrelationContext, target_agent: str, task: TaskInput
    ) -> TaskResult:
        payload: dict[str, Any] = {
            "jsonrpc": "2.0",
            "id": context.request_id,
            "method": "message/send",
            "params": task.model_dump(mode="json"),
        }
        async with httpx.AsyncClient(transport=self.transport, timeout=self.timeout) as client:
            response = await client.post(
                f"{self.gateway_base_url}/a2a/{target_agent}",
                headers=context_headers(context),
                json=payload,
            )
        response.raise_for_status()
        body = response.json()
        return TaskResult.model_validate(body.get("result", body))
