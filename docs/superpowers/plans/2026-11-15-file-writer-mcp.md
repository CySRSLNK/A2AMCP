# File Writer MCP Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Add an isolated local `mcp-file-writer` fixture that exposes a safe `write_file` MCP tool through the existing A2A-to-MCP pipeline.

**Architecture:** Reuse the existing fixture server and JSON-RPC transport, adding a dedicated `file-writer` mode and helper module. Mount a separate writable fixture directory into a new Compose service, register it in runtime configuration, and grant the tool only to worker agents by default.

**Tech Stack:** Python 3.12, FastAPI, pytest, Docker Compose, Pydantic runtime configuration, existing MCP JSON-RPC proxy.

**Spec:** `docs/superpowers/specs/2026-11-15-file-writer-mcp.md`

## Global Constraints

- Writes must remain inside `fixtures/file-writer`.
- Absolute paths and path traversal must be rejected.
- The writer must not expose a new host port.
- The tool must be reachable through the existing `mcp_call` action and event pipeline.
- Existing file-reader behavior must remain unchanged.

## Review Focus

- Path traversal and symlink escape: test that resolved paths cannot leave the fixture root.
- Partial writes: test that the final file is replaced atomically and failed writes do not leave a partial target.
- Size and encoding limits: test the configured byte limit and UTF-8 validation.
- Permission propagation: test that a worker can use `write_file` while a root agent without the tool cannot.
- Configuration migration: test that existing runtime configurations gain the new built-in server without silently widening unrelated tools.

### Task 1: Implement the file-writer fixture

**Files:**
- Create: `services/mcp_fixtures/app/file_writer.py`
- Create: `services/mcp_fixtures/tests/test_file_writer.py`
- Modify: `services/mcp_fixtures/app/server.py`
- Modify: `services/mcp_fixtures/app/tools.py` only if shared tool listing requires a small refactor

**Interfaces:**
- Produces `list_tools("file-writer")` with `write_file` and a `write_file(arguments, file_root, max_bytes)` helper.
- The server returns `tools/list`, `tools/call`, and `initialize` responses for `file-writer`.

- [ ] Write failing tests for successful UTF-8 write, list schema, missing arguments, traversal/absolute path rejection, directory rejection, byte limit rejection, and result metadata.
- [ ] Run `pytest services/mcp_fixtures/tests/test_file_writer.py -q` and verify it fails because the mode and helper do not exist.
- [ ] Implement the smallest isolated writer helper using a resolved root, same-directory temporary file, UTF-8 encoding, byte-limit check, and `os.replace`.
- [ ] Add the `file-writer` server mode while preserving `tools` and `file-tools` behavior.
- [ ] Run the focused tests and then `pytest services/mcp_fixtures/tests -q`.

### Task 2: Add the Compose service and fixture directory

**Files:**
- Create: `fixtures/file-writer/.gitkeep`
- Modify: `docker-compose.yml`
- Modify: `.env.example`
- Modify: `tests/smoke/test_compose_config.py`

**Interfaces:**
- Produces a `mcp-file-writer` service using `MCP_FIXTURE_MODE=file-writer`, `MCP_FILE_ROOT=/var/lib/a2a-mcp/files`, and a read-write bind mount of `./fixtures/file-writer`.
- No host `ports` entry is added; the service remains on the `lab` network.

- [ ] Add a failing Compose smoke assertion for the service, mode, volume, and absence of a host port.
- [ ] Run the focused smoke test and verify it fails.
- [ ] Add the service, `MCP_FILE_WRITER_URL`, and `MCP_FILE_WRITER_MAX_BYTES` defaults.
- [ ] Run the smoke test and `docker-compose config` to verify the rendered topology.

### Task 3: Register runtime configuration and Agent permissions

**Files:**
- Modify: `services/control_plane/app/runtime_config.py`
- Modify: `services/control_plane/app/main.py`
- Modify: `services/gateway/app/main.py`
- Modify: `services/agent_runtime/app/main.py`
- Modify: `services/agent_runtime/app/planner.py`
- Modify: `services/control_plane/tests/test_runtime_config.py`
- Modify: `services/agent_runtime/tests/test_recursive_delegation.py` or add a focused test

**Interfaces:**
- Produces a default `mcp-file-writer` registration with `tools/list`, `tools/call`, and `allowed_tools=["write_file"]`.
- Produces a worker default tool allowlist containing `write_file`; root remains without default tools.
- Produces a model tool contract for `write_file` with `path` and `content` fields.

- [ ] Add failing tests for the default registration, migration of an existing config, gateway target allowlist, and worker planner contract.
- [ ] Run the focused tests and verify the new assertions fail.
- [ ] Add the configuration, migration, gateway registry/policy target, worker environment default, and planner contract.
- [ ] Ensure existing configurations gain the server and worker permission only when the old built-in defaults are being migrated.
- [ ] Run the focused tests and the full Python test suite.

### Task 4: Update scenarios, documentation, and verify the running stack

**Files:**
- Modify: `scenarios/recursive-a2a-mcp.yaml`
- Modify: `README.md`
- Modify: `README_zh.md`

**Interfaces:**
- Produces documentation and seeded scenario data that identify `mcp-file-writer` and the `write_file` contract.

- [ ] Add failing scenario/documentation assertions if existing tests cover these files; otherwise update them directly and validate with Compose/config tests.
- [ ] Add an example prompt that delegates a write to `worker-agent` and clearly states the local-only boundary.
- [ ] Rebuild the fixture, control-plane, gateway, and agent images as needed and restart the stack.
- [ ] Run the full test suite, `git diff --check`, health checks, and a live write/read smoke test inside the Compose network.
- [ ] Commit the scoped changes with `feat: add isolated file writer MCP` and push to `origin master` after verification.
