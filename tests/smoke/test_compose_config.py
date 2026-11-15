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
