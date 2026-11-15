from __future__ import annotations

from typing import Any

from shared.python.lab_core.attack_catalog import AttackCase, AttackCatalog, AttackCatalogLoader


FIXTURE_TOPOLOGIES: dict[str, dict[str, Any]] = {
    "recursive-a2a-mcp": {
        "agents": {"root-agent", "worker-agent"},
        "mcp_servers": {"mcp-tools", "mcp-resources"},
        "capabilities": {"message/send", "tools/list", "tools/call", "resources/read"},
        "policy": {"max_hop": 3},
    }
}


class AttackCatalogRegistry:
    def __init__(
        self,
        *,
        loader: AttackCatalogLoader | None = None,
        fixture_topologies: dict[str, dict[str, Any]] | None = None,
    ) -> None:
        self.loader = loader or AttackCatalogLoader()
        self.fixture_topologies = fixture_topologies or FIXTURE_TOPOLOGIES
        self.catalog: AttackCatalog | None = None

    def import_document(self, document: dict[str, Any]) -> AttackCatalog:
        catalog = self.loader.load(document)
        for case in catalog.cases:
            if case.runnable:
                self._validate_runnable_fixture(case)
        self.catalog = catalog
        return catalog

    def _validate_runnable_fixture(self, case: AttackCase) -> None:
        assert case.fixture_scenario_id is not None
        topology = self.fixture_topologies.get(case.fixture_scenario_id)
        if topology is None:
            raise ValueError(
                f"runnable attack case {case.id} references unknown fixture scenario "
                f"{case.fixture_scenario_id}"
            )

        preconditions = case.preconditions
        for field in ("required_agents", "required_mcp_servers", "required_capabilities"):
            required = set(getattr(preconditions, field))
            available = set(topology.get(field.removeprefix("required_"), set()))
            missing = sorted(required - available)
            if missing:
                raise ValueError(
                    f"runnable attack case {case.id} requires unavailable {field}: {missing}"
                )

        for key, expected in preconditions.required_policy.items():
            if topology.get("policy", {}).get(key) != expected:
                raise ValueError(
                    f"runnable attack case {case.id} requires unsupported policy {key}={expected!r}"
                )

        allowed_agents = set(topology.get("agents", set()))
        allowed_mcp_servers = set(topology.get("mcp_servers", set()))
        for event in case.expected_events:
            if event.protocol == "a2a":
                allowed_actors = allowed_agents | {"control-plane"}
                allowed_targets = allowed_agents
            else:
                allowed_actors = allowed_agents
                allowed_targets = allowed_mcp_servers
            if event.actor is not None and event.actor not in allowed_actors:
                raise ValueError(
                    f"runnable attack case {case.id} has unavailable {event.protocol} actor: {event.actor}"
                )
            if event.target is not None and event.target not in allowed_targets:
                raise ValueError(
                    f"runnable attack case {case.id} has unavailable {event.protocol} target: {event.target}"
                )

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

