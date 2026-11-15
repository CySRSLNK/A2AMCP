import { useState } from "react";
import type { ProtocolEvent } from "../../api/client";

interface Props { events: ProtocolEvent[]; selected?: string; onSelect: (event: ProtocolEvent) => void; showAll?: boolean; }

function isRelayResponse(event: ProtocolEvent) {
  return event.protocol === "a2a"
    && event.operation === "message/send.response"
    && event.direction === "inbound"
    && event.context.agent_id !== "control-plane";
}

export function filterTimelineEvents(events: ProtocolEvent[], showAll = false) {
  return showAll ? events : events.filter((event) => !isRelayResponse(event));
}

export function EventTimeline({ events, selected, onSelect, showAll: showAllProp }: Props) {
  const [showAllState, setShowAllState] = useState(false);
  const showAll = showAllProp ?? showAllState;
  const visibleEvents = filterTimelineEvents(events, showAll);
  return (
    <section className="panel timeline-panel">
      <div className="panel-heading">
        <span>Event timeline</span>
        <div className="timeline-heading-actions">
          <div className="timeline-view-toggle" role="group" aria-label="Timeline event view">
            <button type="button" className={!showAll ? "active" : ""} onClick={() => setShowAllState(false)}>Key events</button>
            <button type="button" className={showAll ? "active" : ""} onClick={() => setShowAllState(true)}>All events</button>
          </div>
          <span className="count">{visibleEvents.length}{showAll ? "" : `/${events.length}`}</span>
        </div>
      </div>
      <div className="timeline" aria-live="polite">
        {!visibleEvents.length && <div className="empty-state">Start a run to observe correlated protocol events.</div>}
        {visibleEvents.map((event) => (
          <button key={event.event_id} type="button" className={`event-row ${selected === event.event_id ? "selected" : ""}`} onClick={() => onSelect(event)}>
            <span className={`protocol protocol-${event.protocol}`}>{event.protocol.toUpperCase()}</span>
            <span className="event-sequence">{String(event.sequence).padStart(3, "0")}</span>
            <span className="event-operation">{event.operation}</span>
            <span className="event-agent">{event.context.agent_id ?? "control"}</span>
            <span className="event-hop">hop {event.context.hop}</span>
          </button>
        ))}
      </div>
    </section>
  );
}
