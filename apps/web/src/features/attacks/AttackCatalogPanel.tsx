import type { AttackEventExpectation, AttackPlan, AttackSummary } from "../../api/client";

export function formatAttackEvent(event: AttackEventExpectation): string {
  const actor = event.actor ?? "unknown actor";
  const target = event.target ? ` -> ${event.target}` : "";
  return `${event.protocol.toUpperCase()} · ${event.operation} · ${actor}${target}`;
}

export function getAttackAvailability(attack: Pick<AttackSummary, "runnable" | "fixture_scenario_id">): string {
  return attack.runnable && attack.fixture_scenario_id ? "local fixture" : "descriptive-only";
}

type Props = {
  attacks: AttackSummary[];
  selectedId: string;
  plan?: AttackPlan;
  loading?: boolean;
  onSelect: (attackId: string) => void;
};

export function AttackCatalogPanel({ attacks, selectedId, plan, loading, onSelect }: Props) {
  return (
    <section className="panel attack-panel">
      <div className="panel-heading">
        <span>Attack catalog</span>
        <span className="muted">read-only plan</span>
      </div>
      <div className="attack-picker">
        <label htmlFor="attack-case">Case</label>
        <select
          id="attack-case"
          value={selectedId}
          onChange={(event) => onSelect(event.target.value)}
          disabled={loading || attacks.length === 0}
        >
          <option value="">Select an attack case</option>
          {attacks.map((attack) => (
            <option key={`${attack.id}@${attack.version}`} value={attack.id}>
              {attack.id} · {attack.title}
            </option>
          ))}
        </select>
      </div>
      {plan ? (
        <div className="attack-detail">
          <div className="attack-detail-header">
            <div>
              <strong>{plan.title}</strong>
              <p>{plan.summary}</p>
            </div>
            <span className={`attack-badge ${plan.runnable ? "runnable" : "descriptive"}`}>
              {getAttackAvailability(plan)}
            </span>
          </div>
          <div className="attack-meta">
            <span>{plan.protocol_path}</span>
            <span>{plan.category}</span>
            <span>{plan.safe_fixture}</span>
          </div>
          <dl className="attack-facts">
            <div><dt>Injection point</dt><dd>{plan.injection_point.component}</dd></div>
            <div><dt>Trust boundary</dt><dd>{plan.injection_point.trust_boundary}</dd></div>
            <div><dt>Impact</dt><dd>{plan.impact}</dd></div>
          </dl>
          <div className="attack-section">
            <span className="attack-section-title">Expected events</span>
            <ol className="attack-events">
              {plan.expected_events.map((event, index) => (
                <li key={`${event.protocol}-${event.operation}-${index}`}>
                  <span>{formatAttackEvent(event)}</span>
                  {event.relation === "optional" ? <small>optional</small> : null}
                </li>
              ))}
            </ol>
          </div>
          <div className="attack-section">
            <span className="attack-section-title">Oracle</span>
            <p className="attack-oracle">{plan.oracle.observable.join(" ")}</p>
          </div>
          <div className="attack-section">
            <span className="attack-section-title">Sources</span>
            <p className="attack-sources">{plan.sources.map((source) => source.id).join(" · ")}</p>
          </div>
        </div>
      ) : (
        <p className="empty-state attack-empty">{loading ? "Loading attack catalog..." : "Select a case to inspect its local plan."}</p>
      )}
    </section>
  );
}
