from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Header, HTTPException
from fastapi.responses import JSONResponse

from shared.python.lab_core.contracts import CorrelationContext

from ..mcp import McpProxy


def build_router(proxy: McpProxy) -> APIRouter:
    router = APIRouter(prefix="/mcp")

    @router.post("/{server_id}")
    async def json_rpc(
        server_id: str,
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
        method = request.get("method")
        try:
            if method == "tools/list":
                result = await proxy.list_tools(context, server_id)
            elif method == "tools/call":
                params = request.get("params", {})
                result = await proxy.call_tool(
                    context, server_id, params["name"], params.get("arguments", {})
                )
            elif method == "resources/read":
                result = await proxy.read_resource(context, server_id, request["params"]["uri"])
            elif method == "initialize":
                result = await proxy.initialize(context, server_id)
            else:
                raise ValueError(f"unsupported MCP operation: {method}")
        except (KeyError, ValueError, PermissionError) as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        return JSONResponse({"jsonrpc": "2.0", "id": request.get("id"), "result": result})

    return router
