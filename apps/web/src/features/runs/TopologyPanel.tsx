import type { Run } from "../../api/client";

export function TopologyPanel({ run }: { run?: Run }) {
  return (
    <section className="panel topology-panel">
      <div className="panel-heading"><span>Topology</span><span className="muted">mediated</span></div>
      <div className="topology-row">
        <div className="node root"><strong>root-agent</strong><small>planner</small></div>
        <span className="edge">A2A</span>
        <div className="node worker"><strong>worker-agent</strong><small>recursive hop</small></div>
        <span className="edge">MCP</span>
        <div className="node tool"><strong>mcp-tools</strong><small>tools / resources</small></div>
      </div>
      <div className="topology-meta">{run ? `Run ${run.id.slice(0, 8)} · ${run.status}` : "No active run"}</div>
    </section>
  );
}
