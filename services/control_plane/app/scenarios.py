from __future__ import annotations

from copy import deepcopy
from pathlib import Path
from threading import Lock
from typing import Any

import yaml

from shared.python.lab_core.scenario import Scenario, ScenarioLoader


BUILTIN_SCENARIO_ID = "recursive-a2a-mcp"


def migrate_builtin_scenario(document: dict[str, Any]) -> dict[str, Any]:
    """Upgrade the shipped scenario without widening unrelated custom scenarios."""
    if document.get("id") != BUILTIN_SCENARIO_ID or int(document.get("version", 1)) >= 2:
        return document

    migrated = deepcopy(document)
    servers = list(migrated.get("mcp_servers", []))
    server_ids = {server.get("id") for server in servers}
    policy = dict(migrated.get("policy_profile", {}))
    allowed_tools = list(policy.get("allowed_tools", []))
    changed = False

    if "mcp-file-reader" not in server_ids:
        servers.append(
            {
                "id": "mcp-file-reader",
                "endpoint": "http://mcp-file-reader:9100/mcp",
                "capabilities": ["tools/list", "tools/call"],
            }
        )
        changed = True

    if "read_file" not in allowed_tools:
        allowed_tools.append("read_file")
        changed = True

    if not changed:
        return document

    policy["allowed_tools"] = allowed_tools
    migrated["mcp_servers"] = servers
    migrated["policy_profile"] = policy
    migrated["version"] = max(int(migrated.get("version", 1)), 2)
    return migrated


class ScenarioRegistry:
    def __init__(self, *, loader: ScenarioLoader | None = None) -> None:
        self.loader = loader or ScenarioLoader()
        self._items: dict[str, Scenario] = {}
        self._lock = Lock()

    def import_document(self, document: dict[str, Any]) -> Scenario:
        scenario = self.loader.load(migrate_builtin_scenario(document))
        with self._lock:
            self._items[scenario.id] = scenario
        return scenario

    def import_file(self, path: str | Path) -> Scenario:
        with Path(path).open(encoding="utf-8") as handle:
            return self.import_document(yaml.safe_load(handle))

    def get(self, scenario_id: str) -> Scenario | None:
        return self._items.get(scenario_id)

    def list(self) -> list[Scenario]:
        return list(self._items.values())
