from __future__ import annotations

import httpx

from .contracts import EventDraft, ProtocolEvent


class EventClient:
    def __init__(self, base_url: str, timeout: float = 5.0):
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout

    def append(self, draft: EventDraft) -> ProtocolEvent:
        response = httpx.post(
            f"{self.base_url}/api/v1/events",
            json=draft.model_dump(mode="json"),
            timeout=self.timeout,
        )
        response.raise_for_status()
        return ProtocolEvent.model_validate(response.json())
