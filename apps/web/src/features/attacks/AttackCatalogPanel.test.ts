import { describe, expect, it } from "vitest";
import { formatAttackEvent, getAttackAvailability } from "./AttackCatalogPanel";

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
    })).toBe("MCP · tools/call:calculator · worker-agent -> mcp-tools");
  });

  it("marks descriptive-only cases as unavailable for the fixed topology", () => {
    expect(getAttackAvailability({ runnable: false, fixture_scenario_id: null })).toBe("descriptive-only");
    expect(getAttackAvailability({ runnable: true, fixture_scenario_id: "recursive-a2a-mcp" })).toBe("local fixture");
  });
});

