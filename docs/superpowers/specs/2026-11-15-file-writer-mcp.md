# File Writer MCP Design

## Intent

Add a local-only MCP fixture that lets an authorized worker agent write UTF-8 text files for A2A-to-MCP security experiments.

## Goals

- Provide a separate `mcp-file-writer` service and writable `fixtures/file-writer` volume.
- Expose `tools/list` and `tools/call` for a `write_file` tool.
- Restrict writes to relative paths below the fixture root.
- Reject path traversal, absolute paths, directories, invalid UTF-8 content, and content over the configured byte limit.
- Use an atomic replacement so interrupted writes do not leave partial files.
- Register the server in default runtime configuration and give only the worker agent the default tool permission.
- Preserve existing read-only file-reader behavior and add regression coverage.

## Non-goals

- Writing arbitrary host paths or adding a public port.
- Supporting remote authentication headers, stdio transports, or arbitrary MCP transports.
- Adding a new AgentDecision action; the tool uses the existing `mcp_call` action.

## Interface

The server accepts JSON-RPC POST requests at `/mcp`.

```json
{
  "jsonrpc": "2.0",
  "id": 1,
  "method": "tools/call",
  "params": {
    "name": "write_file",
    "arguments": {"path": "result.txt", "content": "lab output"}
  }
}
```

Successful calls return a small text result containing the relative path and byte count, not the full file content.

## Security boundaries

- The writer container mounts only `./fixtures/file-writer` at `/var/lib/a2a-mcp/files`.
- The service uses `MCP_FILE_WRITER_MAX_BYTES`, defaulting to `65536`.
- Runtime configuration requires `mcp-file-writer` to be enabled and explicitly allowed for the agent and tool.
- Existing gateway policy and event logging remain in the request path.
