from copy import deepcopy
import asyncio
from pathlib import Path
from uuid import uuid4

import httpx
import pytest
import yaml

from shared.python.lab_core.contracts import CorrelationContext
from services.control_plane.app.attacks import AttackCatalogRegistry
from services.gateway.app.proxy import A2AProxy
from services.gateway.app.transport import HttpTransport


CATALOG_PATH = Path(__file__).resolve().parents[3] / "scenarios" / "attack-catalog.yaml"


def load_seed():
    return yaml.safe_load(CATALOG_PATH.read_text())


def test_seed_catalog_contains_cross_mcp_and_a2a_mcp_cases():
    registry = AttackCatalogRegistry()
    catalog = registry.import_document(load_seed())

    assert {case.protocol_path for case in catalog.cases} == {"cross-mcp", "a2a-mcp"}
    assert len(catalog.cases) >= 8


def test_plan_is_json_safe_and_marks_unavailable_fixtures():
    registry = AttackCatalogRegistry()
    registry.import_document(load_seed())

    plan = registry.plan("MCP-X-001")

    assert plan["safe_fixture"] == "local-only"
    assert plan["runnable"] is False
    assert plan["expected_events"]
    assert "http" not in repr(plan).lower()


def test_runnable_case_uses_gateway_event_contract():
    registry = AttackCatalogRegistry()
    registry.import_document(load_seed())

    case = registry.get("A2A-MCP-005")
    assert case is not None
    assert [event.operation for event in case.expected_events[:3]] == [
        "message/send.request",
        "message/send.request",
        "message/send.request",
    ]
    assert case.expected_events[0].actor == "control-plane"


def test_runnable_a2a_events_match_gateway_proxy():
    registry = AttackCatalogRegistry()
    registry.import_document(load_seed())
    case = registry.get("A2A-MCP-005")
    assert case is not None

    events = []
    proxy = A2AProxy(
        {"root-agent": "http://root:8100", "worker-agent": "http://worker:8100"},
        transport=HttpTransport(
            httpx.MockTransport(
                lambda _: httpx.Response(
                    200, json={"jsonrpc": "2.0", "id": 1, "result": {"ok": True}}
                )
            )
        ),
        event_sink=events.append,
    )

    for expected in case.expected_events[:3]:
        context = CorrelationContext(
            run_id=uuid4(), request_id=f"catalog-{expected.actor}", agent_id=expected.actor
        )
        asyncio.run(
            proxy.forward_send(
                context,
                {"jsonrpc": "2.0", "id": 1, "method": "message/send"},
                expected.target or "worker-agent",
            )
        )
        assert events[-2].operation == expected.operation
        assert events[-2].context.agent_id == expected.actor


def test_registry_rejects_unknown_runnable_fixture():
    document = load_seed()
    runnable = next(case for case in document["cases"] if case["runnable"])
    runnable["fixture_scenario_id"] = "missing-fixture"

    with pytest.raises(ValueError, match="unknown fixture scenario"):
        AttackCatalogRegistry().import_document(document)


def test_registry_rejects_unavailable_runnable_capability():
    document = load_seed()
    runnable = next(case for case in document["cases"] if case["runnable"])
    invalid = deepcopy(runnable)
    invalid["preconditions"]["required_capabilities"].append("filesystem/write")
    document["cases"] = [invalid]

    with pytest.raises(ValueError, match="requires unavailable required_capabilities"):
        AttackCatalogRegistry().import_document(document)


def test_registry_rejects_runnable_event_outside_fixture_topology():
    document = load_seed()
    runnable = next(case for case in document["cases"] if case["runnable"])
    runnable["expected_events"][0]["target"] = "public-prod"

    with pytest.raises(ValueError, match="unavailable a2a target"):
        AttackCatalogRegistry().import_document(document)


def test_latest_case_version_is_selected_without_ambiguity():
    registry = AttackCatalogRegistry()
    registry.import_document(
        {
            "version": 1,
            "cases": [
                {
                    **load_seed()["cases"][0],
                    "version": 1,
                },
                {
                    **load_seed()["cases"][0],
                    "version": 2,
                    "title": "Updated case",
                },
            ],
        }
    )

    assert registry.get("MCP-X-001").version == 2
    assert registry.get("MCP-X-001", version=1).version == 1

