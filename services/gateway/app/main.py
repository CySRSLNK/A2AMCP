import os

from fastapi import FastAPI

from shared.python.lab_core.events_client import EventClient

from .policies import PolicyEngine
from .proxy import A2AProxy
from .routes.a2a import build_router
from .routes import model as model_routes
from .routes.model import ModelProxy, router as model_router
from .routes.mcp import build_router as build_mcp_router
from .mcp import McpProxy


app = FastAPI(title="A2A MCP Lab Gateway", version="0.1.0")
event_client = EventClient(os.getenv("CONTROL_PLANE_URL", "http://control-plane:8000"))
proxy = A2AProxy(
    {
        "root-agent": os.getenv("ROOT_AGENT_URL", "http://root-agent:8100"),
        "worker-agent": os.getenv("WORKER_AGENT_URL", "http://worker-agent:8100"),
    },
    event_sink=event_client.append,
    policy_engine=PolicyEngine(allowed_targets={"root-agent", "worker-agent"}),
)
app.include_router(build_router(proxy))
app.include_router(
    build_mcp_router(
        McpProxy(
            {
                "mcp-tools": os.getenv("MCP_TOOLS_URL", "http://mcp-tools:8200"),
                "mcp-resources": os.getenv("MCP_RESOURCES_URL", "http://mcp-resources:8200"),
            },
            policy_engine=PolicyEngine(allowed_targets={"mcp-tools", "mcp-resources"}),
            event_sink=event_client.append,
        )
    )
)
model_routes.provider_proxy = ModelProxy(
    os.getenv("MODEL_BASE_URL", ""), os.getenv("MODEL_API_KEY", "")
)
app.include_router(model_router)


@app.get("/healthz")
def healthz() -> dict[str, str]:
    return {"status": "ok", "service": os.getenv("SERVICE_NAME", "gateway")}
