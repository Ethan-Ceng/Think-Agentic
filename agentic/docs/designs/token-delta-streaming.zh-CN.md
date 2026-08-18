# Token Delta Streaming 设计

## 文档状态

- 状态：`IMPLEMENTED_VALIDATED`
- 负责人：Agentic Runtime
- 创建日期：2026-08-18
- 最近更新：2026-08-18
- 前置设计：`agentic/docs/designs/lead-agent-runtime-unification.zh-CN.md`

## 背景

Lead Agent 已将简单请求收敛为一次结构化模型调用，并将单目标工具任务与多步骤计划分流。但 `OpenAILLM.invoke()` 仍等待完整 Chat Completions 响应后才返回，用户在长答案生成期间只能看到等待状态。现有 HTTP 层虽然使用 SSE，传输的仍是完整 Message、Plan、Tool 等事件，不是真正的模型 Token Delta。

直接把 Provider Chunk 原样送到前端不可接受：Lead、ReAct 和 Finalizer 都使用结构化 JSON，原始 Chunk 会暴露协议字段、无效的半截 JSON，甚至可能把隐藏推理或 Tool 参数误当成用户答案。Streaming 必须在不增加 Direct 模型调用、不破坏 Tool Loop/HITL、不把临时文本写入正式历史的前提下实施。

## 目标

- 用户可见答案在 Provider 返回首批可见文本后立即增量显示，不等待完整响应。
- Direct 继续保持单次模型调用，不新增“先路由、再回答”的第二次调用。
- React Goal、Plan Step 结果、Plan Finalizer 和 Legacy ReAct 最终回复均可复用同一流式能力。
- 原始结构化 JSON、`reasoning_content`、Tool Call Delta 和内部字段永远不发送给前端。
- Delta 只进入当前 Task 的 Redis/SSE 传输，不写入 `sessions.events` 或逐条写入 Trace；最终 Message 只持久化一次。
- SSE 重连、Provider 不支持流式、模型重试和结构化校验失败时，界面不会重复、残留或提交半截答案。
- Trace 记录模型 TTFT、总延迟、Token Usage 和最终状态，为后续真实模型评测提供基线。

## 功能范围

- 扩展 LLM 协议与 OpenAI-compatible Provider，支持流式 Content/Tool Call 聚合和最终 Message 重建。
- 新增顶层 JSON 字符串字段增量投影器，只投影显式配置的用户可见字段。
- 新增临时 `message_delta` 事件及 `append/reset/abort` 生命周期。
- 为最终 `MessageEvent` 增加可选 `stream_id`，用于用权威完整消息替换前端草稿。
- AgentTaskRunner、Redis Task Stream、AgentService、SSE Mapper 和 Web 消息时间线接通 Delta。
- 增加 `TOKEN_DELTA_STREAMING_ENABLED` Feature Flag，默认关闭并支持无流式 Provider 回退。
- 为 `model_calls` 增加 `ttft_ms`，同步 Trace API 和前端 TracePanel。
- 覆盖 Direct、React、Plan Finalizer、Tool 后最终回复、重试、断线重放和非流式回退测试。

## 非功能范围

- Durable Run/Event/Outbox、进程重启自动恢复和跨进程续传。
- Local Child Agent、Sub-agent、Reviewer、fan-out/fan-in 或 A2A 架构调整。
- Sandbox、Tool Approval 或 Side-effect Ledger 重构。
- 把 Chat Completions 迁移到 Responses API，或增加新的 Provider Registry。
- 流式展示隐藏推理、内部计划草稿、Tool 参数或原始 JSON。
- 将每个 Token 保存为 Session Event、Trace Event 或数据库 Message 记录。
- 音频、图片等多模态 Delta。

## 业务流程

1. Agent 为本次用户可见输出创建稳定 `stream_id`，并声明允许投影的顶层 JSON 字段，例如 Direct 的 `answer`、React/Finalizer 的 `message`、Step 的 `result`。
2. OpenAI-compatible Provider 使用 `stream=true` 接收 Chunk；服务端聚合 Content、Reasoning、Tool Call、Finish Reason 和 Usage，最终重建与块响应兼容的 Assistant Message。
3. 结构化字段投影器只解析 Content 中目标顶层字符串字段；首次可见片段立即产生 `message_delta/append`，后续片段按小批次合并发送。
4. AgentTaskRunner 只把 Delta 写入 Task Output Stream；AgentService 通过现有 SSE 返回，但不写 Session/Trace 正式历史。
5. Web 以 `stream_id` 创建或更新一个临时 Assistant 草稿。`reset` 清空同一草稿，`abort` 删除草稿。
6. 完整响应到达后，服务端执行现有 JSON 解析、Pydantic 契约和 Direct 安全校验。校验成功时发送带同一 `stream_id` 的最终 Message，前端原位替换草稿；附件只在该最终事件中出现。
7. 若流式尝试失败且允许重试，服务端先发 `reset` 再重试；若最终失败或决策回退到其他策略，发 `abort`，随后走现有 Error/Legacy 路径。
8. Provider 不实现流式接口或 Feature Flag 关闭时，保持当前完整响应行为，公共聊天接口不变。

## 核心规则

1. Direct 的 Streaming 不得增加模型调用；路由 JSON 中的 `answer` 是唯一直接答案来源。
2. 只有服务端白名单指定的顶层字符串字段可以投影；不得把完整 Content 或任意 JSON Path 交给前端选择。
3. `reasoning_content`、Tool Call Delta、Tool Arguments 和尚未识别的 Content 永不进入 `message_delta`。
4. Delta 是临时传输事件，不是事实源；最终 `MessageEvent` 是唯一权威用户消息。
5. 同一可见输出只使用一个 `stream_id`；最终 Message 必须关联该 ID，或在从未发送 Delta 时保持为空。
6. 第一个可见片段立即发送；之后以字符阈值或时间阈值做小批次合并，避免每 Token 一次 Redis/SSE/Markdown 渲染。
7. Provider 流结束后必须重建完整 Assistant Message，继续使用现有 Memory、JSON Parser、Tool Loop 和 Trace 完成逻辑。
8. Tool Call 阶段即使使用 Provider Streaming，也只聚合 Tool Call，不产生用户可见 Delta。
9. 结构化校验失败、Direct 安全校验失败或策略不是预期可见模式时，任何已显示草稿必须 `abort`。
10. SSE 重放使用现有 Redis Event ID 去重；Session Snapshot 不包含 Delta，刷新后以最终持久化 Message 为准。
11. 前端不得把草稿当作可分支、可复制的正式消息；最终 Message 到达后才恢复这些动作。
12. Feature Flag 只影响新创建的 AgentTaskRunner；运行中的流不热切换。

## 现有实现分析

### 相关代码与文档

- `api/app/core/llm/base.py`：当前 LLM Protocol 只有完整响应 `invoke()`。
- `api/app/core/llm/openai_llm.py`：当前调用 `chat.completions.create()` 且未设置 `stream=true`。
- `api/app/core/agent/base.py`：统一处理模型重试、Memory、Tool Loop 和 Trace，是接入流式聚合的唯一合适边界。
- `api/app/core/agent/lead_decision.py`：Direct 答案位于结构化决策 JSON 的顶层 `answer` 字段。
- `api/app/core/agent/react.py`：Goal/Finalizer 的可见字段为 `message`，Step 的可见字段为 `result`。
- `api/app/core/agent/agent_task_runner.py`：当前每个 Flow Event 都同时写 Redis、Session 和 Trace，需要为临时 Delta 分离传输与持久化。
- `api/app/services/agent_service.py`、`api/app/controllers/session.py`：已经具备 SSE 与 Event ID 重放，可直接承载新事件类型。
- `web/src/composables/useSessionDetail.ts`、`web/src/lib/session-events.ts`：当前以事件数组构建时间线，适合按 `stream_id` 合并草稿并用最终 Message 替换。
- `api/app/services/trace_service.py`、`api/app/models/run_trace.py`：已有 Model Call 总延迟和 Token Usage，缺少 TTFT。

### 可复用能力

- 现有 Redis Stream ID、SSE `event_id`、前端 `seenEventIds` 可提供同一页面重连去重。
- 现有最终 Message 持久化、Session Snapshot 和流结束校准可作为权威收敛路径。
- 现有 JSON Parser/Pydantic 契约继续负责完整响应校验，增量投影器不替代最终解析。
- 现有 Feature Flag、Trace Model Call 与前后端 SSE Mapper 模式可直接扩展。

### 当前约束

- OpenAI SDK 版本为 1.107.2，Chat Completions 同时支持 `stream` 与 `stream_options`，但兼容 Provider 可能不支持 Usage Chunk 或流式参数。
- 当前 Direct/React/Plan 使用结构化 JSON，不能直接显示原始 Content Chunk。
- 当前 Runtime 仍依赖进程内 Task；本批只能保证连接级续传与最终消息校准，不能宣称服务重启后继续 Delta。
- Provider Streaming 中 Tool Call Arguments 会跨 Chunk 拆分，必须完整聚合后才交给现有 Tool Loop。

## 可选方案

### 方案 A：原始 Provider Chunk 直接透传前端

- 实现方式：把 `delta.content` 作为 SSE 文本直接追加到聊天气泡。
- 优点：改动少，TTFT 最短。
- 缺点：用户会看到 JSON 协议、转义符和无效半截结构，Tool/Reasoning 边界无法保证。
- 风险：内部字段或敏感 Tool 参数泄漏，最终内容无法可靠校验和回滚。

### 方案 B：服务端结构化字段投影 + 最终消息校准（推荐）

- 实现方式：Provider 流在服务端完整聚合；独立投影器只增量解码白名单顶层字符串字段，以 `stream_id` 发送临时 Delta，最后用完整 Message 替换。
- 优点：保留 Direct 单调用，用户能看到真正 Delta，结构化协议和内部信息不泄漏，现有 Tool Loop/Memory/Trace 可复用。
- 缺点：需要可靠的增量 JSON 字符串解析、草稿生命周期和较完整的前后端测试。
- 风险：模型在完整校验前已产生可见草稿；必须通过 `reset/abort` 和最终权威替换收敛。

### 方案 C：Lead 先结构化路由，再单独流式生成答案

- 实现方式：首轮仅返回 `direct/react/plan`，Direct 再进行一次普通文本流式调用。
- 优点：输出流最简单，无需增量 JSON 字段解析。
- 缺点：Direct 从一次模型调用退化为两次，重新引入本次升级刚消除的固定额外延迟与成本。
- 风险：用户体验指标表面有 Streaming，实际 TTFT 和总延迟可能更差。

## 方案对比

| 维度 | 方案 A 原始透传 | 方案 B 字段投影 | 方案 C 双调用 |
| --- | --- | --- | --- |
| 实现复杂度 | 低 | 中高 | 中 |
| Direct 调用次数 | 1 | 1 | 2 |
| 结构化安全 | 差 | 好 | 好 |
| Tool/Reasoning 隔离 | 差 | 好 | 好 |
| 兼容现有 Agent | 表面兼容 | 高 | 改变 Direct 语义 |
| 测试难度 | 中 | 高 | 中 |
| 主要风险 | 协议/敏感信息泄漏 | 草稿与最终消息一致性 | 延迟、成本和调用链回退 |

## 推荐方案

选择方案 B。它是唯一同时满足“Direct 单调用”“真正可见 Delta”“结构化协议不泄漏”和“现有 Tool Loop/HITL 兼容”的方案。方案 A 不满足安全与正确性底线；方案 C 会重新增加固定模型调用，与 Lead 优化目标冲突。

## 数据结构

### MessageDeltaEvent

| 字段 | 类型 | 必填 | 说明 | 约束/默认值 |
| --- | --- | --- | --- | --- |
| `type` | `Literal["message_delta"]` | 是 | 临时流式事件类型 | 固定值 |
| `stream_id` | `str` | 是 | 草稿与最终 Message 的关联 ID | 单次可见输出稳定 |
| `delta` | `str` | 是 | 当前增量文本 | `reset/abort` 时为空 |
| `operation` | `append/reset/abort` | 是 | 草稿操作 | 默认 `append` |
| `sequence` | `int` | 是 | 同一 Stream 的发送序号 | 从 0 单调递增 |
| `role` | `assistant` | 是 | 可见消息角色 | 固定值 |

### MessageEvent 扩展

| 字段 | 类型 | 必填 | 说明 | 约束/默认值 |
| --- | --- | --- | --- | --- |
| `stream_id` | `str | null` | 否 | 替换对应临时草稿 | 无 Delta 时为空 |

### ModelCall 扩展

| 字段 | 类型 | 必填 | 说明 | 约束/默认值 |
| --- | --- | --- | --- | --- |
| `ttft_ms` | `int | null` | 否 | 请求开始到首个 Provider 有效 Chunk | 非流式/Provider 不提供时为空 |

## 接口设计

### LLM.stream

- 输入：与现有 `invoke()` 相同的 messages、tools、response_format、tool_choice。
- 输出：异步 `LLMStreamDelta` 序列，终止前产生一个包含完整 Assistant Message 的 `LLMStreamCompleted`。
- 权限：内部接口，不新增用户权限。
- 幂等/并发：一次调用一个异步迭代器；失败由 BaseAgent 现有重试策略处理。
- 兼容性：保留 `invoke()`；没有 `stream()` 的 Fake/Provider 或 Flag 关闭时使用块响应。

### BaseAgent 可见字段投影

- 输入：模型消息、格式、白名单顶层字段名和可选 `stream_id`。
- 输出：零到多个 `MessageDeltaEvent`，最后返回完整模型 Message 供现有 Tool/JSON 流程处理。
- 权限：字段名只由代码内 Agent 策略选择，用户不能指定。
- 幂等/并发：同一调用序列递增；重试先 `reset`，终止失败 `abort`。
- 兼容性：未传字段时保持现有块调用与事件行为。

### SSE `message_delta`

- 输入：AgentTaskRunner 产生的临时 Delta。
- 输出：SSE event=`message_delta`，data 包含 `event_id/stream_id/delta/operation/sequence/role/created_at`。
- 权限：沿用 Session 所有权与现有 Chat SSE 认证。
- 幂等/并发：Redis Event ID 用于重放去重；`stream_id + sequence` 用于草稿顺序防御。
- 兼容性：旧前端忽略未知事件；Feature Flag 默认关闭。

## 错误处理与可观测性

- Provider 在任何可见文本前失败：沿用现有重试，不产生草稿。
- Provider 在已产生 Delta 后失败：发送 `reset`，清空投影器并重试；重试耗尽发送 `abort` 和现有 Error。
- 完整 JSON、Pydantic 或 Direct 安全校验失败：发送 `abort`，不得把草稿提交为正式消息；Lead 可按现有规则回退 Legacy。
- Provider 不接受 `stream_options`：在尚未收到任何 Chunk 时仅重试一次不带该参数的 Streaming；仍失败则由 BaseAgent 回退/重试。
- SSE 断开不取消已启动 Task；重连按 Event ID 续读。页面刷新若无法续读临时 Delta，以 Session 最终 Message 校准。
- Trace 的 Model Call 记录 `ttft_ms`、`latency_ms`、Usage、Finish Reason 和错误；不保存每个 Delta 或隐藏推理。
- 日志只记录流开始/完成/重置/中止和计数，不记录完整用户答案、原始 JSON 或 Tool Arguments。

## 迁移与回滚

- 迁移：新增可空 `model_calls.ttft_ms`；历史记录保持 `null`。Event/Message 字段均为可选或新类型，无需改写历史 Session JSON。
- 部署：先保持 `TOKEN_DELTA_STREAMING_ENABLED=false`，完成 Fake、API、Web 和真实目标模型评测后在 Staging 开启。
- 回滚：关闭 Flag 后新 Runner 回到完整响应；旧前端忽略未知 Delta。若回滚代码，保留可空数据库列不影响旧版本。

## 风险

| 风险 | 可能性 | 影响 | 缓解措施 | 验证方式 |
| --- | --- | --- | --- | --- |
| 半截/非法 JSON 已显示草稿 | 中 | 中 | 只投影白名单字符串；校验失败 `abort`；最终 Message 权威替换 | 分块、截断、非法尾部测试 |
| JSON 转义或 Unicode 跨 Chunk 解码错误 | 中 | 高 | 独立增量投影器处理 escape、Unicode 和任意 Chunk 边界 | 属性化/参数化分块测试 |
| 每 Token 一次 Redis/SSE 导致开销过高 | 高 | 中高 | 首片立即、后续字符/时间阈值批处理 | 长文本事件数与 TTFT 测试 |
| Tool Call Arguments 聚合错误 | 中 | 高 | 按 Tool Call index 聚合 id/name/arguments；最终沿用 JSON Parser | 多 Chunk Tool Call 测试 |
| 重试后文本重复 | 中 | 高 | 首次失败后发 `reset`；Event ID 与 sequence 去重 | 中途异常重试集成测试 |
| SSE 断线或刷新残留草稿 | 中 | 中 | 重连 cursor；最终 Snapshot 校准；草稿不持久化 | 断线、重连、刷新前端测试 |
| Provider 不兼容 stream_options | 中 | 中 | 首请求未产出时去除参数回退；Flag 可关闭 | Provider Fake 400 回退测试 |
| Markdown 每 Chunk 重渲染卡顿 | 中 | 中 | Delta 批处理；前端只更新一个草稿项 | 长 Markdown 性能测试 |
| Reasoning/协议字段泄漏 | 低 | 高 | 永不投影 reasoning/tool；顶层白名单字段解析 | 安全负例测试 |

## 重要假设

- 当前 OpenAI-compatible Provider 能返回标准 Chat Completion Chunk；不满足时允许完整响应回退。
- Direct、Goal、Step 和 Finalizer 的用户可见内容继续位于代码固定的顶层字符串字段。
- 当前 Redis Task Stream 与 SSE Event ID 足以支持同一运行进程内的断线续读；跨进程恢复留给 Durable Runtime。
- 最终 Message 可以晚于 Delta 到达，并且前端以 `stream_id` 原位替换草稿。
- 本批不要求默认开启 Feature Flag；真实目标模型的 TTFT、正确性和兼容性评测是启用门禁。

## 待决策项

无影响核心设计的待决策项。已采用以下决策：

1. 使用服务端顶层 JSON 字段投影，不把结构化解析推给前端。
2. Direct 保持一次模型调用，不采用路由与回答分离。
3. Delta 不进入 Session/Trace 正式历史，最终 Message 是唯一事实。
4. 本批覆盖文本 Delta，不覆盖多模态、Durable 或 Child Agent。

## 验收标准

- [x] Flag 开启且 Provider 支持 Streaming 时，Direct 在完整响应完成前产生至少一个 `message_delta`，并且模型调用仍只有一次。
- [x] Direct、React Goal、Tool 后最终回复、Plan Step 结果和 Plan Finalizer 的草稿最终都被同 `stream_id` 的完整 Message 原位替换。
- [x] 原始 JSON key、结构符、`reasoning_content`、Tool Call Arguments 和隐藏推理不出现在任何 Delta。
- [x] JSON 字符串的引号、反斜杠、换行、Markdown、中文和 `\uXXXX` 跨任意 Chunk 边界后与最终文本完全一致。
- [x] 模型中途失败并重试时前端先清空旧草稿，不重复文本；最终失败或 Lead 回退时草稿被删除。
- [x] Provider 无 `stream()`、Flag 关闭或 Streaming 参数不兼容时，现有完整 Message 路径正常且无行为回归。
- [x] Delta 只写 Task Output Stream；Session Snapshot、Session Event 和 Trace Event 不包含逐 Token Delta，最终 Message 只保存一次。
- [x] SSE 断线按 Event ID 重连不重复追加；页面刷新后以最终持久化 Message 恢复，不残留临时草稿。
- [x] Model Call 的 `ttft_ms`、总延迟、Usage 与状态可在 Trace API/UI 查看，历史记录兼容 `null`。
- [x] 长文本不会产生每 Token 一个持久化事件；首片立即发送，后续批处理事件数量有确定性上界。
- [x] 后端测试、迁移往返、Ruff、前端测试、类型检查、生产构建和代码审查全部通过，无未处理 blocking/major。
