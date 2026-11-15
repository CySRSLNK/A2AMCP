from __future__ import annotations

import os
from uuid import UUID, uuid4

import httpx

from shared.python.lab_core.correlation import context_headers
from shared.python.lab_core.contracts import CorrelationContext


async def execute_run(
    event_store,
    *,
    run_manager=None,
    run_id: UUID,
    root_agent_id: str,
    prompt: str,
) -> None:
    event_store.update_run_status(str(run_id), "running")
    if run_manager is not None:
        run_manager.transition(run_id, "running")
    task_id = uuid4()
    context = CorrelationContext(
        run_id=run_id,
        task_id=task_id,
        agent_id="control-plane",
        request_id=str(uuid4()),
    )
    task = {
        "run_id": str(run_id),
        "prompt": prompt,
        "agent_id": root_agent_id,
        "task_id": str(task_id),
        "hop": 0,
        "delegation_edges": [],
        "policy": (
            run_manager.get(run_id).policy.model_dump(mode="json")
            if run_manager is not None and run_manager.get(run_id) is not None
            else {}
        ),
    }
    gateway = os.getenv("GATEWAY_BASE_URL", "http://127.0.0.1:8001").rstrip("/")
    try:
        async with httpx.AsyncClient(
            timeout=float(os.getenv("RUN_REQUEST_TIMEOUT", "600"))
        ) as client:
            response = await client.post(
                f"{gateway}/a2a/{root_agent_id}",
                headers=context_headers(context),
                json={"jsonrpc": "2.0", "id": context.request_id, "method": "message/send", "params": task},
            )
            response.raise_for_status()
            result = response.json().get("result", response.json())
        status = result.get("status", "completed")
        event_store.update_run_status(str(run_id), status)
        if run_manager is not None:
            run_manager.transition(run_id, status)
    except Exception:
        event_store.update_run_status(str(run_id), "failed")
        if run_manager is not None:
            run_manager.transition(run_id, "failed")
