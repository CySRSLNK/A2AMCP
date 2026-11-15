import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it } from "vitest";
import type { ProtocolEvent } from "../../api/client";
import { ModelOutputPanel, extractFinalOutput } from "./ModelOutputPanel";

function modelEvent(
  sequence: number,
  operation: "completion.response" | "completion.error",
  payload: Record<string, unknown>,
): ProtocolEvent {
  return {
    event_id: `event-${sequence}`,
    sequence,
    protocol: "model",
    operation,
    direction: "inbound",
    payload,
    context: {
      run_id: "run-1",
      task_id: `task-${sequence}`,
      agent_id: "worker-agent",
      hop: sequence,
      request_id: `request-${sequence}`,
    },
    occurred_at: "2026-11-15T00:00:00Z",
  };
}

describe("model output panel", () => {
  it("shows an empty state before model responses arrive", () => {
    const markup = renderToStaticMarkup(<ModelOutputPanel events={[]} />);

    expect(markup).toContain("Waiting for the final task output.");
  });

  it("extracts the final text returned through the outer A2A context", () => {
    const output = extractFinalOutput([
      modelEvent(8, "completion.response", {
        provider: "openai-compatible",
        model: "deepseek-chat",
        output: { action: "mcp_call", tool_name: "calculator" },
      }),
      {
        ...modelEvent(10, "completion.response", {
          result: {
            status: "completed",
            output: { content: [{ type: "text", text: "15" }] },
          },
        }),
        protocol: "a2a",
        operation: "message/send.response",
        context: { ...modelEvent(10, "completion.response", {}).context, agent_id: "control-plane" },
      },
    ]);

    expect(output).toBe("15");
  });

  it("renders the final output instead of intermediate model decisions", () => {
    const markup = renderToStaticMarkup(
      <ModelOutputPanel
        events={[
          modelEvent(2, "completion.response", { output: { action: "delegate" } }),
          {
            ...modelEvent(10, "completion.response", {
              result: { status: "completed", output: { content: [{ type: "text", text: "15" }] } },
            }),
            protocol: "a2a",
            operation: "message/send.response",
            context: { ...modelEvent(10, "completion.response", {}).context, agent_id: "control-plane" },
          },
        ]}
      />,
    );

    expect(markup).toContain("15");
    expect(markup).not.toContain("delegate");
  });

  it("renders a final error when the outer task fails", () => {
    const markup = renderToStaticMarkup(
      <ModelOutputPanel
        events={[
          {
            ...modelEvent(3, "completion.error", {}),
            protocol: "a2a",
            operation: "message/send.response",
            context: { ...modelEvent(3, "completion.error", {}).context, agent_id: "control-plane" },
            payload: { result: { status: "failed", summary: "model request timed out", output: {} } },
          },
        ]}
      />,
    );

    expect(markup).toContain("model request timed out");
  });

  it("marks blocked orchestration summaries instead of presenting them as model output", () => {
    const output = extractFinalOutput([
      {
        ...modelEvent(4, "completion.error", {}),
        protocol: "a2a",
        operation: "message/send.response",
        context: { ...modelEvent(4, "completion.error", {}).context, agent_id: "control-plane" },
        payload: {
          result: {
            status: "blocked",
            summary: "读取 email.txt 后继续委派给 worker-agent",
            output: {},
          },
        },
      },
    ]);

    expect(output).toBe("[blocked] 读取 email.txt 后继续委派给 worker-agent");
  });
});
