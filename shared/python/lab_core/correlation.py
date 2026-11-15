from __future__ import annotations

from .contracts import CorrelationContext


CORRELATION_HEADERS = {
    "x-lab-run-id": "run_id",
    "x-lab-task-id": "task_id",
    "x-lab-parent-task-id": "parent_task_id",
    "x-lab-agent-id": "agent_id",
    "x-lab-hop": "hop",
    "x-lab-request-id": "request_id",
}


def context_headers(context: CorrelationContext) -> dict[str, str]:
    values = context.model_dump(mode="json")
    return {
        header: str(values[field])
        for header, field in CORRELATION_HEADERS.items()
        if values.get(field) is not None
    }
