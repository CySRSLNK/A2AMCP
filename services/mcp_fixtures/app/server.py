import os

from fastapi import FastAPI

from .resources import read_resource
from .tools import call_tool, list_tools


def handle_message(fixture_mode: str, request: dict) -> dict:
    method = request.get("method")
    params = request.get("params", {})
    try:
        if method == "initialize":
            result = {
                "protocolVersion": "2025-06-18",
                "capabilities": {
                    "tools": {} if fixture_mode == "tools" else None,
                    "resources": {} if fixture_mode == "resources" else None,
                },
                "serverInfo": {"name": f"{fixture_mode}-fixture", "version": "0.1.0"},
            }
        elif method == "tools/list" and fixture_mode == "tools":
            result = {"tools": list_tools()}
        elif method == "tools/call" and fixture_mode == "tools":
            result = call_tool(params["name"], params.get("arguments", {}))
        elif method == "resources/read" and fixture_mode == "resources":
            result = read_resource(params["uri"])
        else:
            return {
                "jsonrpc": "2.0",
                "id": request.get("id"),
                "error": {"code": -32601, "message": f"unsupported operation: {method}"},
            }
    except (KeyError, ValueError) as exc:
        return {
            "jsonrpc": "2.0",
            "id": request.get("id"),
            "error": {"code": -32602, "message": str(exc)},
        }
    return {"jsonrpc": "2.0", "id": request.get("id"), "result": result}


def create_app(mode: str | None = None) -> FastAPI:
    fixture_mode = mode or os.getenv("MCP_FIXTURE_MODE", "unconfigured")
    application = FastAPI(title="A2A MCP Lab Fixture MCP Server", version="0.1.0")

    @application.get("/healthz")
    def healthz() -> dict[str, str]:
        return {
            "status": "ok",
            "service": os.getenv("SERVICE_NAME", "mcp-fixture"),
            "fixture_mode": fixture_mode,
        }

    @application.post("/mcp")
    def mcp(request: dict) -> dict:
        return handle_message(fixture_mode, request)

    return application


app = create_app()
