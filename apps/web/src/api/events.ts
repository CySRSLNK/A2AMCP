import { API_BASE, type ProtocolEvent } from "./client";

export function parseEventData(data: string): ProtocolEvent {
  return JSON.parse(data) as ProtocolEvent;
}

export function mergeProtocolEvents(
  current: ProtocolEvent[],
  incoming: ProtocolEvent[],
): ProtocolEvent[] {
  const byId = new Map(current.map((event) => [event.event_id, event]));
  for (const event of incoming) byId.set(event.event_id, event);
  return [...byId.values()].sort((left, right) => left.sequence - right.sequence);
}

export function subscribeRunEvents(
  runId: string,
  afterSequence: number,
  onEvent: (event: ProtocolEvent) => void,
  onError?: (error: Event) => void,
): () => void {
  let cursor = afterSequence;
  let closed = false;
  let source: EventSource | undefined;
  let retryTimer: number | undefined;

  const connect = () => {
    if (closed) return;
    source = new EventSource(`${API_BASE}/api/v1/runs/${runId}/events/stream?after=${cursor}`);
    source.addEventListener("protocol", (event) => {
      const item = parseEventData((event as MessageEvent).data);
      if (item.sequence <= cursor) return;
      cursor = item.sequence;
      onEvent(item);
    });
    source.onerror = (event) => {
      onError?.(event);
      source?.close();
      if (!closed) retryTimer = window.setTimeout(connect, 500);
    };
  };
  connect();

  return () => {
    closed = true;
    if (retryTimer) window.clearTimeout(retryTimer);
    source?.close();
  };
}
