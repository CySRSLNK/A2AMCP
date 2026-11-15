import asyncio
from pathlib import Path

import httpx

from services.control_plane.app.events import EventStore
from services.control_plane.app.main import create_app


async def request(app, method: str, path: str):
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        return await client.request(method, path)


def test_list_attacks_returns_seeded_cases(tmp_path: Path):
    app = create_app(store=EventStore(f"sqlite:///{tmp_path / 'events.db'}"))

    response = asyncio.run(request(app, "GET", "/api/v1/attacks"))

    assert response.status_code == 200
    body = response.json()
    assert len(body) >= 8
    assert body[0]["id"] == "A2A-MCP-001"
    assert "expected_events" not in body[0]


def test_get_attack_returns_full_case(tmp_path: Path):
    app = create_app(store=EventStore(f"sqlite:///{tmp_path / 'events.db'}"))

    response = asyncio.run(request(app, "GET", "/api/v1/attacks/A2A-MCP-005"))

    assert response.status_code == 200
    body = response.json()
    assert body["fixture_scenario_id"] == "recursive-a2a-mcp"
    assert body["expected_events"][0]["protocol"] == "a2a"


def test_missing_attack_returns_404(tmp_path: Path):
    app = create_app(store=EventStore(f"sqlite:///{tmp_path / 'events.db'}"))

    response = asyncio.run(request(app, "GET", "/api/v1/attacks/MISSING"))

    assert response.status_code == 404


def test_plan_endpoint_does_not_create_run_or_event(tmp_path: Path):
    store = EventStore(f"sqlite:///{tmp_path / 'events.db'}")
    app = create_app(store=store)

    response = asyncio.run(request(app, "GET", "/api/v1/attacks/MCP-X-001/plan"))

    assert response.status_code == 200
    assert response.json()["safe_fixture"] == "local-only"
    assert store.get_run("MCP-X-001") is None
    assert store.list_events("MCP-X-001") == []


def test_explicit_case_version_is_stable(tmp_path: Path):
    app = create_app(store=EventStore(f"sqlite:///{tmp_path / 'events.db'}"))

    response = asyncio.run(
        request(app, "GET", "/api/v1/attacks/A2A-MCP-005?version=1")
    )

    assert response.status_code == 200
    assert response.json()["version"] == 1

