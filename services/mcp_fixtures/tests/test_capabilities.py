from services.mcp_fixtures.app.server import handle_message


def test_tools_fixture_exposes_only_safe_tools():
    response = handle_message(
        "tools", {"jsonrpc": "2.0", "id": 1, "method": "tools/list", "params": {}}
    )

    names = {tool["name"] for tool in response["result"]["tools"]}
    assert names == {"calculator", "fixture_http_get"}


def test_resources_fixture_reads_fixture_uri():
    response = handle_message(
        "resources",
        {
            "jsonrpc": "2.0",
            "id": 1,
            "method": "resources/read",
            "params": {"uri": "fixture://notes/security"},
        },
    )

    assert response["result"]["contents"][0]["text"]
