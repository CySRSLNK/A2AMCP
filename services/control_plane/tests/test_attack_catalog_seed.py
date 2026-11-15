from pathlib import Path

import yaml

from services.control_plane.app.attacks import AttackCatalogRegistry


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

