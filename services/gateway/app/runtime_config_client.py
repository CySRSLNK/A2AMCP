from __future__ import annotations

from typing import Any

import httpx


class RuntimeConfigClient:
    def __init__(
        self,
        control_plane_url: str,
        internal_token: str,
        *,
        transport: httpx.AsyncBaseTransport | None = None,
        timeout: float = 10.0,
    ) -> None:
        self.control_plane_url = control_plane_url.rstrip("/")
        self.internal_token = internal_token
        self.transport = transport
        self.timeout = timeout

    async def get_snapshot(self, run_id: str) -> dict[str, Any]:
        async with httpx.AsyncClient(transport=self.transport, timeout=self.timeout) as client:
            response = await client.get(
                f"{self.control_plane_url}/api/v1/runs/{run_id}/runtime-config",
                headers={"x-control-plane-internal-token": self.internal_token},
            )
        response.raise_for_status()
        return response.json()
