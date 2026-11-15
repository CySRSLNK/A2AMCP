import { describe, expect, it } from "vitest";
import type { AttackSummary } from "../../api/client";
import { filterAttacksByProtocol, formatAttackEvent, getAttackAvailability } from "./AttackCatalogPanel";

describe("attack catalog presentation", () => {
  it("formats a typed event expectation with actor and target", () => {
    expect(formatAttackEvent({
      protocol: "mcp",
      operation: "tools/call:calculator",
      direction: "outbound",
      actor: "worker-agent",
      target: "mcp-tools",
      relation: "required",
      min_count: 1,
    })).toBe("MCP · tools/call:calculator · outbound · worker-agent -> mcp-tools");
  });

  it("marks descriptive-only cases as unavailable for the fixed topology", () => {
    expect(getAttackAvailability({ runnable: false, fixture_scenario_id: null })).toBe("descriptive-only");
    expect(getAttackAvailability({ runnable: true, fixture_scenario_id: "recursive-a2a-mcp" })).toBe("local fixture");
  });

  it("filters cases by protocol path without changing the source list", () => {
    const attacks: AttackSummary[] = [
      { id: "MCP-X-001", protocol_path: "cross-mcp", runnable: false, fixture_scenario_id: null, version: 1, category: "x", title: "x", summary: "x", safe_fixture: "local-only" as const },
      { id: "A2A-MCP-005", protocol_path: "a2a-mcp", runnable: true, fixture_scenario_id: "recursive-a2a-mcp", version: 1, category: "x", title: "x", summary: "x", safe_fixture: "local-only" as const },
    ];

    expect(filterAttacksByProtocol(attacks, "a2a-mcp").map((item) => item.id)).toEqual(["A2A-MCP-005"]);
    expect(filterAttacksByProtocol(attacks, "all")).toHaveLength(2);
  });
});

