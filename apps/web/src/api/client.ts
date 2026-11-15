export type Protocol = "a2a" | "mcp" | "model" | "policy" | "artifact" | "run";

export interface Scenario {
  id: string;
  version: number;
  description?: string;
  agents: Array<{ id: string; role: string; capabilities: string[] }>;
  mcp_servers: Array<{ id: string; capabilities: string[] }>;
  policy_profile: Record<string, unknown>;
  model_provider: Record<string, unknown>;
}

export interface Run {
  id: string;
  scenario_id?: string;
  status: string;
  prompt?: string;
  root_agent_id?: string;
  mode?: string;
  policy?: Record<string, unknown>;
}

export interface ProtocolEvent {
  event_id: string;
  sequence: number;
  protocol: Protocol;
  operation: string;
  direction: string;
  payload: unknown;
  context: {
    run_id: string;
    task_id?: string;
    parent_task_id?: string;
    agent_id?: string;
    hop: number;
    request_id: string;
  };
  policy_decision?: Record<string, unknown>;
  fault_action?: Record<string, unknown>;
  occurred_at: string;
}

export interface AttackEventExpectation {
  protocol: "a2a" | "mcp";
  operation: string;
  direction: "inbound" | "outbound";
  actor?: string | null;
  target?: string | null;
  relation: "required" | "optional";
  min_count: number;
}

export interface AttackSummary {
  id: string;
  version: number;
  protocol_path: "cross-mcp" | "a2a-mcp";
  runnable: boolean;
  fixture_scenario_id?: string | null;
  category: string;
  title: string;
  summary: string;
  safe_fixture: "local-only";
}

export interface AttackCase extends AttackSummary {
  sources: Array<{ id: string; kind: string }>;
  preconditions: {
    required_agents: string[];
    required_mcp_servers: string[];
    required_capabilities: string[];
    required_policy: Record<string, unknown>;
  };
  injection_point: {
    component: string;
    trust_boundary: string;
    input_kind: string;
  };
  expected_events: AttackEventExpectation[];
  impact: string;
  oracle: {
    observable: string[];
    expected_decision: string;
  };
  dry_run_prompt: string;
  mitigations: string[];
  notes: string[];
}

export type AttackPlan = AttackCase & { plan_mode: "read-only" };

export const API_BASE = (import.meta.env.VITE_CONTROL_PLANE_URL as string | undefined) ?? "http://127.0.0.1:8000";

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(`${API_BASE}${path}`, {
    headers: { "Content-Type": "application/json", ...(init?.headers ?? {}) },
    ...init,
  });
  if (!response.ok) {
    const detail = await response.text();
    throw new Error(detail || `Request failed with ${response.status}`);
  }
  return response.json() as Promise<T>;
}

export const seededScenario: Scenario = {
  id: "recursive-a2a-mcp",
  version: 1,
  description: "Root delegation through a worker chain followed by MCP operations.",
  agents: [
    { id: "root-agent", role: "root", capabilities: ["delegate", "answer"] },
    { id: "worker-agent", role: "worker", capabilities: ["delegate", "mcp", "answer"] },
  ],
  mcp_servers: [
    { id: "mcp-tools", capabilities: ["tools/list", "tools/call"] },
    { id: "mcp-resources", capabilities: ["resources/read"] },
  ],
  policy_profile: {
    max_hop: 3,
    allowed_targets: ["root-agent", "worker-agent"],
    allowed_tools: ["calculator", "fixture_http_get"],
  },
  model_provider: { provider: "mock", model: "lab-demo" },
};

export function listScenarios() {
  return request<Scenario[]>("/api/v1/scenarios");
}

export function importScenario(scenario: Scenario) {
  return request<Scenario>("/api/v1/scenarios", { method: "POST", body: JSON.stringify(scenario) });
}

export function createRun(input: {
  scenario_id: string;
  root_agent_id?: string;
  prompt: string;
  policy_profile?: Record<string, unknown>;
  mode?: "mediated" | "direct";
}) {
  return request<Run>("/api/v1/runs", { method: "POST", body: JSON.stringify(input) });
}

export function listEvents(runId: string, after = 0) {
  return request<ProtocolEvent[]>(`/api/v1/runs/${runId}/events?after=${after}`);
}

export function decideApproval(runId: string, approvalId: string, decision: "approve" | "deny") {
  return request(`/api/v1/runs/${runId}/approvals/${approvalId}`, {
    method: "POST",
    body: JSON.stringify({ decision }),
  });
}

export function replayRun(runId: string) {
  return request<{ replay_run_id: string; event_count: number }>(`/api/v1/runs/${runId}/replay`, {
    method: "POST",
  });
}

export function listAttacks() {
  return request<AttackSummary[]>("/api/v1/attacks");
}

export function getAttack(attackId: string, version?: number) {
  const query = version ? `?version=${version}` : "";
  return request<AttackCase>(`/api/v1/attacks/${attackId}${query}`);
}

export function getAttackPlan(attackId: string, version?: number) {
  const query = version ? `?version=${version}` : "";
  return request<AttackPlan>(`/api/v1/attacks/${attackId}/plan${query}`);
}
