from __future__ import annotations

import copy
import re
from typing import Any


_SENSITIVE_KEYS = {"authorization", "api_key", "apikey", "token", "secret", "password"}
_BEARER_PATTERN = re.compile(r"(Bearer\s+)[^\s,;]+", re.IGNORECASE)


def redact_payload(value: Any, *, max_bytes: int = 64 * 1024) -> Any:
    redacted = _redact(copy.deepcopy(value))
    serialized = repr(redacted)
    if len(serialized.encode("utf-8")) > max_bytes:
        return {"_redacted": True, "reason": "payload_too_large", "size": len(serialized)}
    return redacted


def _redact(value: Any) -> Any:
    if isinstance(value, dict):
        return {
            key: "[REDACTED]" if key.lower() in _SENSITIVE_KEYS else _redact(item)
            for key, item in value.items()
        }
    if isinstance(value, list):
        return [_redact(item) for item in value]
    if isinstance(value, str):
        return _BEARER_PATTERN.sub(r"\1[REDACTED]", value)
    return value
