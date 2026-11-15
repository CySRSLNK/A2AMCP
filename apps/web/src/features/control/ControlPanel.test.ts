import { describe, expect, it } from "vitest";
import { buildRuntimeConfigPayload, parseCsv } from "./ControlPanel";

describe("runtime control helpers", () => {
  it("normalizes comma separated policy fields", () => {
    expect(parseCsv(" calculator, fixture_http_get,calculator ")).toEqual([
      "calculator",
      "fixture_http_get",
    ]);
  });

  it("omits the masked key and keeps replacement intent explicit", () => {
    const payload = buildRuntimeConfigPayload(
      {
        version: 4,
        model: {
          provider: "mock",
          model_name: "lab",
          base_url: "",
          request_timeout: 120,
          api_key_set: true,
          api_key_masked: "********",
        },
        agents: {},
        mcp_servers: [],
        a2a_request_timeout: 300,
        mcp_request_timeout: 60,
        run_request_timeout: 600,
      },
      "replace",
      "new-secret",
    );
    expect(payload.api_key).toBe("new-secret");
    expect(JSON.stringify(payload)).not.toContain("********");
  });
});
