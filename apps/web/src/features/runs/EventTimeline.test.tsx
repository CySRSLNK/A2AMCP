import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it } from "vitest";
import type { ProtocolEvent } from "../../api/client";
import { EventTimeline, filterTimelineEvents } from "./EventTimeline";

function event(sequence: number, protocol: ProtocolEvent["protocol"], operation: string, agent_id: string): ProtocolEvent {
  return {
    event_id: `event-${sequence}`,
    sequence,
    protocol,
    operation,
    direction: operation.endsWith("response") ? "inbound" : "outbound",
    payload: {},
    context: { run_id: "run-1", agent_id, hop: 0, request_id: `request-${sequence}` },
    occurred_at: "2026-11-15T00:00:00Z",
  };
}

describe("event timeline filtering", () => {
  it("hides intermediate A2A relay responses while retaining final and MCP results", () => {
    const events = [
      event(1, "a2a", "message/send.request", "control-plane"),
      event(2, "a2a", "message/send.response", "root-agent"),
      event(3, "mcp", "tools/call:calculator", "worker-agent"),
      event(4, "a2a", "message/send.response", "control-plane"),
    ];

    expect(filterTimelineEvents(events).map((item) => item.sequence)).toEqual([1, 3, 4]);
  });

  it("can render all events for protocol debugging", () => {
    const events = [event(1, "a2a", "message/send.response", "root-agent")];
    const markup = renderToStaticMarkup(
      <EventTimeline events={events} showAll onSelect={() => undefined} />,
    );

    expect(markup).toContain("001");
    expect(markup).toContain("All events");
  });
});
