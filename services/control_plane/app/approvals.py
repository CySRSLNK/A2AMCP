from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from threading import Lock
from typing import Literal
from uuid import UUID, uuid4


ApprovalDecision = Literal["approve", "deny"]


@dataclass(frozen=True)
class Approval:
    id: UUID
    run_id: UUID
    operation: str
    status: str
    created_at: datetime
    expires_at: datetime
    decided_at: datetime | None = None
    decision: ApprovalDecision | None = None


class ApprovalManager:
    def __init__(self) -> None:
        self._items: dict[UUID, Approval] = {}
        self._lock = Lock()

    def request(
        self,
        run_id: UUID,
        operation: str,
        *,
        expires_in: timedelta = timedelta(minutes=5),
        now: datetime | None = None,
    ) -> Approval:
        created_at = now or datetime.now(timezone.utc)
        approval = Approval(
            id=uuid4(),
            run_id=run_id,
            operation=operation,
            status="pending",
            created_at=created_at,
            expires_at=created_at + expires_in,
        )
        with self._lock:
            self._items[approval.id] = approval
        return approval

    def get(self, approval_id: UUID) -> Approval:
        try:
            return self._items[approval_id]
        except KeyError as exc:
            raise KeyError(f"approval not found: {approval_id}") from exc

    def decide(
        self,
        approval_id: UUID,
        decision: ApprovalDecision,
        *,
        now: datetime | None = None,
    ) -> Approval:
        if decision not in {"approve", "deny"}:
            raise ValueError("decision must be approve or deny")
        with self._lock:
            current = self.get(approval_id)
            if current.status != "pending":
                raise ValueError("approval already decided")
            decided_at = now or datetime.now(timezone.utc)
            updated = Approval(
                **{
                    **current.__dict__,
                    "status": "approved" if decision == "approve" else "denied",
                    "decision": decision,
                    "decided_at": decided_at,
                }
            )
            self._items[approval_id] = updated
            return updated

    def timeout(self, *, now: datetime | None = None) -> list[Approval]:
        current_time = now or datetime.now(timezone.utc)
        expired: list[Approval] = []
        with self._lock:
            for approval_id, current in list(self._items.items()):
                if current.status == "pending" and current.expires_at <= current_time:
                    updated = Approval(
                        **{
                            **current.__dict__,
                            "status": "denied",
                            "decision": "deny",
                            "decided_at": current_time,
                        }
                    )
                    self._items[approval_id] = updated
                    expired.append(updated)
        return expired
