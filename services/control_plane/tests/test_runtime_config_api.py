import asyncio
from pathlib import Path

import httpx

from services.control_plane.app.events import EventStore
from services.control_plane.app.main import create_app


async def request(app, method: str, path: str, **kwargs):
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        return await client.request(method, path, **kwargs)


def test_config_api_masks_key_and_freezes_run_snapshot(tmp_path: Path, monkeypatch):
    monkeypatch.setenv("CONFIG_ENCRYPTION_KEY", "3" * 43 + "=")
    monkeypatch.setenv("CONTROL_PLANE_INTERNAL_TOKEN", "test-token")
    app = create_app(store=EventStore(f"sqlite:///{tmp_path / 'config.db'}"))

    initial = asyncio.run(request(app, "GET", "/api/v1/config"))
    assert initial.status_code == 200
    version = initial.json()["version"]

    update = asyncio.run(
        request(
            app,
            "PUT",
            "/api/v1/config",
            json={
                **initial.json(),
                "expected_version": version,
                "api_key_action": "replace",
                "api_key": "api-secret",
                "model": {**initial.json()["model"], "model_name": "model-v2"},
            },
        )
    )
    assert update.status_code == 200
    assert update.json()["model"]["api_key_masked"] == "********"
    assert "api-secret" not in update.text

    run = asyncio.run(
        request(
            app,
            "POST",
            "/api/v1/runs",
            json={"prompt": "snapshot", "mode": "direct"},
        )
    )
    assert run.status_code == 200
    run_id = run.json()["id"]
    resolver = asyncio.run(
        request(
            app,
            "GET",
            f"/api/v1/runs/{run_id}/runtime-config",
            headers={"x-control-plane-internal-token": "test-token"},
        )
    )
    assert resolver.status_code == 200
    assert resolver.json()["model"]["model_name"] == "model-v2"
    assert resolver.json()["api_key"] == "api-secret"


def test_config_api_rejects_stale_update_and_hides_internal_resolver(tmp_path: Path):
    app = create_app(store=EventStore(f"sqlite:///{tmp_path / 'config.db'}"))
    current = asyncio.run(request(app, "GET", "/api/v1/config")).json()
    response = asyncio.run(
        request(
            app,
            "PUT",
            "/api/v1/config",
            json={**current, "expected_version": current["version"] + 1},
        )
    )
    assert response.status_code == 409

    missing = asyncio.run(
        request(
            app,
            "GET",
            "/api/v1/runs/00000000-0000-0000-0000-000000000001/runtime-config",
        )
    )
    assert missing.status_code == 404


def test_mcp_registration_crud_changes_only_new_runs(tmp_path: Path):
    app = create_app(store=EventStore(f"sqlite:///{tmp_path / 'config.db'}"))
    current = asyncio.run(request(app, "GET", "/api/v1/config")).json()
    added = asyncio.run(
        request(
            app,
            "POST",
            "/api/v1/config/mcp",
            json={
                "id": "custom-tools",
                "endpoint": "https://mcp.example.test",
                "enabled": True,
                "capabilities": ["tools/call"],
                "allowed_tools": ["calculator"],
                "expected_version": current["version"],
            },
        )
    )
    assert added.status_code == 200
    assert any(item["id"] == "custom-tools" for item in added.json()["mcp_servers"])
    deleted = asyncio.run(
        request(
            app,
            "DELETE",
            f"/api/v1/config/mcp/custom-tools?expected_version={added.json()['version']}",
        )
    )
    assert deleted.status_code == 200
    assert all(item["id"] != "custom-tools" for item in deleted.json()["mcp_servers"])
