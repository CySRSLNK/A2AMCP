import type { ProtocolEvent } from "../../api/client";

export function InspectorPanel({ event }: { event?: ProtocolEvent }) {
  return (
    <section className="panel inspector-panel">
      <div className="panel-heading"><span>Inspector</span><span className="muted">operator view</span></div>
      {!event && <div className="empty-state">Select an event to inspect its safe payload and policy decision.</div>}
      {event && <>
        <dl className="details">
          <div><dt>Sequence</dt><dd>{event.sequence}</dd></div>
          <div><dt>Protocol</dt><dd>{event.protocol} / {event.operation}</dd></div>
          <div><dt>Agent</dt><dd>{event.context.agent_id ?? "control-plane"}</dd></div>
          <div><dt>Task</dt><dd>{event.context.task_id ?? "-"}</dd></div>
          <div><dt>Request</dt><dd>{event.context.request_id}</dd></div>
        </dl>
        <pre className="payload">{JSON.stringify({ payload: event.payload, policy: event.policy_decision, fault: event.fault_action }, null, 2)}</pre>
      </>}
    </section>
  );
}
