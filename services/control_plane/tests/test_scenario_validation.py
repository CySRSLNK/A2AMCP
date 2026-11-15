import pytest
import yaml

from shared.python.lab_core.scenario import ScenarioLoader


def test_scenario_rejects_unknown_fields_and_unknown_services():
    loader = ScenarioLoader(
        allowed_agents={"root-agent", "worker-agent"},
        allowed_mcp_servers={"mcp-tools", "mcp-resources", "mcp-file-reader"},
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
        allowed_mcp_servers={"mcp-tools", "mcp-resources", "mcp-file-reader"},
    ).load(document)

    assert scenario.id == "recursive-a2a-mcp"
    assert {agent.id for agent in scenario.agents} == {"root-agent", "worker-agent"}
    assert {server.id for server in scenario.mcp_servers} == {
        "mcp-tools",
        "mcp-resources",
        "mcp-file-reader",
    }
