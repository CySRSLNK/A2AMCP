# A2A to MCP Security Lab

[中文文档](README_zh.md)

This repository contains a local Docker Compose lab for studying recursive A2A delegation, MCP tools/resources, prompt injection, policy enforcement, and replay behavior. The default topology is a root agent, a worker agent, a gateway, three fixture MCP servers, a control plane, PostgreSQL, and a browser workbench.

## Start the scaffold

```bash
cp .env.example .env
docker-compose up --build
```

The web workbench is available at `http://127.0.0.1:5173` and the control-plane health endpoint is `http://127.0.0.1:8000/healthz`. On systems with the Compose plugin, use `docker compose` instead.

The Workbench `Model output` panel shows the final content returned by the complete delegation chain. For example, when the calculator MCP tool returns `15`, the panel shows `15` instead of an intermediate `delegate` or `mcp_call` decision. The event timeline defaults to key events and hides duplicate-looking intermediate A2A relay responses; switch to `All events` to inspect the complete protocol evidence. Model requests expose only safe metadata; full prompts and API keys are never shown in the panel or event stream.

The `Control` view in the web workbench is a runtime configuration console. It changes the model provider/name/base URL, applies explicit API-key preserve/replace/clear actions, edits root/worker policy allowlists, and manages MCP proxy registrations without restarting Compose. MCP registration is a gateway proxy entry; it does not create or remove containers.

Runtime API keys are encrypted at rest. Generate a Fernet key and set it in `.env` before replacing a key:

```bash
python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
```

```dotenv
CONFIG_ENCRYPTION_KEY=generated-fernet-key
CONTROL_PLANE_INTERNAL_TOKEN=local-internal-token
```

Every new run stores an immutable configuration snapshot in the same database transaction as its run record. Later edits affect only new runs. Agent tasks receive a non-secret projection; the Gateway resolves the full snapshot through a token-protected internal endpoint and is the only component that decrypts the model key for an upstream request.

The control API exposes `GET /api/v1/config`, `PUT /api/v1/config`, `POST /api/v1/config/test-model`, and MCP registration CRUD under `/api/v1/config/mcp`. Updates use `expected_version` for compare-and-swap and `api_key_action` values `preserve`, `replace`, or `clear`. Provider and MCP endpoints are restricted to HTTP(S) origins and reject credentials, redirects, localhost, metadata, and sensitive private networks.

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
{"action":"mcp_call","server_id":"mcp-file-reader","tool_name":"read_file","arguments":{"path":"example.txt"},"summary":"Read the local fixture file."}
```

```json
{"action":"answer","summary":"The task is complete."}
```

The root agent is allowed to delegate to `worker-agent` and has no MCP tools by default. The worker agent can delegate recursively and use `calculator`, `fixture_http_get`, or the isolated `read_file` tool on `mcp-file-reader`. Invalid JSON, unknown agents, unknown MCP servers, disallowed tools, and excessive hop depth fail closed.

The `mcp-file-reader` fixture reads UTF-8 files from the read-only `fixtures/file-reader` directory. Its `read_file` tool accepts a relative `path` and returns the file text as MCP content. Absolute paths, path traversal, directories, non-UTF-8 files, and files larger than `MCP_FILE_MAX_BYTES` are rejected. The returned text is untrusted data and should be treated as a prompt-injection test input.

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
