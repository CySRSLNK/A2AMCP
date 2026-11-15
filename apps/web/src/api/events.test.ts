import { describe, expect, it } from "vitest";
import { parseEventData } from "./events";

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
});
