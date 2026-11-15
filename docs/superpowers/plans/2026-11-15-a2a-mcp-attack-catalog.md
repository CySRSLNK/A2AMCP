# A2A to MCP Attack Catalog Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a typed, local-only attack catalog for cross-MCP and A2A-to-MCP research, expose it through the control plane, and make it browsable in the web workbench without executing external payloads.

**Architecture:** Add typed `AttackCase` and `AttackCatalogLoader` beside the existing scenario model. Load `scenarios/attack-catalog.yaml` during control-plane startup and expose summary, detail, and side-effect-free plan endpoints. Extend the existing React workbench with a read-only catalog panel; selecting a case only changes the displayed plan and never starts or tags a run.

**Tech Stack:** Python 3.12+, Pydantic v2, FastAPI, PyYAML, pytest, React 18, TypeScript, Vitest.

**Spec:** `docs/superpowers/specs/2026-11-15-a2a-mcp-attack-catalog-design.md`

## Global Constraints

- Catalog entries must declare `safe_fixture: local-only`.
- The catalog must reject unknown fields, duplicate `(id, version)` pairs, unsupported protocol paths, malformed event expectations, and unsafe free text.
- The plan endpoint is read-only and must not call models, Agents, MCP Servers, or external endpoints.
- Catalog entries contain no arbitrary executable payloads, credential material, or external destinations.
- Existing mediated run and replay behavior remains compatible.
- All default services remain localhost-only.

## Review Focus

- Invalid catalog fields and duplicate IDs must fail at load time with actionable errors. Test in Task 1.
- A case with a non-local fixture must never be exposed as a runnable plan. Test in Task 1.
- The catalog must be available when the control plane starts even if the database has no prior catalog rows. Test in Task 3.
- Missing attack IDs must return a stable 404 without mutating run or event state. Test in Task 3.
- Selecting a catalog case must not silently start a run or issue a network request. Test in Task 4.

---

### Task 1: Attack Catalog Model and Loader

**Files:**
- Create: `shared/python/lab_core/attack_catalog.py`
- Create: `shared/python/lab_core/tests/test_attack_catalog.py`

**Interfaces:**
- Produces `AttackCase`, `AttackCatalog`, `AttackCatalogLoader.load(document: dict[str, Any]) -> AttackCatalog`, and typed nested `EventExpectation`, `Preconditions`, `InjectionPoint`, and `Oracle` values.
- `AttackCase` exposes `id`, `version`, `protocol_path`, `runnable`, `fixture_scenario_id`, `category`, `title`, `summary`, `sources`, `preconditions`, `injection_point`, `expected_events`, `impact`, `oracle`, `safe_fixture`, and `dry_run_prompt`.

- [ ] **Step 1: Write failing loader tests**

```python
def test_loader_accepts_local_cross_protocol_case(): ...
def test_loader_rejects_duplicate_id_and_version(): ...
def test_loader_rejects_unknown_nested_fields(): ...
def test_loader_rejects_non_local_fixture(): ...
def test_loader_rejects_external_url_or_command_text(): ...
def test_loader_rejects_malformed_event_expectation(): ...
```

- [ ] **Step 2: Run the focused tests and verify they fail**

Run: `pytest shared/python/lab_core/tests/test_attack_catalog.py -q`

Expected: FAIL because the attack catalog model and loader do not exist.

- [ ] **Step 3: Implement the typed models and loader**

Use Pydantic `extra="forbid"`; validate `protocol_path` against `cross-mcp` and `a2a-mcp`, event expectations against observable `a2a`/`mcp` protocols and direction values, unique `(id, version)` pairs, `safe_fixture == "local-only"`, and reject external URLs, shell/credential markers, and arbitrary destinations in free-text fields.

- [ ] **Step 4: Run focused tests and verify they pass**

Run: `pytest shared/python/lab_core/tests/test_attack_catalog.py -q`

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add shared/python/lab_core/attack_catalog.py shared/python/lab_core/tests/test_attack_catalog.py
git commit -m "feat: add local attack catalog model"
```

### Task 2: Seed the Local Attack Catalog

**Files:**
- Create: `scenarios/attack-catalog.yaml`
- Create: `services/control_plane/tests/test_attack_catalog_seed.py`
- Modify: `services/control_plane/app/attacks.py`

**Interfaces:**
- Produces `AttackCatalogRegistry.import_document(document)`, `.get(attack_id, version=None)`, `.list()`, and `.plan(attack_id, version=None)`.
- `plan()` returns a JSON-safe dict containing the case metadata, runnable/fixture status, ordered typed event expectations, safety classification, and oracle.

- [ ] **Step 1: Write failing registry and seed tests**

```python
def test_seed_catalog_contains_cross_mcp_and_a2a_mcp_cases(): ...
def test_plan_is_json_safe_and_marks_unavailable_fixtures(): ...
def test_latest_case_version_is_selected_without_ambiguity(): ...
```

- [ ] **Step 2: Run focused tests and verify they fail**

Run: `pytest services/control_plane/tests/test_attack_catalog_seed.py -q`

Expected: FAIL because the registry and seed catalog do not exist.

- [ ] **Step 3: Add the registry and checked-in YAML**

Seed representative defanged cases for tool shadowing, tool-description poisoning, response injection, token audience confusion, Agent Card spoofing, A2A context injection, multi-hop identity loss, artifact injection, bounded recursive delegation, and agent-side request forgery. Mark only cases backed by the current fixed topology as `runnable`; the rest are descriptive-only. Use source identifiers such as `OWASP-MCP-Top10`, `MSB`, `MCPTox`, `Pluto`, `A2ASecBench`, `a2a-scanner`, and `A2ABreak`; do not include executable payloads or public targets.

- [ ] **Step 4: Run focused tests and verify they pass**

Run: `pytest services/control_plane/tests/test_attack_catalog_seed.py -q`

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add scenarios/attack-catalog.yaml services/control_plane/app/attacks.py services/control_plane/tests/test_attack_catalog_seed.py
git commit -m "feat: seed cross-mcp attack catalog"
```

### Task 3: Control Plane Catalog API

**Files:**
- Modify: `services/control_plane/app/main.py`
- Create: `services/control_plane/tests/test_attack_catalog_api.py`

**Interfaces:**
- Add `GET /api/v1/attacks` for summaries.
- Add `GET /api/v1/attacks/{attack_id}` for the latest full case data.
- Add `GET /api/v1/attacks/{attack_id}?version=N` for an explicit case version.
- Add `GET /api/v1/attacks/{attack_id}/plan` for a read-only dry-run plan.

- [ ] **Step 1: Write failing API tests**

```python
def test_list_attacks_returns_seeded_cases(client): ...
def test_get_attack_returns_full_case(client): ...
def test_missing_attack_returns_404(client): ...
def test_plan_endpoint_does_not_create_run_or_event(client): ...
def test_explicit_case_version_is_stable(client): ...
```

- [ ] **Step 2: Run focused tests and verify they fail**

Run: `pytest services/control_plane/tests/test_attack_catalog_api.py -q`

Expected: FAIL because the endpoints and startup registry are not wired.

- [ ] **Step 3: Load the seed catalog at app creation and add endpoints**

Load `ATTACK_CATALOG_PATH` when set, otherwise resolve `scenarios/attack-catalog.yaml` from the application root. Fail fast on missing or invalid catalog data. Keep the existing database-backed scenario loading behavior unchanged. Return stable 404 errors and never create a run from the plan endpoint.

- [ ] **Step 4: Run focused tests and verify they pass**

Run: `pytest services/control_plane/tests/test_attack_catalog_api.py -q`

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add services/control_plane/app/main.py services/control_plane/tests/test_attack_catalog_api.py
git commit -m "feat: expose attack catalog api"
```

### Task 4: Web Workbench Catalog View

**Files:**
- Modify: `apps/web/src/api/client.ts`
- Modify: `apps/web/src/main.tsx`
- Create: `apps/web/src/features/attacks/AttackCatalogPanel.tsx`
- Modify: `apps/web/src/styles.css`
- Create: `apps/web/src/features/attacks/AttackCatalogPanel.test.tsx`

**Interfaces:**
- Add `listAttacks()`, `getAttack()`, and `getAttackPlan()` client methods.
- The panel must not invoke `createRun()` or mutate the operator prompt; it only renders the selected read-only plan.

- [ ] **Step 1: Write failing frontend tests**

```tsx
it("renders a selected local-only case and its expected event chain", async () => { ... });
it("marks descriptive-only cases as unavailable for the fixed fixture topology", async () => { ... });
```

- [ ] **Step 2: Run focused tests and verify they fail**

Run: `cd apps/web && npm test -- --run src/features/attacks/AttackCatalogPanel.test.tsx`

Expected: FAIL because the panel and API methods do not exist.

- [ ] **Step 3: Implement the panel and wire it into the workbench**

Keep the existing mediated run button as the only run trigger. Show protocol path, category, prerequisites, injection point, typed expected events, oracle, source identifiers, runnable/fixture status, and the local-only safety label. Selecting a case changes only the plan view.

- [ ] **Step 4: Run focused tests and verify they pass**

Run: `cd apps/web && npm test -- --run src/features/attacks/AttackCatalogPanel.test.tsx`

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add apps/web/src/api/client.ts apps/web/src/main.tsx apps/web/src/features/attacks apps/web/src/styles.css
git commit -m "feat: browse attack catalog in workbench"
```

### Task 5: Documentation and Full Verification

**Files:**
- Modify: `README.md`
- Modify: `docs/experiments/recursive-a2a-mcp.md`
- Create: `scripts/list-attacks.sh`
- Create: `tests/smoke/test_attack_catalog.py`

- [ ] **Step 1: Write failing smoke/documentation contract tests**

```python
def test_attack_catalog_file_exists_and_has_expected_protocol_paths(): ...
def test_list_attacks_script_uses_read_only_api(): ...
```

- [ ] **Step 2: Run focused tests and verify they fail**

Run: `pytest tests/smoke/test_attack_catalog.py -q`

Expected: FAIL because the script and documentation contract do not exist.

- [ ] **Step 3: Add the read-only CLI helper and documentation**

Document the catalog files, API endpoints, version selection, dry-run semantics, source families, runnable/descriptive distinction, and local-only boundary. The script should list or show cases through the control-plane API and must not start runs.

- [ ] **Step 4: Run the focused test and the complete suites**

Run: `pytest tests/smoke/test_attack_catalog.py -q`

Expected: PASS.

Run: `pytest -q`

Expected: PASS for the full Python suite.

Run: `cd apps/web && npm test && npm run build`

Expected: PASS for frontend tests and TypeScript/Vite build.

- [ ] **Step 5: Commit**

```bash
git add README.md docs/experiments/recursive-a2a-mcp.md scripts/list-attacks.sh tests/smoke/test_attack_catalog.py
git commit -m "docs: document local attack catalog"
```
