# LLMOps 平台架构与当前实现

记录日期：2026-06-05。

本文是 `llmops` 当前架构和实现边界的最终汇总版，用于替代旧的架构总结、企业平台计划和平台底座待办文档。

## 1. 产品定位

`llmops` 是企业级 Agent 应用平台，核心职责是：

- 管理模型、密钥、文件、知识库、工具、工作流和 AI 应用。
- 提供 AI 应用的创建、调试、发布和渠道调用能力。
- 提供 WorkerAgent 和 PlannerAgent 的运行、编排、追踪和治理底座。
- 把运行过程持久化为任务、计划、步骤、Worker 调用和 Trace，便于审计和排障。

平台边界：

- 控制面：账号、设置、模型、文件、知识库、工具、工作流、AI 应用、发布渠道、任务记录。
- 运行面：模型调用、工具调用、RAG、Workflow、WorkerRuntime、PlannerRuntime、Trace。
- 治理面：权限、敏感配置、审批、审计、回放、评估，部分能力后续继续增强。

## 2. 顶层架构

```text
Vue Console
  -> FastAPI API
      -> App / Workflow / Tool / Dataset / Model / File services
      -> Agent Runtime services
      -> ChatCompletionRuntime
      -> Storage / Vector / Queue / DB

PostgreSQL
  -> app_config / model / dataset / tool / workflow
  -> agent_task / agent_plan / agent_step / worker_call / trace_event

Redis / Celery
  -> 异步任务、文档处理、运行辅助

Weaviate
  -> 知识库向量检索

Object Storage / local storage
  -> 文件资产、artifact、上传内容
```

前端提供 AI 应用、工作流、工具、知识库、模型、文件、任务记录等管理界面。后端以 FastAPI service 层为主，运行时能力按领域模块抽象。

## 3. 核心模块

### 3.1 设置与敏感配置

平台设置通过 `account_settings` 和 `SettingService` 管理。敏感字段加密保存、脱敏展示、运行时解密后注入 Storage、LLM Provider、Tool Runtime 等能力。

### 3.2 模型系统

模型管理支持 provider、模型名称、上下文窗口、价格和参数模板。`ChatCompletionRuntime` 通过 OpenAI-compatible `/chat/completions` 调用模型，并支持常见参数透传。

当前注意事项：

- DeepSeek 系统模型源已按 V4 口径调整为 `deepseek-v4-flash` / `deepseek-v4-pro`。
- 运行时对非法采样参数做防护，避免错误模板影响调试链路。

### 3.3 文件资产

文件资产统一进入 `files` 体系。文件可以作为用户输入传给 Agent Runtime，也可以作为 Worker 产物被登记为 artifact。

运行时约定：

- `input_file_ids` 会校验账号归属。
- 小型文本文件可内联预览到 Worker 上下文。
- Worker 产物统一表示为 `ArtifactRef`。
- Agent 生成的文本产物可登记为 `files.source = agent`。

### 3.4 工具、知识库与工作流

工具包括内置工具和自定义 API 工具。知识库通过文档处理、切分、向量化和召回接入 AI 应用。工作流提供可视化编排和服务端执行模型。

这些能力在 WorkerAgent 中作为可调用 capability 暴露：

- 工具调用。
- API provider 调用。
- Dataset retrieval。
- Workflow 调用。
- A2A 外部 Agent 仍以外部 WorkerAgent 接入，当前暂缓专项实施。
- V5 优先增强 WorkerAgent Runtime：Worker 内部可在自身任务边界内选择 RAG、工具、Workflow、API、MCP 或 sandbox executor。

## 4. AI 应用模型

当前 AI 应用下有两类同级 Agent：

```text
AI 应用
  - WorkerAgent
  - PlannerAgent
```

通过 `agent_type` 区分：

- `worker`：面向具体任务执行，配置模型、提示词、工具、知识库、工作流。
- `planner`：面向任务编排，绑定多个 WorkerAgent，生成计划并调度 Worker 执行。

创建时选择类型。列表和详情页展示类型标签。详情页大部分复用现有 AI 应用配置、预览与调试、发布能力；差异主要在“应用能力”区域。

### 4.1 WorkerAgent

WorkerAgent 是实际执行单元。它不修改全局计划，只接收 `WorkerInvocation` 并返回 `WorkerResult`。

当前 WorkerAgent 主链路：

```text
WorkerRuntime.invoke()
  -> ReActWorkerAgent
  -> AppService.run_app_worker()
  -> ChatCompletionRuntime
  -> tools / dataset / workflow
  -> WorkerResult
```

V5 后 WorkerAgent 的能力边界进一步明确为“局部 ReAct 执行 Agent”：

- WorkerAgent 可以在单个 `WorkerInvocation` 内做局部步骤规划和工具选择。
- WorkerAgent 可以调用自身配置的 RAG、工具、Workflow、API executor；MCP/sandbox 预留 policy 和事件协议，后续独立接入。
- WorkerAgent 可以返回内部工具事件、`confidence`、`retryable`、`replan_signal`、`missing_info`、短期记忆压缩摘要和产物引用。
- WorkerAgent 不调用其他 WorkerAgent，不修改 `RouterPlan`，不绕过 Planner 的绑定和调度关系。
- PlannerAgent 仍只看到 Worker descriptor、routing policy 和 `WorkerResult`，不直接理解 Worker 内部工具协议。

V5 Worker 内部事件建议统一为：

```text
worker.runtime.started
worker.runtime.state_changed
worker.runtime.iteration_started
worker.tool.started
worker.tool.succeeded
worker.tool.failed
worker.memory.compacted
worker.runtime.completed
worker.runtime.failed
worker.runtime.cancelled
```

Worker 是否需要重规划不通过单独事件抢占 Planner 决策，而是写入 `WorkerResult.data.replan_signal` 和终止事件 payload，由 Router/Planner 读取后决定是否重规划。

V5 运行记录的访问面分为两层：

- 后台排障面：`WorkerCall.result_json`、`TraceEvent.payload`、`WorkerResult.data.thoughts`、`events[].payload.raw_event` 和任务页 `Runtime JSON` 只面向登录后的平台后台用户，用于排查 Planner/Worker 调度和 executor 执行问题。
- 发布端调用面：Web App Chat、OpenAPI Chat 和微信等发布渠道不读取 `WorkerCall` / `TraceEvent` / V5 Runtime JSON。它们仍可能返回普通 App 执行链路的 `agent_thoughts`，用于展示“运行流程”，其中可能包含工具输入、工具输出或知识库检索 observation。外部终端用户场景建议通过发布配置控制 `agent_thoughts` 是否展示，默认隐藏运行流程，只展示最终 answer。

Worker 内部状态机建议固定为：

```text
preparing -> reasoning -> tool_calling -> observing -> summarizing -> completed|failed|cancelled
```

### 4.2 PlannerAgent

PlannerAgent 是编排单元。它不直接执行工具，不直接查询知识库，不直接访问外部业务系统。它负责：

- 理解用户目标。
- 基于可用 Worker descriptor 生成 `RouterPlan`。
- 校验和落库计划。
- 顺序调度 Worker。
- 汇总 Worker 结果。
- 在后续版本中支持重规划、等待用户、审批和并行 DAG。

PlannerAgent 绑定 WorkerAgent 的接口为：

```text
/apps/{app_id}/planner/workers
```

PlannerAgent 调试复用统一入口：

```text
/apps/{app_id}/debug-chat
```

后端根据 `agent_type = planner` 将调试请求路由到 Planner 调试链路。对用户来说，不需要理解独立的 Planner debug API。

### 4.3 v2 外部 WorkerAgent 口径

v2 后 WorkerAgent 不只包含本系统 App Worker，也包含可被平台治理和调度的外部 Agent。

A2A 外部 Agent 的架构口径：

- A2A 不进入插件广场混管，也不作为 Planner 直接可见工具。
- A2A Agent 同步为外部 WorkerAgent，仍通过 AI 应用体系展示和管理；产品上可以称为 Planner 添加外部子 Agent，但数据上仍是 PlannerAgent 绑定 WorkerAgent。
- 数据形态使用 `agent_type = worker`、`target_ref_type = a2a_agent`、`target_ref_id = <a2a_agent_id>`。
- 版本配置使用 `worker_config.executor_type = a2a` 保存协议、Agent Card、凭据引用和能力快照；v2.2 主流程只保留字段和展示口径，v2.4 实施 A2A 时必须让 `WorkerRuntime` 同时识别 `executor_type = a2a` 和 `execution_agent_type = a2a_worker`。
- PlannerAgent 通过同一套 `AgentBinding` 绑定本系统 WorkerAgent 和外部 A2A WorkerAgent。
- Planner 只看到 Worker descriptor、routing policy 和 `WorkerResult`，不直接处理 A2A 协议细节。
- WorkerRuntime 根据 `target_ref_type` / `executor_type` 派发到 App executor 或 A2A executor。
- Planner Worker 绑定接口必须支持按 `worker_agent_id` 绑定；`worker_app_id` 只保留为本系统 App Worker 的兼容入口。

能力感知编排的架构口径：

- Worker descriptor 进入版本化 `worker_config.capability_summary`。
- Worker 编排规则进入 `router_config.routing_policy`，不写死在代码和普通提示词里。
- RouterRuntime 在计划落库或 step 执行前做 capability preflight。
- 能力不匹配、模型不支持、远程 Agent 不可用等错误统一归类，并映射为产品化提示。

## 5. Agent Runtime 数据模型

当前运行记录围绕以下对象组织：

- `AgentTask`：一次 Planner/Agent 运行任务。
- `AgentPlan`：任务计划，保存 `RouterPlan`。
- `AgentStep`：计划步骤。
- `WorkerCall`：一次 Worker 调用，保存 `WorkerInvocation` 和 `WorkerResult`。
- `TraceEvent`：运行过程事件。
- `ApprovalRequest`：审批请求，后续阶段加强。

运行协议围绕以下结构展开：

- `WorkerInvocation`：Planner/Router 调用 Worker 的标准输入。
- `WorkerResult`：Worker 的标准输出。
- `AgentEvent`：Worker 内部事件。
- `ArtifactRef`：文件、文本、URL、结构化数据等产物引用。

`WorkerResult` 保留 `answer` 字段兼容旧调用，同时提供结构化字段：

- `actions`
- `evidence`
- `artifacts`
- `events`
- `errors`

## 6. PlannerAgent v1 运行链路

PlannerAgent v1 的闭环如下：

```text
UI 预览与调试
  -> /apps/{app_id}/debug-chat
  -> AppService 判断 agent_type = planner
  -> RouterAgentManagerService.stream_planner_debug_run()
  -> RouterPlannerAgent.create_plan()
  -> RouterPlan
  -> RouterRuntime.validate_plan()
  -> fallback: manager_rule_v1
  -> AgentTask / AgentPlan / AgentStep
  -> WorkerRuntime.invoke()
  -> ReActWorkerAgent
  -> AppService.run_app_worker()
  -> WorkerResult / WorkerCall / TraceEvent
  -> 汇总结果写回聊天消息
```

v1 固定约束：

- 只支持同步顺序执行。
- 不启用动态重规划。
- 不启用并行 DAG。
- 不启用人工审批。
- Planner 输出必须经过 schema 和业务校验。
- Worker 必须是 PlannerAgent 已绑定的 WorkerAgent。
- Planner 失败或输出不可执行时回退到 `manager_rule_v1`。

## 7. 前端架构与体验原则

前端以 Vue 和 Element Plus 为主，AI 应用页面承担 WorkerAgent 和 PlannerAgent 的统一管理。

当前界面原则：

- 不新增孤立的 Planner 专属页面。
- AI 应用列表和详情页显示类型标签。
- 创建 AI 应用时选择 `WorkerAgent` 或 `PlannerAgent`。
- 详情页主体复用 WorkerAgent 既有体验。
- PlannerAgent 在“应用能力”区域管理 WorkerAgent 绑定。
- 调试入口复用“预览与调试”。
- Planner 运行流程可以在聊天消息或任务详情中展开查看。

任务详情应能看到：

- plan。
- step。
- worker call。
- trace。
- fallback 原因。
- artifact。

## 8. 当前实现边界

已经完成的关键边界：

- `WorkerRuntime` 不再是占位实现。
- `ReActWorkerAgent` 通过 `AppService.run_app_worker()` 复用现有 App 执行内核。
- `AppService.debug_chat()` 继续兼容原有 WorkerAgent 调试 SSE。
- `RouterAgentManagerService` 通过 `WorkerRuntime.invoke()` 调 Worker。
- 文件输入和 artifact 已接入 Runtime。
- PlannerAgent v1 基础编排闭环已跑通。
- PlannerAgent 多轮调试已传递 `recent_history` 和 `conversation_id`。
- 2026-06-04 真实联调确认：`GAODE_API_KEY` / `SERPER_API_KEY` 生效后，内置高德天气和 Serper 搜索可由 Worker 能力调用；PlannerAgent 绑定对应 Worker 后，可通过 `/apps/{app_id}/debug-chat` 成功回答广州实时天气问题。
- 2026-06-04 最后调试 session `0e37f677-e29c-4b41-a533-299b4e821035` 抽检确认：10 个 Planner 任务和 11 次 Worker 调用均可关联 plan、step、worker call、trace；多轮短追问、多 step、多 Worker 和 Worker 失败路径已覆盖。v1 基础闭环按大体通过处理。
- 图片上传和图片识别输入链路已通过：图片可进入 task 和 worker invocation，支持视觉能力的 Worker 可正常返回图片内容说明。

仍需收尾的 v1 产品化事项：

- fallback、Worker 产物 artifact、未绑定 Worker、非法 plan、停止调试等边界继续作为非阻塞专项验证。
- 优化“搜索/预警/最新信息”等意图下的 Worker 选择稳定性。
- 增加 WorkerAgent 能力模板。
- 明确能力不足时的用户提示。

已落地的 v2.1 后端边界：

- Worker capability descriptor v2 已定义为 `worker_capability_v2`，并保存到 `agent_versions.worker_config.capability_summary`。
- 内部 WorkerAgent 能力摘要已能从模型 features、工具、知识库、工作流和描述生成，并支持 `manual_overrides`。
- Planner routing policy 已定义为 `routing_policy_v1`，保存到 `agent_versions.router_config.routing_policy`。
- Router capability preflight 已接入 `RouterRuntime`，支持图片输入和搜索/最新信息硬约束。
- Planner worker descriptor 已注入 `capability_summary`，用于能力感知计划生成。
- Planner 调试和 manager run 已在计划落库后、Worker 调用前执行 preflight；失败会写入 plan、step 和 trace，并以结构化错误终止。
- 已新增能力摘要、routing policy 和 preflight 诊断 API。
- 前端已展示 Worker 能力摘要、Planner 绑定 Worker 能力摘要、routing policy JSON 编辑/校验/保存、preflight 诊断和任务页 preflight 结果。

仍未实现但设计已固定的 v2 架构边界：

- 动态重规划 `RouterPlannerAgent.update_plan()` 已落地。
- 任务页已展示重规划原因、新旧计划、attempt、replan trace、Agent 名称、Worker 执行任务、选择理由、Step 输入输出、WorkerCall Invocation/Result 摘要和调度回放。
- Planner dry-run 已落地，可只生成 plan 和 preflight 结果，不创建任务、不调用 Worker，用于排查 Worker 选择。
- PlannerAgent 页面不会直接读取自身 `capability-summary`；Worker 能力摘要只属于 WorkerAgent，Planner 在绑定列表中查看和使用各 Worker 的能力摘要。
- A2A call trace 在 A2A 专项中补充。
- A2A 外部 WorkerAgent 注册、Agent Card 同步、绑定和 text `message/send` executor；该部分设计固定但暂缓实施。

v2 当前代码承载点：

- `agents.target_ref_type` / `agents.target_ref_id` 已能表达 Worker 背后的目标资源。
- `agents.product_category` 可标识 `custom`、`a2a` 等产品来源。
- `agent_versions.worker_config` 已保存内部 Worker 的 `capability_summary`，后续仍可保存 `executor_type` 和 A2A 快照。
- `agent_versions.router_config` 已保存 `routing_policy`。
- `agent_versions.capability_bindings` 可继续保存工具、知识库、workflow 或 A2A skills 摘要。
- `agent_bindings` 继续作为 PlannerAgent 绑定内部 Worker 和外部 A2A Worker 的唯一绑定模型。
- `WorkerRuntime` 当前只实际派发到 App/ReAct Worker，v2.2 先预留 executor 字段和展示口径，v2.4 再增加 A2A executor 分支。
- `RouterRuntime` 已增加 capability preflight；v2.3 已在重规划新计划上再次执行 preflight。
- Planner 绑定、候选 Worker、requested worker、preflight 和任务页已统一到 WorkerAgent id 维度；`worker_app_id` 只作为本系统 App Worker 的兼容绑定入口，读取 App 展示信息时才依赖 `target_ref_type = app`。

v2 实施顺序：

1. v2.1 先实现能力感知地基，不新增 A2A 表：复用 `worker_config.capability_summary`、`router_config.routing_policy`，新增 preflight、错误码和任务页展示。
2. v2.2 已硬化 PlannerAgent + 内部 WorkerAgent 主流程：统一 WorkerAgent id 口径，支持 `worker_agent_id` 绑定，清理 `target_ref_type = app` 隐含限制，并让任务页按 WorkerAgent 展示。
3. v2.3 已实现动态重规划：新增 `RouterPlannerAgent.update_plan()`，只允许改写未执行 step，并对新计划再次执行 preflight。
4. v2.4 后续再实现 A2A 外部 Worker：新增 `a2a_agents` 表，`agents.target_ref_type = a2a_agent` 指向该表，`WorkerRuntime` 增加 text `message/send` executor。

v2.4 A2A 数据和运行时边界：

- `a2a_agents` 保存远程 Agent 注册信息、Agent Card 快照、同步状态和 `auth_ref`，不保存明文凭据。
- 映射出的外部 Worker 使用 `agent_type = worker`、`product_category = a2a`、`target_ref_type = a2a_agent`。
- `agent_versions.worker_config.executor_type = a2a`，并保存 `a2a.card_snapshot` 和 `capability_summary`，保证历史任务回放稳定；可同时写入 `execution_agent_type = a2a_worker` 作为运行时派发兼容字段。
- `WorkerRuntime` 根据 `executor_type` 或 `target_ref_type` 派发到 `A2AWorkerExecutor`；Planner 协议不增加 A2A 专用字段。
- A2A 调用结果必须归一化为 `WorkerResult`，并写入 `WorkerCall` 和 `TraceEvent`。

v2.4 A2A 安全边界：

- 默认只允许 `https://` A2A base URL；本地开发例外必须显式配置。
- 默认禁止内网、环回、链路本地、metadata 地址和保留网段，DNS 解析后必须再次校验最终 IP。
- 禁止自动跟随跨 host 重定向；如允许重定向，重定向后的 host/IP 必须重新校验。
- Agent Card 拉取、message/send 调用必须有超时、最大响应体和协议版本校验。
- A2A 首期不上传本地文件、不转发内部文件 URL、不启用 streaming、push notification 或远程回调。
- A2A 凭据只保存 `auth_ref`，明文继续走平台敏感配置体系。
- 任务页、Trace、WorkerCall 必须脱敏 Authorization、cookie、token、签名参数和敏感 headers。

v2.3 重规划边界：

- 不新增表；每次重规划追加新的 `AgentPlan` 和对应 `AgentStep`，通过 `plan_json.replan` 记录 parent plan、失败 step、原因、attempt、替换 step 和新 preflight。
- 已完成 step 不可改写；新计划只包含后续要执行的 step。
- 每个任务默认最多自动重规划一次，避免无限循环。
- 新计划仍必须经过 `RouterRuntime.validate_plan()`、绑定校验、依赖校验和 capability preflight。
- `TraceEvent` 使用 `planner.replan.*` 记录 requested/generated/validated/applied/fallback/limit_exceeded。
- 任务页按同一 `task_id` 展示原计划、新计划、失败原因、改派 Worker 和最终完成/未完成说明。

## 9. 验证命令

常用后端验证：

```powershell
uv run ruff check app tests
uv run pytest -q
```

常用前端验证：

```powershell
pnpm type-check
pnpm build
```

PlannerAgent v1 最近一次完整验证记录：

- 后端 `ruff` 通过。
- 后端 `pytest -q` 通过，结果为 `141 passed`。
- 前端 `pnpm type-check` 通过。
- API 服务 `/docs` 可访问。
- 前端调试页可通过 `/apps/{app_id}/debug-chat` 运行 PlannerAgent。

2026-06-04 手工联调记录：

- Docker Compose 重新创建 `llmops-api` 和 `llmops-celery` 后启动正常。
- UI `http://localhost:3100` 返回 200。
- API `http://localhost:5011/docs` 返回 200。
- UI 代理 `http://localhost:3100/api/docs` 返回 200。
- 内置工具正常管理器路径调用 `gaode_weather` 成功返回广州天气预报。
- 内置工具正常管理器路径调用 `google_serper` 成功返回搜索结果。
- PlannerAgent 绑定天气/搜索 Worker 后，真实调试问题“今天广州天气怎么样”可成功返回实时天气结果。
- 最后调试 session `0e37f677-e29c-4b41-a533-299b4e821035` 抽检通过：plan、step、worker call、trace、多轮、多 step、多 Worker、Worker error 主链路均有真实落库记录。
- 图片上传和图片识别输入链路已通过；fallback 命中数为 0，WorkerResult artifact 均为空，后两项未作为本轮 v1 主链路阻塞。

## 10. 架构规则

后续开发需要保持以下规则：

- PlannerAgent 只做规划、编排、调度和汇总。
- WorkerAgent 只做具体能力执行。
- Worker 不修改全局计划。
- Planner 不直接执行工具或知识库检索。
- 所有 Worker 输出归一化为 `WorkerResult`。
- 所有运行事件归一化为 `TraceEvent`。
- 新的 executor 类型必须隐藏在 WorkerRuntime 后面，不能污染 Planner 协议。
- A2A 外部 Agent 必须以外部 WorkerAgent 接入，不进入插件广场，也不作为 Planner 直接工具。
- A2A 外部调用必须经过 URL/SSRF 防护、超时、响应体大小限制、凭据脱敏和审计记录。
- Worker 能力摘要必须版本化保存，Planner 计划回放时使用当时的能力快照。
- Worker 编排规则属于 `router_config.routing_policy`，代码负责解析、渲染和执行 preflight。
- 前端优先复用 AI 应用、预览调试和任务详情，不提前拆出复杂独立控制台。
