# Agentic Run / Trace 与工具治理落地调研

整理日期：2026-07-09

本文用于回答一个具体问题：在 `agentic` 已经具备工具管理、API 工具源注册、运行时工具过滤的前提下，是否还需要优先补标准化 Run / Trace / tool_calls / model_calls，以及这部分应该如何落地。

结论：需要优先补，但不要照搬 `llmops` 的重型 App / Worker / CapabilityCall 体系。更合适的第一版是贴合 `agentic` 现有事件流、API 工具源配置方式和 Planner/ReAct 执行链路，先做一个最小可用的运行账本。

## 1. 优先级判断

Run / Trace 建议作为下一阶段 P0，排在重型 Agent Profile、Skill、Knowledge、发布入口之前，至少要先落一个最小闭环。

原因：

- 工具管理已经进入运行时，但目前只能控制“能不能调用”，不能稳定回答“谁在什么时候调用了什么工具、输入输出是什么、失败在哪里”。
- 自定义 API 工具、Shell、Browser、File、A2A 都属于高风险执行能力。没有 tool_calls 审计表，后续 approval、配置变更审计、发布入口都会缺底座。
- `sessions.events` 是 UI/SSE 兼容事件，不适合作为长期可查询、可分析、可关联的 Trace 源。
- `OpenAILLM.invoke()` 当前只返回 `choices[0].message`，token usage、finish_reason、延迟、模型请求快照都没有结构化保存，后续调试模型行为会很困难。
- 相比 Agent Profile / Skill / Knowledge，最小 Run / Trace 对现有产品心智侵入更小，可以直接基于现有事件投影落地。

因此推荐优先顺序调整为：

```text
P0 Run / Trace 最小账本
P1 Agent Profile
P2 Skill / Runbook
P3 Knowledge
P4 发布入口
P5 审批、团队、分析等治理增强
```

这里的 P0 不是做完整 LLMOps 报表，而是先让执行过程可复盘、可审计、可调试。

## 当前落地状态

截至 2026-07-09，Run / Trace 最小闭环已经初步落地：

- 新增迁移：`agentic/api/alembic/versions/20260709_0001_run_trace.py`。
- 新增表：`agent_runs`、`run_steps`、`tool_calls`、`model_calls`、`trace_events`。
- 新增 ORM：`agentic/api/app/models/run_trace.py`。
- 新增 repository：`trace_repository.py`、`db_trace_repository.py`，并接入 `DBUnitOfWork`。
- 新增 `TraceService`，负责事件投影、模型调用记录、查询。
- `AgentTaskRunner` 在每条用户输入开始时创建 run，并在 `_put_and_add_event()` 投影事件。
- `BaseAgent._invoke_llm()` 记录每次模型调用；`OpenAILLM.invoke()` 保留 usage 和 finish_reason 到 `_trace_metadata`。
- 新增查询接口：`/api/runs`。
- 新增前端 API client：`agentic/web/src/lib/api/runs.ts`。
- 新增前端 Trace 面板：`agentic/web/src/components/TracePanel.vue`。
- 会话页头部已提供 Trace 图标入口，可查看 run 列表、timeline、step、tool call、model call。
- 新增单测：`agentic/api/tests/app/services/test_trace_service.py`。

仍未完成：

- 审计保存策略配置。
- 配置变更审计。
- 高风险工具确认与审批记录关联。

## 2. Agentic 当前事实

### 2.1 工具管理已经落地

当前工具治理主线：

```text
Settings Tools tab
  -> /api/tools
  -> ToolConfigService
  -> UserConfigService
  -> configs(config_type = "tool")
  -> ToolRegistry / ToolCapabilityService / ToolPreflightService
  -> ToolFactory
  -> FilteredTool
  -> PlannerReActFlow / ReActAgent
```

关键代码：

- `agentic/api/app/core/entities/tool_config.py`
- `agentic/api/app/schemas/tool_config.py`
- `agentic/api/app/services/tool_config_service.py`
- `agentic/api/app/services/tool_capability_service.py`
- `agentic/api/app/services/tool_preflight_service.py`
- `agentic/api/app/core/tools/registry.py`
- `agentic/api/app/core/tools/factory.py`
- `agentic/api/app/core/tools/filter.py`
- `agentic/api/app/core/tools/api.py`
- `agentic/web/src/components/SettingsModal.vue`

当前 `ToolConfig`：

```text
ToolConfig
  schema_version = "tool_config_v1"
  mode = "default_allow"
  bindings: dict[tool_id, ToolBinding]
  registrations: dict[registration_id, ToolRegistration]
  runtime_policy: RuntimeToolPolicy
```

当前 `ToolBinding`：

```text
enabled
risk_level
params
```

当前 `RuntimeToolPolicy`：

```text
allowed_executor_types = ["builtin", "mcp", "a2a", "api"]
max_tool_iterations
```

当前还没有：

- `approval = none | ask | deny`
- 高风险工具执行前确认
- 工具调用审计表
- 工具配置变更审计表
- 标准化 model_calls

### 2.2 工具注册边界与 llmops 不同

`agentic` 当前没有 `llmops` 式通用 provider/tool 注册中心。内置工具来自代码中的 built-in catalog，用户只能通过 UI/API 调整启停、风险等级和运行时策略。

`agentic` 已落地的是自定义 API 工具源注册：这部分保存在用户级 `configs` JSONB 中，而不是独立 provider/tool 表。

当前注册结构：

```text
ToolRegistration
  registration_id
  provider_id
  provider_label
  source_type = "api"
  executor_type = "api"
  group
  category
  description
  enabled
  builtin
  editable
  requires_sandbox
  requires_browser
  requires_credentials
  config
```

`APITool` 从 `ToolConfig.registrations` 动态解析 OpenAPI schema，生成 LLM 可见 function：

```text
api_<provider>_<operation>
```

当前 `registration_id` 在创建时等于 `provider_id`，但 Trace 设计不应强依赖这个事实。建议在工具描述和调用记录里显式保存 `registration_id`。

### 2.3 当前运行时事件边界

当前执行主线：

```text
AgentService.chat()
  -> AgentTaskRunner
  -> PlannerReActFlow
  -> PlannerAgent
  -> ReActAgent
  -> BaseAgent._invoke_llm()
  -> BaseAgent._invoke_tool()
  -> ToolEvent / StepEvent / PlanEvent / MessageEvent
  -> AgentTaskRunner._put_and_add_event()
  -> sessions.events
```

关键边界：

- `BaseAgent._invoke_llm()` 是 LLM 调用入口。
- `BaseAgent.invoke()` 会根据 LLM tool_calls 生成 `ToolEvent(CALLING)` 和 `ToolEvent(CALLED)`。
- `ReActAgent.execute_step()` 会生成 `StepEvent(STARTED|COMPLETED|FAILED)`。
- `AgentTaskRunner._put_and_add_event()` 是事件写入 Redis output stream 和 `sessions.events` 的统一边界。

这意味着第一版 Trace 可以不重写 Agent 流程，而是在这些边界做投影。

## 3. llmops 可借鉴与不可照搬

### 3.1 可借鉴

`llmops` 中值得借鉴的是运行账本和事件投影思路：

- `AgentTask`
- `AgentPlan`
- `AgentStep`
- `WorkerCall`
- `CapabilityCall`
- `TraceEvent`
- `ApprovalRequest`
- `TraceService.record()`
- `ChatRuntimeEventService`

这些能力能回答：

- 一次任务从何时开始、何时结束、状态是什么。
- 计划、步骤、worker/tool 调用如何关联。
- 每个能力调用的输入、输出、风险、审批和耗时是什么。
- runtime event 如何转换成前端可读 timeline。

### 3.2 不应照搬

不要把 `llmops` 的下列结构直接搬到 `agentic`：

- App / AppVersion / Worker 配置心智。
- 完整 Workspace / Team / RBAC。
- `CapabilityCall` 命名和能力模型。
- provider/tool 独立表作为自定义 API 工具的唯一来源。
- 完整审批流和运营分析。

原因是两者产品模型不同：

```text
llmops = 平台控制面 + App/Worker/Capability 编排
agentic = 自部署执行型 Agent + Planner/ReAct + Sandbox/Browser/Shell/File/MCP/A2A/API
```

`agentic` 的 Trace 应围绕 `run / step / tool_call / model_call / trace_event` 建模，而不是强行引入 Worker/Capability 语义。

## 4. 第一版目标模型

第一版只解决“可复盘”和“可审计”：

```text
agent_runs
run_steps
tool_calls
model_calls
trace_events
```

`artifacts` 可以暂缓。当前已有 `files` 和 `sessions.files`，第一版只需要在 Trace 记录中引用 file id / filepath / URL。

### 4.1 agent_runs

一次用户输入触发的一轮 Agent 执行。

建议字段：

```text
id
trace_id
user_id
session_id
task_id
input_event_id
status                 pending | running | waiting | completed | failed | cancelled
input_summary
final_summary
error
tool_config_snapshot   JSONB, 脱敏后的运行时工具配置摘要
agent_config_snapshot  JSONB, 脱敏后的 Agent 配置摘要
llm_config_snapshot    JSONB, 只保存 provider/base_url/model/temperature/max_tokens，不保存 api_key
started_at
finished_at
created_at
updated_at
```

索引：

```text
user_id, created_at
session_id, created_at
trace_id
task_id
```

### 4.2 run_steps

从 `StepEvent` 投影而来。

建议字段：

```text
id
run_id
session_id
event_id
step_id
step_index
title
description
status                 started | completed | failed
success
result_summary
error
attachments            JSONB
started_at
finished_at
created_at
updated_at
```

注意：

- `StepEvent(STARTED)` upsert step。
- `StepEvent(COMPLETED|FAILED)` 更新 step。
- 如果暂时无法稳定维护 step_index，可以先保存 `step.id` 和事件顺序。

### 4.3 tool_calls

从 `ToolEvent(CALLING|CALLED)` 投影而来。

建议字段：

```text
id
run_id
step_id
session_id
event_id
tool_call_id
tool_id
tool_name
function_name
provider_id
registration_id
source_type
executor_type
risk_level
enabled_effective
requires_sandbox
requires_browser
requires_credentials
status                 calling | called | failed | blocked
arguments              JSONB, 脱敏或可配置保存
arguments_preview
arguments_hash
result                 JSONB, 脱敏或可配置保存
result_preview
success
error
latency_ms
started_at
finished_at
created_at
updated_at
```

工具元数据解析建议：

- 在 `AgentTaskRunner` 保存 `tool_config` 和 `ToolRegistry(tool_config=tool_config)`。
- 对每个 `ToolEvent` 调用 `ToolRegistry.resolve_binding(tool_config, event.tool_name, event.function_name)` 得到 `tool_id`、`risk_level`、`executor_type`、是否启用。
- 对 API 工具，优先通过 `ToolDescriptor.provider_id` 反查 `tool_config.registrations`，记录 `registration_id`。
- 更稳妥的改造是给 `ToolDescriptor` 增加可选 `registration_id` 字段，`ToolRegistry._build_api_descriptors()` 从 `APIToolDefinition.registration_id` 填充。

### 4.4 model_calls

从 LLM 调用入口记录。

建议字段：

```text
id
run_id
step_id
session_id
agent_name             planner | react
provider
base_url
model_name
temperature
max_tokens
tool_schema_count
message_count
tool_choice
response_format
status                 started | succeeded | failed
finish_reason
prompt_tokens
completion_tokens
total_tokens
latency_ms
request_preview        JSONB, 脱敏、截断
response_preview       JSONB, 脱敏、截断
error
started_at
finished_at
created_at
updated_at
```

当前 `OpenAILLM.invoke()` 只返回 message，会丢掉 usage。第一版需要做一个小改造：

- 方案 A：扩展 LLM 返回结构，返回 `LLMResponse(message, usage, finish_reason, raw_metadata)`。
- 方案 B：保持 `invoke()` 返回 message，新增可选 observer/callback，在 `OpenAILLM.invoke()` 内部记录 usage 和 latency。

推荐方案 B 起步，改动面更小；中期再改成结构化 `LLMResponse`。

### 4.5 trace_events

append-only 事件账本，用于保留完整时间线。

建议字段：

```text
id
trace_id
run_id
session_id
event_id
event_type
source                 agentic
payload                JSONB, 脱敏、截断
created_at
```

第一版可直接从 `AgentTaskRunner._put_and_add_event()` 写入。

事件类型建议：

```text
run.started
run.completed
run.failed
plan.created
plan.updated
plan.completed
step.started
step.completed
step.failed
tool.calling
tool.called
message.created
wait.created
error.created
done.created
model.started
model.succeeded
model.failed
```

## 5. 落地点

### 5.1 新增 ORM / migration / repository

建议新增：

```text
agentic/api/app/models/run_trace.py
agentic/api/app/repositories/trace_repository.py
agentic/api/app/repositories/db_trace_repository.py
agentic/api/app/services/trace_service.py
agentic/api/alembic/versions/<revision>_run_trace.py
```

同时扩展：

```text
agentic/api/app/models/__init__.py
agentic/api/app/repositories/uow.py
agentic/api/app/repositories/db_uow.py
```

`TraceService` 只做很薄的投影和 upsert，不要引入复杂状态机。

### 5.2 AgentTaskRunner 创建 run

推荐在 `AgentTaskRunner.invoke()` 中，成功 pop 到用户 `MessageEvent` 后创建 `agent_run`：

```text
MessageEvent(user)
  -> create agent_run
  -> run.status = running
  -> trace_events run.started
  -> _run_flow()
```

这样可以拿到：

- `session_id`
- `user_id`
- `task.id`
- 用户输入 event id
- 用户消息和 attachments
- 当前运行时配置快照

### 5.3 AgentTaskRunner 投影事件

在 `_put_and_add_event()` 保持原有逻辑：

```text
output stream
sessions.events
```

同时追加：

```text
trace_events
run_steps
tool_calls
agent_runs status
```

映射规则：

```text
PlanEvent      -> trace_events
StepEvent      -> run_steps + trace_events
ToolEvent      -> tool_calls + trace_events
MessageEvent   -> trace_events
WaitEvent      -> agent_runs.status = waiting + trace_events
ErrorEvent     -> agent_runs.status = failed + trace_events
DoneEvent      -> agent_runs.status = completed + trace_events
```

### 5.4 model_calls 记录方式

最小侵入路径：

1. 给 `BaseAgent` 增加可选 `trace_context` 或 `model_call_observer`。
2. `_invoke_llm()` 调用前生成 `model_call_id`、开始时间、agent_name、message_count、tool_schema_count。
3. `OpenAILLM.invoke()` 内部保留完整 SDK response metadata，或者通过 observer 返回 usage。
4. 调用结束后写 `model_calls`。
5. 调用异常时写失败记录。

需要注意：

- `BaseAgent._invoke_llm()` 有 retry。每次 retry 应记录一条独立 `model_call`，不要只记录最终成功。
- `message_count` 和 `tool_schema_count` 足够第一版调试，不建议保存完整 prompt，除非用户开启详细审计。
- API key、Authorization header、cookie、上传文件内容必须脱敏。

### 5.5 tool_calls 记录方式

`ToolEvent(CALLING)`：

```text
insert tool_calls
status = calling
started_at = event.created_at
arguments / arguments_preview / arguments_hash
tool metadata snapshot
```

`ToolEvent(CALLED)`：

```text
update tool_calls by run_id + tool_call_id
status = called 或 failed
success = function_result.success
result / result_preview
latency_ms = finished_at - started_at
finished_at = event.created_at
```

如果找不到 CALLING 记录，允许补 insert，避免 Trace 因事件丢失而中断。

## 6. API 与 UI

第一版 API：

```text
GET /api/runs?session_id=&limit=
GET /api/runs/{run_id}
GET /api/runs/{run_id}/events
GET /api/runs/{run_id}/tool-calls
GET /api/runs/{run_id}/model-calls
```

第一版 UI 不需要做复杂分析，只需要在会话侧边或详情页提供：

- Run 列表。
- Timeline。
- Step 展开。
- Tool call 输入输出摘要。
- Model call 摘要、耗时、token。
- 错误定位。

`sessions.events` 继续服务现有聊天 UI，不急于迁移。

## 7. 脱敏与存储策略

默认策略：

- 不保存明文 API key、Authorization、Cookie、token、password、secret。
- `arguments` 和 `result` 默认截断。
- 提供 `preview` 和 `hash`，便于排查和去重。
- 大文件、截图、下载内容只保存文件引用，不把完整内容写进 Trace。
- 自定义 API response body 默认只保存摘要，完整保存应由用户显式开启。

建议新增工具审计配置：

```text
trace_policy
  capture_arguments: preview | full | none
  capture_results: preview | full | none
  max_preview_chars
  redact_sensitive_fields
```

第一版可先写死为 preview 策略。

## 8. 分阶段落地

### P0-A：Schema 与事件投影

- 新增 `agent_runs`、`run_steps`、`tool_calls`、`model_calls`、`trace_events`。
- `AgentTaskRunner` 创建 run。
- `_put_and_add_event()` 投影 Step/Tool/Done/Error/Wait。
- 保持 `sessions.events` 不变。
- 增加 repository/service 单元测试。

状态：已初步完成。

### P0-B：model_calls

- 给 LLM 调用加 observer 或结构化返回。
- 记录 latency、model、token usage、finish_reason、失败重试。
- 记录 `planner` / `react` agent_name。

状态：已初步完成。当前通过 `_trace_metadata` 保存 OpenAI SDK usage 和 finish_reason。

### P0-C：Trace 查询 API

- 新增 run 查询接口。
- 前端先做简单 timeline。
- 支持按 session 查看最近 runs。

状态：已初步完成。当前会话页 Trace 侧边面板支持按 session 查看最近 runs，并展示 timeline、step、tool call、model call。

### P1：工具元数据快照

- `ToolDescriptor` 增加 `registration_id`。
- `tool_calls` 保存 provider、registration、executor、risk、requires_* 快照。
- API 工具调用记录 OpenAPI operation 摘要。

### P2：治理增强

- `approval = none | ask | deny`。
- 高风险工具调用前确认。
- 工具配置变更审计。
- MCP tool 级缓存和细粒度开关。
- 发布入口按 Run/Trace 做审计。

## 9. 风险与注意事项

- 不要把 Trace 写入做成影响主流程的强依赖。写 Trace 失败应记录日志，但不应直接中断用户任务，除非是审计强制模式。
- `AgentTaskRunner` 当前使用多个 `async with self._uow`。Trace 写入应使用短事务，避免长事务包住工具执行或 LLM 调用。
- `DoneEvent` 不一定代表业务成功，需要结合 `ErrorEvent`、step 状态和 final message 判断。
- 当前 `ToolEvent.tool_name` 是工具包名，`function_name` 才是 LLM function。审计必须保存两者，并解析稳定 `tool_id`。
- `model_calls` 不能只在 `OpenAILLM` 外层估算，否则拿不到 usage 和 finish_reason。
- 自定义 API 工具定义来自用户配置，Trace 必须保存调用时快照，避免用户后续修改注册配置后历史记录失真。

## 10. 最小验收标准

第一版完成后，应该能稳定回答：

- 这轮用户输入生成了哪个 `run_id`。
- 这轮执行包含哪些 plan/step。
- 每个 step 下调用了哪些工具。
- 每个工具调用的 `tool_id`、provider、registration、risk、输入摘要、输出摘要、成功失败和耗时是什么。
- 调用了哪些模型、用了哪个 model、耗时多少、token usage 多少。
- 失败发生在 LLM、工具、步骤还是运行器。

达到这个标准后，再继续做 Agent Profile、Skill、Knowledge 和发布入口，后续能力都会更容易调试和治理。
