from __future__ import annotations

from dataclasses import dataclass
from uuid import uuid4


class NonReplayableError(ValueError):
    pass


@dataclass(frozen=True)
class ReplayPlan:
    source_run_id: str
    replay_run_id: str
    event_count: int
    event_id_map: dict[str, str]


class ReplayEngine:
    def create_plan(self, source_run_id: str, events: list[dict]) -> ReplayPlan:
        event_id_map: dict[str, str] = {}
        for event in events:
            payload = event.get("payload")
            if payload is None or (isinstance(payload, dict) and payload.get("_redacted")):
                raise NonReplayableError("run is not replayable: retained body is missing or redacted")
            event_id = str(event.get("event_id") or "")
            if not event_id:
                raise NonReplayableError("run is not replayable: event id is missing")
            event_id_map[event_id] = str(uuid4())
        return ReplayPlan(
            source_run_id=source_run_id,
            replay_run_id=str(uuid4()),
            event_count=len(events),
            event_id_map=event_id_map,
        )
