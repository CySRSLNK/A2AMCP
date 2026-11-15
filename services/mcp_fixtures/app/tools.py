from __future__ import annotations


def list_tools() -> list[dict]:
    return [
        {
            "name": "calculator",
            "description": "Add or multiply two numbers.",
            "inputSchema": {"type": "object", "properties": {"a": {"type": "number"}, "b": {"type": "number"}}},
        },
        {
            "name": "fixture_http_get",
            "description": "Read a deterministic fixture URL.",
            "inputSchema": {"type": "object", "properties": {"url": {"type": "string"}}},
        },
    ]


def call_tool(name: str, arguments: dict) -> dict:
    if name == "calculator":
        operation = arguments.get("operation", "add")
        a = float(arguments.get("a", 0))
        b = float(arguments.get("b", 0))
        value = a * b if operation == "multiply" else a + b
        return {"content": [{"type": "text", "text": str(int(value) if value.is_integer() else value)}]}
    if name == "fixture_http_get":
        url = arguments.get("url", "")
        if not url.startswith("fixture://"):
            raise ValueError("fixture_http_get only accepts fixture:// URLs")
        return {"content": [{"type": "text", "text": f"fixture response for {url}"}]}
    raise ValueError(f"unknown tool: {name}")
