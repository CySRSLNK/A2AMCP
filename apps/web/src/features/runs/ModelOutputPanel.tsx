import type { ProtocolEvent } from "../../api/client";

interface Props {
  events: ProtocolEvent[];
}

function asRecord(value: unknown): Record<string, unknown> {
  return value && typeof value === "object" && !Array.isArray(value)
    ? value as Record<string, unknown>
    : {};
}

function displayJson(value: unknown) {
  try {
    return JSON.stringify(value ?? {}, null, 2);
  } catch {
    return "Unable to render model output.";
  }
}

function outputText(value: unknown): string | null {
  if (typeof value === "string" || typeof value === "number" || typeof value === "boolean") {
    return String(value);
  }
  if (Array.isArray(value)) {
    const parts = value.map(outputText).filter((item): item is string => Boolean(item));
    return parts.length ? parts.join("\n") : null;
  }
  if (!value || typeof value !== "object") return null;
  const record = asRecord(value);
  if (typeof record.text === "string") return record.text;
  if (record.content !== undefined) return outputText(record.content);
  if (record.output !== undefined) return outputText(record.output);
  if (typeof record.summary === "string") return record.summary;
  if (Object.keys(record).length === 0) return null;
  return displayJson(value);
}

function finalResponseEvent(events: ProtocolEvent[]) {
  const responses = events
    .filter((event) => event.protocol === "a2a" && event.operation === "message/send.response" && event.direction === "inbound")
    .sort((a, b) => b.sequence - a.sequence);
  return responses.find((event) => event.context.agent_id === "control-plane") ?? responses[0];
}

export function extractFinalOutput(events: ProtocolEvent[]): string | null {
  const finalEvent = finalResponseEvent(events);
  if (!finalEvent) return null;
  const result = asRecord(asRecord(finalEvent.payload).result);
  const output = outputText(result.output);
  if (output) return output;
  if (typeof result.summary === "string" && result.summary) return result.summary;
  const error = outputText(asRecord(finalEvent.payload).error);
  return error;
}

export function ModelOutputPanel({ events }: Props) {
  const finalEvent = finalResponseEvent(events);
  const output = extractFinalOutput(events);

  return (
    <section className="panel model-output-panel">
      <div className="panel-heading">
        <span>Model output</span>
        <span className="count">{output ? 1 : 0}</span>
      </div>
      {!output && <div className="empty-state">Waiting for the final task output.</div>}
      <div className="model-output-list">
        {output && finalEvent && <article className="model-output-item">
          <div className="model-output-header">
            <span className="model-output-sequence">#{String(finalEvent.sequence).padStart(3, "0")}</span>
            <span className="model-output-kind">final</span>
          </div>
          <div className="model-output-meta">
            <span>{finalEvent.context.agent_id ?? "control-plane"}</span>
            <span>hop {finalEvent.context.hop}</span>
            <span>message/send.response</span>
          </div>
          <pre className="model-output-payload">{output}</pre>
        </article>}
      </div>
    </section>
  );
}
