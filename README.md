# A2A to MCP Security Lab

[中文文档](README_zh.md)

This repository contains a local Docker Compose lab for studying recursive A2A delegation, MCP tools/resources, prompt injection, policy enforcement, and replay behavior. The default topology is a root agent, a worker agent, a gateway, two fixture MCP servers, a control plane, PostgreSQL, and a browser workbench.

## Start the scaffold

```bash
cp .env.example .env
docker-compose up --build
```

The web workbench is available at `http://127.0.0.1:5173` and the control-plane health endpoint is `http://127.0.0.1:8000/healthz`. On systems with the Compose plugin, use `docker compose` instead.

The default services are local-only and use a deterministic mock model. External model providers are opt-in through `.env`; model calls still pass through the gateway when configured.

To let a real OpenAI-compatible model decide whether to answer, delegate, or call an MCP tool, set `MODEL_PROVIDER=openai-compatible`, choose `MODEL_NAME`, and point `MODEL_BASE_URL` at a model service reachable from the gateway container:

```dotenv
MODEL_PROVIDER=openai-compatible
MODEL_NAME=your-model
MODEL_BASE_URL=http://model-service:8000
MODEL_API_KEY=your-key
MODEL_REQUEST_TIMEOUT=120
A2A_REQUEST_TIMEOUT=300
MCP_REQUEST_TIMEOUT=60
RUN_REQUEST_TIMEOUT=600
```

The model must return one JSON action. The agent runtime validates the action before execution:

```json
{"action":"delegate","target_agent":"worker-agent","summary":"Delegate the task for fixture inspection."}
```

```json
{"action":"mcp_call","server_id":"mcp-tools","tool_name":"calculator","arguments":{"operation":"add","a":1,"b":2},"summary":"Calculate the result."}
```

```json
{"action":"answer","summary":"The task is complete."}
```

The root agent is allowed to delegate to `worker-agent` and has no MCP tools by default. The worker agent can delegate recursively and use `calculator` or `fixture_http_get`. Invalid JSON, unknown agents, unknown MCP servers, disallowed tools, and excessive hop depth fail closed.

Each agent makes a fresh model decision when it receives a task, so the runtime can produce `root-agent -> worker-agent -> mcp-tools` or `root-agent -> worker-agent -> worker-agent -> mcp-tools` depending on the model output. The runtime accepts the canonical fields `action`, `target_agent`, `server_id`, and `tool_name`, and normalizes common provider aliases `type`, `target`, `server`, and `tool` before applying the same allowlist validation. The timeout variables above keep slower recursive model calls from being cut off by an intermediate HTTP hop.

The first run in the workbench loads `scenarios/recursive-a2a-mcp.yaml`, creates a mediated run, and displays A2A/MCP events in sequence. The terminal equivalent is:

```bash
scripts/smoke.sh
```

Useful endpoints are `POST /api/v1/scenarios`, `POST /api/v1/runs`, `GET /api/v1/runs/{run_id}/events`, and `POST /api/v1/runs/{run_id}/replay`. See [the experiment note](docs/experiments/recursive-a2a-mcp.md) for the event model, security boundaries, and teardown behavior.

## Attack catalog

The repository includes a local-only catalog at `scenarios/attack-catalog.yaml`. It normalizes cross-MCP and A2A-to-MCP cases from public taxonomies and benchmarks into reviewable metadata: prerequisites, injection point, expected A2A/MCP events, impact, oracle, and mitigations. Entries are either `local fixture` cases that map to the fixed Compose topology or `descriptive-only` cases that require a future fixture.

The catalog API is read-only:

```text
GET /api/v1/attacks
GET /api/v1/attacks/{attack_id}?version=1
GET /api/v1/attacks/{attack_id}/plan
```

List cases from a running control plane with:

```bash
scripts/list-attacks.sh
scripts/list-attacks.sh A2A-MCP-005
```

The plan endpoint only reads and validates catalog data. It does not start a run, call a model, invoke an Agent or MCP Server, or contact an external target. The web workbench exposes the same plan view under `Attack catalog`.
