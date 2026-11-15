# Runtime Control Plane Design

## Intent

为 A2A 到 MCP 安全实验室增加一个控制后台，使操作者可以在不编辑 `.env` 或重启 Compose 的情况下，配置后续实验使用的模型和 MCP 拓扑。

## Goals

- 在 Control Plane 中持久化一份当前运行配置。
- 通过 API 和 Web 控制台修改模型供应商、模型名称、API Key、超时和 Agent/MCP 权限。
- API Key 只返回掩码；浏览器只能提交一次性替换/清除动作，不在事件、任务、页面或本地存储中回显明文。
- 支持新增、编辑、启用、禁用和删除 MCP Server，并配置其能力声明。
- 新运行在创建时冻结配置快照；运行期间不受后台修改影响。
- Gateway 根据内部鉴权的 `run_id` 读取完整快照；Agent 只接收不含密钥的运行时投影，保留当前 A2A/MCP allowlist 校验。

## Non-goals

- 本阶段不实现多用户认证、RBAC 或远程公网部署。
- 本阶段不让后台配置绕过已有 Agent、Server、Tool 和 hop 限制。
- 本阶段不迁移现有 Compose fixture 的服务发现方式；默认 MCP Server 仍由 Compose 提供。

## Constraints

- 继续使用 FastAPI、SQLAlchemy、PostgreSQL、React 和现有 Docker Compose 拓扑。
- 配置修改必须可审计，但独立的配置审计表只能记录版本、动作、变更字段和 Key 是否设置，不能记录明文；审计不能依赖带 `run_id` 的运行事件表。
- 运行策略和配置都在创建运行时冻结。
- MCP 和模型 URL 只允许 `http/https`，拒绝用户信息、重定向、localhost、云元数据地址和敏感私网地址；自定义地址是代理注册，不创建或删除 Compose 容器。
- 密钥在数据库中使用 `CONFIG_ENCRYPTION_KEY` 加密；没有加密密钥时不能写入新 API Key。
- 配置更新使用版本号/CAS，避免并发完整替换互相覆盖。

## Approaches

1. **编辑 `.env` 并重启容器**：改动少，但不满足即时控制，也容易影响正在运行的实验。
2. **独立配置服务**：边界清晰，但增加部署、认证和同步复杂度。
3. **Control Plane 作为配置中心**：复用现有数据库、API 和 Web 工作台；Gateway/Agent 按运行快照执行。选择此方案，因为它最符合当前实验平台的结构，并且能保持实验可复现。

## Design

Control Plane 新增 `runtime_config`、`run_config_snapshot` 和 `config_audit` 持久化记录，并提供实际数据库迁移。活动配置是单例文档，包含模型供应商/名称/base URL/超时、root/worker 的 Agent 权限、MCP 代理注册和请求超时。MCP 记录明确表示代理注册，不代表 Compose 服务生命周期；每个注册拥有稳定 ID 和 revision，删除或禁用只影响新运行。

`GET /api/v1/config` 返回脱敏后的模型配置、Agent 权限和 MCP 列表；`PUT /api/v1/config` 接收 `expected_version` 以及 `api_key_action=preserve|replace|clear`，返回新版本号。已有密钥只返回 `api_key_set` 和固定掩码，掩码不能作为替换值。`POST /api/v1/config/test-model` 复用同一 URL 校验和出站限制，并限制请求/响应大小和超时，避免把 Control Plane 变成 SSRF 代理。

创建运行时，Control Plane 在同一数据库事务中插入 `RunRecord` 和不可变的 `RunConfigSnapshotRecord`，并保存配置版本、完整密文快照和受限后的策略。重放运行复制源快照或使用记录响应，不重新读取活动配置。执行器向初始任务只传 `runtime_config` 非密钥投影。Gateway 通过仅对内部网络开放且要求 `CONTROL_PLANE_INTERNAL_TOKEN` 的 resolver 按 `run_id` 读取完整快照；API Key 只在 Gateway 内存中解密并用于上游模型请求，绝不进入 A2A body、Agent 进程、MCP 请求或事件。

运行策略采用一个统一快照结构：`agent.allowed_targets`、`agent.allowed_mcp_servers`、`agent.allowed_tools` 与服务器/工具能力的交集决定最终权限。Scenario 或创建运行时传入的 policy 只能进一步收紧活动配置，不能扩大权限。Gateway 还会拒绝快照外、已禁用或未知的 server/tool。

Web 控制台新增 `Control` 页面，分为 Model、Agent Policy 和 MCP Servers 三个区域。模型 API Key 输入框默认空白，已有 Key 显示为掩码并支持“保持不变”；MCP Server 表单包含 ID、URL、启用状态、能力集合和允许工具集合。保存后显示配置版本和生效范围。

## Open Decisions Settled by Implementation

- 配置采用版本号和更新时间，不做历史版本回滚 UI；事件记录保留变更摘要。
- MCP Server 删除只影响新运行，旧运行快照仍可复现。
- 当前 Compose 环境的 `mcp-tools` 和 `mcp-resources` 作为默认种子配置。
- 模型和 MCP endpoint 校验使用统一的 scheme/host/端口限制，HTTP 客户端不跟随重定向；DNS 解析结果在出站前拒绝敏感私网和元数据网段。
- `GET /api/v1/runs/{run_id}/runtime-config` 是内部 resolver，不属于公开控制台 API；调用必须携带内部 token，响应只允许 Gateway 使用。
