from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]


def test_compose_declares_required_services_and_safe_defaults():
    compose = (ROOT / "docker-compose.yml").read_text()

    for service in (
        "postgres:",
        "control-plane:",
        "gateway:",
        "root-agent:",
        "worker-agent:",
        "mcp-tools:",
        "mcp-resources:",
        "mcp-file-reader:",
        "mcp-file-writer:",
        "web:",
    ):
        assert service in compose

    assert "read_only: true" in compose
    assert "cap_drop:" in compose
    assert "LAB_BIND_HOST" in compose


def test_compose_keeps_public_ports_bound_to_configured_local_host():
    compose = (ROOT / "docker-compose.yml").read_text()

    assert '"${LAB_BIND_HOST:-127.0.0.1}:8000:8000"' in compose
    assert '"${LAB_BIND_HOST:-127.0.0.1}:5173:5173"' in compose


def test_compose_file_writer_isolated_and_not_public():
    compose = (ROOT / "docker-compose.yml").read_text()
    service = compose.split("  mcp-file-writer:\n", 1)[1].split("\n  web:\n", 1)[0]

    assert "MCP_FIXTURE_MODE: file-writer" in service
    assert "MCP_FILE_WRITER_MAX_BYTES" in service
    assert "./fixtures/file-writer:/var/lib/a2a-mcp/files" in service
    assert 'user: "${MCP_FILE_WRITER_UID:-1000}:${MCP_FILE_WRITER_GID:-1000}"' in service
    assert "ports:" not in service


def test_compose_grants_write_file_only_to_worker_default():
    compose = (ROOT / "docker-compose.yml").read_text()

    assert "AGENT_ALLOWED_TOOLS: ${ROOT_AGENT_ALLOWED_TOOLS:-}" in compose
    assert "AGENT_ALLOWED_TOOLS: ${WORKER_AGENT_ALLOWED_TOOLS:-calculator,fixture_http_get,read_file,write_file}" in compose
