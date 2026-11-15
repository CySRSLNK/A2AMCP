# A2A to MCP Security Lab

[中文文档](README_zh.md)

This repository contains a local Docker Compose lab for studying recursive A2A delegation, MCP tools/resources, prompt injection, policy enforcement, and replay behavior. The default topology is a root agent, a worker agent, a gateway, four fixture MCP servers, a control plane, PostgreSQL, and a browser workbench.

## Start the scaffold

```bash
cp .env.example .env
docker-compose up --build
```

The web workbench is available at `http://127.0.0.1:5173` and the control-plane health endpoint is `http://127.0.0.1:8000/healthz`. On systems with the Compose plugin, use `docker compose` instead.

The Workbench `Model output` panel shows the final content returned by the complete delegation chain. For example, when the calculator MCP tool returns `15`, the panel shows `15` instead of an intermediate `delegate` or `mcp_call` decision. The event timeline defaults to key events and hides duplicate-looking intermediate A2A relay responses; switch to `All events` to inspect the complete protocol evidence. Model requests expose only safe metadata; full prompts and API keys are never shown in the panel or event stream.

## Remote deployment

Ubuntu 22.04 can run the same stack with Docker Engine and the Compose plugin. For access through the server's IP, set `LAB_BIND_HOST=0.0.0.0` in the server's `.env` and open `http://SERVER_IP:5173`. The browser uses same-origin `/api` requests; Nginx in the web container proxies them to `control-plane:8000`, with response buffering disabled for SSE and a long read timeout for delegated tasks. Browser access does not require opening port 8000 or adding a server-specific CORS origin. `LAB_BIND_HOST` controls both published ports, so restrict external access to port 8000 through the server's security group. The control console has no built-in login; use an SSH tunnel, source restrictions, or an authenticated reverse proxy.

For an existing deployment, rebuild the web container to replace the old JavaScript and add the proxy:

```bash
git pull --ff-only
docker compose up -d --build --no-deps web
curl -i http://127.0.0.1:5173/api/v1/scenarios
```

The last request should return a JSON array, not the SPA's HTML. With legacy Compose, use `docker-compose` instead. Refresh the browser with `Ctrl+F5` after rebuilding. Leave `VITE_CONTROL_PLANE_URL` unset for the default same-origin setup; remove any old frontend build override pointing at `127.0.0.1:8000`. Local `npm run dev` uses Vite's `/api` proxy to the local backend on port 8000. Match `MCP_FILE_WRITER_UID`/`MCP_FILE_WRITER_GID` to the fixture directory's owner, and set `CONFIG_ENCRYPTION_KEY` before saving model API keys in the console.

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
{"action":"mcp_call","server_id":"mcp-file-writer","tool_name":"write_file","arguments":{"path":"result.txt","content":"local experiment output"},"summary":"Write a local fixture file."}
```

```json
{"action":"answer","summary":"The task is complete."}
```

The root agent is allowed to delegate to `worker-agent` and has no MCP tools by default. The worker agent can delegate recursively and use `calculator`, `fixture_http_get`, the isolated `read_file` tool on `mcp-file-reader`, or the isolated `write_file` tool on `mcp-file-writer`. Invalid JSON, unknown agents, unknown MCP servers, disallowed tools, and excessive hop depth fail closed.

The `mcp-file-reader` fixture reads UTF-8 files from a read-only mount of `fixtures/`. Its `read_file` tool accepts a relative `path`, so `{"path":"example.txt"}` reads `fixtures/example.txt`, and returns the file text as MCP content. Absolute paths, path traversal, directories, non-UTF-8 files, and files larger than `MCP_FILE_MAX_BYTES` are rejected. The returned text is untrusted data and should be treated as a prompt-injection test input.

The `mcp-file-writer` fixture writes UTF-8 files through a writable mount of the same `fixtures/` directory. Its `write_file` tool accepts a relative `path` and string `content`, enforces `MCP_FILE_WRITER_MAX_BYTES`, rejects absolute paths, path traversal, directories, and partial writes, and returns only the relative path and byte count. It has no host port and is intended for local write-boundary experiments. A file written as `result.txt` can immediately be read by `read_file` with the same path. Host edits also take effect without restarting either MCP service. The sample files `example.txt` and `email.txt` are tracked; other fixture outputs are ignored by Git.

The writer process defaults to UID/GID `1000:1000` so a bind-mounted directory created by the usual local user is writable without running as root. On a server, set `MCP_FILE_WRITER_UID` and `MCP_FILE_WRITER_GID` to the owner of the shared `fixtures/` directory before starting Compose, or grant that configured user ownership of the directory. Starting Compose as root does not override the writer's configured container user.

To upgrade an existing deployment, stop both file MCP services before migrating. The ownership commands below assume the default writer UID/GID; substitute your configured values if different:

```bash
docker compose stop mcp-file-reader mcp-file-writer
git pull --ff-only
python3 scripts/migrate_fixtures.py
sudo chown 1000:1000 fixtures
sudo chmod 755 fixtures
docker compose up -d --force-recreate mcp-file-reader mcp-file-writer
```

The migration script moves legacy files and subdirectories into `fixtures/`, preserves their content and permissions, and removes the empty legacy directories. Name conflicts with the root or between legacy directories abort before moving any data; rename conflicting entries and retry. The script can be rerun after migration. With legacy Compose, use `docker-compose` instead.

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
