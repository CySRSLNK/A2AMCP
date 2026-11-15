from __future__ import annotations

import json
import os
from dataclasses import asdict
from pathlib import Path
from uuid import UUID, uuid4

from fastapi import BackgroundTasks, FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, StreamingResponse
import yaml

from shared.python.lab_core.contracts import EventDraft
from shared.python.lab_core.scenario import ScenarioLoader

from .approvals import ApprovalManager
from .attacks import AttackCatalogRegistry
from .artifacts import ArtifactStore, RunDestroyer
from .events import EventStore
from .executor import execute_run
from .orchestrator import RunManager
from .replay import NonReplayableError, ReplayEngine
from .scenarios import ScenarioRegistry


async def event_stream(store: EventStore, run_id: UUID, after: int):
    async for event in store.iter_after(run_id, after):
        yield (
            f"id: {event.sequence}\n"
            "event: protocol\n"
            f"data: {json.dumps(event.model_dump(mode='json'))}\n\n"
        )


def _default_attack_catalog_path() -> Path:
    return Path(__file__).resolve().parents[3] / "scenarios" / "attack-catalog.yaml"


def _load_attack_catalog(
    registry: AttackCatalogRegistry,
    *,
    path: str | Path | None = None,
    document: dict | None = None,
) -> None:
    if document is not None:
        registry.import_document(document)
        return
    catalog_path = Path(path or os.getenv("ATTACK_CATALOG_PATH", _default_attack_catalog_path()))
    try:
        loaded = yaml.safe_load(catalog_path.read_text())
    except OSError as exc:
        raise RuntimeError(f"attack catalog is unavailable: {catalog_path}") from exc
    try:
        registry.import_document(loaded)
    except ValueError as exc:
        raise RuntimeError(f"attack catalog is invalid: {catalog_path}: {exc}") from exc


def create_app(
    store: EventStore | None = None,
    *,
    attack_catalog: dict | None = None,
    attack_catalog_path: str | Path | None = None,
) -> FastAPI:
    event_store = store or EventStore(os.getenv("DATABASE_URL", "sqlite:///./data/control-plane.db"))
    application = FastAPI(title="A2A MCP Lab Control Plane", version="0.1.0")
    application.add_middleware(
        CORSMiddleware,
        allow_origins=[
            "http://127.0.0.1:5173",
            "http://localhost:5173",
        ],
        allow_methods=["*"],
        allow_headers=["*"],
    )
    application.state.scenarios = ScenarioRegistry(
        loader=ScenarioLoader(
            allowed_agents={"root-agent", "worker-agent"},
            allowed_mcp_servers={"mcp-tools", "mcp-resources"},
        )
    )
    for document in event_store.list_scenarios():
        try:
            application.state.scenarios.import_document(document)
        except ValueError:
            continue
    application.state.attacks = AttackCatalogRegistry()
    _load_attack_catalog(
        application.state.attacks,
        path=attack_catalog_path,
        document=attack_catalog,
    )
    application.state.runs = RunManager()
    application.state.approvals = ApprovalManager()
    application.state.replay = ReplayEngine()
    application.state.artifacts = ArtifactStore(
        os.getenv("ARTIFACT_ROOT", "./data/artifacts")
    )

    @application.get("/healthz")
    def healthz() -> dict[str, str]:
        return {"status": "ok", "service": os.getenv("SERVICE_NAME", "control-plane")}

    @application.post("/api/v1/scenarios")
    def import_scenario(body: dict) -> dict:
        try:
            scenario = application.state.scenarios.import_document(body)
        except ValueError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc
        event_store.upsert_scenario(scenario.id, scenario.version, scenario.model_dump(mode="json"))
        return scenario.model_dump(mode="json")

    @application.get("/api/v1/scenarios")
    def list_scenarios() -> list[dict]:
        return [scenario.model_dump(mode="json") for scenario in application.state.scenarios.list()]

    @application.get("/api/v1/attacks")
    async def list_attacks() -> list[dict]:
        return [
            case.model_dump(
                mode="json",
                include={
                    "id",
                    "version",
                    "protocol_path",
                    "runnable",
                    "fixture_scenario_id",
                    "category",
                    "title",
                    "summary",
                    "safe_fixture",
                },
            )
            for case in application.state.attacks.list()
        ]

    @application.get("/api/v1/attacks/{attack_id}")
    async def get_attack(attack_id: str, version: int | None = Query(default=None, ge=1)) -> dict:
        case = application.state.attacks.get(attack_id, version=version)
        if case is None:
            raise HTTPException(status_code=404, detail="attack case not found")
        return case.model_dump(mode="json")

    @application.get("/api/v1/attacks/{attack_id}/plan")
    async def get_attack_plan(attack_id: str, version: int | None = Query(default=None, ge=1)) -> dict:
        try:
            return application.state.attacks.plan(attack_id, version=version)
        except KeyError as exc:
            raise HTTPException(status_code=404, detail="attack case not found") from exc

    @application.post("/api/v1/runs")
    def create_run(body: dict, background_tasks: BackgroundTasks) -> dict:
        scenario_id = body.get("scenario_id")
        scenario = application.state.scenarios.get(scenario_id) if scenario_id else None
        if scenario_id and scenario is None:
            raise HTTPException(status_code=404, detail="scenario not found")
        policy_profile = body.get("policy_profile")
        if policy_profile is None and scenario is not None:
            policy_profile = scenario.policy_profile
        run = application.state.runs.create(
            scenario_id=scenario_id,
            root_agent_id=body.get("root_agent_id") or (scenario.agents[0].id if scenario else None),
            prompt=body.get("prompt"),
            mode=body.get("mode", "mediated"),
            policy_profile=policy_profile,
        )
        created = event_store.create_run(
            str(run.id),
            scenario_id=scenario_id,
            prompt=body.get("prompt"),
        )
        if run.mode == "mediated" and run.root_agent_id and run.prompt:
            background_tasks.add_task(
                execute_run,
                event_store,
                run_manager=application.state.runs,
                run_id=run.id,
                root_agent_id=run.root_agent_id,
                prompt=run.prompt,
            )
        return {
            **created,
            "root_agent_id": run.root_agent_id,
            "mode": run.mode,
            "policy": run.policy.model_dump(mode="json"),
        }

    @application.get("/api/v1/runs/{run_id}")
    def get_run(run_id: UUID) -> dict:
        run = event_store.get_run(str(run_id))
        if run is None:
            raise HTTPException(status_code=404, detail="run not found")
        state = application.state.runs.get(run_id)
        if state is not None:
            run.update(
                {
                    "root_agent_id": state.root_agent_id,
                    "mode": state.mode,
                    "policy": state.policy.model_dump(mode="json"),
                    "status": state.status,
                }
            )
        return run

    @application.post("/api/v1/runs/{run_id}/approvals")
    def request_approval(run_id: UUID, body: dict) -> dict:
        if event_store.get_run(str(run_id)) is None:
            raise HTTPException(status_code=404, detail="run not found")
        approval = application.state.approvals.request(
            run_id,
            body.get("operation", "unknown"),
        )
        return _approval_json(approval)

    @application.post("/api/v1/runs/{run_id}/approvals/{approval_id}")
    def decide_approval(run_id: UUID, approval_id: UUID, body: dict) -> dict:
        try:
            approval = application.state.approvals.get(approval_id)
        except KeyError as exc:
            raise HTTPException(status_code=404, detail="approval not found") from exc
        if approval.run_id != run_id:
            raise HTTPException(status_code=404, detail="approval not found")
        try:
            updated = application.state.approvals.decide(approval_id, body.get("decision", "deny"))
        except ValueError as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc
        return _approval_json(updated)

    @application.post("/api/v1/runs/{run_id}/replay")
    def replay_run(run_id: UUID) -> dict:
        source = event_store.get_run(str(run_id))
        if source is None:
            raise HTTPException(status_code=404, detail="run not found")
        events = [event.model_dump(mode="json") for event in event_store.list_events(str(run_id))]
        try:
            plan = application.state.replay.create_plan(str(run_id), events)
        except NonReplayableError as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc
        event_store.create_run(
            plan.replay_run_id,
            scenario_id=source.get("scenario_id"),
            prompt=source.get("prompt"),
        )
        return asdict(plan)

    @application.delete("/api/v1/runs/{run_id}")
    def destroy_run(run_id: UUID) -> dict:
        if event_store.get_run(str(run_id)) is None:
            raise HTTPException(status_code=404, detail="run not found")
        report = RunDestroyer(event_store, application.state.artifacts).destroy(run_id)
        return asdict(report)

    @application.post("/api/v1/events")
    def append_event(draft: EventDraft):
        return JSONResponse(event_store.append(draft).model_dump(mode="json"))

    @application.get("/api/v1/runs/{run_id}/events")
    def list_events(run_id: UUID, after: int = Query(default=0, ge=0)):
        return [event.model_dump(mode="json") for event in event_store.list_events(str(run_id), after)]

    @application.get("/api/v1/runs/{run_id}/events/stream")
    async def stream_events(run_id: UUID, after: int = Query(default=0, ge=0)):
        return StreamingResponse(event_stream(event_store, run_id, after), media_type="text/event-stream")

    return application


def _approval_json(approval) -> dict:
    result = asdict(approval)
    for key in ("id", "run_id"):
        result[key] = str(result[key])
    for key in ("created_at", "expires_at", "decided_at"):
        if result[key] is not None:
            result[key] = result[key].isoformat()
    return result


app = create_app()
