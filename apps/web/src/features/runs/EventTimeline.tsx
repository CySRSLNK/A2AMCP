import type { ProtocolEvent } from "../../api/client";

interface Props { events: ProtocolEvent[]; selected?: string; onSelect: (event: ProtocolEvent) => void; }

export function EventTimeline({ events, selected, onSelect }: Props) {
  return (
    <section className="panel timeline-panel">
      <div className="panel-heading"><span>Event timeline</span><span className="count">{events.length}</span></div>
      <div className="timeline" aria-live="polite">
        {!events.length && <div className="empty-state">Start a run to observe correlated protocol events.</div>}
        {events.map((event) => (
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
