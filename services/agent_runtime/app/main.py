import os

from fastapi import FastAPI, HTTPException

from .a2a_client import A2AClient
from .agent_card import AgentCard
from .model_proxy import MockModelAdapter, OpenAICompatibleAdapter
from .mcp_adapter import GatewayMcpClient
from .planner import AgentRuntime, TaskInput


def _csv_env(name: str, default: str = "") -> set[str]:
    value = os.getenv(name, default)
    return {item.strip() for item in value.split(",") if item.strip()}


app = FastAPI(title="A2A MCP Lab Agent", version="0.1.0")
agent_id = os.getenv("AGENT_ID", "unconfigured")
gateway_base_url = os.getenv("GATEWAY_BASE_URL", "http://gateway:8001")
model_provider = os.getenv("MODEL_PROVIDER", "mock")
model_name = os.getenv("MODEL_NAME", "lab-agent")
model_timeout = float(os.getenv("MODEL_REQUEST_TIMEOUT", "120"))
a2a_timeout = float(os.getenv("A2A_REQUEST_TIMEOUT", "300"))
mcp_timeout = float(os.getenv("MCP_REQUEST_TIMEOUT", "60"))
if model_provider == "openai-compatible":
    model = OpenAICompatibleAdapter(
        f"{gateway_base_url}/model", os.getenv("MODEL_API_KEY", ""), timeout=model_timeout
    )
else:
    model = MockModelAdapter()
default_targets = "worker-agent"
default_tools = "calculator,fixture_http_get" if agent_id == "worker-agent" else ""
runtime = AgentRuntime(
    agent_id=agent_id,
    model=model,
    a2a_client=A2AClient(gateway_base_url, timeout=a2a_timeout),
    mcp_client=GatewayMcpClient(gateway_base_url, timeout=mcp_timeout),
    max_hop=int(os.getenv("AGENT_MAX_HOP", "8")),
    model_provider=model_provider,
    model_name=model_name,
    allowed_targets=_csv_env("AGENT_ALLOWED_TARGETS", default_targets),
    allowed_mcp_servers=_csv_env("AGENT_ALLOWED_MCP_SERVERS", "mcp-tools,mcp-resources"),
    allowed_tools=_csv_env("AGENT_ALLOWED_TOOLS", default_tools),
)


@app.get("/healthz")
def healthz() -> dict[str, str]:
    return {
        "status": "ok",
        "service": os.getenv("SERVICE_NAME", "agent-runtime"),
        "agent_id": os.getenv("AGENT_ID", "unconfigured"),
    }


@app.get("/.well-known/agent-card.json")
def agent_card():
    return AgentCard(
        id=agent_id,
        name=agent_id.replace("-", " ").title(),
        description="A configurable A2A lab agent",
        url=f"http://{agent_id}:8100",
    )


@app.post("/a2a")
async def a2a(request: dict):
    if request.get("method") != "message/send":
        raise HTTPException(status_code=400, detail="unsupported operation")
    task = TaskInput.model_validate(request.get("params", {}))
    result = await runtime.handle_task(task)
    return {"jsonrpc": "2.0", "id": request.get("id"), "result": result.model_dump(mode="json")}
