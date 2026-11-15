from __future__ import annotations

from collections.abc import AsyncIterator
from typing import Any

import httpx

from shared.python.lab_core.correlation import context_headers
from shared.python.lab_core.contracts import CorrelationContext


class HttpTransport:
    def __init__(self, transport: httpx.AsyncBaseTransport | None = None, timeout: float = 10.0):
        self.transport = transport
        self.timeout = timeout

    async def request(
        self,
        method: str,
        url: str,
        *,
        context: CorrelationContext,
        payload: dict[str, Any] | None = None,
    ) -> httpx.Response:
        async with httpx.AsyncClient(transport=self.transport, timeout=self.timeout) as client:
            return await client.request(method, url, headers=context_headers(context), json=payload)

    async def stream(
        self,
        method: str,
        url: str,
        *,
        context: CorrelationContext,
        payload: dict[str, Any] | None = None,
    ) -> AsyncIterator[bytes]:
        async with httpx.AsyncClient(transport=self.transport, timeout=self.timeout) as client:
            async with client.stream(
                method, url, headers=context_headers(context), json=payload
            ) as response:
                response.raise_for_status()
                async for chunk in response.aiter_bytes():
                    yield chunk
