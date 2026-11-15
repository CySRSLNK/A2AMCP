from __future__ import annotations

from typing import Any

from shared.python.lab_core.attack_catalog import AttackCase, AttackCatalog, AttackCatalogLoader


class AttackCatalogRegistry:
    def __init__(self, *, loader: AttackCatalogLoader | None = None) -> None:
        self.loader = loader or AttackCatalogLoader()
        self.catalog: AttackCatalog | None = None

    def import_document(self, document: dict[str, Any]) -> AttackCatalog:
        catalog = self.loader.load(document)
        self.catalog = catalog
        return catalog

    def list(self) -> list[AttackCase]:
        if self.catalog is None:
            return []
        latest: dict[str, AttackCase] = {}
        for case in self.catalog.cases:
            current = latest.get(case.id)
            if current is None or case.version > current.version:
                latest[case.id] = case
        return [latest[key] for key in sorted(latest)]

    def get(self, attack_id: str, *, version: int | None = None) -> AttackCase | None:
        if self.catalog is None:
            return None
        matches = [case for case in self.catalog.cases if case.id == attack_id]
        if version is not None:
            return next((case for case in matches if case.version == version), None)
        return max(matches, key=lambda case: case.version, default=None)

    def plan(self, attack_id: str, *, version: int | None = None) -> dict[str, Any]:
        case = self.get(attack_id, version=version)
        if case is None:
            raise KeyError(attack_id)
        plan = case.model_dump(mode="json")
        plan["plan_mode"] = "read-only"
        return plan

