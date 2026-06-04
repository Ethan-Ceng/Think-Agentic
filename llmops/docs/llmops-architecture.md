# LLMOps 平台架构与当前实现

记录日期：2026-06-04。

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
- 后续可扩展 MCP、A2A、Sandbox 等外部执行器。

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

仍需收尾的 v1 产品化事项：

- 固定 PlannerAgent 验收清单。
- 用真实任务记录确认任务页展示完整。
- 增加 WorkerAgent 能力模板。
- 明确能力不足时的用户提示。

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

## 10. 架构规则

后续开发需要保持以下规则：

- PlannerAgent 只做规划、编排、调度和汇总。
- WorkerAgent 只做具体能力执行。
- Worker 不修改全局计划。
- Planner 不直接执行工具或知识库检索。
- 所有 Worker 输出归一化为 `WorkerResult`。
- 所有运行事件归一化为 `TraceEvent`。
- 新的 executor 类型必须隐藏在 WorkerRuntime 后面，不能污染 Planner 协议。
- 前端优先复用 AI 应用、预览调试和任务详情，不提前拆出复杂独立控制台。
