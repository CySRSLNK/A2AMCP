from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator
from typing import Any

from shared.python.lab_core.contracts import CorrelationContext


class FaultProfile:
    def __init__(self, actions: dict[str, dict[str, Any]] | None = None):
        self.actions = actions or {}

    async def apply(
        self,
        context: CorrelationContext,
        operation: str,
        response_stream: AsyncIterator[bytes],
    ) -> AsyncIterator[bytes]:
        action = self.actions.get(operation, {})
        fault_type = action.get("type")
        if fault_type == "delay":
            await asyncio.sleep(float(action.get("seconds", 0)))
        if fault_type == "timeout":
            raise TimeoutError(f"fault injected for {operation}")
        if fault_type == "drop_stream":
            return
        if fault_type == "malformed":
            yield b"{"
            return
        if fault_type == "replayed":
            yield str(action.get("body", "")).encode("utf-8")
            return
        async for chunk in response_stream:
            yield chunk
            if fault_type == "duplicate":
                yield chunk
