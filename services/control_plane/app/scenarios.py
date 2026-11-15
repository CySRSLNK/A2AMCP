from __future__ import annotations

from pathlib import Path
from threading import Lock
from typing import Any

import yaml

from shared.python.lab_core.scenario import Scenario, ScenarioLoader


class ScenarioRegistry:
    def __init__(self, *, loader: ScenarioLoader | None = None) -> None:
        self.loader = loader or ScenarioLoader()
        self._items: dict[str, Scenario] = {}
        self._lock = Lock()

    def import_document(self, document: dict[str, Any]) -> Scenario:
        scenario = self.loader.load(document)
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
