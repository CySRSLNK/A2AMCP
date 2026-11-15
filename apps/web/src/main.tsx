import { useEffect, useMemo, useState } from "react";
import React from "react";
import { createRoot } from "react-dom/client";
import { createRun, importScenario, listEvents, listScenarios, seededScenario, type ProtocolEvent, type Run, type Scenario } from "./api/client";
import { subscribeRunEvents } from "./api/events";
import { EventTimeline } from "./features/runs/EventTimeline";
import { InspectorPanel } from "./features/runs/InspectorPanel";
import { TopologyPanel } from "./features/runs/TopologyPanel";
import { ReplayControls } from "./features/replay/ReplayControls";
import { ScenarioForm } from "./features/scenarios/ScenarioForm";
import "./styles.css";

function App() {
  const [scenarios, setScenarios] = useState<Scenario[]>([]);
  const [selectedScenario, setSelectedScenario] = useState(seededScenario.id);
  const [prompt, setPrompt] = useState("Trace a delegated task through a worker and use the calculator MCP tool.");
  const [run, setRun] = useState<Run>();
  const [events, setEvents] = useState<ProtocolEvent[]>([]);
  const [selectedEvent, setSelectedEvent] = useState<ProtocolEvent>();
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState("Ready for a mediated run.");

  useEffect(() => {
    listScenarios().then(setScenarios).catch(() => setMessage("Control plane is offline. Seed a scenario after starting it."));
  }, []);

  useEffect(() => {
    if (!run) return;
    let active = true;
    setEvents([]); setSelectedEvent(undefined);
    listEvents(run.id).then((initial) => { if (active) setEvents(initial); }).catch(() => undefined);
    const stop = subscribeRunEvents(run.id, 0, (event) => {
      setEvents((current) => current.some((item) => item.event_id === event.event_id) ? current : [...current, event].sort((a, b) => a.sequence - b.sequence));
    }, () => setMessage("Live stream reconnecting..."));
    return () => { active = false; stop(); };
  }, [run?.id]);

  const currentScenario = useMemo(() => scenarios.find((item) => item.id === selectedScenario) ?? seededScenario, [scenarios, selectedScenario]);

  const seed = async () => {
    setBusy(true); setMessage("Loading seeded topology...");
    try {
      const loaded = await importScenario(seededScenario);
      setScenarios((current) => [...current.filter((item) => item.id !== loaded.id), loaded]);
      setSelectedScenario(loaded.id); setMessage("Seeded topology loaded.");
    } catch (error) { setMessage(error instanceof Error ? error.message : "Scenario import failed"); }
    finally { setBusy(false); }
  };

  const start = async () => {
    setBusy(true); setMessage("Creating mediated run...");
    try {
      const scenario = scenarios.some((item) => item.id === selectedScenario) ? currentScenario : await importScenario(seededScenario);
      if (!scenarios.some((item) => item.id === scenario.id)) setScenarios((current) => [...current, scenario]);
      const created = await createRun({ scenario_id: scenario.id, root_agent_id: scenario.agents[0]?.id, prompt, policy_profile: scenario.policy_profile, mode: "mediated" });
      setRun(created); setMessage("Run queued. Events will appear as the chain executes.");
    } catch (error) { setMessage(error instanceof Error ? error.message : "Run creation failed"); }
    finally { setBusy(false); }
  };

  return (
    <main className="app-shell">
      <header className="topbar">
        <div><p className="eyebrow">A2A / MCP SECURITY LAB</p><h1>Run workbench</h1></div>
        <div className={`status-chip ${run?.status ?? "idle"}`}><span className="status-dot" />{run?.status ?? "idle"}</div>
      </header>
      <section className="command-bar panel">
        <ScenarioForm scenarios={scenarios} selected={selectedScenario} onSelect={setSelectedScenario} onSeed={seed} disabled={busy} />
        <label className="prompt-field" htmlFor="prompt"><span>Operator prompt</span><textarea id="prompt" rows={2} value={prompt} onChange={(event) => setPrompt(event.target.value)} disabled={busy} /></label>
        <button className="primary-button" type="button" onClick={start} disabled={busy}>{busy ? "Working..." : "Start mediated run"}</button>
      </section>
      <p className="system-message" role="status">{message}</p>
      <div className="workspace-grid">
        <div className="main-column"><TopologyPanel run={run} /><EventTimeline events={events} selected={selectedEvent?.event_id} onSelect={setSelectedEvent} /></div>
        <aside className="side-column"><InspectorPanel event={selectedEvent} /><section className="panel controls-panel"><div className="panel-heading"><span>Run controls</span><span className="muted">{events.length} events</span></div><ReplayControls runId={run?.id} /></section></aside>
      </div>
      <footer className="footer-note">Capture mode: <strong>mediated</strong> · policy snapshot: <strong>frozen at run start</strong> · hidden reasoning is never rendered</footer>
    </main>
  );
}

createRoot(document.getElementById("root")!).render(
  <React.StrictMode>
    <App />
  </React.StrictMode>,
);
