# A2A to MCP Security Lab

This repository contains a local Docker Compose lab for studying recursive A2A delegation, MCP tools/resources, prompt injection, policy enforcement, and replay behavior. The default topology is a root agent, a worker agent, a gateway, two fixture MCP servers, a control plane, PostgreSQL, and a browser workbench.

## Start the scaffold

```bash
cp .env.example .env
docker-compose up --build
```

The web workbench is available at `http://127.0.0.1:5173` and the control-plane health endpoint is `http://127.0.0.1:8000/healthz`. On systems with the Compose plugin, use `docker compose` instead.

The default services are local-only and use a deterministic mock model. External model providers are opt-in through `.env`; model calls still pass through the gateway when configured.

The first run in the workbench loads `scenarios/recursive-a2a-mcp.yaml`, creates a mediated run, and displays A2A/MCP events in sequence. The terminal equivalent is:

```bash
scripts/smoke.sh
```

Useful endpoints are `POST /api/v1/scenarios`, `POST /api/v1/runs`, `GET /api/v1/runs/{run_id}/events`, and `POST /api/v1/runs/{run_id}/replay`. See [the experiment note](docs/experiments/recursive-a2a-mcp.md) for the event model, security boundaries, and teardown behavior.
