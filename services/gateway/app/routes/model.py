from __future__ import annotations

from typing import Any

import httpx
from fastapi import APIRouter, HTTPException
from fastapi.responses import Response


class ModelProxy:
    def __init__(
        self,
        base_url: str,
        api_key: str = "",
        *,
        transport: httpx.AsyncBaseTransport | None = None,
        timeout: float = 60.0,
    ):
        self.base_url = base_url.rstrip("/")
        self.api_key = api_key
        self.transport = transport
        self.timeout = timeout

    async def forward(self, payload: dict[str, Any]) -> httpx.Response:
        headers = {"content-type": "application/json"}
        if self.api_key:
            headers["authorization"] = f"Bearer {self.api_key}"
        async with httpx.AsyncClient(transport=self.transport, timeout=self.timeout) as client:
            return await client.post(
                f"{self.base_url}/v1/chat/completions", headers=headers, json=payload
            )


router = APIRouter(prefix="/model")
provider_proxy = ModelProxy("", "")


@router.get("/healthz")
def healthz() -> dict[str, str]:
    return {"status": "ok", "service": "model-proxy"}


@router.post("/v1/chat/completions")
async def chat_completions(payload: dict):
    if not provider_proxy.base_url:
        raise HTTPException(status_code=503, detail="model provider is not configured")
    response = await provider_proxy.forward(payload)
    return Response(content=response.content, status_code=response.status_code, media_type="application/json")
