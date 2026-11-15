# Model Output Panel Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Record each model decision as a safe protocol event and show the final delegated task output in a live Web Workbench panel.

**Architecture:** Agent Runtime emits `model` request/response/error events through the existing Control Plane event API using the task correlation context. The existing SSE event stream delivers all events to the browser, where `ModelOutputPanel` extracts the outermost A2A final response and `EventTimeline` hides intermediate relay responses by default without adding a second run-result API.

**Tech Stack:** Python 3.12, FastAPI, Pydantic, httpx, React, TypeScript, Vite, Vitest.

**Spec:** `docs/superpowers/specs/2026-11-15-model-output-panel-design.md`

## Global Constraints

- Model events must not include API keys or complete prompts.
- Model event payloads remain subject to the existing Control Plane redaction and size limits.
- Existing A2A/MCP event contracts and SSE endpoints remain backward compatible.
- A telemetry failure must not fail an otherwise valid model decision.

## Review Focus

- Event emission must preserve the current task/run correlation context; test in Task 1.
- A model timeout or invalid decision must produce an observable error event without changing fail-closed behavior; test in Task 1.
- Final A2A output may be missing or non-object shaped at the UI boundary; test in Task 2.
- The final output panel must extract the outermost A2A result while preserving event order; test in Task 2.
- The empty state must remain useful before the first model event; test in Task 2.

### Task 1: Emit Model Decision Events

**Files:**
- Modify: `services/agent_runtime/app/planner.py`
- Modify: `services/agent_runtime/app/main.py`
- Create: `services/agent_runtime/tests/test_model_events.py`

**Interfaces:**
- `AgentRuntime.__init__(..., event_sink: Callable[[EventDraft], Any] | None = None)` accepts an optional synchronous event sink.
- The runtime emits `EventDraft` values with protocol `model` and operations `completion.request`, `completion.response`, or `completion.error`.
- The main service passes `EventClient(...).append` as the event sink; tests inject an in-memory collector.

- [ ] **Step 1: Write the failing tests**

Add tests that run a scripted model through `AgentRuntime.handle_task` and assert:

- successful completion emits one outbound `completion.request` and one inbound `completion.response` event;
- both events carry the input task's `run_id`, `task_id`, `agent_id`, and `hop`;
- response payload contains `provider`, `model`, `output`, and `usage`;
- a model timeout emits one inbound `completion.error` event and returns `failed`;
- emitted request payload contains metadata only and no `messages` or API key fields.

- [ ] **Step 2: Run the focused tests and verify they fail**

Run: `pytest services/agent_runtime/tests/test_model_events.py -q`

Expected: FAIL because `AgentRuntime` does not accept an event sink and emits no model events.

- [ ] **Step 3: Implement model event emission**

In `planner.py`, create the correlation context before the model call, emit a metadata-only request event, emit a response event after `ModelResponse`, and emit a stable error summary for timeout, HTTP, validation, or value failures. Wrap telemetry writes so event delivery errors are ignored. Use source keys derived from the task id and operation suffix.

In `main.py`, construct an `EventClient` for `CONTROL_PLANE_URL` (default `http://control-plane:8000`) and pass its `append` method to both agent runtime instances through the existing module-level runtime construction.

- [ ] **Step 4: Run the focused tests and verify they pass**

Run: `pytest services/agent_runtime/tests/test_model_events.py -q`

Expected: PASS.

### Task 2: Add the Live Model Output Panel

**Files:**
- Create: `apps/web/src/features/runs/ModelOutputPanel.tsx`
- Create: `apps/web/src/features/runs/ModelOutputPanel.test.tsx`
- Modify: `apps/web/src/main.tsx`
- Modify: `apps/web/src/styles.css`

**Interfaces:**
- `ModelOutputPanel({ events }: { events: ProtocolEvent[] })` receives the full run event list.
- The component extracts the outermost A2A final result, shows its agent/hop metadata, and prints the returned text or structured output.

- [ ] **Step 1: Write the failing component tests**

Add tests that assert:

- an empty `events` array renders the model output empty state;
- an outermost A2A response renders the final returned text;
- an error event renders an error state and the error summary;
- intermediate model and A2A relay events do not replace the final output.

- [ ] **Step 2: Run the focused test and verify it fails**

Run: `npm test -- --run apps/web/src/features/runs/ModelOutputPanel.test.tsx`

Expected: FAIL because the component does not exist.

- [ ] **Step 3: Implement the panel and integrate it**

Implement defensive payload normalization in `ModelOutputPanel.tsx`. In `main.tsx`, pass the full `events` state to the panel and render it in the Workbench side column. Add compact, responsive styles that match the existing dark workbench and keep long output scrollable.

- [ ] **Step 4: Run the focused test and verify it passes**

Run: `npm test -- --run apps/web/src/features/runs/ModelOutputPanel.test.tsx`

Expected: PASS.

### Task 3: Full Verification and Documentation

**Files:**
- Modify: `README.md`
- Modify: `README_zh.md`

- [ ] **Step 1: Document the new panel**

Add a short Workbench note explaining that the final delegated result appears in the Model output panel, while the event timeline can switch between key events and the complete A2A/MCP protocol trace; state that prompts and API keys are not displayed there.

- [ ] **Step 2: Run the full verification suite**

Run: `pytest -q` and `npm test -- --run` and `npm run build` from `apps/web`.

Expected: all existing and new tests pass, and the frontend build succeeds.

- [ ] **Step 3: Verify the Compose path**

Run: `docker-compose up -d --build` followed by `docker-compose ps` and confirm all eight services are healthy. Start a mediated run and confirm the model output panel receives at least one model response event.
