import { describe, expect, it } from "vitest";
import { buildRuntimeConfigPayload, formatModelTestResult, formatRuntimeConfigSaved, parseCsv } from "./ControlPanel";

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

  it("includes the model error returned by the connection test", () => {
    expect(formatModelTestResult({ ok: false, status_code: 401, error: "invalid API key" }))
      .toBe("Model connection failed (401): invalid API key.");
  });

  it("reports the version saved by the runtime config update", () => {
    expect(formatRuntimeConfigSaved(7)).toBe("Runtime config v7 saved.");
  });
});
