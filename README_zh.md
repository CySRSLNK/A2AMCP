# A2A 到 MCP 安全实验室

这是一个基于 Docker Compose 的本地安全研究环境，用于观察和验证 Agent-to-Agent（A2A）委托与 Model Context Protocol（MCP）调用之间的信任边界。实验环境包含递归 Agent 委托、MCP 工具与资源、策略检查、提示词注入、事件记录、回放以及本地攻击案例目录。

默认使用确定性的 mock 模型，不需要外部模型凭据。所有服务只在本地 Compose 网络中运行，适合构建可重复的实验和测试用例。

## 使用真实模型决策

项目已经支持 OpenAI-compatible 模型。真实模型不直接访问 Agent 或 MCP，而是返回一个动作 JSON，由 Agent Runtime 校验后执行。这样模型负责分析和选择动作，A2A、MCP、allowlist 和审计仍由实验环境控制。

在 `.env` 中配置：

```dotenv
MODEL_PROVIDER=openai-compatible
MODEL_NAME=your-model
MODEL_BASE_URL=http://model-service:8000
MODEL_API_KEY=your-key
MODEL_REQUEST_TIMEOUT=120
A2A_REQUEST_TIMEOUT=300
MCP_REQUEST_TIMEOUT=60
RUN_REQUEST_TIMEOUT=600
```

`MODEL_BASE_URL` 必须是 gateway 容器可以访问的模型服务地址。Docker Desktop 通常可以使用 `host.docker.internal` 访问宿主机上的模型服务；Linux 环境需要让模型服务加入同一个 Docker 网络，或额外配置宿主机映射。

模型必须返回以下三种动作之一，并且只返回 JSON：

```json
{"action":"delegate","target_agent":"worker-agent","summary":"把任务交给 worker 检查 fixture。"}
```

```json
{"action":"mcp_call","server_id":"mcp-tools","tool_name":"calculator","arguments":{"operation":"add","a":1,"b":2},"summary":"调用计算器。"}
```

```json
{"action":"answer","summary":"任务已完成。"}
```

root agent 默认只能委派给 `worker-agent`，不能调用 MCP 工具；worker agent 可以继续委派，并允许调用 `calculator` 和 `fixture_http_get`。未知 Agent、MCP server、工具、非法 JSON 和超出 hop 限制的决策都会被拒绝。

每个 Agent 收到任务后都会重新请求模型，由当前 Agent 自己选择 `answer`、`delegate` 或 `mcp_call`。因此实际链路可以是 `root-agent -> worker-agent -> mcp-tools`，也可以是 `root-agent -> worker-agent -> worker-agent -> mcp-tools`。运行时不会预先把 worker 固定为 MCP 调用者，只会执行模型返回且通过 allowlist 校验的动作。为了兼容部分 OpenAI-compatible 服务返回的字段别名，运行时也会把 `type/server/tool/target` 归一化为 `action/server_id/tool_name/target_agent`，未知字段仍会被拒绝。

真实模型推理可能超过默认的短 HTTP 等待时间。`MODEL_REQUEST_TIMEOUT` 控制单次模型请求，`A2A_REQUEST_TIMEOUT` 控制 Agent 委托，`MCP_REQUEST_TIMEOUT` 控制 MCP 请求，`RUN_REQUEST_TIMEOUT` 控制 Control Plane 等待整条链路；递归链路较长时应同时提高 A2A 和 run 超时。

## 快速启动

需要安装 Docker，以及 Docker Compose。执行：

```bash
cp .env.example .env
docker-compose up --build -d
```

如果系统使用新版 Compose 插件，也可以执行：

```bash
docker compose up --build -d
```

启动后访问：

- Web 工作台：http://127.0.0.1:5173
- Control Plane API：http://127.0.0.1:8000
- API 文档：http://127.0.0.1:8000/docs
- 健康检查：http://127.0.0.1:8000/healthz

Workbench 中的 `Model output` 面板会显示整条委派链最终返回的内容。例如调用 calculator 得到 `15` 时，面板显示 `15`，而不是中间模型的 `delegate` 或 `mcp_call` 决策。事件时间线默认隐藏中间 Agent 转发产生的重复 A2A response；切换 `All events` 可以查看完整协议证据。模型请求只记录安全元数据；完整提示词和 API Key 不会显示在面板或事件中。

## 运行时控制后台

打开 Web 工作台右上角的 `Control` 页面，可以在不重启 Compose 的情况下修改后续运行使用的模型和 MCP 代理注册：

- Model：选择 `mock` 或 `openai-compatible`，修改模型名、Base URL、超时，并执行保留、替换或清除 API Key。
- Agent policy：分别调整 root/worker 的最大 hop、可委派 Agent、可用 MCP server 和工具。
- MCP proxy registrations：新增、编辑、启用/禁用或删除 HTTP(S) MCP 代理地址。这里管理的是网关注册，不会创建或删除 Compose 容器。

API Key 只在 Control Plane 数据库中以 Fernet 密文保存，公开 API 和页面只返回是否设置及固定掩码。首次使用动态密钥前，在 `.env` 设置一个 Fernet 密钥，例如：

```bash
python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
```

```dotenv
CONFIG_ENCRYPTION_KEY=生成的密钥
CONTROL_PLANE_INTERNAL_TOKEN=仅供 Compose 内部 Gateway 使用的随机值
```

每次 `POST /api/v1/runs` 都会在同一事务中保存配置快照。之后修改模型或删除 MCP 注册只影响新运行；旧运行仍解析自己的快照。Agent 任务只携带非敏感投影，API Key 不会进入 A2A body、Agent 容器、MCP 请求或事件记录。

控制 API：

```text
GET  /api/v1/config
PUT  /api/v1/config
POST /api/v1/config/test-model
POST /api/v1/config/mcp
PUT  /api/v1/config/mcp/{server_id}
DELETE /api/v1/config/mcp/{server_id}
```

配置更新使用 `expected_version` 做并发保护；`api_key_action` 可取 `preserve`、`replace` 或 `clear`。模型和 MCP 地址只允许 HTTP(S) origin，拒绝凭据、重定向以及 localhost、元数据和敏感私网地址。

检查容器状态：

```bash
docker-compose ps
```

停止服务：

```bash
docker-compose down
```

## 实验拓扑

```text
浏览器工作台
      |
      v
Control Plane ---- PostgreSQL
      |
      v
   Gateway
   /     \
  v       v
Root Agent -> Worker Agent
                  |
                  v
              MCP Gateway
              /          \
             v            v
        mcp-tools   mcp-resources
```

各组件职责如下：

| 组件 | 作用 | 对外端口 |
| --- | --- | --- |
| `web` | 浏览器工作台，查看拓扑、事件和攻击目录 | `5173` |
| `control-plane` | 场景、运行、事件、回放和攻击目录 API | `8000` |
| `gateway` | 统一转发 A2A、MCP 和模型请求，执行策略 | Compose 内部 |
| `root-agent` | 顶层 Agent，负责初始任务和委托 | Compose 内部 |
| `worker-agent` | 接收委托、继续分配任务并调用 MCP | Compose 内部 |
| `mcp-tools` | 本地工具型 MCP fixture，包含 calculator 等工具 | Compose 内部 |
| `mcp-resources` | 本地资源型 MCP fixture | Compose 内部 |
| `postgres` | 保存运行、事件和场景元数据 | Compose 内部 |

默认递归场景位于 `scenarios/recursive-a2a-mcp.yaml`。典型链路是：

```text
control-plane -> root-agent -> worker-agent -> worker-agent -> MCP tool
```

每个 mediated 请求都会关联 run、task、agent、hop、request 和 sequence 信息，便于还原跨 Agent 的调用链。

## 使用 Web 工作台

1. 打开 `http://127.0.0.1:5173`。
2. 点击加载默认的 `recursive-a2a-mcp` 场景。
3. 输入操作提示词，选择 `mediated` 模式并启动运行。
4. 在事件时间线中检查 A2A、MCP、策略和模型事件。
5. 在右侧查看事件详情，在运行控制区域执行回放。
6. 在 `Attack catalog` 区域按 `cross-mcp` 或 `a2a-mcp` 筛选攻击案例。

终端也可以执行同样的冒烟流程：

```bash
scripts/smoke.sh
```

脚本会导入默认场景、创建运行、等待结果并输出运行 ID、最终状态和事件数量。

## 攻击案例目录

攻击目录位于 `scenarios/attack-catalog.yaml`，当前包含：

- Cross-MCP 案例：`MCP-X-001` 至 `MCP-X-005`
- A2A 到 MCP 案例：`A2A-MCP-001` 至 `A2A-MCP-006`
- `A2A-MCP-005` 是映射到固定 Compose 拓扑的本地 fixture
- 其余案例是只读的 `descriptive-only` 研究条目

目录记录前置 Agent、MCP 服务、能力和策略、注入点、预期协议事件、影响、检测 Oracle、缓解措施以及来源标识。它用于研究和审计，不代表当前环境可以执行所有攻击。

攻击目录 API 是只读的：

```text
GET /api/v1/attacks
GET /api/v1/attacks/{attack_id}?version=1
GET /api/v1/attacks/{attack_id}/plan
```

命令行查询：

```bash
scripts/list-attacks.sh
scripts/list-attacks.sh A2A-MCP-005
```

计划接口只读取并校验目录数据，不会创建运行、调用模型、触发 Agent 或 MCP，也不会访问外部目标。

当前目录使用实验室可观测事件名称，例如：

```text
A2A: message/send.request
MCP: tools/call:calculator
```

`actor` 表示产生事件的 `CorrelationContext.agent_id`，`target` 表示网关选择的路由目标。Control Plane 会校验事件节点、协议操作、前置能力和 runnable 案例是否属于固定本地拓扑。

## 常用 API

场景和运行接口：

```text
POST /api/v1/scenarios
GET  /api/v1/scenarios
POST /api/v1/runs
GET  /api/v1/runs/{run_id}
GET  /api/v1/runs/{run_id}/events
POST /api/v1/runs/{run_id}/replay
```

查看 OpenAPI 文档：

```text
http://127.0.0.1:8000/docs
```

删除运行及其持久化数据：

```bash
scripts/destroy-run.sh RUN_ID
```

## 配置

复制 `.env.example` 到 `.env` 后可以调整以下配置：

| 变量 | 默认值 | 说明 |
| --- | --- | --- |
| `LAB_BIND_HOST` | `127.0.0.1` | Web 和 API 的绑定地址 |
| `MODEL_PROVIDER` | `mock` | 默认使用确定性 mock 模型 |
| `MODEL_NAME` | `lab-agent` | 发送给模型服务的模型名称 |
| `MODEL_BASE_URL` | 空 | 可选的模型服务地址 |
| `MODEL_API_KEY` | 空 | 可选的模型服务凭据 |
| `MODEL_REQUEST_TIMEOUT` | `120` | 单次模型请求超时时间（秒） |
| `A2A_REQUEST_TIMEOUT` | `300` | Gateway 转发 Agent 请求超时时间（秒） |
| `MCP_REQUEST_TIMEOUT` | `60` | MCP 请求超时时间（秒） |
| `RUN_REQUEST_TIMEOUT` | `600` | Control Plane 等待整条运行链路的超时时间（秒） |
| `DATABASE_URL` | Compose PostgreSQL | Control Plane 数据库连接 |
| `GATEWAY_BASE_URL` | `http://gateway:8001` | Agent 使用的网关地址 |
| `CONFIG_ENCRYPTION_KEY` | 空 | 运行时 API Key 的 Fernet 加密密钥；写入新密钥时必填 |
| `CONTROL_PLANE_INTERNAL_TOKEN` | `lab-internal-dev-token` | Control Plane resolver 与 Gateway 之间的内部令牌 |
| `MCP_TOOLS_URL` | `http://mcp-tools:8200` | 默认工具 MCP 代理地址 |
| `MCP_RESOURCES_URL` | `http://mcp-resources:8200` | 默认资源 MCP 代理地址 |

外部模型是可选配置。启用后，请确保模型服务只在你授权的范围内使用，并保留网关策略和事件记录。

## 数据与回放

- 运行、场景和事件元数据保存到 PostgreSQL。
- 大型 payload 保存到 `artifact-data` 卷，并以 SHA-256 标识。
- 持久化前会执行 payload 脱敏。
- 回放使用已经保存的响应体，不会重新访问外部目标。
- 缺少或已脱敏的响应体会被标记为不可回放。

## 安全边界

这个仓库面向本地安全研究，不是生产部署模板。默认 Compose 服务具备以下限制：

- 使用本地 fixture 和 mock 模型。
- 容器以只读文件系统运行，并限制临时目录、CPU、内存和进程数。
- 服务通过网关进行 A2A、MCP 和模型调用。
- 工具、资源、目标、hop 深度和 payload 大小受策略控制。
- 攻击目录计划接口是只读的，不执行案例。

请只在你拥有授权的本地或隔离环境中扩展攻击 fixture，不要把真实凭据、生产地址或未经授权的目标写入场景和目录。

## 开发与测试

Python 测试：

```bash
.venv/bin/pytest -q
```

前端测试和构建：

```bash
cd apps/web
npm test
npm run build
```

Compose 配置检查：

```bash
docker-compose config --quiet
```

更详细的事件模型、策略边界和回放行为见 [递归 A2A 到 MCP 实验说明](docs/experiments/recursive-a2a-mcp.md)。英文说明见 [README.md](README.md)。
