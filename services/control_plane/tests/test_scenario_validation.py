import pytest
import yaml

from services.control_plane.app.events import EventStore
from services.control_plane.app.main import create_app
from services.control_plane.app.scenarios import ScenarioRegistry
from shared.python.lab_core.scenario import ScenarioLoader


def test_scenario_rejects_unknown_fields_and_unknown_services():
    loader = ScenarioLoader(
        allowed_agents={"root-agent", "worker-agent"},
        allowed_mcp_servers={"mcp-tools", "mcp-resources", "mcp-file-reader", "mcp-file-writer"},
    )

    with pytest.raises(ValueError, match="unknown field"):
        loader.load(
            {
                "id": "bad",
                "version": 1,
                "agents": [],
                "mcp_servers": [],
                "unexpected": True,
            }
        )

    with pytest.raises(ValueError, match="agent registration"):
        loader.load(
            {
                "id": "bad",
                "version": 1,
                "agents": [{"id": "rogue-agent", "role": "worker"}],
                "mcp_servers": [],
            }
        )


def test_seeded_yaml_loads_with_fixed_topology():
    document = yaml.safe_load(open("scenarios/recursive-a2a-mcp.yaml"))
    scenario = ScenarioLoader(
        allowed_agents={"root-agent", "worker-agent"},
        allowed_mcp_servers={"mcp-tools", "mcp-resources", "mcp-file-reader", "mcp-file-writer"},
    ).load(document)

    assert scenario.id == "recursive-a2a-mcp"
    assert {agent.id for agent in scenario.agents} == {"root-agent", "worker-agent"}
    assert {server.id for server in scenario.mcp_servers} == {
        "mcp-tools",
        "mcp-resources",
        "mcp-file-reader",
        "mcp-file-writer",
    }


def test_legacy_seeded_scenario_is_upgraded_for_file_reader_and_writer():
    legacy = yaml.safe_load(open("scenarios/recursive-a2a-mcp.yaml"))
    legacy["version"] = 1
    legacy["mcp_servers"] = [
        server for server in legacy["mcp_servers"] if server["id"] != "mcp-file-reader"
    ]
    legacy["policy_profile"]["allowed_tools"].remove("read_file")

    registry = ScenarioRegistry(
        loader=ScenarioLoader(
            allowed_agents={"root-agent", "worker-agent"},
            allowed_mcp_servers={"mcp-tools", "mcp-resources", "mcp-file-reader", "mcp-file-writer"},
        )
    )

    scenario = registry.import_document(legacy)

    assert scenario.version == 3
    assert any(server.id == "mcp-file-reader" for server in scenario.mcp_servers)
    assert "read_file" in scenario.policy_profile["allowed_tools"]
    assert any(server.id == "mcp-file-writer" for server in scenario.mcp_servers)
    assert "write_file" in scenario.policy_profile["allowed_tools"]


def test_startup_persists_legacy_seeded_scenario_upgrade(tmp_path):
    store = EventStore(f"sqlite:///{tmp_path / 'events.db'}")
    legacy = yaml.safe_load(open("scenarios/recursive-a2a-mcp.yaml"))
    legacy["version"] = 1
    legacy["mcp_servers"] = [
        server for server in legacy["mcp_servers"] if server["id"] != "mcp-file-reader"
    ]
    legacy["policy_profile"]["allowed_tools"].remove("read_file")
    store.upsert_scenario(legacy["id"], legacy["version"], legacy)

    app = create_app(store=store)
    response = app.state.scenarios.get("recursive-a2a-mcp")

    assert response is not None
    assert response.version == 3
    persisted = store.list_scenarios()[0]
    assert any(server["id"] == "mcp-file-reader" for server in persisted["mcp_servers"])
    assert "read_file" in persisted["policy_profile"]["allowed_tools"]
    assert any(server["id"] == "mcp-file-writer" for server in persisted["mcp_servers"])
    assert "write_file" in persisted["policy_profile"]["allowed_tools"]
