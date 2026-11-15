import type { AttackEventExpectation, AttackPlan, AttackSummary } from "../../api/client";

export function formatAttackEvent(event: AttackEventExpectation): string {
  const actor = event.actor ?? "unknown actor";
  const target = event.target ? ` -> ${event.target}` : "";
  const count = event.min_count > 1 ? ` ×${event.min_count}` : "";
  return `${event.protocol.toUpperCase()} · ${event.operation} · ${event.direction} · ${actor}${target}${count}`;
}

export function getAttackAvailability(attack: Pick<AttackSummary, "runnable" | "fixture_scenario_id">): string {
  return attack.runnable && attack.fixture_scenario_id ? "local fixture" : "descriptive-only";
}

export type AttackProtocolFilter = "all" | AttackSummary["protocol_path"];

export function filterAttacksByProtocol(attacks: AttackSummary[], filter: AttackProtocolFilter): AttackSummary[] {
  return filter === "all" ? attacks : attacks.filter((attack) => attack.protocol_path === filter);
}

type Props = {
  attacks: AttackSummary[];
  selectedId: string;
  plan?: AttackPlan;
  loading?: boolean;
  onSelect: (attackId: string) => void;
  protocolFilter: AttackProtocolFilter;
  onProtocolFilterChange: (filter: AttackProtocolFilter) => void;
};

export function AttackCatalogPanel({ attacks, selectedId, plan, loading, onSelect, protocolFilter, onProtocolFilterChange }: Props) {
  const filteredAttacks = filterAttacksByProtocol(attacks, protocolFilter);
  const visiblePlan = filteredAttacks.some((attack) => attack.id === selectedId) ? plan : undefined;

  return (
    <section className="panel attack-panel">
      <div className="panel-heading">
        <span>Attack catalog</span>
        <span className="muted">read-only plan</span>
      </div>
      <div className="attack-picker">
        <label htmlFor="attack-protocol">Path</label>
        <select
          id="attack-protocol"
          value={protocolFilter}
          onChange={(event) => onProtocolFilterChange(event.target.value as AttackProtocolFilter)}
          disabled={loading}
        >
          <option value="all">All protocol paths</option>
          <option value="cross-mcp">Cross-MCP</option>
          <option value="a2a-mcp">A2A to MCP</option>
        </select>
        <label htmlFor="attack-case">Case</label>
        <select
          id="attack-case"
          value={filteredAttacks.some((attack) => attack.id === selectedId) ? selectedId : ""}
          onChange={(event) => onSelect(event.target.value)}
          disabled={loading || filteredAttacks.length === 0}
        >
          <option value="">Select an attack case</option>
          {filteredAttacks.map((attack) => (
            <option key={`${attack.id}@${attack.version}`} value={attack.id}>
              {attack.id} · {attack.title}
            </option>
          ))}
        </select>
      </div>
      {visiblePlan ? (
        <div className="attack-detail">
          <div className="attack-detail-header">
            <div>
              <strong>{visiblePlan.title}</strong>
              <p>{visiblePlan.summary}</p>
            </div>
            <span className={`attack-badge ${visiblePlan.runnable ? "runnable" : "descriptive"}`}>
              {getAttackAvailability(visiblePlan)}
            </span>
          </div>
          <div className="attack-meta">
            <span>{visiblePlan.protocol_path}</span>
            <span>{visiblePlan.category}</span>
            <span>{visiblePlan.safe_fixture}</span>
          </div>
          <dl className="attack-facts">
            <div><dt>Injection point</dt><dd>{visiblePlan.injection_point.component}</dd></div>
            <div><dt>Trust boundary</dt><dd>{visiblePlan.injection_point.trust_boundary}</dd></div>
            <div><dt>Impact</dt><dd>{visiblePlan.impact}</dd></div>
          </dl>
          <div className="attack-section">
            <span className="attack-section-title">Prerequisites</span>
            <p className="attack-prerequisites">
              Agents: {visiblePlan.preconditions.required_agents.join(" · ") || "none"}<br />
              MCP servers: {visiblePlan.preconditions.required_mcp_servers.join(" · ") || "none"}<br />
              Capabilities: {visiblePlan.preconditions.required_capabilities.join(" · ") || "none"}<br />
              Policy: {Object.keys(visiblePlan.preconditions.required_policy).length > 0 ? JSON.stringify(visiblePlan.preconditions.required_policy) : "none"}
            </p>
          </div>
          <div className="attack-section">
            <span className="attack-section-title">Expected events</span>
            <ol className="attack-events">
              {visiblePlan.expected_events.map((event, index) => (
                <li key={`${event.protocol}-${event.operation}-${index}`}>
                  <span>{formatAttackEvent(event)}</span>
                  {event.relation === "optional" ? <small>optional</small> : null}
                </li>
              ))}
            </ol>
          </div>
          <div className="attack-section">
            <span className="attack-section-title">Oracle</span>
            <p className="attack-oracle">{visiblePlan.oracle.observable.join(" ")}</p>
          </div>
          <div className="attack-section">
            <span className="attack-section-title">Sources</span>
            <p className="attack-sources">{visiblePlan.sources.map((source) => source.id).join(" · ")}</p>
          </div>
        </div>
      ) : (
        <p className="empty-state attack-empty">{loading ? "Loading attack catalog..." : "Select a case to inspect its local plan."}</p>
      )}
    </section>
  );
}
