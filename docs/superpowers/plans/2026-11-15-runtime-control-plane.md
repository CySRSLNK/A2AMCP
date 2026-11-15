# Runtime Control Plane Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a persistent control backend and Web console for changing model credentials, model names, Agent policies, and MCP Server registrations without restarting Compose, while freezing configuration per run.

**Architecture:** Control Plane owns a singleton active configuration and stores a full immutable encrypted configuration snapshot for each run in the same transaction as `RunRecord`. Agent task payloads carry only the non-secret runtime projection; Gateway resolves the full snapshot by `run_id` from an internal token-protected Control Plane endpoint before model and MCP calls. Existing allowlists remain authoritative and are intersected with the run snapshot. Replay reuses the source snapshot or recorded responses.

**Tech Stack:** FastAPI, SQLAlchemy/PostgreSQL, Pydantic, HTTPX, React/Vite, Vitest, Docker Compose.

**Spec:** `docs/superpowers/specs/2026-11-15-runtime-control-plane-design.md`

## Global Constraints

- API Keys are write-only from the UI and are never returned in public responses, events, or run payloads.
- API keys are encrypted at rest with `CONFIG_ENCRYPTION_KEY`; the resolver token and encryption key are server-side settings, never browser fields.
- Configuration changes affect only runs created after the change; each run uses its frozen snapshot.
- Existing A2A/MCP policy checks, hop limits, and payload redaction remain enabled.
- MCP registrations are limited to HTTP(S) endpoints and validated IDs; disabled servers cannot be selected by an Agent.
- MCP registration manages a proxy endpoint only; it does not create or destroy Compose services. Endpoints reject credentials, redirects, localhost, metadata, and sensitive private ranges, with bounded timeouts and response sizes.
- Updates use `expected_version`/CAS and write an independent `config_audit` record without secrets.
- Existing Compose fixtures remain available as the default configuration.

## Review Focus

- A run created before a configuration edit must still use the old model/MCP snapshot; test in the run creation and resolver task.
- A blank API key update must preserve the existing key, while an explicit replacement must change it; test in config API/store tests.
- Public config and run responses must mask or omit API keys; test all serialization paths.
- A disabled or deleted MCP Server must be rejected for new tasks but remain available through an old run snapshot; test Gateway resolver behavior.
- An invalid endpoint, duplicate server ID, unknown Agent, or unknown tool must fail validation without changing the active config; test API validation and transaction behavior.

### Task 1: Configuration Schema and Persistence

**Files:**
- Create: `services/control_plane/app/runtime_config.py`
- Create: `services/control_plane/alembic/versions/20261115_runtime_control_plane.py`
- Modify: `services/control_plane/app/models.py`
- Modify: `services/control_plane/app/events.py`
- Test: `services/control_plane/tests/test_runtime_config.py`

**Interfaces:**
- `RuntimeConfig`, `ModelRuntimeConfig`, `AgentRuntimeConfig`, and `McpServerRuntimeConfig` Pydantic models.
- `RuntimeConfigStore.get_active() -> RuntimeConfig`
- `RuntimeConfigStore.replace_active(config: RuntimeConfig, api_key_action: Literal["preserve", "replace", "clear"], api_key: str | None, expected_version: int | None) -> RuntimeConfig`
- `RuntimeConfigStore.create_snapshot(run_id: str, config: RuntimeConfig) -> None`
- `RuntimeConfigStore.get_snapshot(run_id: str) -> dict`
- `RuntimeConfigStore.public(config: RuntimeConfig) -> dict`

- [ ] **Step 1: Write failing tests** for default seeding from environment, API-key masking, blank-key preservation, server validation, and immutable per-run snapshots.
- [ ] **Step 2: Run** `.venv/bin/pytest -q services/control_plane/tests/test_runtime_config.py` and verify the tests fail because the store/models do not exist.
- [ ] **Step 3: Add** `RuntimeConfigRecord`, `RunConfigSnapshotRecord`, and `ConfigAuditRecord` tables with an actual migration. Encrypt the API key, validate provider/base URL and MCP endpoints, implement singleton active config, secret-preserving updates, CAS, and immutable JSON snapshots using the existing `EventStore` engine/session factory.
- [ ] **Step 4: Run** the focused tests and then the full Python suite.
- [ ] **Step 5: Commit** `feat: add persistent runtime configuration store`.

### Task 2: Control Plane Configuration API and Run Snapshots

**Files:**
- Modify: `services/control_plane/app/main.py`
- Modify: `services/control_plane/app/orchestrator.py`
- Modify: `services/control_plane/app/executor.py`
- Test: `services/control_plane/tests/test_runtime_config_api.py`

**Interfaces:**
- `GET /api/v1/config` returns a public masked configuration.
- `PUT /api/v1/config` replaces model/agent/MCP configuration with `expected_version` and explicit `api_key_action`; blank input never accidentally clears a key.
- `POST /api/v1/config/test-model` validates a proposed provider/model/base URL without changing active configuration.
- `POST /api/v1/config/mcp`, `PUT /api/v1/config/mcp/{server_id}`, and `DELETE /api/v1/config/mcp/{server_id}` manage MCP registrations.
- `GET /api/v1/runs/{run_id}/runtime-config` is an internal resolver endpoint returning the full decrypted snapshot only with `CONTROL_PLANE_INTERNAL_TOKEN`.

- [ ] **Step 1: Write failing API tests** for masked GET, update semantics, MCP CRUD, invalid input rejection, model test failure reporting, and snapshot immutability.
- [ ] **Step 2: Run** the focused tests and verify the endpoint failures.
- [ ] **Step 3: Add** API routes, initialize the default config from current `.env`/Compose values without overwriting user edits, create a config snapshot atomically with `RunRecord`, and include only a non-secret runtime projection in the initial Agent task.
- [ ] **Step 4: Add** resolver authentication, internal ownership checks, and a response that includes the secret only for Gateway; never expose it through public run/config responses.
- [ ] **Step 5: Run** focused and full Python tests.
- [ ] **Step 6: Commit** `feat: expose runtime configuration control API`.

### Task 3: Dynamic Gateway and Agent Configuration

**Files:**
- Create: `services/gateway/app/runtime_config_client.py`
- Modify: `services/gateway/app/main.py`
- Modify: `services/gateway/app/routes/model.py`
- Modify: `services/gateway/app/routes/mcp.py`
- Modify: `services/gateway/app/mcp.py`
- Modify: `services/agent_runtime/app/planner.py`
- Modify: `services/agent_runtime/app/model_proxy.py`
- Modify: `services/agent_runtime/app/main.py`
- Modify: `services/agent_runtime/app/a2a_client.py`
- Test: `services/gateway/tests/test_runtime_config_client.py`
- Test: `services/gateway/tests/test_dynamic_model_proxy.py`
- Test: `services/gateway/tests/test_dynamic_mcp_proxy.py`
- Test: `services/agent_runtime/tests/test_runtime_config_snapshot.py`

**Interfaces:**
- `RuntimeConfigClient.get_snapshot(run_id: UUID) -> dict` (sends the internal token and caches only for the request)
- `ModelProxy.forward(payload: dict, run_id: UUID | None = None) -> httpx.Response`
- `McpProxy` resolves the endpoint for `(run_id, server_id)` from the run snapshot before forwarding.
- `TaskInput.runtime_config` contains provider/model, agent permissions, MCP IDs, and snapshot version, never the API key.

- [ ] **Step 1: Write failing tests** proving model requests use the run snapshot, MCP calls use the snapshot endpoint, Agent decisions use snapshot model/allowlist values, and the API key never enters task/event payloads.
- [ ] **Step 2: Run** the focused tests and confirm the current env-only behavior fails them.
- [ ] **Step 3: Add** the Gateway resolver client and run-ID propagation through model headers; keep static env configuration as fallback for health checks and non-run calls. Do not place the key in task/body/header.
- [ ] **Step 4: Update** Agent Runtime to read model name/provider and effective Agent/MCP allowlists from `TaskInput.runtime_config`; keep the current intersection with scenario policy.
- [ ] **Step 5: Update** Gateway model/MCP routes to resolve the frozen snapshot and preserve current policy checks, timeouts, response redaction, endpoint validation, and disabled/unknown server rejection.
- [ ] **Step 6: Run** focused tests and full Python tests.
- [ ] **Step 7: Commit** `feat: apply frozen runtime config to agent and gateway calls`.

### Task 4: Web Control Console

**Files:**
- Modify: `apps/web/src/api/client.ts`
- Modify: `apps/web/src/main.tsx`
- Create: `apps/web/src/features/control/ControlPanel.tsx`
- Create: `apps/web/src/features/control/ControlPanel.test.tsx`
- Modify: `apps/web/src/styles.css`

**Interfaces:**
- TypeScript types mirror the public config response and MCP registration form.
- The UI has Model, Agent Policy, and MCP Server sections with save/test/enable/delete actions.
- Existing run workbench remains the default view; Control is an adjacent panel accessible without losing the current run.

- [ ] **Step 1: Write failing Vitest tests** for loading masked configuration, preserving a blank API key, adding/editing/removing MCP Server rows, and rendering validation errors.
- [ ] **Step 2: Run** `npm test -- --run apps/web/src/features/control/ControlPanel.test.tsx` and confirm failure.
- [ ] **Step 3: Add** API client functions and the control panel using the existing form/select/button styling, with no secret value rendered after load.
- [ ] **Step 4: Add** save/test feedback and keep the current run state intact while switching panels.
- [ ] **Step 5: Run** all frontend tests and `npm run build`.
- [ ] **Step 6: Commit** `feat: add runtime configuration control console`.

### Task 5: Compose, Documentation, and End-to-End Verification

**Files:**
- Modify: `.env.example`
- Modify: `README.md`
- Modify: `README_zh.md`
- Modify: `docker-compose.yml`
- Create: `services/control_plane/tests/test_runtime_config_e2e.py`

- [ ] **Step 1: Add** `CONFIG_CONTROL_ENABLED`, resolver URL, `CONTROL_PLANE_INTERNAL_TOKEN`, `CONFIG_ENCRYPTION_KEY`, and safe default timeout/config variables to Compose and `.env.example`.
- [ ] **Step 2: Document** API endpoints, UI usage, snapshot semantics, secret handling, MCP registration format, and a local configuration example.
- [ ] **Step 3: Add** an end-to-end test that changes the active model/MCP config, creates two runs around the change, and proves each run resolves its own snapshot while old snapshots survive disable/delete.
- [ ] **Step 4: Run** `.venv/bin/pytest -q`, `npm test`, `npm run build`, `docker-compose config --quiet`, and a Compose health check.
- [ ] **Step 5: Commit** `docs: document runtime control backend` and push the completed feature.
