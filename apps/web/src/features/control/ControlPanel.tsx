import { useEffect, useState } from "react";
import {
  addMcpServer,
  deleteMcpServer,
  getRuntimeConfig,
  testRuntimeModel,
  updateMcpServer,
  updateRuntimeConfig,
  type McpServerRuntimeConfig,
  type RuntimeConfig,
} from "../../api/client";

export function parseCsv(value: string): string[] {
  return [...new Set(value.split(",").map((item) => item.trim()).filter(Boolean))];
}

export function formatModelTestResult(result: { ok: boolean; status_code?: number; error?: string }) {
  if (result.ok) return "Model connection succeeded.";
  const status = result.status_code ? ` (${result.status_code})` : "";
  const detail = result.error ? `: ${result.error}` : "";
  return `Model connection failed${status}${detail}${detail.endsWith(".") ? "" : "."}`;
}

export function formatRuntimeConfigSaved(version: number) {
  return `Runtime config v${version} saved.`;
}

export function buildRuntimeConfigPayload(
  config: RuntimeConfig,
  apiKeyAction: "preserve" | "replace" | "clear",
  apiKey: string,
) {
  const { api_key_set: _apiKeySet, api_key_masked: _masked, ...model } = config.model;
  const payload: Record<string, unknown> = {
    version: config.version,
    expected_version: config.version,
    model,
    agents: config.agents,
    mcp_servers: config.mcp_servers,
    a2a_request_timeout: config.a2a_request_timeout,
    mcp_request_timeout: config.mcp_request_timeout,
    run_request_timeout: config.run_request_timeout,
    api_key_action: apiKeyAction,
  };
  if (apiKeyAction === "replace" && apiKey) payload.api_key = apiKey;
  return payload;
}

function comma(items: string[]) {
  return items.join(", ");
}

function emptyServer(): McpServerRuntimeConfig {
  return {
    id: "new-server",
    endpoint: "https://",
    enabled: true,
    capabilities: ["tools/list", "tools/call"],
    allowed_tools: [],
    revision: 1,
  };
}

type FeedbackTone = "info" | "success" | "error";
type Feedback = { tone: FeedbackTone; message: string };

export function ControlPanel({ onMessage }: { onMessage: (message: string) => void }) {
  const [config, setConfig] = useState<RuntimeConfig>();
  const [apiKeyAction, setApiKeyAction] = useState<"preserve" | "replace" | "clear">("preserve");
  const [apiKey, setApiKey] = useState("");
  const [saving, setSaving] = useState(false);
  const [testingModel, setTestingModel] = useState(false);
  const [feedback, setFeedback] = useState<Feedback>();
  const [servers, setServers] = useState<McpServerRuntimeConfig[]>([]);

  useEffect(() => {
    getRuntimeConfig().then((loaded) => {
      setConfig(loaded);
      setServers(loaded.mcp_servers);
    }).catch((error) => onMessage(error instanceof Error ? error.message : "配置加载失败"));
  }, [onMessage]);

  if (!config) return <section className="panel control-panel"><div className="empty-state">Loading runtime configuration...</div></section>;

  const updateModel = (field: string, value: string | number) => {
    setConfig({ ...config, model: { ...config.model, [field]: value } });
  };

  const save = async () => {
    setSaving(true);
    setFeedback({ tone: "info", message: "Saving runtime config..." });
    try {
      const saved = await updateRuntimeConfig(buildRuntimeConfigPayload({ ...config, mcp_servers: servers }, apiKeyAction, apiKey));
      setConfig(saved); setServers(saved.mcp_servers); setApiKey(""); setApiKeyAction("preserve");
      const message = formatRuntimeConfigSaved(saved.version);
      setFeedback({ tone: "success", message });
      onMessage(message);
    } catch (error) {
      const message = error instanceof Error ? error.message : "配置保存失败";
      setFeedback({ tone: "error", message });
      onMessage(message);
    }
    finally { setSaving(false); }
  };

  const testModel = async () => {
    setTestingModel(true);
    setFeedback({ tone: "info", message: "Testing model connection..." });
    try {
      const result = await testRuntimeModel({ model: { provider: config.model.provider, model_name: config.model.model_name, base_url: config.model.base_url, request_timeout: config.model.request_timeout }, ...(apiKey ? { api_key: apiKey } : {}) });
      const message = formatModelTestResult(result);
      setFeedback({ tone: result.ok ? "success" : "error", message });
      onMessage(message);
    } catch (error) {
      const message = error instanceof Error ? error.message : "模型测试失败";
      setFeedback({ tone: "error", message });
      onMessage(message);
    }
    finally { setTestingModel(false); }
  };

  const editAgent = (agentId: string, field: string, value: string | number) => {
    const agent = config.agents[agentId];
    setConfig({ ...config, agents: { ...config.agents, [agentId]: { ...agent, [field]: typeof value === "string" ? parseCsv(value) : value } } });
  };

  const setServer = (index: number, update: Partial<McpServerRuntimeConfig>) => {
    setServers(servers.map((item, itemIndex) => itemIndex === index ? { ...item, ...update } : item));
  };

  const saveServer = async (server: McpServerRuntimeConfig) => {
    try {
      const input = { ...server, expected_version: config.version };
      const saved = config.mcp_servers.some((item) => item.id === server.id) ? await updateMcpServer(server.id, input) : await addMcpServer(input);
      setConfig(saved); setServers(saved.mcp_servers);
      const message = `MCP ${server.id} saved.`;
      setFeedback({ tone: "success", message });
      onMessage(message);
    } catch (error) {
      const message = error instanceof Error ? error.message : "MCP 保存失败";
      setFeedback({ tone: "error", message });
      onMessage(message);
    }
  };

  const removeServer = async (server: McpServerRuntimeConfig) => {
    try {
      const saved = await deleteMcpServer(server.id, config.version);
      setConfig(saved); setServers(saved.mcp_servers);
      const message = `MCP ${server.id} removed.`;
      setFeedback({ tone: "success", message });
      onMessage(message);
    } catch (error) {
      const message = error instanceof Error ? error.message : "MCP 删除失败";
      setFeedback({ tone: "error", message });
      onMessage(message);
    }
  };

  return (
    <section className="panel control-panel">
      <div className="panel-heading"><span>Runtime control</span><span className="muted">version {config.version}</span></div>
      {feedback && <p className={`control-feedback ${feedback.tone}`} role={feedback.tone === "error" ? "alert" : "status"}>{feedback.message}</p>}
      <div className="control-section">
        <div className="control-section-heading"><strong>Model provider</strong><button className="quiet-button" type="button" onClick={() => void testModel()} disabled={testingModel}>{testingModel ? "Testing..." : "Test connection"}</button></div>
        <div className="control-grid">
          <label>Provider<select value={config.model.provider} onChange={(event) => updateModel("provider", event.target.value)}><option value="mock">mock</option><option value="openai-compatible">openai-compatible</option></select></label>
          <label>Model name<input value={config.model.model_name} onChange={(event) => updateModel("model_name", event.target.value)} /></label>
          <label>Base URL<input value={config.model.base_url} onChange={(event) => updateModel("base_url", event.target.value)} placeholder="https://api.example.com" /></label>
          <label>Timeout<input type="number" min={5} max={600} value={config.model.request_timeout} onChange={(event) => updateModel("request_timeout", Number(event.target.value))} /></label>
          <label>API key action<select value={apiKeyAction} onChange={(event) => setApiKeyAction(event.target.value as typeof apiKeyAction)}><option value="preserve">Keep current ({config.model.api_key_set ? config.model.api_key_masked : "not set"})</option><option value="replace">Replace</option><option value="clear">Clear</option></select></label>
          {apiKeyAction === "replace" && <label>New API key<input type="password" autoComplete="new-password" value={apiKey} onChange={(event) => setApiKey(event.target.value)} /></label>}
        </div>
      </div>
      <div className="control-section">
        <div className="control-section-heading"><strong>Agent policy</strong></div>
        <div className="control-grid">
          {Object.entries(config.agents).map(([agentId, agent]) => <div className="control-subpanel" key={agentId}>
            <strong>{agentId}</strong>
            <label>Max hop<input type="number" min={0} max={64} value={agent.max_hop} onChange={(event) => editAgent(agentId, "max_hop", Number(event.target.value))} /></label>
            <label>Targets<input value={comma(agent.allowed_targets)} onChange={(event) => editAgent(agentId, "allowed_targets", event.target.value)} /></label>
            <label>MCP servers<input value={comma(agent.allowed_mcp_servers)} onChange={(event) => editAgent(agentId, "allowed_mcp_servers", event.target.value)} /></label>
            <label>Tools<input value={comma(agent.allowed_tools)} onChange={(event) => editAgent(agentId, "allowed_tools", event.target.value)} /></label>
          </div>)}
        </div>
      </div>
      <div className="control-section">
        <div className="control-section-heading"><strong>MCP proxy registrations</strong><button className="quiet-button" type="button" onClick={() => setServers([...servers, emptyServer()])}>Add server</button></div>
        <div className="server-list">{servers.map((server, index) => <div className="control-subpanel" key={`${server.id}-${index}`}>
          <div className="server-row"><input aria-label="server id" value={server.id} onChange={(event) => setServer(index, { id: event.target.value })} /><label className="checkbox-label"><input type="checkbox" checked={server.enabled} onChange={(event) => setServer(index, { enabled: event.target.checked })} /> enabled</label></div>
          <label>Endpoint<input value={server.endpoint} onChange={(event) => setServer(index, { endpoint: event.target.value })} /></label>
          <label>Capabilities<input value={comma(server.capabilities)} onChange={(event) => setServer(index, { capabilities: parseCsv(event.target.value) })} /></label>
          <label>Allowed tools<input value={comma(server.allowed_tools)} onChange={(event) => setServer(index, { allowed_tools: parseCsv(event.target.value) })} /></label>
          <div className="server-actions"><button className="quiet-button" type="button" onClick={() => void saveServer(server)}>Save MCP</button>{config.mcp_servers.some((item) => item.id === server.id) && <button className="danger-button" type="button" onClick={() => void removeServer(server)}>Delete</button>}</div>
        </div>)}</div>
      </div>
      <div className="control-actions"><button className="primary-button" type="button" onClick={() => void save()} disabled={saving}>{saving ? "Saving..." : "Save runtime config"}</button></div>
    </section>
  );
}
