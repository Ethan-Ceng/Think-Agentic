# Token Delta Streaming 实施计划

## 关联设计

- 设计文档：`agentic/docs/designs/token-delta-streaming.zh-CN.md`
- 开发分支：`feature/token-delta-streaming`
- 实施基线：Lead Agent Runtime Unification（`ce71be8`）
- 约束：本批不实施 Sandbox、Durable Runtime、Sub Agent/A2A 内部委派、Responses API 迁移或多模态流式协议。

## 当前进度

- 整体状态：`READY_TO_MERGE`
- 当前阶段：completed
- 当前任务：无
- 已完成：7 / 7
- 阻塞问题：无
- 最近更新时间：2026-08-18 12:50（Asia/Shanghai）

## 本批交付边界

本计划把当前“事件级流式”升级为安全的用户可见 Token Delta 流式：Provider 返回的 Chat Completions chunk 先在服务端聚合，并且只投影当前 Agent 输出契约中指定的顶层字符串字段，再通过 Redis/SSE 发送临时 `message_delta` 事件。原始 JSON、思考内容、工具参数和未验证结构不得暴露给前端。最终 `message` 事件仍是唯一持久化、可恢复和可追踪的权威答案。

本批必须实现：

- OpenAI-compatible Chat Completions 流式调用与完整消息重建；
- Direct 的 `answer`、React Goal/Finalizer 的 `message`、Plan Step 的 `result` 安全增量投影；
- retry/reset/abort/final 协议和同一 `stream_id` 关联；
- Redis/SSE 临时传输、前端草稿合并与最终消息替换；
- 首 Token 延迟 `ttft_ms` 观测、数据库迁移、API 和 Trace UI 展示；
- Feature Flag、非流式 Provider/Fake 兼容和完整回归验证。

本批明确不做：

- 保存每个 Delta 到 `sessions.events`、Trace Event 或数据库；
- 输出 reasoning、原始 JSON、tool call arguments 或未通过校验的内容；
- 为 Direct 增加“路由一次、回答一次”的第二次模型调用；
- 修改现有 Sub Agent/A2A、Sandbox、Durable Run 或附件协议。

## 全局约束

- `TOKEN_DELTA_STREAMING_ENABLED` 默认关闭，只影响新建 Runner/Run；关闭后保持当前行为。
- Provider 原始 chunk 只能进入服务端聚合器，公共事件只允许携带被选中的可见字符串字段。
- 首个可见片段立即发送，后续片段按字符数或短时间窗口批量发送，避免每个字符都写 Redis。
- Delta 只进入当前输出 Redis Stream；最终 `MessageEvent` 才进入 Session Repository、Session Snapshot 和 Trace 投影。
- 同一回答的 Delta 与 Final 使用相同 `stream_id`；Final 到达后原地替换草稿，不能生成重复消息。
- 已向客户端发送 Delta 后发生重试必须先发 `reset`；最终验证失败或流式路径被放弃必须发 `abort`。
- Provider 不支持 streaming、测试 Fake 没有 `stream()`、或兼容端拒绝 `stream_options` 时，必须安全回退且不能让 Run 失败。
- 不自动提交、推送、创建 PR 或合并；状态变化、测试结果和审查结论即时写回本计划。

## 状态变更记录

| 日期时间 | 整体状态 | 当前任务 | 变更原因 |
| --- | --- | --- | --- |
| 2026-08-18（Asia/Shanghai） | `PLAN_READY` | 无 | 设计已确认；拆分 Provider、Agent、传输、前端与观测实施任务。 |
| 2026-08-18 11:25（Asia/Shanghai） | `IN_PROGRESS` | Task 1 | 独立分支、设计与计划均已就绪；开始以失败测试建立 Provider 流式契约。 |
| 2026-08-18 11:29（Asia/Shanghai） | `IN_PROGRESS` | Task 2 | Task 1 的 5 项流式合同测试、15 项 Lead 回归、Ruff 与编译检查通过；进入安全字段投影。 |
| 2026-08-18 11:38（Asia/Shanghai） | `IN_PROGRESS` | Task 3 | Task 2 的 14 项新增测试与 117 项 Agent/LLM 回归通过；进入公共事件和 Lead/React/Plan 接线。 |
| 2026-08-18 11:50（Asia/Shanghai） | `IN_PROGRESS` | Task 4 | Task 3 的公共事件、四类可见输出和关闭开关已验证，122 项 Agent/Event/Config 回归通过；进入临时传输边界。 |
| 2026-08-18 11:56（Asia/Shanghai） | `IN_PROGRESS` | Task 5 | Task 4 已证明 Delta 仅写 Redis、异常/取消自动 abort，41 项 Runner/Service/Controller 回归通过；进入前端草稿合并。 |
| 2026-08-18 12:18（Asia/Shanghai） | `IN_PROGRESS` | Task 7 | 前端草稿、TTFT 与迁移完成；进入全量验证和代码审查。 |
| 2026-08-18 12:50（Asia/Shanghai） | `READY_TO_MERGE` | 无 | 全量回归、迁移往返、目标 Provider/模型实测和自审完成；两项 major 已修复，无未解决 blocking/major。 |

## Task 1：建立 LLM 流式协议与 Provider 消息聚合

状态：completed

### 目标

让 OpenAI-compatible Provider 能以异步事件返回 content chunk，同时在服务端准确重建与当前 `invoke()` 等价的完整 Assistant Message，并记录首个有效 chunk 的 TTFT。

### 涉及文件

- `agentic/api/app/core/llm/base.py`
- `agentic/api/app/core/llm/openai_llm.py`
- `agentic/api/tests/app/core/llm/test_openai_llm_streaming.py`（新建）

### 实施步骤

1. 为 LLM 层定义内部 Delta/Completed 事件契约，Completed 必须包含完整 message、usage、finish reason 和 `ttft_ms`。
2. 实现 Chat Completions `stream=True` 调用，聚合普通 content、reasoning content 和按 index 分片的 tool calls；reasoning/tool 参数只保留在内部完整消息中。
3. 跳过没有 choices 的 usage-only chunk，并以第一个 content/reasoning/tool 增量记录 TTFT。
4. 首次创建流失败且兼容端不接受 `stream_options` 时只重试一次不带该参数的请求；开始消费 chunk 后不在 Provider 层偷偷重放。
5. 保留现有 `invoke()` 行为，新增流式能力不得破坏不支持流式的测试替身和调用方。
6. 覆盖 content、usage-only、reasoning、tool-call 分片、空 content、错误和兼容回退测试。

### 验证方式

- `uv run pytest tests/app/core/llm/test_openai_llm_streaming.py -q`
- `uv run ruff check app/core/llm/base.py app/core/llm/openai_llm.py tests/app/core/llm/test_openai_llm_streaming.py`
- `uv run python -m py_compile app/core/llm/base.py app/core/llm/openai_llm.py`

### 完成条件

- 任意合法 chunk 边界都能得到正确完整消息；usage 与 TTFT 可用；Provider 兼容降级可验证；公共层尚未接触原始 chunk。

### 执行结果

新增内部 `LLMStreamDelta/LLMStreamCompleted` 契约与 `OpenAILLM.stream()`。实现了 content、reasoning 和按 index 分片的 tool call 聚合，最终重建现有 Agent 可消费的完整 Assistant Message；TTFT 从首个有效 content/reasoning/tool chunk 计算并写入 `_trace_metadata`。兼容端明确拒绝 `stream_options` 时仅在消费前去除参数重试一次，消费开始后的异常不会在 Provider 层重放。

### 验证证据

```text
2026-08-18 11:29 +08:00
- uv run pytest tests/app/core/llm/test_openai_llm_streaming.py -q
  首次 Exit 1：预期失败，LLMStreamDelta/LLMStreamCompleted 尚不存在。
  实现后 Exit 0：5 passed。
- uv run pytest tests/app/core/agent/test_lead_decision.py tests/app/core/agent/test_lead_agent_direct.py -q
  Exit 0：15 passed。
- uv run ruff check app/core/llm/base.py app/core/llm/openai_llm.py tests/app/core/llm/test_openai_llm_streaming.py
  Exit 0：All checks passed。
- uv run python -m py_compile app/core/llm/base.py app/core/llm/openai_llm.py
  Exit 0。
```

## Task 2：实现安全 JSON 字段投影与 BaseAgent 流式生命周期

状态：completed

### 目标

从任意分片的结构化 JSON 中只增量解码明确指定的顶层字符串字段，并让 BaseAgent 在 retry、memory、trace、tool loop 语义不变的前提下提供可选的投影流。

### 涉及文件

- `agentic/api/app/core/llm/json_stream.py`（新建）
- `agentic/api/app/core/agent/base.py`
- `agentic/api/tests/app/core/llm/test_json_stream.py`（新建）
- `agentic/api/tests/app/core/agent/test_base_agent_streaming.py`（新建）

### 实施步骤

1. 实现面向指定顶层 key 的增量 JSON 字符串状态机，正确处理任意 chunk、转义、Unicode 转义、代理对、换行、引号和反斜杠。
2. 确保相同 key 出现在嵌套对象或其他字符串文本中时不会被误投影；非字符串目标字段必须拒绝。
3. 为 BaseAgent 增加内部流式调用生命周期，复用现有 memory、retry、trace、响应验证和 tool loop，非流式入口保持兼容。
4. 首个可见片段立即发出，后续按阈值批量；已发内容后重试产生 reset，流式失败产生 abort，并最终返回完整响应供现有解析器校验。
5. Fake/Provider 没有流式能力时自动调用 `invoke()`，只产生 Final，不伪造 Delta。
6. 使用单元测试覆盖解析边界、retry/reset/abort、工具后续模型调用、memory 一次写入和 trace 一次完成。

### 验证方式

- `uv run pytest tests/app/core/llm/test_json_stream.py tests/app/core/agent/test_base_agent_streaming.py -q`
- `uv run ruff check app/core/llm/json_stream.py app/core/agent/base.py tests/app/core/llm/test_json_stream.py tests/app/core/agent/test_base_agent_streaming.py`
- `uv run python -m py_compile app/core/llm/json_stream.py app/core/agent/base.py`

### 完成条件

- 只有被允许的顶层字符串可成为 Delta；原始 JSON、reasoning 与 tool 参数不可见；现有 invoke/tool/memory/trace 契约不回归。

### 执行结果

新增独立 `TopLevelJSONStringProjector`，以完整词法状态处理任意 chunk、转义、Unicode 代理对和嵌套值，只允许代码指定的顶层字符串字段产生增量。BaseAgent 已将块响应和流式响应收敛到同一 retry/memory/trace 生命周期，提供内部 append/reset/abort/completed 事件；首片立即发送、后续按字符或时间阈值批量，并覆盖初次调用、工具后调用、HITL resume 与无 `stream()` Fake 回退。

### 验证证据

```text
2026-08-18 11:38 +08:00
- uv run pytest tests/app/core/llm/test_json_stream.py tests/app/core/agent/test_base_agent_streaming.py -q
  首次 Exit 1：预期失败，json_stream 与内部投影事件尚不存在。
  实现后 Exit 0：14 passed。
- uv run pytest tests/app/core/agent/test_interaction_resume.py tests/app/core/agent/test_branch_context_seed.py tests/app/core/agent/test_skill_runtime_context.py tests/app/core/agent/test_prompt_locale_routing.py -q
  Exit 0：34 passed。
- uv run pytest tests/app/core/agent tests/app/core/llm -q
  Exit 0：117 passed。
- uv run ruff check app/core/llm/json_stream.py app/core/agent/base.py tests/app/core/llm/test_json_stream.py tests/app/core/agent/test_base_agent_streaming.py
  Exit 0：All checks passed。
- uv run python -m py_compile app/core/llm/json_stream.py app/core/agent/base.py
  Exit 0。
```

## Task 3：接入公共事件协议与 Lead/React/Plan 可见输出

状态：completed

### 目标

定义前后端稳定的 `message_delta` 协议，并将 Direct、React Goal、Plan Step 与 Finalizer 的正确字段接入流式投影，不改变 Planner 自身的不可见规划语义。

### 涉及文件

- `agentic/api/app/core/entities/event.py`
- `agentic/api/app/schemas/event.py`
- `agentic/api/app/core/agent/lead_decision.py`
- `agentic/api/app/core/agent/lead.py`
- `agentic/api/app/core/agent/react.py`
- `agentic/api/app/core/flows/planner_react.py`
- `agentic/api/app/core/config.py`
- `agentic/api/tests/app/core/test_interaction_events.py`
- `agentic/api/tests/app/core/test_config.py`
- `agentic/api/tests/app/core/agent/test_lead_agent_streaming.py`（新建）
- `agentic/api/tests/app/core/agent/test_react_streaming.py`（新建）

### 实施步骤

1. 新增 `MessageDeltaEvent`，包含 `stream_id`、`sequence`、`delta`、`operation=append|reset|abort` 与 assistant role；为 Final `MessageEvent` 增加可选 `stream_id`。
2. 在 Lead Decision 中只投影 Direct 的 `answer`；若最终判定不是 Direct、校验失败或降级，终止任何意外草稿。
3. React Goal/Finalizer 投影 `message`，Plan Step 投影 `result`；所有 Final Message 传递同一 `stream_id`。
4. Planner 的 plan JSON、决策 reason、工具参数和错误详情不得流向用户。
5. 将配置 `TOKEN_DELTA_STREAMING_ENABLED=false` 注入 Lead、Legacy Flow 和 Agent；保持旧构造方式与测试 Fake 兼容。
6. 覆盖 Direct 一次模型调用、React 工具循环、Plan Step、Finalizer、HITL resume、错误与关闭开关测试。

### 验证方式

- `uv run pytest tests/app/core/agent/test_lead_agent_streaming.py tests/app/core/agent/test_react_streaming.py tests/app/core/test_interaction_events.py tests/app/core/test_config.py -q`
- `uv run pytest tests/app/core/agent/test_lead_agent_direct.py tests/app/core/agent/test_lead_agent_react.py tests/app/core/agent/test_lead_agent_plan.py tests/app/core/agent/test_interaction_resume.py -q`
- `uv run ruff check app/core/entities/event.py app/schemas/event.py app/core/agent/lead_decision.py app/core/agent/lead.py app/core/agent/react.py app/core/flows/planner_react.py app/core/config.py`

### 完成条件

- 四类用户可见模型输出均按正确字段产生 Delta；Planner/工具内部数据不泄漏；Final 能唯一关闭对应草稿；开关关闭时事件形状保持原样。

### 执行结果

新增严格的 `MessageDeltaEvent` 与 Final `MessageEvent.stream_id`，同步 SSE schema/mapper，并加入默认关闭的 `TOKEN_DELTA_STREAMING_ENABLED`。新增 `VisibleMessageStream` 统一分配 stream ID、sequence 和 abort；Lead Decision 只投影 Direct `answer`，安全校验失败先 abort 再回退。React Goal/Finalizer 投影 `message`，Plan Step/Resume 投影 `result`，最终契约校验成功后才发送带同一 stream ID 的权威 Message。Legacy Flow 与 Runner 已接收关闭开关，但 Delta 的非持久化边界留在 Task 4 实施。

### 验证证据

```text
2026-08-18 11:50 +08:00
- uv run pytest tests/app/core/test_interaction_events.py tests/app/core/test_config.py -q
  首次 Exit 1：预期失败，MessageDeltaEvent 尚不存在。
  实现后 Exit 0：12 passed；补充严格载荷校验后相关集合 17 passed。
- uv run pytest tests/app/core/agent/test_lead_agent_streaming.py tests/app/core/agent/test_react_streaming.py -q
  首次 Exit 1：预期失败，LeadDecisionCompleted 尚不存在。
  中间验证发现一个合法答案跨两个 Delta，修正测试为聚合语义；最终 Exit 0：7 passed。
- uv run pytest tests/app/core/agent/test_lead_agent_streaming.py tests/app/core/agent/test_react_streaming.py tests/app/core/test_interaction_events.py tests/app/core/test_config.py tests/app/core/agent/test_lead_agent_direct.py tests/app/core/agent/test_lead_agent_react.py tests/app/core/agent/test_lead_agent_plan.py tests/app/core/agent/test_interaction_resume.py -q
  Exit 0：40 passed。
- uv run pytest tests/app/core/agent tests/app/core/test_interaction_events.py tests/app/core/test_config.py -q
  Exit 0：122 passed。
- uv run ruff check（Task 3 全部实现与测试文件）
  Exit 0：All checks passed。
- uv run python -m py_compile（Task 3 全部后端实现文件）
  Exit 0。
```

## Task 4：建立临时 Redis/SSE 传输边界

状态：completed

### 目标

让 Delta 经现有输出 Redis Stream 和 SSE 实时送达，但不进入 Session 事件历史、Snapshot 或持久 Trace；Final 继续沿用现有权威持久化路径。

### 涉及文件

- `agentic/api/app/core/agent/agent_task_runner.py`
- `agentic/api/app/services/agent_service.py`
- `agentic/api/app/interfaces/endpoints/session.py`
- `agentic/api/tests/app/core/agent/test_agent_task_runner_streaming.py`（新建）
- `agentic/api/tests/app/services/test_agent_service_streaming.py`（新建）
- `agentic/api/tests/app/interfaces/endpoints/test_session_streaming.py`（新建）

### 实施步骤

1. 在 Runner 中为 Delta 建立仅写 output stream 的临时事件路径，不调用 `session.add_event()` 或 `trace_service.project_event()`。
2. 保持 Final Message、附件同步、latest_message、Run 完成和错误状态的原有事务边界。
3. 验证 TypeAdapter、Redis 序列化和 SSE Mapper 能映射 append/reset/abort/final。
4. 验证断线重连可重放仍在 Redis 窗口内的 Delta，但数据库快照只恢复 Final；重复 event id 由客户端去重。
5. 验证错误和取消时不会遗留无法结束的客户端草稿。

### 验证方式

- `uv run pytest tests/app/core/agent/test_agent_task_runner_streaming.py tests/app/services/test_agent_service_streaming.py tests/app/interfaces/endpoints/test_session_streaming.py -q`
- `uv run pytest tests/app/core/agent/test_agent_task_runner_completion.py tests/app/services/test_agent_interactions.py tests/app/interfaces/endpoints/test_session_recovery_route.py -q`
- `uv run ruff check app/core/agent/agent_task_runner.py app/services/agent_service.py app/interfaces/endpoints/session.py tests/app/core/agent/test_agent_task_runner_streaming.py tests/app/services/test_agent_service_streaming.py tests/app/interfaces/endpoints/test_session_streaming.py`

### 完成条件

- 在线客户端实时收到 Delta；数据库和 Trace 不随 token 数增长；Final 与完成状态仍只写一次；重连无重复最终消息。

### 执行结果

Runner 新增 transient output 路径，`MessageDeltaEvent` 只写 Task Output Redis Stream，不调用 Session Repository 或 Trace 投影；Final Message 与 Done/Error 仍沿用原持久化边界。Runner 跟踪活动 stream，在 Flow Error、取消、Wait/Error/Done 前自动发送未持久化 abort，避免残留草稿。AgentService 沿现有 cursor 重放 Delta/Final，且跳过 Delta 的未读计数数据库更新；Controller 无需协议分支即可映射 SSE。

### 验证证据

```text
2026-08-18 11:56 +08:00
- uv run pytest tests/app/core/agent/test_agent_task_runner_completion.py -q
  首次 Exit 1：预期失败，Delta 被写入 Session。
  实现与错误/取消补测后 Exit 0：12 passed。
- uv run pytest tests/app/services/test_agent_service_recovery.py -q
  Exit 0：10 passed；覆盖 cursor 递进、Delta/Final/Done 重放和 Delta 零未读写入。
- uv run pytest tests/app/controllers/test_session_streaming.py -q
  Exit 0：1 passed；SSE 输出 message_delta/message/done 并转发请求 cursor。
- uv run pytest tests/app/core/agent/test_agent_task_runner_completion.py tests/app/core/agent/test_agent_task_runner_lazy_sandbox.py tests/app/services/test_agent_service_recovery.py tests/app/services/test_agent_interactions.py tests/app/controllers/test_session_streaming.py tests/app/core/test_interaction_events.py -q
  Exit 0：41 passed。
- uv run ruff check（Task 4 实现与测试文件）
  Exit 0：All checks passed。
- uv run python -m py_compile app/core/agent/agent_task_runner.py app/services/agent_service.py app/controllers/session.py
  Exit 0。
```

## Task 5：实现前端流式草稿合并与最终替换

状态：completed

### 目标

在会话时间线中平滑显示 Assistant 草稿，正确处理 append/reset/abort/final、SSE 重放与运行状态，并避免草稿拥有仅最终消息允许的操作。

### 涉及文件

- `agentic/web/src/lib/api/types.ts`
- `agentic/web/src/lib/session-events.ts`
- `agentic/web/src/composables/useSessionDetail.ts`
- `agentic/web/src/components/SessionDetailView.vue`
- `agentic/web/src/components/chat/ChatMessage.vue`
- `agentic/web/src/lib/session-events.spec.ts`
- `agentic/web/src/composables/useSessionDetail.spec.ts`
- `agentic/web/src/components/SessionDetailView.spec.ts`
- `agentic/web/src/components/chat/ChatMessage.spec.ts`

### 实施步骤

1. 增加 Delta/Final `stream_id` 类型，并为时间线 Assistant 项增加临时 streaming 状态。
2. append 创建或追加同一草稿，reset 清空草稿，abort 移除草稿，Final 在原位置替换草稿并结束 streaming。
3. 使用 event id 和 sequence 防御 Redis 重放、乱序与重复；Session Snapshot 无 Delta 时仍只渲染 Final。
4. 有可见 Assistant 草稿时隐藏重复的 Thinking Indicator；草稿不允许 branch/copy/source-event 等最终态操作。
5. 覆盖正常流、重试、终止、重连重放、Final-only fallback 和多消息连续运行。

### 验证方式

- `pnpm test:run -- src/lib/session-events.spec.ts src/composables/useSessionDetail.spec.ts src/components/SessionDetailView.spec.ts`
- `pnpm type-check`
- `pnpm build`

### 完成条件

- 用户看到连续更新的一条 Assistant 消息；reset/abort/final 均无重复、残影或错误操作；非流式响应 UI 不回归。

### 执行结果

Web SSE 类型已加入 `message_delta` 与 Final `stream_id`。`eventsToTimeline` 以 `stream_id` 聚合同一条 Assistant 草稿，并用 sequence 忽略重复和倒序 Delta；append/reset/abort 分别原位追加、清空和移除，Final Message 在草稿原位置完成权威替换，Final-only 非流式路径保持兼容。会话组合函数沿现有 event id cursor 接收和重放临时 Delta，Snapshot 对账后只保留持久化 Final。草稿期间隐藏 Thinking Indicator、空回复状态以及复制/分支操作，Final 到达后恢复现有消息能力。

### 验证证据

```text
2026-08-18 12:08 +08:00
- pnpm test:run -- src/lib/session-events.spec.ts src/components/chat/ChatMessage.spec.ts src/components/SessionDetailView.spec.ts src/composables/useSessionDetail.spec.ts
  首次 Exit 1：预期失败，现有前端不识别 message_delta，未隐藏草稿操作与 Thinking Indicator。
  实现后 Exit 0：4 files、39 passed。
- pnpm type-check
  Exit 0。
- pnpm test:run
  Exit 0：43 files、180 passed。
- pnpm build
  Exit 0：vue-tsc 与 Vite production build 均成功。
```

## Task 6：增加 TTFT 数据迁移、API 与 Trace UI

状态：completed

### 目标

记录和展示模型调用首个有效 Token 的延迟，使流式优化可以与总延迟、token 使用量一起评估，同时保持历史记录和非流式调用兼容。

### 涉及文件

- `agentic/api/app/models/run_trace.py`
- `agentic/api/app/services/trace_service.py`
- `agentic/api/alembic/versions/20260818_0001_add_model_call_ttft.py`（新建）
- `agentic/api/tests/app/services/test_trace_service.py`
- `agentic/web/src/lib/api/types.ts`
- `agentic/web/src/components/TracePanel.vue`
- `agentic/web/src/components/TracePanel.spec.ts`（新建或扩展现有测试）

### 实施步骤

1. 为 `model_calls` 增加 nullable `ttft_ms`，新 migration 以当前唯一 head `20260726_0001` 为 down revision。
2. 从 LLM `_trace_metadata` 投影 TTFT 到 ModelCall 与 `model.succeeded` payload；非流式/旧数据保持 null。
3. 在 Trace API schema、Web 类型与 TracePanel 中展示 TTFT，不改变 latency 含义。
4. 验证 migration upgrade/downgrade/upgrade、旧记录读取、流式与非流式 trace。

### 验证方式

- `uv run pytest tests/app/services/test_trace_service.py -q`
- `uv run alembic heads`
- `uv run alembic upgrade head`（仅在隔离测试数据库）
- `uv run alembic downgrade 20260726_0001 && uv run alembic upgrade head`（仅在隔离测试数据库）
- `pnpm test:run -- src/components/TracePanel.spec.ts`
- `pnpm type-check`

### 完成条件

- 新流式调用可查询和显示 TTFT；历史与非流式记录不报错；迁移只有一个 head 且可正反执行。

### 执行结果

`model_calls` 新增 nullable integer `ttft_ms`，迁移从原唯一 head `20260726_0001` 线性升级。TraceService 从 LLM `_trace_metadata` 将流式 TTFT 写入 ModelCall 和 `model.succeeded` payload；非流式调用数据库字段保持 null，事件 payload 不伪造 TTFT。仓储和 Runs API 沿通用列字典自动返回该字段。Web 类型与 TracePanel 分别展示“首 Token”和“总耗时”，历史记录缺少 TTFT 时显示 `-`。

### 验证证据

```text
2026-08-18 12:18 +08:00
- uv run pytest tests/app/services/test_trace_service.py -q
  首次 Exit 1：预期失败，Trace 尚未投影 ttft_ms。
  实现及非流式 null 兼容补测后 Exit 0：6 passed。
- pnpm test:run -- src/components/TracePanel.spec.ts
  首次 Exit 1：预期失败，UI 尚未区分首 Token 与总耗时。
  实现后 Exit 0：2 passed。
- uv run pytest tests/app/core/llm tests/app/core/agent/test_base_agent_streaming.py tests/app/services/test_trace_service.py -q
  Exit 0：25 passed。
- uv run alembic heads
  Exit 0：20260818_0001 (head)，仅一个 head。
- 一次性 PostgreSQL 16 隔离容器迁移往返
  upgrade head：ttft_ms=nullable integer；downgrade 20260726_0001：列数 0；再次 upgrade head：current=20260818_0001 (head)。容器随后停止并自动删除。
- uv run ruff check（Task 6 Backend 实现、迁移与测试）
  Exit 0：All checks passed。
- uv run python -m py_compile app/models/run_trace.py app/services/trace_service.py alembic/versions/20260818_0001_add_model_call_ttft.py
  Exit 0。
- pnpm type-check
  Exit 0。
- pnpm build
  Exit 0：vue-tsc 与 Vite production build 均成功。
```

## Task 7：全量验证、目标模型实测与增量代码审查

状态：completed

### 目标

证明实现满足安全、兼容、时延和体验要求，完成自审与问题修复，形成是否可合并和是否可默认启用的证据。

### 涉及文件

- `agentic/docs/designs/token-delta-streaming.zh-CN.md`
- `agentic/docs/plans/token-delta-streaming-plan.md`
- 本计划全部代码与测试文件

### 实施步骤

1. 运行 Backend LLM/Agent/Event/Service/Endpoint/Trace/Skill 聚焦回归与全量静态检查。
2. 运行 Web 全量单测、类型检查和生产构建。
3. 在隔离数据库验证迁移，并检查 Session Event/Trace 中没有 per-delta 数据。
4. 临时开启 Feature Flag，在当前目标模型执行 Direct、React Tool、Plan、错误重试和非流式 fallback 代表任务；记录首 Delta、Final、模型调用数和 TTFT。
5. 检查 SSE 数据中没有原始 answer JSON、reasoning、tool arguments 或半截 JSON；确认 Direct 仍只有一次模型调用。
6. 按设计和计划做增量代码审查，修复所有 blocking/major 后重新运行受影响与最终验证。
7. 更新设计实现状态、计划证据和默认开关建议；未经用户授权不提交、推送、建 PR 或合并。

### 验证方式

- `uv run pytest tests/app/core/llm tests/app/core/agent tests/app/core/test_interaction_events.py tests/app/core/test_config.py tests/app/services/test_trace_service.py tests/app/services/test_agent_interactions.py tests/app/integration/test_skill_runtime_flow.py -q`
- `uv run ruff check app tests`
- `uv run python -m compileall -q app/core/llm app/core/agent app/core/entities app/core/flows app/schemas app/services`
- `pnpm test:run`
- `pnpm type-check`
- `pnpm build`
- `git diff --check`
- 目标模型 Live Smoke：Direct / React / Plan / retry / fallback，人工核对 SSE 顺序、泄漏和调用数。

### 完成条件

- 自动化验证全部通过；目标模型代表任务达到设计阈值；无未解决 blocking/major；计划状态为 `READY_TO_MERGE` 或明确记录 `BLOCKED/FAILED` 及原因。

### 执行结果

完成全量 Backend/Web/迁移验证，并使用现有 `deepseek-v4-pro` 配置在不替换当前服务的只读源码容器中完成真实 Provider 与 Agent 输出实测。审查发现并修复两项 major：Provider 明确拒绝 streaming 时未回退块调用；Final/abort 后的迟到 Delta 可改写或复活前端终态。补充专用异常、消费前安全降级、流终态封闭和回归测试后复审通过。Feature Flag 继续默认关闭；建议先在 Staging 开启并观测 TTFT、错误率和 Redis/SSE 事件量。

### 验证证据

```text
2026-08-18 12:50 +08:00
- Backend 全量：452 passed（包含新增长文本批处理和两项审查缺陷回归）。
- Web 全量：44 files / 183 passed。
- Ruff：All checks passed；Python compileall Exit 0；git diff --check Exit 0。
- Web：vue-tsc -b Exit 0；Vite production build Exit 0。
- Alembic：20260818_0001 为唯一 head；PostgreSQL 16 upgrade/downgrade/upgrade 往返通过，ttft_ms=integer nullable。
- 真实 Provider：deepseek-v4-pro 返回 32 个流式 chunk，安全投影为 stream-ok，TTFT=932ms，finish_reason=stop。
- 真实 Lead 路由：Direct、React、三阶段 Plan 均为 1 次 stream / 0 次 invoke；Direct 产生 Delta 并带 Final stream_id；React/Plan 决策无错误草稿。
- 真实 Agent 输出：React Goal 8 个 Delta、Plan Step 14 个 Delta；均产生 Final 且 stream_id 一致，Plan Step success=true。
- Retry、流中断、无 stream()、显式 streaming 不兼容和 stream_options 不兼容由确定性回归测试覆盖。
- 自审文档：agentic/docs/reviews/token-delta-streaming-review.md。
```

## 最终验证

### 执行命令

```bash
uv run pytest -q --tb=short --disable-warnings -o log_cli=false
uv run ruff check app tests
uv run python -m compileall -q app
uv run alembic heads
pnpm test:run
pnpm type-check
pnpm build
git diff --check
```

### 执行结果

- 单元与集成测试：隔离 PostgreSQL/Redis 启动并迁移至 head 后，Backend `452 passed`；Web `44 files / 183 passed`。
- 静态检查：Ruff 全量 `All checks passed`；Python compileall Exit 0；`git diff --check` Exit 0。
- 类型检查：`vue-tsc -b` Exit 0。
- 构建：Vite production build Exit 0。
- 数据库迁移：`20260818_0001` 为唯一 head；独立 PostgreSQL 16 已完成 upgrade/downgrade/upgrade 往返并核验 nullable integer 列。
- 真实模型验证：`deepseek-v4-pro` 原生流式、Direct/React/Plan 路由、React Goal 和 Plan Step 均通过；Direct 保持单次模型调用，Agent 可见输出的 Delta/Final 使用相同 `stream_id`。
- 审查修复：Provider streaming 不兼容安全回退、Final/abort 后迟到 Delta 封闭均已补测并通过。
- 部署说明：当前运行中的 `manus-api` 是未挂载工作区的旧镜像，数据库 Alembic revision 为工作区不存在的 `20260728_0001`；为避免覆盖现有文档处理版本，未直接重建该服务。合并不受影响，但重启该实例前必须先把其文档处理版本和迁移链回收到仓库。

### 未通过项目

- 无功能或合并门禁失败项。未对当前 `localhost:8088` 旧镜像做原地升级；这是部署版本漂移的前置治理，不应通过覆盖旧服务绕过。

### 最终状态

READY_TO_MERGE

## 恢复点

- 当前分支：`feature/token-delta-streaming`
- 下一个动作：等待用户决定是否提交/合并；部署前先回收当前运行镜像独有的 `20260728_0001` 文档处理迁移，再在 Staging 开启 `TOKEN_DELTA_STREAMING_ENABLED=true`。
- 继续前检查：`git status --short --branch`；不要直接重建当前 `manus-api`，直到部署迁移链与仓库一致。
