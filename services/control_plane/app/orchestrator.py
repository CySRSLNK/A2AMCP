from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from threading import Lock
from uuid import UUID, uuid4

from .policies import PolicySnapshot, freeze_policy


@dataclass
class RunState:
    id: UUID
    scenario_id: str | None
    root_agent_id: str | None
    prompt: str | None
    mode: str
    status: str = "queued"
    policy: PolicySnapshot = field(default_factory=PolicySnapshot)
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))


class RunManager:
    def __init__(self) -> None:
        self._runs: dict[UUID, RunState] = {}
        self._lock = Lock()

    def create(
        self,
        *,
        scenario_id: str | None,
        root_agent_id: str | None,
        prompt: str | None,
        mode: str = "mediated",
        policy_profile: dict | PolicySnapshot | None = None,
    ) -> RunState:
        if mode not in {"mediated", "direct"}:
            raise ValueError("mode must be mediated or direct")
        run = RunState(
            id=uuid4(),
            scenario_id=scenario_id,
            root_agent_id=root_agent_id,
            prompt=prompt,
            mode=mode,
            policy=freeze_policy(policy_profile or {}),
        )
        with self._lock:
            self._runs[run.id] = run
        return run

    def get(self, run_id: UUID) -> RunState | None:
        return self._runs.get(run_id)

    def transition(self, run_id: UUID, status: str) -> RunState:
        with self._lock:
            run = self._runs[run_id]
            run.status = status
            return run
