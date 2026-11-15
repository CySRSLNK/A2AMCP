# A2A to MCP Attack Catalog Design

## Intent

Add a local, reviewable attack catalog for cross-MCP and A2A-to-MCP security research. The catalog turns public taxonomies and benchmark families into normalized, defanged cases that can be browsed from the control plane and frontend without sending traffic to external targets.

## Goals

- Store attack cases as versioned YAML that is easy to review, diff, and extend.
- Cover cross-MCP trust-boundary problems and A2A delegation chains that end in MCP calls.
- Preserve source attribution, prerequisites, expected protocol path, impact, and detection oracle.
- Validate that catalog entries are local-only and do not contain arbitrary executable payloads.
- Expose catalog listing, detail, and dry-run plan endpoints through the control plane.
- Let the browser workbench browse cases and preview the expected event chain without starting a run.
- Keep the first release descriptive and deterministic; local exploit fixtures can be added later as separate scenarios.

## Non-goals

- Running attack payloads against public or third-party MCP/A2A services.
- Embedding shell commands, arbitrary URLs, credential material, or destructive actions in catalog entries.
- Claiming that a benchmark case is a verified vulnerability in every implementation.
- Dynamically provisioning containers per attack case.
- Replacing the existing mediated run and replay model.

## Constraints

- The catalog must use the existing Pydantic/YAML patterns in `shared/python/lab_core`.
- Existing scenario validation and Compose topology remain compatible.
- Catalog data is local and read-only at runtime; mutations happen through reviewed repository changes.
- Every case must declare `safe_fixture: local-only` and at least one expected protocol.
- The dry-run plan must have no network or filesystem side effects beyond reading the catalog.
- Public references are identifiers and citations, not copied attack payloads.

## Chosen Approach

Use a typed `AttackCase` model and `AttackCatalogLoader` alongside the existing scenario loader. Keep one checked-in catalog file at `scenarios/attack-catalog.yaml`, grouped by `cross-mcp` and `a2a-mcp` protocol paths. Each case contains an ID, title, category, source references, preconditions, injection point, expected event chain, impact, detection oracle, safety classification, and a deterministic dry-run prompt.

The control plane loads the catalog at startup and exposes `GET /api/v1/attacks`, `GET /api/v1/attacks/{attack_id}`, and `GET /api/v1/attacks/{attack_id}/plan`. The plan endpoint returns normalized steps only; it does not create a run or call a model, Agent, MCP Server, or external endpoint.

The frontend adds an attack catalog panel beside the existing scenario form. Researchers can filter by protocol path, select a case, and inspect its preconditions and expected events. The panel is read-only in the MVP; it does not start a run or associate a run with a case.

## Attack Case Schema

Required fields:

- `id`: stable identifier such as `MCP-X-001` or `A2A-MCP-001`.
- `version`: positive integer within a stable case ID.
- `runnable`: whether the current fixed Compose topology has a local fixture that can exercise the case.
- `fixture_scenario_id`: optional scenario ID required when `runnable` is true.
- `protocol_path`: `cross-mcp` or `a2a-mcp`.
- `category`: normalized attack family.
- `title` and `summary`: operator-facing description.
- `sources`: public benchmark or taxonomy identifiers.
- `preconditions`: bounded assumptions required for the case.
- `injection_point`: where untrusted data enters the chain.
- `expected_events`: typed ordered event expectations using the currently observable `a2a` and `mcp` protocol operations, direction, actor, and target.
- `impact`: security consequence category.
- `oracle`: observable evidence that distinguishes the expected behavior.
- `safe_fixture`: must be `local-only` for the MVP.
- `dry_run_prompt`: deterministic prompt suitable for the local fixture scenario.

Optional fields include `mitigations`, `notes`, and `references` metadata. Unknown fields are rejected to keep catalog entries reviewable.

## Initial Catalog Coverage

The first catalog contains representative, defanged cases:

- Cross-MCP tool shadowing and name collision.
- Cross-MCP tool-description poisoning and response injection.
- Cross-MCP token audience confusion and over-sharing.
- Agent Card spoofing or capability inflation before delegation.
- A2A message/context injection before an MCP call.
- Multi-hop identity loss and confused-deputy behavior.
- Artifact-triggered injection crossing from A2A into MCP.
- Recursive delegation cycle and bounded resource exhaustion.
- Agent-side request forgery reaching a local MCP fixture.

These entries describe expected observations and safe fixture boundaries; they do not include exploit strings or external destinations. Cases that depend on artifact or policy events that are not emitted by the current MVP are marked descriptive-only rather than runnable.

## API and UI Behavior

`GET /api/v1/attacks` returns stable catalog summaries sorted by ID. `GET /api/v1/attacks/{attack_id}` returns the full typed case. `GET /api/v1/attacks/{attack_id}/plan` returns the case ID, safety classification, prerequisites, ordered protocol steps, and oracle without mutating state.

The frontend keeps the existing run workflow intact. Selecting a case only shows the plan; it does not update the run form or start a run. The UI must clearly distinguish a catalog plan from an executed security finding. Run/case association is deferred until local fixture execution is added.

## Verification

- Unit tests reject duplicate `(id, version)` pairs, unsupported protocol paths, malformed event expectations, non-local fixtures, unsafe free text, and unknown fields.
- Control-plane tests cover listing, detail, missing-case errors, and side-effect-free plan responses.
- Frontend tests cover catalog loading and selecting a case for the prompt field.
- The complete Python and frontend test suites must pass.

## Alternatives Considered

### Import external benchmark repositories at runtime

Rejected because it adds network and supply-chain dependencies, makes experiments non-reproducible, and may import payloads that are unsafe outside their intended harness.

### Store only free-form Markdown notes

Rejected because the UI, API, and future fixture runner need stable fields and machine-checkable safety constraints.

### Build an executable exploit runner first

Rejected because it would blur the boundary between a local research harness and a tool that can target arbitrary services. The catalog and dry-run plan provide a safer foundation for later local fixtures.
