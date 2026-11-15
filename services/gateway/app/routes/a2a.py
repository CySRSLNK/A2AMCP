from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Header, HTTPException
from fastapi.responses import Response, StreamingResponse

from shared.python.lab_core.contracts import CorrelationContext

from ..proxy import A2AProxy


def build_router(proxy: A2AProxy) -> APIRouter:
    router = APIRouter(prefix="/a2a")

    @router.get("/{agent_id}/.well-known/agent-card.json")
    async def card(agent_id: str):
        try:
            response = await proxy.forward_card(agent_id)
        except ValueError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        return Response(content=response.content, status_code=response.status_code, media_type="application/json")

    @router.post("/{agent_id}")
    async def json_rpc(
        agent_id: str,
        request: dict,
        x_lab_run_id: UUID = Header(alias="x-lab-run-id"),
        x_lab_request_id: str = Header(alias="x-lab-request-id"),
        x_lab_task_id: UUID | None = Header(default=None, alias="x-lab-task-id"),
        x_lab_parent_task_id: UUID | None = Header(default=None, alias="x-lab-parent-task-id"),
        x_lab_agent_id: str | None = Header(default=None, alias="x-lab-agent-id"),
        x_lab_hop: int = Header(default=0, alias="x-lab-hop"),
    ):
        context = CorrelationContext(
            run_id=x_lab_run_id,
            task_id=x_lab_task_id,
            parent_task_id=x_lab_parent_task_id,
            agent_id=x_lab_agent_id,
            hop=x_lab_hop,
            request_id=x_lab_request_id,
        )
        try:
            if request.get("method") == "message/stream":
                return StreamingResponse(proxy.forward_stream(context, request, agent_id))
            response = await proxy.forward(context, request, agent_id)
        except (ValueError, PermissionError) as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        return Response(content=response.content, status_code=response.status_code, media_type="application/json")

    return router
