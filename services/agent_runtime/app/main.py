import os

from fastapi import FastAPI, HTTPException

from .a2a_client import A2AClient
from .agent_card import AgentCard
from .model_proxy import MockModelAdapter, OpenAICompatibleAdapter
from .mcp_adapter import GatewayMcpClient
from .planner import AgentRuntime, TaskInput


app = FastAPI(title="A2A MCP Lab Agent", version="0.1.0")
agent_id = os.getenv("AGENT_ID", "unconfigured")
gateway_base_url = os.getenv("GATEWAY_BASE_URL", "http://gateway:8001")
if os.getenv("MODEL_PROVIDER", "mock") == "openai-compatible":
    model = OpenAICompatibleAdapter(
        f"{gateway_base_url}/model", os.getenv("MODEL_API_KEY", "")
    )
else:
    model = MockModelAdapter()
runtime = AgentRuntime(
    agent_id=agent_id,
    model=model,
    a2a_client=A2AClient(gateway_base_url),
    mcp_client=GatewayMcpClient(gateway_base_url),
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
