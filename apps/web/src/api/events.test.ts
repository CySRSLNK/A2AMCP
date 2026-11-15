import { describe, expect, it } from "vitest";
import { mergeProtocolEvents, parseEventData } from "./events";

describe("event stream contract", () => {
  it("parses a protocol event without changing its sequence", () => {
    const event = parseEventData(JSON.stringify({
      event_id: "e1",
      sequence: 4,
      protocol: "mcp",
      operation: "tools/call",
      direction: "outbound",
      payload: { name: "calculator" },
      context: { run_id: "r1", hop: 2, request_id: "req-4" },
      occurred_at: "2026-11-15T00:00:00Z",
    }));

    expect(event.sequence).toBe(4);
    expect(event.protocol).toBe("mcp");
    expect(event.payload).toEqual({ name: "calculator" });
  });

  it("merges the initial snapshot without dropping events received from SSE", () => {
    const event = (event_id: string, sequence: number) => ({
      event_id,
      sequence,
      protocol: "mcp" as const,
      operation: "tools/call:read_file",
      direction: "outbound",
      payload: {},
      context: { run_id: "r1", hop: 1, request_id: event_id },
      occurred_at: "2026-11-15T00:00:00Z",
    });

    const merged = mergeProtocolEvents(
      [event("example", 10), event("calculator", 14)],
      [event("email", 8), event("example", 10)],
    );

    expect(merged.map((item) => item.sequence)).toEqual([8, 10, 14]);
    expect(merged.map((item) => item.event_id)).toEqual(["email", "example", "calculator"]);
  });
});
