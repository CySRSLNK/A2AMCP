# A2A-to-MCP Security Lab Design

## Intent

Build a local, disposable experiment platform for studying how an LLM-driven root agent delegates work through A2A, how delegated agents recursively delegate through A2A, and how agents use MCP tools and resources. The platform must make every hop inspectable and make security behavior configurable so the same scenario can be replayed with different policies, faults, and agent/tool implementations.

The first release targets one researcher running experiments on a workstation. It is a laboratory, not a production multi-tenant service.

## Goals

- Start the complete lab with Docker Compose and one command.
- Register agents with A2A Agent Cards and expose standards-compatible task/message endpoints.
- Let the root agent create child tasks through A2A, including recursive delegation by worker agents.
- Let agents discover and call MCP tools/resources through MCP clients.
- Route A2A and MCP traffic through a transparent experiment gateway that can record, inspect, allow, deny, delay, mutate, or replay calls.
- Show topology, live task state, protocol messages, tool calls, policy decisions, artifacts, and errors in a browser.
- Persist runs as append-only events so a run can be replayed without calling the model or tools again.
- Provide safe defaults: local-only exposure, explicit tool allowlists, bounded resources, redaction, timeouts, and disposable workspaces.
- Support a deterministic mock model and an OpenAI-compatible model adapter so protocol experiments do not require credentials.

## Non-goals

- Production-grade identity, billing, or multi-tenant isolation.
- Full Kubernetes deployment in the first release.
- Arbitrary host shell access from an MCP server.
- Supporting every A2A binding, MCP transport, or vendor-specific extension on day one.
- Treating the browser as a trusted control plane for secrets.

## Anti-goals

- Hiding protocol traffic behind a chat-only interface.
- Making destructive tools reachable by default.
- Using the model transcript as the only source of truth for what happened.
- Making a protocol adapter that silently changes messages while claiming to be transparent.

## Constraints

- The repository is currently an empty Git repository, so the initial structure must be self-contained and easy to run.
- The lab must run on a developer workstation with Docker Compose; external cloud services are optional.
- All generated runs and credentials must remain local unless the researcher explicitly configures an external model endpoint.
- Every network boundary must be observable and attributable to a run, agent, task, or tool call.
- Security experiments may contain intentionally hostile prompts or agent/tool behavior. The default deployment must bind only to localhost and must not mount the host filesystem into agent containers.

## Chosen Approach

Use a Docker Compose deployment with independently running Python services and a React frontend.

The control plane owns scenario definitions, run state, the event log, policy evaluation, and the public API. An experiment gateway is the only configured destination for A2A and MCP traffic in the default scenario. It forwards standards-compatible requests to registered agent and MCP services while recording the original request, forwarded request, response, timing, policy result, and fault-injection result. The gateway can be disabled per run to compare direct and mediated behavior.

Each agent runs the same reusable runtime image with role configuration. The root agent receives the user task and model response, decides whether to answer or delegate, and calls worker Agent Cards through A2A. A worker may call another Agent Card through the same A2A client. Agents reach MCP servers through an MCP client configured with the gateway endpoint. A worker's delegation and tool use therefore appear as child events under the originating task.

The frontend is a workbench rather than a marketing page. The primary screen is a run workspace with a left-side topology, a central live event timeline, and a right-side inspector for the selected task, A2A message, MCP call, artifact, or policy decision. Separate views cover scenarios, registered Agent Cards, MCP capabilities, and replay.

## System Shape

```text
Browser
  |
  | REST + SSE
  v
Control Plane ---- PostgreSQL event store
  |  \- scenario/run/policy APIs
  |
  \- Experiment Gateway
       |  \- A2A JSON-RPC/HTTP forwarding
       |  \- MCP forwarding
       |  \- capture, policy, delay, mutation, replay
       |
       +--> root-agent
       +--> worker-agent-* ----> mcp-server-*
```

The first transport slice supports A2A over HTTP with JSON-RPC requests and streaming events where the selected SDK supports them. MCP starts with the transport that is easiest to isolate inside Compose, while keeping the client/server interface behind an internal adapter so a second transport can be added without changing scenarios or the UI.

## Services and Responsibilities

### `control-plane`

- FastAPI HTTP API for scenarios, runs, registry, policies, event queries, and replay.
- Run manager that creates a root task and tracks parent/child task relationships.
- Policy engine for allow/deny/approval decisions on A2A delegation, MCP tool calls, artifact access, and outbound network destinations.
- Append-only event writer and SSE publisher.
- Model provider interface with `mock` and `openai-compatible` implementations.

### `experiment-gateway`

- A2A proxy for Agent Card lookup, task creation, task updates, messages, artifacts, and streaming responses.
- MCP proxy for capability discovery, tool calls, resource reads, and prompt retrieval.
- Correlation headers and event envelopes carrying `run_id`, `task_id`, `parent_task_id`, `agent_id`, `protocol`, and `hop`.
- Policy and fault-injection hooks before forwarding and after receiving a response.
- Raw payload capture with configurable redaction and body-size limits.

### `agent-runtime`

- Loads one agent role from environment/configuration.
- Serves an Agent Card and A2A endpoint.
- Uses the model adapter to decide whether to answer, delegate, or call an MCP capability.
- Maintains a bounded local context and emits structured reasoning decisions without persisting hidden chain-of-thought.
- Creates child A2A tasks through the gateway and records delegation rationale as an operator-visible summary.

### `mcp-server-*`

Initial servers are intentionally narrow and local: calculator/data transform, a fixture-backed file/resource server, and a controlled HTTP fixture server. They expose no host shell and no unrestricted filesystem. Later experiments can add intentionally vulnerable servers as separate images.

### `web`

- React + TypeScript single-page workbench.
- Run creation form with scenario, root agent, model adapter, policy set, and fault profile.
- Live topology and event timeline over SSE.
- Inspectors for Agent Cards, A2A envelopes, MCP calls/results, policy decisions, artifacts, and errors.
- Replay controls that select an event range and run it against recorded responses.

### `postgres`

Stores scenario versions, agent/MCP registrations, runs, tasks, artifacts metadata, policies, and append-only events. Payloads are JSON with indexed correlation fields so the UI can filter by run, task, hop, protocol, or capability.

## Core Data Model

- `Scenario`: immutable versioned definition of agents, MCP servers, policies, model adapter, and fault profile.
- `Run`: one execution of a scenario, with status, timestamps, root task, and replay source.
- `AgentRegistration`: agent id, Agent Card, endpoint, capabilities, trust labels, and enabled state.
- `McpRegistration`: server id, endpoint/transport, advertised capabilities, trust labels, and enabled state.
- `Task`: A2A task id, parent task id, owner agent, requested capability, status, and artifact references.
- `Event`: append-only envelope with sequence, correlation ids, direction, protocol, operation, redacted request/response, policy decision, fault action, and timing.
- `PolicyDecision`: rule id, input summary, outcome (`allow`, `deny`, `approval_required`), and reason.
- `Artifact`: content metadata, producing task, media type, hash, and storage reference. Large bodies are stored separately from the event row.

## Scenario Format

Scenarios are JSON or YAML documents stored with a version and imported through the control plane. The first schema includes:

- agent ids, roles, Agent Card metadata, model adapter, initial system policy, and allowed A2A targets;
- MCP server ids, capability allowlists, fixture data, and network policy;
- policy rules for delegation depth, tool names, destinations, payload sizes, approvals, and secrets;
- fault actions such as delay, timeout, malformed response, dropped stream, duplicate delivery, and replayed response;
- redaction and retention settings.

The runtime must reject unknown scenario fields unless the document opts into an extension namespace. This keeps experiments reproducible and makes malformed configuration visible.

## Security Boundaries

- Compose services use a private network; only the control plane and web UI bind to localhost by default.
- Agent and MCP containers run as non-root users with read-only root filesystems, dropped Linux capabilities, bounded CPU/memory/PIDs, and no host mounts.
- The gateway enforces destination allowlists and request size/time limits.
- Credentials are injected only into the selected service process and are never written into event payloads; default logs redact common token and key patterns.
- Dangerous capabilities require a policy rule and an explicit run-time approval event.
- A run can be destroyed as a unit, including ephemeral workspaces and captured payloads.
- The UI may display sensitive payloads only when the run policy enables it; otherwise it shows redacted fields with hashes and sizes.

## MVP Acceptance Criteria

1. `docker compose up` starts the web UI, control plane, gateway, one root agent, one worker agent, two MCP fixture servers, and PostgreSQL.
2. A researcher can create a run with a natural-language task from the UI.
3. One demonstration run exercises both recursive A2A delegation and MCP usage: the root agent delegates to the worker, the worker delegates to a second logical worker hop, and the resulting task chain calls an MCP tool or reads an MCP resource.
4. The UI shows the topology and a live, ordered event timeline containing the parent/child task chain and A2A/MCP calls.
5. A policy can deny a selected MCP tool or enforce a maximum delegation depth, and the UI shows the decision and resulting task state.
6. A run can be replayed from captured responses without calling the model or MCP server.
7. A test suite covers correlation IDs, parent/child task creation, policy decisions, redaction, replay determinism, and gateway forwarding for one A2A and one MCP operation.

## Alternatives Considered

### Single-process simulator

Fastest to prototype, but it collapses the very trust and network boundaries the lab is intended to study. It remains useful as a test fixture, not as the primary deployment.

### Kubernetes-first deployment

Offers stronger isolation and realistic service discovery, but increases iteration time and makes the first experiments harder to reproduce. It should be a later deployment target once the Compose protocol contracts and event model are stable.

## Resolved MVP Decisions

The builder review identified several choices that would otherwise make the first implementation ambiguous. These are fixed for the MVP:

- **Provisioning:** Compose starts a fixed topology: one root agent, one worker agent, two fixture MCP servers, one gateway, one control plane, one web UI, and PostgreSQL. Scenarios select and configure these registrations; they do not create arbitrary containers or networks per run. Adding dynamic provisioning is a later project.
- **Protocol surface:** A2A supports Agent Card lookup plus `send`, `get`, `cancel`, and `stream` task operations. MCP uses Streamable HTTP and supports `tools/list`, `tools/call`, and `resources/read`. Other operations are rejected with a recorded unsupported-operation event.
- **Model-call boundary:** Agents call a `model-proxy` through the experiment gateway. The proxy supports the deterministic mock adapter and an OpenAI-compatible adapter. Request metadata and model responses are captured as events; hidden chain-of-thought is never persisted or displayed.
- **Replay:** Replay creates a new run that re-executes the agent state machines against recorded model and protocol responses. New runtime IDs are mapped to original logical IDs, task parentage and policy outcomes are preserved, and a missing or redacted response makes the replay explicitly non-replayable instead of silently calling an external service.
- **Concurrent runs:** Multiple runs may overlap against the fixed stateless agent and fixture services. Run/task correlation is mandatory on every gateway request. Fixture state is read-only in the MVP; per-run mutable workspaces are deferred until the artifact subsystem is added.
- **Gateway bypass:** Mediated traffic is the default and the only mode with complete protocol capture. An explicit direct mode is allowed for comparison experiments, records only run-level control events, and is labeled as unobserved network traffic in the UI.
- **Approvals and policies:** Policies are immutable after a run starts. An `approval_required` decision pauses the affected task; the browser can issue a one-shot approval or denial with an audit event. Approval timeout becomes a denial and the task transitions to `blocked` or `failed` according to the operation type.
- **Event ordering:** The database assigns a strictly increasing per-run sequence in the same transaction as the event insert. SSE delivery is at-least-once with the sequence as the resume cursor; duplicate source events are idempotent, while duplicate deliveries remain visible as delivery metadata.
- **Payload storage:** Small redacted payloads are stored as JSONB. Large or explicitly retained bodies go into a local content-addressed volume with hash and size metadata. Destroying a run deletes payload blobs and event rows together; a tombstone is retained only when a parent run references the deletion for audit.
- **Failures and retries:** The gateway records each fault as a distinct event. Read-only discovery/read operations may retry once with an idempotency key; side-effecting calls are never retried automatically. Duplicate requests are represented as separate delivery events but share the original idempotency key.
- **Auth and trust:** The MVP uses per-service local bearer tokens checked by the gateway and trust labels in the registry. Signed Agent Cards, delegated credentials, and external identity providers are later extensions.
- **Artifacts:** Text and JSON artifacts up to 1 MiB are stored inline; larger artifacts use the content-addressed volume. Cross-task access requires an explicit artifact reference and is subject to policy. Replay reuses retained artifact bytes and fails clearly when they were redacted or destroyed.

Remaining builder choices are implementation details: exact compatible SDK versions, migration tooling, frontend graph/timeline libraries, and the internal shape of model decision summaries.

## References

- A2A protocol: https://a2a-protocol.org/latest/
- A2A Python SDK: https://github.com/a2aproject/a2a-python
- Model Context Protocol specification: https://modelcontextprotocol.io/specification/
- MCP Python SDK: https://github.com/modelcontextprotocol/python-sdk
