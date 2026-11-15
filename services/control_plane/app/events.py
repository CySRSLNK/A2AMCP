from __future__ import annotations

import asyncio
from collections import defaultdict
from threading import Lock
from typing import AsyncIterator

from sqlalchemy import delete, func, select
from sqlalchemy.orm import Session

from shared.python.lab_core.contracts import EventDraft, ProtocolEvent
from shared.python.lab_core.redaction import redact_payload

from .db import build_engine, init_database, session_factory
from .models import EventRecord, RunRecord, ScenarioRecord


class EventStore:
    def __init__(self, database_url: str = "sqlite:///./data/control-plane.db"):
        self.engine = build_engine(database_url)
        init_database(self.engine)
        self._session_factory = session_factory(self.engine)
        self._locks: defaultdict[str, Lock] = defaultdict(Lock)

    def ensure_run(self, run_id: str, *, status: str = "running", prompt: str | None = None) -> None:
        with self._session_factory.begin() as session:
            if session.get(RunRecord, run_id) is None:
                session.add(RunRecord(id=run_id, status=status, prompt=prompt))

    def create_run(self, run_id: str, *, scenario_id: str | None, prompt: str | None) -> dict:
        with self._session_factory.begin() as session:
            session.add(RunRecord(id=run_id, scenario_id=scenario_id, status="queued", prompt=prompt))
        return {"id": run_id, "scenario_id": scenario_id, "status": "queued", "prompt": prompt}

    def upsert_scenario(self, scenario_id: str, version: int, document: dict) -> None:
        with self._session_factory.begin() as session:
            row = session.get(ScenarioRecord, scenario_id)
            if row is None:
                session.add(ScenarioRecord(id=scenario_id, version=version, document=document))
            else:
                row.version = version
                row.document = document

    def list_scenarios(self) -> list[dict]:
        with self._session_factory() as session:
            rows = session.scalars(select(ScenarioRecord).order_by(ScenarioRecord.id)).all()
            return [row.document for row in rows]

    def update_run_status(self, run_id: str, status: str) -> None:
        with self._session_factory.begin() as session:
            row = session.get(RunRecord, run_id)
            if row is not None:
                row.status = status

    def get_run(self, run_id: str) -> dict | None:
        with self._session_factory() as session:
            row = session.get(RunRecord, run_id)
            if row is None:
                return None
            return {"id": row.id, "scenario_id": row.scenario_id, "status": row.status, "prompt": row.prompt}

    def append(self, draft: EventDraft) -> ProtocolEvent:
        run_id = str(draft.context.run_id)
        with self._locks[run_id]:
            self.ensure_run(run_id)
            with self._session_factory.begin() as session:
                if draft.source_event_key:
                    duplicate = session.scalar(
                        select(EventRecord).where(
                            EventRecord.run_id == run_id,
                            EventRecord.source_event_key == draft.source_event_key,
                        )
                    )
                    if duplicate is not None:
                        return self._to_contract(duplicate)
                last_sequence = session.scalar(
                    select(func.max(EventRecord.sequence)).where(EventRecord.run_id == run_id)
                )
                row = EventRecord(
                    event_id=str(draft.event_id),
                    run_id=run_id,
                    sequence=(last_sequence or 0) + 1,
                    task_id=str(draft.context.task_id) if draft.context.task_id else None,
                    parent_task_id=(
                        str(draft.context.parent_task_id) if draft.context.parent_task_id else None
                    ),
                    agent_id=draft.context.agent_id,
                    hop=draft.context.hop,
                    request_id=draft.context.request_id,
                    protocol=draft.protocol,
                    operation=draft.operation,
                    direction=draft.direction,
                    payload=redact_payload(draft.payload),
                    policy_decision=draft.policy_decision,
                    fault_action=draft.fault_action,
                    source_event_key=draft.source_event_key,
                    occurred_at=draft.occurred_at,
                )
                session.add(row)
                session.flush()
                return self._to_contract(row)

    def list_events(self, run_id: str, after: int = 0) -> list[ProtocolEvent]:
        with self._session_factory() as session:
            rows = session.scalars(
                select(EventRecord)
                .where(EventRecord.run_id == run_id, EventRecord.sequence > after)
                .order_by(EventRecord.sequence)
            ).all()
            return [self._to_contract(row) for row in rows]

    def delete_run(self, run_id: str) -> int:
        with self._session_factory.begin() as session:
            result = session.execute(delete(EventRecord).where(EventRecord.run_id == run_id))
            session.execute(delete(RunRecord).where(RunRecord.id == run_id))
            return int(result.rowcount or 0)

    async def iter_after(self, run_id, sequence: int = 0) -> AsyncIterator[ProtocolEvent]:
        for event in self.list_events(str(run_id), sequence):
            yield event
            await asyncio.sleep(0)

    @staticmethod
    def _to_contract(row: EventRecord) -> ProtocolEvent:
        from uuid import UUID

        from shared.python.lab_core.contracts import CorrelationContext

        return ProtocolEvent(
            event_id=UUID(row.event_id),
            context=CorrelationContext(
                run_id=UUID(row.run_id),
                task_id=UUID(row.task_id) if row.task_id else None,
                parent_task_id=UUID(row.parent_task_id) if row.parent_task_id else None,
                agent_id=row.agent_id,
                hop=row.hop,
                request_id=row.request_id,
            ),
            protocol=row.protocol,
            operation=row.operation,
            direction=row.direction,
            payload=row.payload,
            policy_decision=row.policy_decision,
            fault_action=row.fault_action,
            source_event_key=row.source_event_key,
            occurred_at=row.occurred_at,
            sequence=row.sequence,
        )
