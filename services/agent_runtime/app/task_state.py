from __future__ import annotations

from typing import Literal


TaskStatus = Literal["queued", "running", "blocked", "failed", "completed", "canceled"]


ALLOWED_TRANSITIONS: dict[TaskStatus, set[TaskStatus]] = {
    "queued": {"running", "canceled"},
    "running": {"blocked", "failed", "completed", "canceled"},
    "blocked": {"running", "failed", "canceled"},
    "failed": set(),
    "completed": set(),
    "canceled": set(),
}


def transition(current: TaskStatus, target: TaskStatus) -> TaskStatus:
    if target not in ALLOWED_TRANSITIONS[current]:
        raise ValueError(f"invalid task transition: {current} -> {target}")
    return target
