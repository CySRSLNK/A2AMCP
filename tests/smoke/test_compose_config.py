from pathlib import Path

import yaml

from services.mcp_fixtures.app.server import handle_message


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
    assert "./fixtures:/var/lib/a2a-mcp/files" in service
    assert 'user: "${MCP_FILE_WRITER_UID:-1000}:${MCP_FILE_WRITER_GID:-1000}"' in service
    assert "ports:" not in service


def test_compose_grants_write_file_only_to_worker_default():
    compose = (ROOT / "docker-compose.yml").read_text()

    assert "AGENT_ALLOWED_TOOLS: ${ROOT_AGENT_ALLOWED_TOOLS:-}" in compose
    assert "AGENT_ALLOWED_TOOLS: ${WORKER_AGENT_ALLOWED_TOOLS:-calculator,fixture_http_get,read_file,write_file}" in compose


def test_file_reader_can_read_writer_output_from_compose_mounts(tmp_path):
    services = yaml.safe_load((ROOT / "docker-compose.yml").read_text())["services"]
    reader_mount = services["mcp-file-reader"]["volumes"][0].split(":")
    writer_mount = services["mcp-file-writer"]["volumes"][0].split(":")
    reader_root = tmp_path / reader_mount[0]
    writer_root = tmp_path / writer_mount[0]
    reader_root.mkdir(parents=True, exist_ok=True)
    writer_root.mkdir(parents=True, exist_ok=True)

    written = handle_message(
        "file-writer",
        {
            "jsonrpc": "2.0",
            "id": 1,
            "method": "tools/call",
            "params": {"name": "write_file", "arguments": {"path": "result.txt", "content": "48"}},
        },
        file_root=str(writer_root),
    )
    read = handle_message(
        "file-tools",
        {
            "jsonrpc": "2.0",
            "id": 2,
            "method": "tools/call",
            "params": {"name": "read_file", "arguments": {"path": "result.txt"}},
        },
        file_root=str(reader_root),
    )

    assert "error" not in written
    assert read.get("result") == {"content": [{"type": "text", "text": "48"}]}
    assert (tmp_path / "fixtures/result.txt").read_text() == "48"
    assert reader_mount[1:] == ["/var/lib/a2a-mcp/files", "ro"]
    assert writer_mount[1:] == ["/var/lib/a2a-mcp/files"]
