import { useState } from "react";
import { replayRun } from "../../api/client";

export function ReplayControls({ runId }: { runId?: string }) {
  const [message, setMessage] = useState("");
  const [busy, setBusy] = useState(false);
  const replay = async () => {
    if (!runId) return;
    setBusy(true); setMessage("");
    try { const result = await replayRun(runId); setMessage(`Replay ${result.replay_run_id.slice(0, 8)} created from ${result.event_count} events.`); }
    catch (error) { setMessage(error instanceof Error ? error.message : "Replay failed"); }
    finally { setBusy(false); }
  };
  return <div className="replay-controls"><button type="button" onClick={replay} disabled={!runId || busy}>{busy ? "Preparing..." : "Replay retained responses"}</button>{message && <span className="muted">{message}</span>}</div>;
}
