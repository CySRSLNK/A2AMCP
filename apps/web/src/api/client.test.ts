import { afterEach, describe, expect, it, vi } from "vitest";

afterEach(() => {
  vi.unstubAllGlobals();
  vi.unstubAllEnvs();
  vi.resetModules();
});

describe("API routing from a remote browser", () => {
  it.each([
    [undefined, "http://lab.example.test:5173/api/v1/scenarios"],
    ["https://api.example.test/", "https://api.example.test/api/v1/scenarios"],
  ])("routes HTTP requests with API override %s", async (override, expected) => {
    vi.stubEnv("VITE_CONTROL_PLANE_URL", override);
    let requestedUrl = "";
    vi.stubGlobal("fetch", async (input: RequestInfo | URL) => {
      requestedUrl = new URL(String(input), "http://lab.example.test:5173/").href;
      return new Response("[]", { headers: { "content-type": "application/json" } });
    });

    const { listScenarios } = await import("./client");
    expect(await listScenarios()).toEqual([]);
    expect(requestedUrl).toBe(expected);
  });

  it.each([
    [undefined, "http://lab.example.test:5173/api/v1/runs/run-7/events/stream?after=4"],
    ["https://api.example.test/", "https://api.example.test/api/v1/runs/run-7/events/stream?after=4"],
  ])("routes event streams with API override %s", async (override, expected) => {
    vi.stubEnv("VITE_CONTROL_PLANE_URL", override);
    let requestedUrl = "";
    vi.stubGlobal("EventSource", class {
      constructor(url: string) {
        requestedUrl = new URL(url, "http://lab.example.test:5173/").href;
      }
      addEventListener() {}
      close() {}
    });

    const { subscribeRunEvents } = await import("./events");
    const unsubscribe = subscribeRunEvents("run-7", 4, () => {});
    try {
      expect(requestedUrl).toBe(expected);
    } finally {
      unsubscribe();
    }
  });
});
