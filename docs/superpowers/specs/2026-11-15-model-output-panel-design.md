# 模型输出面板设计

## 目标

在 Web Workbench 中实时查看 root/worker 每一轮模型的结构化决策，验证模型如何选择 `answer`、`delegate` 或 `mcp_call`，并把决策与 A2A/MCP 事件按同一个 run 和 task 关联起来。

## 范围

- Agent Runtime 为每次模型调用写入 `model` 协议事件。
- 复用 Control Plane 已有的事件存储、事件列表 API 和 SSE 流，不新增结果接口。
- Web Workbench 增加模型输出面板，实时展示模型响应、调用者和错误。
- 模型事件只记录安全的请求元数据、结构化输出和 usage；不记录 API Key，也不记录完整 prompt。

## 事件设计

成功调用产生两条事件：

- `model / completion.request / outbound`：provider、model、agent_id、hop、可用动作集合和消息数量。
- `model / completion.response / inbound`：provider、model、结构化 `output` 和 `usage`。

超时、上游 HTTP 错误或非法 JSON 产生 `model / completion.error / inbound`，payload 只包含稳定的错误摘要。所有事件使用当前 task 的 `CorrelationContext`，并使用稳定的 `source_event_key` 防止重试重复写入。

## 前端行为

模型输出面板位于 Workbench 右侧，显示最外层 A2A `message/send.response` 的最终返回内容。例如 calculator 返回 `15` 时面板显示 `15`，不显示中间模型的 `delegate` 或 `mcp_call` 决策。事件时间线默认隐藏中间 Agent relay response，保留请求、模型决策和 MCP 结果；切换 `All events` 可以查看完整事件证据，点击事件可继续查看通用 Inspector。

## 验证

- Agent Runtime 测试验证成功模型调用产生 request/response 事件，失败调用产生 error 事件。
- 前端测试验证面板渲染空状态、模型信息、动作和结构化输出。
- 运行现有 Python 测试、前端测试和构建，确认 Compose 运行链路不受影响。
