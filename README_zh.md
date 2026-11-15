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

root agent 默认只能委派给 `worker-agent`，不能调用 MCP 工具；worker agent 可以继续委派，并允许调用 `calculator`、`fixture_http_get`、`mcp-file-reader` 的 `read_file` 和 `mcp-file-writer` 的 `write_file`。未知 Agent、MCP server、工具、非法 JSON 和超出 hop 限制的决策都会被拒绝。

读取文件的模型动作示例：

```json
{"action":"mcp_call","server_id":"mcp-file-reader","tool_name":"read_file","arguments":{"path":"example.txt"},"summary":"读取本地 fixture 文件。"}
```

```json
{"action":"mcp_call","server_id":"mcp-file-writer","tool_name":"write_file","arguments":{"path":"result.txt","content":"本地实验输出"},"summary":"写入本地 fixture 文件。"}
```

`mcp-file-reader` 只读挂载 `fixtures/`，`path` 必须是该目录内的相对路径。例如 `{"path":"example.txt"}` 读取宿主机的 `fixtures/example.txt`。文件内容会作为不可信 MCP 数据返回，适合用来测试提示词注入和跨 Agent 传播；绝对路径、路径穿越、目录、非 UTF-8 文件和超出大小限制的文件会被拒绝。

`mcp-file-writer` 可写挂载同一个 `fixtures/`，提供 `write_file`。参数为相对 `path` 和字符串 `content`，只允许写入该目录，拒绝绝对路径、路径穿越、目录和超过 `MCP_FILE_WRITER_MAX_BYTES` 的内容，并使用原子替换避免产生半写入文件。返回值只包含相对路径和字节数，不返回完整文件内容。该服务不开放宿主机端口，仅用于本地写入边界实验。

读写工具共用同一目录，writer 写入 `result.txt` 后，reader 可以直接读取 `result.txt`，无需复制或重启容器。直接编辑 `fixtures/` 中的文件也会立即对 MCP 生效。样例 `example.txt`、`email.txt` 受 Git 管理，其余实验输出默认忽略。

```text
fixtures/
├── example.txt
├── email.txt
└── result.txt    # 实验生成，默认不提交
```

从旧目录布局升级时，先停掉两个文件 MCP，再拉取并迁移旧数据。以下命令适用于 writer 使用默认 `1000:1000` 的服务器；自定义 UID/GID 时替换 `chown` 中的数值：

```bash
docker compose stop mcp-file-reader mcp-file-writer
git pull --ff-only
python3 scripts/migrate_fixtures.py
sudo chown 1000:1000 fixtures
sudo chmod 755 fixtures
docker compose up -d --force-recreate mcp-file-reader mcp-file-writer
```

迁移脚本把旧目录里的文件和子目录移动到 `fixtures/`，保留内容和权限，然后移除空的旧目录。发现根目录或两个旧目录之间存在同名条目时，会在移动任何文件前退出；先重命名冲突文件再重试。重复运行脚本不会影响已经迁移的文件。旧版 Compose 可将命令替换为 `docker-compose`。

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

## Ubuntu 22.04 与远程访问

Ubuntu 22.04 安装 Docker Engine 和 Compose 插件后，可以使用相同的 Compose 配置。模型通过远程 API 调用时，服务器无需 GPU。

通过服务器 IP 访问时，在服务器的 `.env` 中设置：

```dotenv
LAB_BIND_HOST=0.0.0.0
```

然后启动服务，浏览器打开 `http://服务器IP:5173`。前端默认使用同源 `/api`，Web 容器中的 Nginx 将请求转发到 `control-plane:8000`；SSE 事件流关闭代理缓冲，并允许长任务等待。浏览器无需直接连接 8000 端口，也无需单独配置服务器 IP 的 CORS。`LAB_BIND_HOST` 同时影响 Web 和 API 的宿主机绑定，服务器安全组可限制 8000 的外部访问。控制后台没有内置登录认证，应通过 SSH 隧道、访问来源限制或带认证的反向代理访问。

写文件 MCP 的 `MCP_FILE_WRITER_UID`、`MCP_FILE_WRITER_GID` 应与共享 `fixtures/` 目录所有者一致；使用前端保存模型 Key 前，须设置下文的 `CONFIG_ENCRYPTION_KEY`。使用 root 启动 Compose 时，writer 仍按配置的 UID/GID 运行，需要为该用户授予目录写权限。

从旧版本更新前端连接修复时，在服务器仓库目录执行：

```bash
git pull --ff-only
docker compose up -d --build --no-deps web
curl -i http://127.0.0.1:5173/api/v1/scenarios
```

最后一个请求应返回 JSON 数组；如果返回 HTML，说明仍在运行旧的 Web 镜像或代理配置。旧版 Compose 将 `docker compose` 替换为 `docker-compose`。更新后使用 `Ctrl+F5` 刷新页面；仅重启容器不会重新编译旧的 JS。默认无需设置 `VITE_CONTROL_PLANE_URL`，已有的前端构建配置若指向 `127.0.0.1:8000`，应移除该覆盖并重新构建。前端本地开发的 `npm run dev` 也会通过 Vite 将 `/api` 转发到本机 8000 端口。

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
          /       |       \
         v        v        v
     mcp-tools mcp-resources mcp-file-reader mcp-file-writer
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
| `mcp-file-reader` | 只读文件型 MCP fixture，提供 `read_file` | Compose 内部 |
| `mcp-file-writer` | 在共享 `fixtures/` 内写文件的 MCP fixture，提供 `write_file` | Compose 内部 |
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
| `MCP_FILE_READER_URL` | `http://mcp-file-reader:8200` | 只读文件 MCP 代理地址 |
| `MCP_FILE_MAX_BYTES` | `65536` | 单个文件允许返回的最大字节数 |
| `MCP_FILE_WRITER_URL` | `http://mcp-file-writer:8200` | 写文件 MCP 代理地址 |
| `MCP_FILE_WRITER_MAX_BYTES` | `65536` | 单次写入允许的最大字节数 |
| `MCP_FILE_WRITER_UID` | `1000` | writer 绑定目录的宿主机用户 UID；服务器上按实际目录所有者调整 |
| `MCP_FILE_WRITER_GID` | `1000` | writer 绑定目录的宿主机用户 GID；服务器上按实际目录所有者调整 |

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
