from __future__ import annotations

from typing import Any
from uuid import UUID

import httpx
from fastapi import APIRouter, Header, HTTPException
from fastapi.responses import Response


class ModelProxy:
    def __init__(
        self,
        base_url: str,
        api_key: str = "",
        *,
        transport: httpx.AsyncBaseTransport | None = None,
        timeout: float = 60.0,
        runtime_config_client=None,
    ):
        self.base_url = base_url.rstrip("/")
        self.api_key = api_key
        self.transport = transport
        self.timeout = timeout
        self.runtime_config_client = runtime_config_client

    async def forward(self, payload: dict[str, Any], run_id: UUID | str | None = None) -> httpx.Response:
        base_url = self.base_url
        api_key = self.api_key
        timeout = self.timeout
        if run_id is not None and self.runtime_config_client is not None:
            snapshot = await self.runtime_config_client.get_snapshot(str(run_id))
            model = snapshot.get("model", {})
            base_url = str(model.get("base_url", "")).rstrip("/")
            api_key = snapshot.get("api_key") or self.api_key
            timeout = float(model.get("request_timeout", self.timeout))
        if not base_url:
            raise ValueError("model provider is not configured")
        headers = {"content-type": "application/json"}
        if api_key:
            headers["authorization"] = f"Bearer {api_key}"
        async with httpx.AsyncClient(
            transport=self.transport, timeout=timeout, follow_redirects=False
        ) as client:
            return await client.post(
                f"{base_url}/v1/chat/completions", headers=headers, json=payload
            )


router = APIRouter(prefix="/model")
provider_proxy = ModelProxy("", "")


@router.get("/healthz")
def healthz() -> dict[str, str]:
    return {"status": "ok", "service": "model-proxy"}


@router.post("/v1/chat/completions")
async def chat_completions(
    payload: dict,
    x_lab_run_id: UUID | None = Header(default=None, alias="x-lab-run-id"),
):
    try:
        response = await provider_proxy.forward(payload, x_lab_run_id)
    except (ValueError, httpx.HTTPError) as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    return Response(content=response.content, status_code=response.status_code, media_type="application/json")
