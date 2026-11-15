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
from .runtime_config_client import RuntimeConfigClient
from .transport import HttpTransport


app = FastAPI(title="A2A MCP Lab Gateway", version="0.1.0")
event_client = EventClient(os.getenv("CONTROL_PLANE_URL", "http://control-plane:8000"))
gateway_timeout = float(os.getenv("A2A_REQUEST_TIMEOUT", "300"))
mcp_timeout = float(os.getenv("MCP_REQUEST_TIMEOUT", "60"))
model_timeout = float(os.getenv("MODEL_REQUEST_TIMEOUT", "120"))
runtime_config_client = RuntimeConfigClient(
    os.getenv("CONTROL_PLANE_URL", "http://control-plane:8000"),
    os.getenv("CONTROL_PLANE_INTERNAL_TOKEN", "lab-internal-dev-token"),
    timeout=10,
)
proxy = A2AProxy(
    {
        "root-agent": os.getenv("ROOT_AGENT_URL", "http://root-agent:8100"),
        "worker-agent": os.getenv("WORKER_AGENT_URL", "http://worker-agent:8100"),
    },
    transport=HttpTransport(timeout=gateway_timeout),
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
                "mcp-file-reader": os.getenv("MCP_FILE_READER_URL", "http://mcp-file-reader:8200"),
            },
            transport=HttpTransport(timeout=mcp_timeout),
            policy_engine=PolicyEngine(
                allowed_targets={"mcp-tools", "mcp-resources", "mcp-file-reader"}, allow_dynamic_targets=True
            ),
            event_sink=event_client.append,
            runtime_config_client=runtime_config_client,
        )
    )
)
model_routes.provider_proxy = ModelProxy(
    os.getenv("MODEL_BASE_URL", ""),
    os.getenv("MODEL_API_KEY", ""),
    timeout=model_timeout,
    runtime_config_client=runtime_config_client,
)
app.include_router(model_router)


@app.get("/healthz")
def healthz() -> dict[str, str]:
    return {"status": "ok", "service": os.getenv("SERVICE_NAME", "gateway")}
