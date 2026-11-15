# Recursive A2A to MCP experiment

The seeded `recursive-a2a-mcp` scenario keeps the topology fixed: `root-agent` delegates to `worker-agent`, the worker delegates one more logical hop, and the final worker calls the `calculator` tool through the MCP gateway. The mock model is deterministic, so the run is reproducible without external credentials.

Start the stack with `docker-compose up --build` (or `docker compose up --build` on hosts with the Compose plugin), open `http://127.0.0.1:5173`, load the seeded topology, and start a mediated run. The control plane is on port 8000 and the web workbench is on port 5173. `scripts/smoke.sh` performs the same setup from the terminal and prints the run id, final status, and event count.

Every mediated A2A and MCP request is correlated with a run id, task id, agent id, hop, request id, protocol, operation, and per-run sequence. The workbench uses the event stream cursor to reconnect without reordering already received events. Payloads are redacted before persistence and large bodies are stored by SHA-256 under the named artifact volume.

Use the fixture capabilities to study prompt injection and provenance handling without granting shell access or unrestricted network access. The `fixture://notes/security` resource is intentionally explicit about its provenance. The `fixture_http_get` tool accepts only `fixture://` URLs. Policy profiles can limit targets, tools, payload size, hop depth, or require one-shot approvals.

Replay creates a new logical run from retained response bodies. A missing or redacted body returns a non-replayable error and never causes an external request. Destroy a run and its payloads with `scripts/destroy-run.sh RUN_ID`.

The local attack catalog is stored in `scenarios/attack-catalog.yaml`. It contains cross-MCP and A2A-to-MCP cases with source identifiers, typed event expectations, local fixture status, and detection oracles. `scripts/list-attacks.sh` and the web workbench read the catalog through the control-plane API. Catalog plans are read-only; descriptive-only cases are not claims that the current fixed topology can execute or verify the attack.

Event expectations use the lab's observable contract: A2A request events are named `message/send.request`, and `actor` is the `CorrelationContext.agent_id` that emitted the gateway event. `target` records the route selected by the proxy, so a runnable chain starts with `control-plane -> root-agent` before delegated agent hops.

The current MVP captures mediated protocol traffic. Unsupported A2A operations and direct-mode traffic are intentionally outside the complete capture path; use mediated mode when collecting evidence for a security finding.
