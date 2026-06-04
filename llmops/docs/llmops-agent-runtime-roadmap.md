# LLMOps Agent Runtime 与 PlannerAgent 路线图

记录日期：2026-06-04。

本文是 Agent Runtime、WorkerAgent、PlannerAgent、agentic 调研结论、Planner v1 落地记录和后续阶段计划的最终汇总版。

## 1. 核心边界

Agent Runtime 的长期目标是把 `llmops` 从“可调试的 AI 应用平台”推进到“可治理的多 Agent 编排平台”。

核心分工：

- PlannerAgent：全局规划者，负责目标理解、任务拆分、Worker 选择、计划校验、调度顺序、汇总答案，后续负责动态重规划。
- WorkerAgent：执行者，负责调用模型、工具、知识库、工作流或外部能力，返回结构化结果。
- RouterRuntime：计划校验和执行策略约束。
- WorkerRuntime：屏蔽底层 executor 差异，统一接收 `WorkerInvocation` 并返回 `WorkerResult`。
- Task/Trace：记录可观测、可审计、可回放的运行过程。

不可打破的规则：

- PlannerAgent 和 WorkerAgent 是 AI 应用下的同级类型。
- PlannerAgent 不直接执行工具、知识库或外部 API。
- WorkerAgent 不修改全局计划。
- PlannerAgent 只能调用已绑定的 WorkerAgent。
- 所有计划必须经过 schema 校验和 `RouterRuntime.validate_plan()`。
- 所有 Worker 输出必须归一化为 `WorkerResult`。
- 所有运行事件必须归一化为 `TraceEvent`。

## 2. 当前产品口径

AI 应用类型：

```text
AI 应用
  - PlannerAgent
  - WorkerAgent
```

`agent_type`：

- `worker`：具体能力执行。
- `planner`：多 Worker 编排。

页面和交互：

- 都在 AI 应用页面管理。
- 创建时选择类型。
- 列表和详情页展示类型标签。
- 详情页主体大部分一致。
- 差异集中在“应用能力”区域。
- PlannerAgent 调试复用“预览与调试”。
- PlannerAgent 调试请求走统一 `/apps/{app_id}/debug-chat`。

这取代了早期文档中“v1 不新增 Planner 类型 / 不新增 UI”的保守假设。

## 3. 运行协议

### 3.1 Planner 输入

Planner 输入由运行时组装，不直接暴露给前端：

```text
PlannerInput
  - user_message
  - recent_history
  - conversation_id
  - available_workers
  - constraints
  - files
  - context
```

`recent_history` 用于多轮短追问，例如用户先问“今天天气如何”，再输入“广州”。Planner 应理解第二轮是在补充地点。

### 3.2 RouterPlan

Planner 输出 `RouterPlan`：

```text
RouterPlan
  - schema_version = router_plan_v1
  - execution_mode = sync
  - objective
  - steps
  - risk_assessment
```

v1 校验规则：

- `schema_version` 必须是 `router_plan_v1`。
- step id 不能重复。
- step 只能调用已绑定 Worker。
- dependencies 必须存在。
- v1 只允许 `execution_mode = sync`。
- v1 不允许 `required_approval = true`。
- `risk_assessment.source` 标识 `llm_planner_v1` 或 `manager_rule_v1`。

### 3.3 WorkerInvocation

`WorkerInvocation` 是 Planner/Router 调用 Worker 的标准输入：

```text
WorkerInvocation
  - schema_version = worker_invocation_v1
  - task_id
  - step_id
  - worker_id
  - instruction
  - input
  - context
  - target_ref_type
  - target_ref_id
```

上下文可包含：

- conversation_id。
- recent_history。
- input_files。
- artifacts。
- previous_step_results。

### 3.4 WorkerResult

`WorkerResult` 是 Worker 的标准输出：

```text
WorkerResult
  - schema_version = worker_result_v1
  - status
  - answer
  - actions
  - evidence
  - artifacts
  - events
  - errors
```

`answer` 用于兼容旧链路和聊天消息展示。结构化字段用于任务详情、trace、后续重规划和评估。

### 3.5 TraceEvent

TraceEvent 用于记录关键运行事件。建议命名空间：

- `planner.*`
- `router.*`
- `worker.*`
- `worker.event.*`
- `tool.*`
- `artifact.*`
- `wait.*`
- `approval.*`
- `task.*`
- `error.*`

v1 至少需要记录：

- Planner 开始。
- Planner 输出。
- Plan 校验成功或失败。
- fallback 原因。
- Worker 调用开始和结束。
- Worker 内部事件摘要。
- 最终汇总结果。

## 4. WorkerAgent 当前实现

WorkerAgent 已完成 Runtime 主链路：

```text
WorkerRuntime.invoke()
  -> ReActWorkerAgent
  -> AppService.run_app_worker()
  -> ChatCompletionRuntime
  -> tool / dataset / workflow
  -> WorkerResult
```

关键事实：

- `WorkerRuntime` 不再是 placeholder。
- `ReActWorkerAgent` 是 WorkerAgent 的执行引擎，不作为第三类产品类型暴露。
- `AppService.debug_chat()` 继续兼容原有 WorkerAgent 流式调试。
- `AppService.run_app_worker()` 是 WorkerRuntime 复用 App 执行能力的内核入口。
- `WorkerCall.invocation_json` 保存标准 `WorkerInvocation`。
- `WorkerCall.result_json` 保存标准 `WorkerResult`。
- 文件输入和 artifact 传播已经接入后端 Runtime。

WorkerAgent 后续重点不是重写主链路，而是补能力模板和 executor 类型。

## 5. PlannerAgent v1 当前状态

v1 目标：作为 AI 应用类型跑通“单轮计划 + 顺序执行 + 可观测 + 可回退”的基础编排闭环。

当前状态：

- PlannerAgent / WorkerAgent 已作为同级 AI 应用类型管理。
- PlannerAgent 能绑定 WorkerAgent，并维护绑定优先级和启停状态。
- PlannerAgent 调试复用 `/apps/{app_id}/debug-chat`。
- 后端按 `agent_type = planner` 路由到 Planner 调试链路。
- Planner 使用 `RouterPlannerAgent.create_plan()` 输出 `RouterPlan`。
- Planner 输出经过 Pydantic 和 `RouterRuntime.validate_plan()` 校验。
- Planner 失败、输出非法、使用未绑定 Worker、输出 async 或 approval 时，回退到 `manager_rule_v1`。
- Worker 执行继续走 `WorkerRuntime -> ReActWorkerAgent -> AppService.run_app_worker()`。
- Planner 调试运行过程可在聊天消息中展示，并可停止。
- Planner 多轮调试已接入 `recent_history` 和 `conversation_id`。
- 任务记录已经能关联 `AgentTask / AgentPlan / AgentStep / WorkerCall / TraceEvent`。
- 2026-06-04 真实联调确认：天气/搜索工具凭据配置后，PlannerAgent 可编排绑定 Worker 成功回答广州实时天气问题；此前失败属于 Worker 工具凭据未配置。
- 2026-06-04 对最后调试 session `0e37f677-e29c-4b41-a533-299b4e821035` 抽检确认：10 个任务均落库并关联 plan、step、worker call、trace；多轮短追问、多 step、多 Worker 调度和 Worker 失败路径均已覆盖。v1 基础编排闭环按大体通过处理。

当前主链路：

```text
UI 预览与调试
  -> /apps/{app_id}/debug-chat
  -> AppService._debug_planner_chat()
  -> RouterAgentManagerService.stream_planner_debug_run()
  -> RouterPlannerAgent.create_plan()
  -> RouterPlan
  -> RouterRuntime.validate_plan()
  -> fallback: manager_rule_v1
  -> AgentTask / AgentPlan / AgentStep
  -> WorkerRuntime.invoke()
  -> WorkerResult
  -> 聊天消息展示最终结果
```

注意：如果 WorkerAgent 没有实时天气、搜索或外部 API 能力，PlannerAgent 即使理解上下文，也不能凭空提供实时数据。这是 Worker 能力配置问题，不是 Planner 编排主链路问题。

## 6. v1 验收清单

v1 收尾应以验收和产品化为主，不再大改主链路。

已验证：

- 创建 PlannerAgent 并绑定 WorkerAgent。
- 创建 WorkerAgent，并确认 WorkerAgent 原调试流在同一套最新服务中正常回复。
- PlannerAgent 通过“预览与调试”提交问题。
- PlannerAgent 调试请求使用 `/apps/{app_id}/debug-chat`。
- 天气/搜索工具凭据配置后，PlannerAgent 可调度绑定 Worker 返回广州实时天气结果。
- API/UI 服务启动和访问正常，内置高德天气、Serper 搜索工具调用正常。
- 多轮短追问能继承上下文。
- 多 Worker 场景下能调度不同 Worker，并出现过两步任务。
- Worker 执行失败路径已覆盖，图片输入选择不支持视觉能力模型时会落 `worker.call.failed` 和 `worker.event.error`。
- 图片上传和图片识别输入链路已覆盖，图片可通过 `image_urls` 进入 task 和 worker invocation，支持视觉能力的 Worker 可正常返回图片内容说明。
- 任务记录主链路已覆盖 plan、step、worker call 和 trace。

非阻塞待补测：

- AI 应用列表和详情页展示类型标签。
- Planner 输出非法时 fallback 到 `manager_rule_v1`。
- Planner 试图调用未绑定 Worker 时 fallback 或拒绝。
- v1 出现 async / approval plan 时被校验拒绝。
- 停止调试可终止前端等待状态。
- 任务页展示 fallback 原因和 Worker 产物 artifact。
- capability_calls 表级记录本轮未覆盖；当前只在 `WorkerResult.used_capabilities` 中看到工具能力使用。

已知观察项：

- 明确包含“搜索一下”的天气预警问题被拆成 `天气查询 -> 通用问答`，没有直接选择搜索 Worker；后续可通过优化 Worker 描述和 Planner prompt 提升路由稳定性。
- 图片输入已通过 `image_urls` 传入 task 和 worker invocation；`input_file_ids`、`input_files` 和 Worker 产物 artifact 仍为空，后续只需在文件 ID 输入和 Worker 产物生成场景中专项验证。

建议补充的 WorkerAgent 模板：

- 实时天气 Worker。
- 搜索 Worker。
- 通用问答 Worker。
- 数据分析 Worker。
- 文档总结 Worker。

用户提示口径：

- Planner 编排成功但 Worker 能力不足时，应提示“当前绑定 Worker 不具备该实时能力”，并建议绑定对应能力 Worker。
- 不应把这类问题描述为 Planner 上下文错误。

## 7. v2 定稿：能力感知编排、A2A 外部 Worker 与动态重规划

v2 目标：让 PlannerAgent 从“一次性任务拆分器”升级为“能力感知、可接入外部 Agent、可根据执行结果调整计划的编排 Agent”。

v2 不重做 AI 应用体系，不新增独立 Planner 控制台，不把 A2A/MCP 暴露为 Planner 内部协议。Planner 仍只面向 Worker descriptor、routing policy 和 `WorkerResult`；WorkerRuntime 负责隐藏本系统 Worker、A2A Agent 和后续 executor 的差异。

### 7.1 市场和产品调研结论

调研对象包括 LangChain/LangGraph、OpenAI Agents SDK、AutoGen、CrewAI、Dify、A2A Protocol 和本地 `agentic`。

- 市场主流多 Agent 形态不是“一个大 Agent 包办所有工具”，而是 supervisor/manager 协调多个专业 Agent。LangChain 和 OpenAI Agents SDK 都把 manager/agents-as-tools 作为常见模式，强调专业 Agent 的描述和职责边界。
- 生产化编排需要状态持久化、可恢复和可观察。LangGraph 强调 checkpoint、thread、fault tolerance、human-in-the-loop；Dify 把 Workflow/Chatflow 定位为带条件、检查点和 fallback 的可控流程。
- CrewAI 和 AutoGen 都保留“团队/crew/team”概念，但真实平台化落地需要把执行过程、状态、终止条件、重试和日志结构化，而不是只依赖 prompt。
- A2A Protocol 的 Agent Card 是外部 Agent 的能力发现入口，包含 `defaultInputModes`、`defaultOutputModes`、`skills`、`capabilities`、认证和协议操作。A2A 还定义了 capability validation、`message/send`、`message/stream`、任务状态、artifact、文件交换和多轮输入。
- `agentic` 当前把 A2A 实现为 ReAct Agent 的工具：通过 `get_remote_agent_cards` 获取 card，再用 `call_remote_agent` 调远程 Agent。这适合单 Agent 自主执行，但不适合 `llmops` 的平台治理目标。`llmops` 应把外部 A2A Agent 同步为外部 WorkerAgent，让 Planner 通过统一绑定体系调度。

参考资料：

- LangChain supervisor/subagents: https://docs.langchain.com/oss/python/langchain/supervisor
- LangGraph persistence / checkpoint: https://docs.langchain.com/oss/python/langgraph/persistence
- OpenAI Agents SDK multi-agent patterns: https://openai.github.io/openai-agents-python/agents/
- AutoGen Teams: https://microsoft.github.io/autogen/stable/user-guide/agentchat-user-guide/tutorial/teams.html
- CrewAI Crews / Flows: https://docs.crewai.com/en/concepts/crews
- Dify Agent / Workflow / Tools: https://docs.dify.ai/en/use-dify/build/agent
- A2A Protocol specification: https://a2a-protocol.org/dev/specification/

### 7.2 v2 范围

v2 必须包含：

- Worker capability descriptor v2。
- Planner routing policy 配置。
- Router capability preflight。
- 结构化错误 taxonomy 和用户提示映射。
- A2A Agent 注册、同步和绑定为外部 WorkerAgent。
- A2A WorkerRuntime executor，第一阶段只要求 text `message/send`。
- `RouterPlannerAgent.update_plan()` 动态重规划。
- 任务页展示原计划、重规划原因、新计划、改派记录和外部 Agent 调用 trace。

v2 不包含：

- 并行 DAG。
- 人工审批。
- sandbox 代码执行和完整产物链路。
- MCP/sandbox/api 全量 executor 生态。
- 复杂可视化 routing policy 编辑器。

### 7.3 Worker Capability Descriptor v2

Worker descriptor 不再只描述本系统 App Worker，而是描述一个可调度执行单元。A2A Agent Card、内部 Worker 配置、Workflow、MCP、Sandbox 后续都映射到同一结构。

```json
{
  "schema_version": "worker_capability_v2",
  "executor_type": "app|a2a|workflow|mcp|sandbox|api",
  "input_modalities": ["text/plain", "image/png", "application/pdf"],
  "output_modalities": ["text/plain", "application/json"],
  "semantic_tags": ["search", "weather", "vision", "document_qa"],
  "skills": [
    {
      "id": "weather_alert",
      "name": "Weather Alert",
      "description": "Query weather forecasts and active alerts",
      "tags": ["weather", "forecast", "alert"],
      "input_modes": ["text/plain"],
      "output_modes": ["text/plain"]
    }
  ],
  "tool_names": ["gaode_weather", "google_serper"],
  "model_features": ["tool_call", "image_input"],
  "constraints": {
    "requires_credentials": true,
    "requires_approval": false,
    "max_timeout_seconds": 120
  },
  "protocol": {
    "type": "a2a",
    "version": "0.3|1.0",
    "streaming": false,
    "push_notifications": false
  }
}
```

映射规则：

- 内部 WorkerAgent：从模型 features、工具、知识库、工作流、应用描述和用户维护的能力标签生成。
- A2A Agent：从 Agent Card 的 `defaultInputModes`、`defaultOutputModes`、`skills`、`capabilities`、`security` 映射。
- `semantic_tags` 是平台路由标签，可由系统推断，也允许用户修正。
- `tool_names` 是内部可观测字段，不作为 Planner 选择的唯一依据。
- descriptor 必须进入 `AgentVersion.worker_config.capability_summary` 或同等版本化字段，保证计划回放时能力快照稳定。

### 7.4 A2A 外部 WorkerAgent

A2A 不作为“插件”混入插件广场，也不作为 Planner 直接可见工具。A2A Agent 是外部 WorkerAgent。

目标数据形态：

- `agents.runtime_type = "worker"`。
- `agents.product_category = "a2a"`。
- `agents.target_ref_type = "a2a_agent"`。
- `agents.target_ref_id = <a2a_agent_id>`。
- `agent_versions.worker_config.executor_type = "a2a"`。
- `agent_versions.worker_config.a2a` 保存 base_url、card_url、protocol_version、auth_ref、capabilities 快照和最近同步时间。
- `agent_versions.capability_bindings` 或 `worker_config.capability_summary.skills` 保存 Agent Card skills。

产品入口：

- 在 PlannerAgent 的“应用能力 / Worker 编排”中，除了绑定本系统 WorkerAgent，还能添加外部 A2A Agent。
- 添加 A2A Agent 时输入 base URL，系统拉取 `/.well-known/agent-card.json` 或协议版本对应的 Agent Card。
- UI 展示 Agent 名称、描述、输入输出模式、skills、streaming、认证需求、最近同步状态、启停状态。
- 用户可手工补充或修正 `semantic_tags`、优先级和适用条件。
- 外部 A2A Agent 进入同一个 `agent_bindings` 绑定表，不新增独立绑定模型。

调用边界：

- v2 第一阶段只支持 text `message/send` 或等价 JSON-RPC/REST send message。
- v2 可以保存远程 task id 和 context id，但不要求完整 push notification。
- streaming、文件 parts、artifact parts、多轮 input-required 进入 v2 后半或 v3/v5。
- A2A 返回必须归一化为 `WorkerResult`，远程 Agent 的 task/status/artifact/message 作为 `data/evidence/artifacts/events` 保存。

### 7.5 Routing Policy

编排规则不写死在代码里，也不混入普通提示词。PlannerAgent 增加单独的 `router_config.routing_policy`。

```json
{
  "schema_version": "routing_policy_v1",
  "rules": [
    {
      "id": "image_requires_vision",
      "when": {"input_modality_any": ["image/png", "image/jpeg"]},
      "require": {"input_modality_any": ["image/png", "image/jpeg"]},
      "on_missing": "capability_missing:image_input"
    },
    {
      "id": "latest_info_requires_search",
      "when": {"intent_keywords_any": ["搜索", "最新", "预警", "网页", "来源"]},
      "require": {"semantic_tags_any": ["search"]},
      "on_missing": "capability_missing:search"
    }
  ],
  "fallback_policy": {
    "on_planner_invalid": "manager_rule_v1",
    "on_preflight_failed": "structured_error",
    "on_worker_failed": "replan_once"
  }
}
```

使用方式：

- 代码只负责解析 routing policy、渲染给 Planner prompt、执行硬性 preflight。
- 用户可以在 PlannerAgent 详情中编辑“Worker 编排规则”，但 v2 第一阶段可先用 JSON/表单混合的简版配置。
- prompt 只描述策略，不承担安全兜底。

### 7.6 Capability Preflight 与错误 taxonomy

Router 在计划落库或 step 执行前做 capability preflight。preflight 是确定性代码逻辑，不依赖模型。

基础错误码：

| error_code | 场景 |
| --- | --- |
| `capability_missing:image_input` | 用户输入包含图片，但计划 Worker 不支持图片输入 |
| `capability_missing:file_input` | 用户输入包含文件，但 Worker 不支持文件输入 |
| `capability_missing:search` | routing policy 要求搜索能力，但计划 Worker 不具备搜索标签 |
| `worker_model_unsupported:image_input` | Worker 声称支持图片，但实际模型 features 不支持 |
| `worker_unavailable` | Worker 禁用、下线或 A2A card 同步失败 |
| `external_agent_auth_required` | A2A 远程 Agent 需要认证但未配置凭据 |
| `external_agent_protocol_error` | A2A 协议调用失败或版本不兼容 |

trace 事件：

- `router.capability_preflight.started`
- `router.capability_preflight.succeeded`
- `router.capability_preflight.failed`
- `worker.external.a2a.card.synced`
- `worker.external.a2a.call.started`
- `worker.external.a2a.call.succeeded`
- `worker.external.a2a.call.failed`

用户提示通过错误码映射，不直接展示底层英文异常。提示语言由用户消息语言、账号语言或前端 i18n 决定。

### 7.7 动态重规划

重规划只允许修改未执行 step，不允许改写已完成 step。

触发条件：

- capability preflight 失败且存在可替代 Worker。
- Worker 返回 `failed` 且 `retryable=true`。
- Worker 返回结构化 `errors`，例如 `capability_missing:*`、`external_agent_protocol_error`。
- Worker 输出不完整，缺少后续 step 必需 artifact 或 evidence。

重规划输入：

```json
{
  "original_plan": {},
  "completed_steps": [],
  "failed_step": {},
  "worker_result": {},
  "error": {
    "error_code": "capability_missing:image_input",
    "message": "..."
  },
  "available_workers": [],
  "routing_policy": {},
  "trace_summary": []
}
```

重规划输出仍是 `RouterPlan`，但只包含后续未执行步骤。RouterRuntime 必须再次校验：

- worker 必须已绑定。
- dependencies 不能引用不存在 step。
- 不能修改已完成 step。
- step 数不能超过限制。
- 不能绕过 preflight。

重规划失败时：

- 记录 `planner.replan.fallback`。
- 如果已有可用结果，汇总已有结果并说明未完成部分。
- 如果没有可用结果，返回结构化能力不足提示。

### 7.8 任务页和产品体验

任务页需要让用户看清：

- 原计划。
- 每个 step 的 Worker 类型：本系统 Worker / A2A 外部 Agent。
- Worker capability snapshot。
- preflight 结果。
- Worker call / A2A call trace。
- 失败原因和错误码。
- 重规划原因。
- 新计划和改派到的 Worker。
- 最终汇总和未完成说明。

PlannerAgent 详情页需要新增或调整：

- Worker 绑定列表支持内部 Worker 和 A2A 外部 Worker。
- A2A Agent 添加、同步、启停、凭据引用、skills 预览。
- Worker 编排规则 `routing_policy`。
- Worker 能力摘要预览和人工修正入口。
- 失败提示模板或 i18n key 预览。

### 7.9 v2 交付拆分

v2.1：能力感知地基

- `capability_summary` 数据结构。
- 内部 Worker capability 映射。
- routing policy 配置。
- preflight 和错误 taxonomy。
- 任务页展示 preflight 和错误提示。

v2.2：A2A 外部 Worker

- A2A Agent 注册和 Agent Card 同步。
- 外部 A2A Agent 映射为 WorkerAgent。
- Planner 绑定 A2A Worker。
- A2A text `message/send` executor。
- A2A 调用 trace 和 `WorkerResult` 归一化。

v2.3：动态重规划

- `RouterPlannerAgent.update_plan()`。
- WorkerResult/error/trace 摘要进入重规划。
- 改派备用 Worker。
- 任务页展示原计划、新计划和重规划原因。

v2 验收通过标准：

- 同一个 Planner 可同时绑定本系统 Worker 和 A2A 外部 Worker。
- Planner 能基于 descriptor 和 routing policy 选择合适 Worker。
- 图片/文件/搜索等基础能力不匹配时 preflight 能阻断并给出结构化提示。
- A2A text Agent 可被 Planner 调用，结果进入 `WorkerResult`、`WorkerCall`、`TraceEvent`。
- Worker 失败后可重规划到另一个绑定 Worker，或给出明确不可完成原因。

### 7.10 v2 实施设计和下一步任务

当前代码承载情况：

- `agents.target_ref_type` / `agents.target_ref_id` 已能表达 Worker 背后的目标资源。
- `agents.product_category` 可用于区分 `custom`、`a2a` 等产品来源。
- `agent_versions.worker_config`、`router_config`、`capability_bindings` 已是 JSONB；当前已承载内部 Worker 能力摘要和 Planner 编排规则，后续继续承载 A2A 快照。
- `agent_bindings` 已能表达 PlannerAgent 到 WorkerAgent 的绑定关系，A2A 外部 Worker 不需要单独绑定表。
- `WorkerRuntime` 当前只派发到 `ReActWorkerAgent`，`ReActWorkerAgent` 当前只支持 `target_ref_type = app`。v2.2 需要新增 A2A executor 分支。
- `RouterRuntime.validate_plan()` 负责计划结构、绑定和依赖校验；`RouterRuntime.preflight_plan()` 已负责能力硬约束校验。

v2.1 能力感知地基已落地。下一步按 v2.2 A2A 外部 Worker、v2.3 动态重规划推进，完成后 V2 功能闭环关闭。

#### 7.10.1 v2.1 能力感知地基

2026-06-04 落地状态：

- v2.1-1 到 v2.1-4 主链路已完成。
- 已新增 `worker_capability_v2`、`routing_policy_v1`、错误码和中文用户提示映射。
- 内部 WorkerAgent 同步 AgentVersion 时会生成 `worker_config.capability_summary`，并保留人工 `manual_overrides`。
- Planner worker descriptor 已注入 `capability_summary`。
- `RouterRuntime.preflight_plan()` 已支持图片输入和搜索/最新信息硬约束。
- Planner 调试和 manager run 已接入 preflight；失败会写入 `AgentPlan.plan_json.preflight`、`AgentStep.input_json.preflight` 和 `TraceEvent`，并阻止 Worker 调用。
- 已新增 `/apps/{app_id}/capability-summary`、`/agents/{agent_id}/capability-summary`、`/apps/{planner_app_id}/planner/routing-policy` 和 `/apps/{planner_app_id}/planner/preflight` 后端接口。
- 前端已接入 Worker 能力摘要展示、Planner 绑定 Worker 能力摘要、routing policy JSON 编辑/校验/保存、preflight 诊断和任务页 preflight 展示。
- 自动化验证通过：`uv run ruff check app tests`、`uv run pytest -q`、`pnpm type-check`、`pnpm build`，后端测试结果为 `146 passed`。

非阻塞待补记录：

- v2.1-5 已完成功能验收和自动化回归；后续 V2 回归时补充真实 Planner/Worker session/task id，作为正式交付记录。

数据设计：

- 暂不新增业务表，优先复用 `agent_versions.worker_config` 和 `agent_versions.router_config`。
- Worker 能力摘要保存到 `agent_versions.worker_config.capability_summary`。
- Planner 编排规则保存到 `agent_versions.router_config.routing_policy`。
- 已落库的 `WorkerCall.invocation_json` 和 `WorkerCall.result_json` 保留当次调用的能力快照、preflight 结果和错误码，保证任务回放稳定。

`capability_summary` 最小结构：

```json
{
  "schema_version": "worker_capability_v2",
  "generated_from": "internal_worker",
  "executor_type": "app",
  "input_modalities": ["text/plain"],
  "output_modalities": ["text/plain"],
  "semantic_tags": ["weather", "search", "vision", "document_qa"],
  "skills": [],
  "tool_names": ["gaode_weather", "google_serper"],
  "model_features": ["tool_call", "image_input"],
  "constraints": {
    "requires_credentials": false,
    "requires_approval": false,
    "max_timeout_seconds": 120
  },
  "manual_overrides": {
    "semantic_tags": [],
    "input_modalities": []
  },
  "updated_at": "2026-06-04T00:00:00Z"
}
```

内部 Worker 映射规则：

- 模型支持图片输入时加入 `image/*` 或具体图片 MIME，并写入 `model_features = ["image_input"]`。
- 绑定高德天气工具时加入 `semantic_tags = ["weather"]` 和对应 `tool_names`。
- 绑定 Serper/搜索工具时加入 `semantic_tags = ["search"]`。
- 绑定知识库时加入 `semantic_tags = ["document_qa"]` 或 `["knowledge_retrieval"]`。
- 绑定工作流时记录 workflow 名称和 `semantic_tags`，但不直接让 Planner 调 workflow。
- 用户手动修正的标签放入 `manual_overrides`，系统重新生成能力摘要时必须保留。

`routing_policy` 最小结构：

```json
{
  "schema_version": "routing_policy_v1",
  "rules": [
    {
      "id": "image_requires_vision",
      "when": {"input_modality_any": ["image/png", "image/jpeg", "image/webp"]},
      "require": {"input_modality_any": ["image/png", "image/jpeg", "image/webp"]},
      "on_missing": "capability_missing:image_input"
    },
    {
      "id": "latest_info_requires_search",
      "when": {"intent_keywords_any": ["搜索", "最新", "预警", "网页", "来源"]},
      "require": {"semantic_tags_any": ["search"]},
      "on_missing": "capability_missing:search"
    }
  ],
  "fallback_policy": {
    "on_planner_invalid": "manager_rule_v1",
    "on_preflight_failed": "structured_error",
    "on_worker_failed": "replan_once"
  }
}
```

后端任务：

- 新增能力摘要构建服务，负责从 AgentVersion 的模型、工具、知识库、工作流和描述生成 `capability_summary`。
- Planner 可用 Worker descriptor 中加入 `capability_summary`，供 `RouterPlannerAgent.create_plan()` 使用。
- `RouterRuntime` 增加 `preflight_plan()` 或等价能力校验入口，在计划落库前和 step 执行前校验 Worker 是否满足输入模态、搜索等硬约束。
- 结构化错误统一使用 `error_code`，并写入 `WorkerResult.errors`、`TraceEvent` 和任务页数据。
- 新增用户提示映射层，把底层错误码转换为中文产品提示，不直接暴露英文异常。

前端任务：

- PlannerAgent 的 Worker 绑定列表展示能力摘要：输入类型、关键标签、工具名、模型能力。
- WorkerAgent 详情增加能力摘要预览和手工修正入口。
- PlannerAgent 详情增加“Worker 编排规则”入口；v2.1 可先使用 JSON 编辑器加 schema 校验。
- 任务页展示 preflight 结果、失败 Worker、错误码和用户可理解的失败原因。

v2.1 验收用例：

- 图片输入被 Planner 分配给不支持图片的 Worker 时，preflight 阻断并返回 `capability_missing:image_input`。
- 明确要求搜索/最新信息但绑定 Worker 不具备 `search` 标签时，preflight 或计划校验返回 `capability_missing:search`。
- 支持图片的 Worker 被正确识别为可处理图片输入。
- 绑定高德天气、Serper 搜索工具的 Worker 能生成正确 `semantic_tags` 和 `tool_names`。
- 用户手动补充的 `semantic_tags` 在重新生成能力摘要后不丢失。
- 任务页能看到 preflight 成功或失败记录。
- 现有 v1 Planner 调试和 Worker 调试链路不回退。

#### 7.10.2 v2.2 A2A 外部 Worker

目标：

- 把一个远程 A2A Agent 注册成平台内的外部 WorkerAgent。
- PlannerAgent 仍只绑定和调用 WorkerAgent，不直接感知 A2A 协议。
- WorkerRuntime 负责把 `WorkerInvocation` 转成 A2A text `message/send`，并把远程响应归一化为 `WorkerResult`。
- Agent Card 和能力摘要必须版本化保存，历史任务回放不受远程 Agent Card 后续变化影响。

非目标：

- 不把 A2A Agent 放入插件广场。
- 不把 A2A Agent 暴露成 Planner prompt 里的普通工具。
- 不支持文件上传、图片二进制转发、streaming、push notification、远程回调或长轮询任务。
- 不实现完整 A2A artifact 生态；v2.2 只保存远程 artifact 摘要和文本结果。

数据设计：

```text
a2a_agents
  id uuid pk
  tenant_id uuid
  created_by uuid nullable
  name varchar
  description text
  base_url varchar
  agent_card_url varchar
  provider_name varchar
  provider_url varchar
  protocol_version varchar
  card_version varchar
  card_snapshot jsonb
  auth_type varchar              # none | bearer | api_key | custom
  auth_ref varchar               # 敏感配置引用，不存明文
  status varchar                 # active | disabled | sync_failed | deleted
  sync_status varchar            # never | succeeded | failed
  last_sync_error text
  last_synced_at timestamp
  metadata jsonb
  created_at / updated_at
```

索引：

- `ix_a2a_agents_tenant_status`：`tenant_id, status`。
- `ix_a2a_agents_tenant_base_url`：`tenant_id, base_url`，同租户内避免重复注册。

外部 WorkerAgent 映射：

- `agents.runtime_type = "worker"`。
- `agents.product_category = "a2a"`。
- `agents.target_ref_type = "a2a_agent"`。
- `agents.target_ref_id = str(a2a_agents.id)`。
- `agent_versions.worker_config.executor_type = "a2a"`。
- `agent_versions.worker_config.a2a.card_snapshot` 保存发布或草稿当时使用的 Agent Card 快照。
- `agent_versions.worker_config.a2a.auth_ref` 只保存敏感配置引用。
- `agent_versions.worker_config.capability_summary` 保存由 Agent Card 映射出的 `worker_capability_v2`。

Agent Card 到能力摘要的映射：

```json
{
  "schema_version": "worker_capability_v2",
  "executor_type": "a2a",
  "input_modalities": ["text/plain"],
  "output_modalities": ["text/plain"],
  "semantic_tags": ["search", "document_qa"],
  "skills": [
    {
      "id": "remote_skill_id",
      "name": "Remote skill name",
      "description": "Remote skill description",
      "tags": ["a2a", "remote"],
      "input_modes": ["text/plain"],
      "output_modes": ["text/plain"]
    }
  ],
  "tool_names": [],
  "model_features": [],
  "constraints": {
    "requires_credentials": true,
    "requires_approval": false,
    "max_timeout_seconds": 30,
    "a2a_protocol_version": "..."
  },
  "manual_overrides": {},
  "generated_at": 0
}
```

映射规则：

- `AgentCard.name` -> WorkerAgent `name`。
- `AgentCard.description` -> WorkerAgent `description`。
- `AgentCard.url` / `provider` / `version` -> `worker_config.a2a.card_snapshot`。
- `defaultInputModes` / `defaultOutputModes` -> `input_modalities` / `output_modalities`。
- `skills[]` -> `capability_summary.skills`，并从 skill name/description/tags 推断 `semantic_tags`。
- `capabilities.streaming`、`pushNotifications` 只进入 snapshot，不启用。
- `security` 或 `auth_type != none` -> `constraints.requires_credentials = true`。
- 用户可通过现有能力摘要人工修正入口补 `semantic_tags`。

后端服务拆分：

- `A2AAgentService`：注册、列表、详情、禁用、同步 Agent Card、创建/刷新映射 WorkerAgent。
- `A2AClient`：拉取 Agent Card、发送 text `message/send`，只负责协议 HTTP 通信。
- `A2ASecurityService`：URL/SSRF 校验、DNS 解析后 IP 校验、重定向校验、响应体大小限制。
- `A2ACapabilityMapper`：Agent Card -> `worker_capability_v2`。
- `A2AWorkerExecutor`：`WorkerInvocation` -> A2A message/send -> `WorkerResult`。

API 设计：

- `POST /a2a-agents/discover`：输入 base URL 和可选 `auth_ref`，只拉取并校验 Agent Card，不落库。
- `POST /a2a-agents`：注册远程 Agent，同步 Agent Card，创建或更新对应 WorkerAgent 草稿。
- `GET /a2a-agents` / `GET /a2a-agents/{id}`：列表和详情。
- `PATCH /a2a-agents/{id}`：更新名称、描述、状态、标签、`auth_ref`。
- `POST /a2a-agents/{id}/sync-card`：重新同步 Agent Card，刷新对应 WorkerAgent 草稿能力摘要。
- `POST /a2a-agents/{id}/test-message`：发送 text 测试消息，不创建 Planner 任务。
- `DELETE /a2a-agents/{id}`：软删除或禁用；已被 Planner 绑定时返回提示，优先禁用。
- `POST /apps/{planner_app_id}/planner/workers`：复用现有绑定入口，绑定已映射出的 A2A WorkerAgent。

Runtime 设计：

```text
PlannerAgent
  -> RouterPlan step.worker_id = A2A WorkerAgent id
  -> RouterRuntime.validate_plan()
  -> RouterRuntime.preflight_plan()
  -> WorkerRuntime.invoke()
  -> A2AWorkerExecutor.invoke()
  -> A2AClient.message_send()
  -> WorkerResult
  -> WorkerCall / TraceEvent / AgentStep
```

派发规则：

- `WorkerRuntime._execution_agent_type()` 优先读取 `worker_config.executor_type`。
- `executor_type = "a2a"` 或 `target_ref_type = "a2a_agent"` 时派发到 `A2AWorkerExecutor`。
- `executor_type = "react_worker"` 或 `target_ref_type = "app"` 继续走现有 `ReActWorkerAgent`。

message/send 输入：

- `WorkerInvocation.task.task` 作为当前远程任务说明。
- `WorkerInvocation.context.recent_history` 合并为文本上下文，但限制长度并脱敏。
- `WorkerInvocation.context.input_files` 只作为文本摘要传入，不发送内部文件 URL。
- `WorkerInvocation.context.image_urls` 在 v2.2 不转发；如输入包含图片，preflight 必须阻断不支持图片的 A2A Worker。

WorkerResult 归一化：

- 远程成功并返回文本 parts：`status = "succeeded"`，`summary` 为文本摘要，`data.a2a` 保存脱敏后的远程响应摘要。
- 远程返回 task id/context id：进入 `data.a2a.remote_task_id`、`data.a2a.remote_context_id`。
- 远程 artifact：只保存 `artifacts[].metadata.remote_artifact_id`、名称、mime、摘要，不保存二进制。
- 缺少凭据：`external_agent_auth_required`，`retryable = false`。
- 网络超时或服务不可达：`worker_unavailable`，`retryable = true`。
- Agent Card 无效、协议版本不兼容、响应结构不可解析：`external_agent_protocol_error`，`retryable = true`。

TraceEvent：

- `worker.external.a2a.card.synced`
- `worker.external.a2a.call.started`
- `worker.external.a2a.call.succeeded`
- `worker.external.a2a.call.failed`

trace 脱敏规则：

- 允许保存 base URL 的 host/path、协议版本、远程 task/context id。
- 禁止保存 Authorization、cookie、token、签名 query、完整敏感 headers。
- 远程响应体只保存摘要和结构化安全字段，默认截断。

安全边界：

- 默认只允许 `https://`；本地开发必须通过显式配置允许 `http://localhost`。
- 禁止内网、环回、链路本地、metadata、保留网段；DNS 解析后校验最终 IP。
- 禁止跨 host 自动重定向；如果允许重定向，重定向后的 host/IP 必须再次校验。
- Agent Card 拉取超时 5 秒，响应体上限 512 KB。
- message/send 超时 30 秒，响应体上限 2 MB。
- 不发送平台内部文件 URL、图片二进制、浏览器 cookie 或用户会话凭据。

前端任务：

- PlannerAgent 的 Worker 编排区域增加“添加外部 A2A Agent”。
- 添加弹窗支持 base URL、认证方式、`auth_ref`，可先 discover 预览 Agent Card。
- A2A Worker 列表展示类型、skills、输入输出模式、认证状态、同步状态、最近同步时间。
- 绑定区继续复用内部 Worker 的绑定、优先级、启停和能力摘要展示。
- A2A Worker 详情页提供同步 Agent Card、测试消息、禁用、能力修正入口。
- 任务页在 WorkerCall 中标识 A2A 外部调用并展示脱敏 trace。

v2.2 自动化测试：

- Agent Card discover 成功并映射 `capability_summary`。
- 注册 A2A Agent 后创建或更新对应 WorkerAgent。
- 同一 Planner 能绑定内部 Worker 和 A2A Worker。
- `WorkerRuntime` 能派发 `a2a_agent` executor。
- A2A text `message/send` 成功后归一化为 `WorkerResult`。
- 缺少凭据返回 `external_agent_auth_required`。
- 协议不兼容返回 `external_agent_protocol_error`。
- 网络不可达返回 `worker_unavailable`。
- SSRF 防护拒绝内网、metadata、非 HTTP(S) scheme。
- Agent Card 重新同步不覆盖历史任务中的 capability snapshot。

v2.2 手工验收：

- 在 Planner Worker 编排区域添加外部 A2A Agent。
- 同一个 Planner 同时绑定内部 Worker 和 A2A Worker。
- Planner 选择 A2A Worker 后，A2A text `message/send` 调用成功。
- 任务页能看到 A2A WorkerCall 和脱敏 trace。
- Agent Card 重新同步后，新任务使用新快照，历史任务仍展示旧快照。

#### 7.10.3 v2.3 动态重规划

目标：

- Worker 失败或能力不匹配时，Planner 有一次机会调整未执行步骤。
- 重规划结果必须仍是 `RouterPlan`，继续经过 schema、绑定、依赖和 preflight 校验。
- 任务页能清楚展示原计划、失败步骤、重规划原因、新计划和改派 Worker。

非目标：

- 不实现无限循环 agent loop。
- 不改写已完成 step。
- 不启用并行 DAG。
- 不进入人工审批或等待用户输入；这些属于 v3。
- 不让 Worker 自行修改全局计划。

触发条件：

- capability preflight 失败，且 `preflight.suggested_worker_ids` 非空。
- Worker 返回 `status = failed` 且 `retryable = true`。
- WorkerResult 中包含可重规划错误码，例如 `capability_missing:*`、`worker_unavailable`、`external_agent_protocol_error`。
- Worker 输出缺少后续 step 所需的关键 evidence 或 artifact，且 routing policy 允许重规划。

不触发条件：

- `routing_policy.fallback_policy.on_worker_failed != "replan_once"`。
- 当前任务已经重规划过一次。
- 失败 step 要求人工审批。
- 失败错误不可重试，例如 `external_agent_auth_required`、`replan_limit_exceeded`。
- 没有可替代 Worker，或替代 Worker preflight 仍失败。

重规划输入 schema：

```json
{
  "schema_version": "router_replan_input_v1",
  "router_id": "planner-agent-id",
  "attempt": 1,
  "original_plan": {},
  "active_plan": {},
  "completed_steps": [
    {
      "step_id": "step_1",
      "worker_id": "worker-id",
      "task": "done task",
      "summary": "worker result summary",
      "artifacts": [],
      "evidence": []
    }
  ],
  "failed_step": {
    "step_id": "step_2",
    "worker_id": "worker-id",
    "task": "failed task",
    "status": "failed"
  },
  "worker_result": {},
  "preflight": {},
  "error": {
    "error_code": "worker_unavailable",
    "message": "..."
  },
  "available_workers": [],
  "routing_policy": {},
  "trace_summary": []
}
```

重规划输出：

- 仍使用 `router_plan_v1`。
- `steps` 只包含后续要执行的步骤，不包含已完成 step。
- 新 step 的 `step_id` 必须带 attempt 前缀或后缀，例如 `replan_1_step_1`，避免与原计划 step 冲突。
- 新 step 不允许依赖已完成 step id；需要使用已完成结果时，必须在 `task` 文本里说明“基于已完成结果 ...”。
- `risk_assessment.source = "llm_replan_v1"`。
- `final_response_policy.mode` 继续使用 `summarize_worker_results`。

存储设计：

- 不新增表。
- 每次重规划追加一条新的 `AgentPlan`。
- 原 `AgentPlan.status` 标记为 `superseded` 或保持原状态并在 `plan_json.replan.superseded_by_plan_id` 记录新 plan id；实现时优先使用已有 `status` 字段。
- 新 `AgentPlan.plan_json.replan` 保存：

```json
{
  "attempt": 1,
  "parent_plan_id": "old-plan-id",
  "reason": {
    "trigger": "worker_failed",
    "failed_step_id": "step_2",
    "failed_worker_id": "worker-id",
    "error_code": "worker_unavailable",
    "message": "..."
  },
  "completed_step_ids": ["step_1"],
  "replaced_step_ids": ["step_2", "step_3"],
  "selected_worker_ids": ["new-worker-id"],
  "preflight": {}
}
```

- 新计划的 `AgentStep` 只为新 `RouterPlan.steps` 创建。
- `WorkerCall.invocation_json.execution_policy.plan_attempt` 标记本次调用来自第几次计划。
- `AgentTask.version` 可作为任务执行版本递增；不依赖它表达重规划历史。
- 任务详情通过同一 `task_id` 拉出多条 `AgentPlan`、多组 `AgentStep`、`WorkerCall` 和 `TraceEvent`。

TraceEvent：

- `planner.replan.requested`
- `planner.replan.generated`
- `planner.replan.validated`
- `planner.replan.preflight.succeeded`
- `planner.replan.preflight.failed`
- `planner.replan.applied`
- `planner.replan.fallback`
- `planner.replan.limit_exceeded`

后端执行流：

```text
create_plan()
  -> validate_plan()
  -> preflight_plan()
  -> persist original AgentPlan/AgentStep
  -> execute steps sequentially
      -> step preflight failed or worker failed
      -> _maybe_replan()
          -> build ReplanInput
          -> RouterPlannerAgent.update_plan()
          -> RouterRuntime.validate_plan()
          -> RouterRuntime.preflight_plan()
          -> persist new AgentPlan/AgentStep
          -> continue executing new steps
      -> summarize completed outputs
```

`_maybe_replan()` 决策：

- 读取 `routing_policy.fallback_policy.on_preflight_failed` 和 `on_worker_failed`。
- 统计当前 task 已有 `planner.replan.applied` 次数，默认最多 1 次。
- 过滤候选 Worker：必须已绑定、启用、不是失败 Worker，且 capability 满足失败原因。
- 如果重规划成功，返回新的 `RouterManagerRunResult` 或新 steps 队列。
- 如果重规划失败，返回结构化失败，沿用已有结果汇总可完成部分。

PlannerPromptBuilder 增量：

- 新增 `build_replan_user_prompt()`。
- 系统提示强调：“Do not rewrite completed steps. Return only a RouterPlan for remaining work.”
- 输入中提供 completed summaries、failed reason、available worker descriptors、routing policy 和 trace summary。
- 输出必须是 JSON object，不允许自然语言解释。

RouterRuntime 增量：

- 新增 `validate_replan()` 或在 `validate_plan()` 外包一层：
  - 新 step id 不能与已完成 step id 重复。
  - 新计划 step 数不能超过剩余额度。
  - 新计划 worker 必须已绑定。
  - 新计划不能引用不存在的依赖。
  - 新计划必须再次执行 preflight。

失败收敛：

- 重规划失败但已有成功 step：最终回答说明已完成部分和未完成原因。
- 重规划失败且无成功 step：返回结构化错误码和用户提示。
- 第二次失败不再重规划，返回 `replan_limit_exceeded` 或原始失败原因。
- 所有失败都写入 `AgentTask.error_code/error_message/final_result` 和 trace。

前端任务：

- 任务详情计划区按时间展示多条计划：原计划、重规划计划。
- step 列表显示 `plan_attempt`、原计划/重规划来源、失败原因、改派 Worker。
- WorkerCall 列表标记调用来自原计划还是重规划。
- preflight 展示同时支持原计划和重规划计划。
- 最终结果区展示“已完成”“未完成”“建议操作”。

v2.3 自动化测试：

- Worker failed 且有备用 Worker 时触发一次重规划。
- preflight failed 且有可替代 Worker 时改派。
- 已完成 step 不被重规划覆盖。
- 新计划仍经过 schema、绑定、依赖和 preflight 校验。
- 重规划后再次失败不会无限循环。
- 不可重试错误不会触发重规划。
- 任务详情能返回多条 plan、对应 steps、WorkerCall 和 replan trace。

v2.3 手工验收：

- 构造两个可替代 Worker，一个故意失败，一个成功；Planner 能改派到成功 Worker。
- 构造搜索能力缺失场景；preflight 失败后能改派到 search Worker。
- 任务页能完整展示原计划、失败步骤、重规划原因、新计划和改派 Worker。
- 最终回答能说明已完成部分和未完成部分。
- 用户能根据任务页错误提示知道该调整 Worker、凭据还是输入。

#### 7.10.4 v2.1 API 合约

v2.1 API 只处理本系统 Worker 能力摘要、Planner 编排规则和 preflight 诊断，不接入 A2A。

能力摘要读取：

```http
GET /agents/{agent_id}/capability-summary
```

响应：

```json
{
  "agent_id": "worker-agent-id",
  "version_id": "agent-version-id",
  "capability_summary": {
    "schema_version": "worker_capability_v2",
    "executor_type": "app",
    "input_modalities": ["text/plain", "image/png"],
    "semantic_tags": ["weather", "vision"],
    "tool_names": ["gaode_weather"],
    "model_features": ["tool_call", "image_input"],
    "manual_overrides": {}
  }
}
```

能力摘要刷新：

```http
POST /agents/{agent_id}/capability-summary/refresh
```

请求：

```json
{
  "preserve_manual_overrides": true
}
```

响应：

```json
{
  "refreshed": true,
  "capability_summary": {},
  "warnings": []
}
```

能力摘要人工修正：

```http
PATCH /agents/{agent_id}/capability-summary
```

请求：

```json
{
  "manual_overrides": {
    "semantic_tags": ["weather", "search"],
    "input_modalities": ["text/plain", "image/png"]
  }
}
```

Planner 编排规则读取和保存：

```http
GET /apps/{planner_app_id}/planner/routing-policy
PUT /apps/{planner_app_id}/planner/routing-policy
POST /apps/{planner_app_id}/planner/routing-policy/validate
```

保存请求：

```json
{
  "routing_policy": {
    "schema_version": "routing_policy_v1",
    "rules": [],
    "fallback_policy": {
      "on_preflight_failed": "structured_error"
    }
  }
}
```

校验响应：

```json
{
  "valid": true,
  "errors": [],
  "warnings": []
}
```

Preflight 诊断：

```http
POST /apps/{planner_app_id}/planner/preflight
```

请求：

```json
{
  "message": "识别这张图并搜索最新背景资料",
  "input_modalities": ["text/plain", "image/png"],
  "candidate_worker_ids": ["worker-a", "worker-b"]
}
```

响应：

```json
{
  "status": "failed",
  "results": [
    {
      "worker_id": "worker-a",
      "passed": false,
      "error_code": "capability_missing:image_input",
      "user_message": "当前绑定 Worker 不支持图片输入，请选择具备视觉能力的 Worker。",
      "capability_snapshot": {}
    }
  ],
  "suggested_worker_ids": ["worker-b"]
}
```

接口规则：

- 所有接口必须校验 tenant/account 权限。
- `refresh` 不应修改用户手动 overrides。
- `routing_policy` 保存前必须 schema 校验。
- preflight 诊断接口不创建 `AgentTask`，只用于配置页和调试前检查。
- 真正任务执行时仍必须在服务端再次执行 preflight，不能信任前端诊断结果。

#### 7.10.5 错误码和用户提示映射

错误码必须稳定，供后端、前端、任务页、测试和后续重规划共同使用。

| error_code | HTTP 建议 | retryable | 用户提示 | 建议操作 |
| --- | --- | --- | --- | --- |
| `capability_missing:image_input` | 422 | false | 当前绑定 Worker 不支持图片输入。 | 绑定或改派具备视觉能力的 Worker。 |
| `capability_missing:file_input` | 422 | false | 当前绑定 Worker 不支持文件输入。 | 绑定支持文件处理的 Worker，或移除文件后重试。 |
| `capability_missing:search` | 422 | false | 当前绑定 Worker 不具备搜索或最新信息能力。 | 绑定搜索 Worker，或给现有 Worker 配置搜索工具。 |
| `worker_model_unsupported:image_input` | 422 | false | Worker 配置了图片能力，但当前模型不支持图片输入。 | 更换支持视觉的模型，或关闭该能力标签。 |
| `worker_unavailable` | 503 | true | 目标 Worker 当前不可用。 | 检查 Worker 启停状态、发布版本或外部 Agent 同步状态。 |
| `external_agent_auth_required` | 401 | false | 外部 Agent 需要认证，但当前未配置有效凭据。 | 为该 A2A Agent 配置凭据引用。 |
| `external_agent_protocol_error` | 502 | true | 外部 Agent 协议调用失败或版本不兼容。 | 检查 Agent Card、协议版本、网络和远程服务状态。 |
| `routing_policy_invalid` | 400 | false | Worker 编排规则格式不正确。 | 修正规则 JSON 后重新保存。 |
| `capability_summary_invalid` | 400 | false | Worker 能力摘要格式不正确。 | 重新生成能力摘要或修正人工覆盖字段。 |
| `replan_limit_exceeded` | 409 | false | 本次任务已达到自动重规划次数上限。 | 查看失败原因后手动调整 Worker 或任务输入。 |

提示映射规则：

- 后端返回稳定 `error_code`、英文/技术 `message` 和可选 `details`。
- 前端显示 `user_message` 或 i18n 映射文案，不直接展示 Python/HTTP/SDK 原始异常。
- 用户消息语言优先使用当前会话语言；配置页优先使用账号语言。
- 任务页必须同时保存 `error_code` 和当时展示的用户提示，避免后续文案变化影响历史回放。

#### 7.10.6 任务页数据展示契约

任务页不直接解析模型输出，而是读取标准化任务数据。

Plan 区域：

```json
{
  "plan": {
    "plan_id": "plan-id",
    "schema_version": "router_plan_v1",
    "objective": "...",
    "source": "llm_planner_v1",
    "replan_of": null
  }
}
```

Step 区域：

```json
{
  "step": {
    "step_id": "step_1",
    "status": "succeeded|failed|skipped|replanned",
    "worker_id": "worker-id",
    "worker_name": "天气查询 Worker",
    "worker_target_ref_type": "app|a2a_agent",
    "capability_snapshot": {},
    "preflight": {
      "status": "succeeded|failed|skipped",
      "checks": [
        {
          "rule_id": "image_requires_vision",
          "passed": false,
          "error_code": "capability_missing:image_input",
          "user_message": "当前绑定 Worker 不支持图片输入。"
        }
      ]
    }
  }
}
```

Worker call 区域：

```json
{
  "worker_call": {
    "worker_call_id": "call-id",
    "executor_type": "app|a2a",
    "status": "succeeded|failed",
    "started_at": "...",
    "finished_at": "...",
    "invocation_json": {},
    "result_json": {},
    "error_code": null,
    "events": []
  }
}
```

A2A call 展示字段：

```json
{
  "a2a": {
    "base_url": "https://agent.example.com",
    "card_url": "https://agent.example.com/.well-known/agent-card.json",
    "protocol_version": "0.3|1.0",
    "remote_task_id": "remote-task-id",
    "remote_context_id": "remote-context-id",
    "request_mode": "message/send",
    "response_status": "completed|failed|input-required",
    "agent_name": "External Agent"
  }
}
```

Replan 区域：

```json
{
  "replan": {
    "attempt": 1,
    "trigger": "worker_failed|capability_preflight_failed",
    "failed_step_id": "step_1",
    "reason_code": "capability_missing:image_input",
    "original_plan_id": "plan-a",
    "new_plan_id": "plan-b",
    "changed_steps": [
      {
        "old_step_id": "step_2",
        "new_step_id": "step_2r",
        "old_worker_id": "worker-a",
        "new_worker_id": "worker-b"
      }
    ]
  }
}
```

展示规则：

- 第一屏优先显示最终状态、失败原因、涉及 Worker 和可执行建议。
- 详情展开后展示 plan、step、worker call、trace、preflight 和 replan。
- capability snapshot 只展示摘要字段，不展示凭据、完整 tool input 或敏感 headers。
- A2A base URL 可以展示域名和路径，凭据、Authorization、cookie 必须脱敏。
- 历史任务展示当时保存的 snapshot，不实时读取最新 Worker 配置覆盖历史。

#### 7.10.7 A2A 安全边界

A2A 接入必须先做安全默认值，不允许先裸连任意 URL。

URL 和 SSRF 防护：

- `base_url` 只允许 `https://`，本地开发可通过显式配置允许 `http://localhost`。
- 默认禁止内网、环回、链路本地、metadata 地址和保留网段。
- DNS 解析后必须校验最终 IP，不只校验字符串。
- 禁止自动跟随跨 host 重定向；如允许重定向，重定向后的 host/IP 必须再次校验。
- 禁止 `file://`、`ftp://`、`gopher://` 等非 HTTP(S) scheme。

请求限制：

- Agent Card 拉取超时默认 5 秒，A2A message/send 默认 30 秒，账号或 Worker 可配置上限但不能无限。
- Agent Card 响应体默认最大 512 KB。
- message/send 响应体默认最大 2 MB。
- v2.2 不上传本地文件、不转发图片二进制、不发送内部文件 URL。
- v2.2 不启用 streaming、push notification 和远程回调 URL。

凭据边界：

- `a2a_agents` 和 `worker_config` 只保存 `auth_ref`，不保存明文密钥。
- 运行时通过现有敏感配置体系解密并注入 Authorization。
- 任务页、trace、WorkerCall 必须脱敏 headers、token、cookie 和签名参数。
- 凭据缺失或解密失败返回 `external_agent_auth_required`。

Agent Card 同步边界：

- 同步失败不删除历史 card，标记 `sync_status = failed` 并保存 `last_sync_error`。
- 如果从未成功同步，不允许创建可绑定 Worker。
- 如果已有历史 card 但最新同步失败，可继续使用已发布版本快照，但 UI 必须提示“同步失败，使用旧快照”。
- Agent Card 的能力变化不自动覆盖用户手动 `semantic_tags`。

审计边界：

- 每次 A2A card 同步记录 `worker.external.a2a.card.synced` 或 failed trace/审计事件。
- 每次 A2A 调用记录目标 agent id、base URL host、协议版本、耗时、状态和错误码。
- 不记录完整密钥、原始 Authorization header、cookie 和敏感 query 参数。

#### 7.10.8 分阶段测试矩阵

v2.1 自动化测试：

- `capability_summary` 从模型 features、工具、知识库、工作流生成。
- 手动 overrides 在 refresh 后保留。
- routing policy schema 校验通过和失败分支。
- preflight 图片输入命中 `capability_missing:image_input`。
- preflight 搜索意图命中 `capability_missing:search`。
- `worker_model_unsupported:image_input` 能区分“标签声明支持”和“模型实际不支持”。
- v1 Planner/Worker 调试回归通过。

v2.1 手工验收：

- Worker 详情能看到能力摘要。
- Planner Worker 绑定列表能看到关键能力标签。
- Planner 编排规则能保存、校验和恢复。
- 任务页能展示 preflight 成功/失败和中文提示。

v2.2 自动化测试：

- A2A Agent Card 拉取成功并映射 `capability_summary`。
- 无凭据访问需要认证的远程 Agent 返回 `external_agent_auth_required`。
- 协议不兼容返回 `external_agent_protocol_error`。
- SSRF 防护拒绝内网、metadata 和非 HTTP(S) scheme。
- `WorkerRuntime` 能派发 `a2a_agent` executor。
- A2A 响应归一化为 `WorkerResult`。

v2.2 手工验收：

- 在 Planner Worker 编排区域添加外部 A2A Agent。
- 同一个 Planner 同时绑定内部 Worker 和 A2A Worker。
- A2A text `message/send` 调用成功，任务页能看到 A2A call trace。
- Agent Card 重新同步后，历史任务仍展示旧快照。

v2.3 自动化测试：

- Worker failed 且有备用 Worker 时触发一次重规划。
- preflight failed 且有可替代 Worker 时改派。
- 已完成 step 不被重规划覆盖。
- 重规划后再次失败不会无限循环。
- 新计划仍经过 schema、绑定、依赖和 preflight 校验。

v2.3 手工验收：

- 任务页能看见原计划、失败步骤、重规划原因、新计划和改派 Worker。
- 最终回答能说明已完成部分和未完成部分。
- 用户能根据任务页错误提示知道该调整 Worker、凭据还是输入。

#### 7.10.9 具体落地顺序

按 PR 或任务批次推进：

1. v2.1-1：后端 schema 和服务骨架。定义 `capability_summary`、`routing_policy`、错误码常量、用户提示映射，不改变 Planner 行为。已完成。
2. v2.1-2：内部 Worker 能力摘要生成。覆盖模型、工具、知识库、工作流和手动 overrides。已完成。
3. v2.1-3：Planner descriptor 注入和 Router preflight。先只做硬阻断，不做自动重规划。已完成。
4. v2.1-4：前端能力摘要、编排规则 JSON 编辑器和任务页 preflight 展示。已完成。
5. v2.1-5：v1 回归和 v2.1 验收矩阵补齐。自动化回归和手工功能验收已完成，真实 session/task id 后续在 V2 回归记录中补充。
6. v2.2-1：`a2a_agents` 迁移、模型、服务、SSRF/URL 安全校验和 Agent Card 同步。
7. v2.2-2：A2A Agent 映射为外部 WorkerAgent，并接入现有 `AgentBinding`。
8. v2.2-3：`A2AWorkerExecutor` 和 WorkerRuntime 派发，支持 text `message/send`。
9. v2.2-4：A2A 前端添加/同步/测试/绑定/任务页 trace。
10. v2.2-5：A2A 安全、协议错误和历史快照验收。
11. v2.3-1：`RouterPlannerAgent.update_plan()` 和重规划输入输出 schema。
12. v2.3-2：失败触发、改派、最多一次重规划和新计划二次校验。
13. v2.3-3：任务页原计划/新计划/replan trace 展示。
14. v2.3-4：完整 V2 回归：内部 Worker、A2A Worker、能力缺失、Worker 失败、历史任务回放。

每个批次完成标准：

- 有迁移的批次必须包含 migration upgrade/downgrade 验证。
- 后端批次至少跑 `ruff` 和相关 pytest。
- 前端批次至少跑 type-check 和 build。
- 涉及 Planner/Worker 行为的批次必须用真实调试任务验证，并记录 session/task id。

## 8. v3：等待用户输入与人工审批

目标：任务信息不足或高风险时不直接失败，而是暂停并等待用户或审批人继续。

核心待办：

- 区分 `waiting_user` 和 `waiting_approval`。
- Worker 能返回“需要用户补充”的结构化结果。
- Planner 能把任务暂停，并在用户补充后恢复。
- 高风险工具、外部 API、导出、删除等操作进入审批。
- 前端任务页支持继续输入和审批操作。

协议方向：

- `WorkerResult.status = waiting_user` 表示信息不足。
- `WorkerResult.status = waiting_approval` 表示需要审批。
- `TraceEvent` 记录等待原因、恢复输入和审批结果。
- `AgentTask.status` 支持 paused/waiting/running/done/failed。

## 9. v4：并行 DAG 与依赖执行

目标：让 `RouterPlan` 支持非线性执行和依赖编排，而不只做顺序 step。

核心待办：

- 支持 `execution_mode = async`。
- 支持 step dependencies 的 DAG 执行。
- 无依赖 Worker 并发运行。
- 汇总节点等待前置结果。
- WorkerResult 进入依赖 step 的上下文。
- UI 展示 DAG 或并行时间线。

约束：

- 并发只发生在依赖关系允许的 step。
- 汇总 step 必须能看到前置 WorkerResult。
- 失败策略需要可配置：fail-fast、continue、fallback worker。

## 10. v5：非 A2A executor 生态扩展

目标：在 v2 已完成 `app` 和 `a2a_agent` 两类 Worker 调度后，把 WorkerRuntime 扩展为更完整的执行器生态，同时保持 Planner 协议稳定。

执行类型演进：

| target_ref_type | 状态 / 说明 |
| --- | --- |
| `app` | 现有本系统 WorkerAgent |
| `a2a_agent` | v2.2 落地的外部 A2A WorkerAgent |
| `workflow` | 直接调用工作流 |
| `mcp` | MCP 工具集合 Worker |
| `sandbox` | 代码、浏览器、文件执行环境 |
| `api` | 外部服务封装 Worker |

规则：

- Planner 只面向 Worker descriptor、routing policy 和 `WorkerResult`。
- WorkerRuntime 根据 `target_ref_type` 和 `worker_config.executor_type` 派发到不同 executor。
- 每个 executor 必须把输出归一化为 `WorkerResult`。
- A2A 已在 v2 作为外部 WorkerAgent 进入统一绑定体系，不等到 v5。
- MCP、sandbox、api 不作为 Planner 内部协议，而是后续 Worker executor 扩展。

## 11. v6：评估、治理和生产化

目标：让 PlannerAgent 可用于真实业务运行和持续优化。

核心待办：

- Planner 计划质量评估。
- Worker 选择命中率统计。
- fallback 率。
- 失败率。
- 平均 step 数。
- 平均耗时。
- Planner prompt/version 管理。
- Planner 策略配置：最大 step、是否允许并行、是否允许审批、失败策略。
- 历史任务回放。
- 评测集和回归评估。

治理能力：

- 高风险工具审批。
- 外部 API 调用审计。
- 文件和 artifact 访问审计。
- 成本统计。
- 用户、账号、应用维度的运行报表。

## 12. agentic 调研结论

可以吸收的能力：

- Planner 只负责生成和更新全局计划。
- ReAct 负责单步执行和工具调用。
- 结构化 plan/result 协议。
- 动态重规划思想。
- 事件流和可观测性设计。
- A2A Agent Card 拉取、缓存和远程调用的最小闭环。
- 工具失败返回结构化结果，让上层 Agent 有机会继续处理或解释。

不建议直接迁移的部分：

- 不整体迁移 agentic 的 `PlannerReActFlow` 状态机。
- 不把 agentic 的 A2A 工具模型直接复制到 `llmops`。agentic 目前更接近“ReAct Agent 可自主调用远程 Agent 工具”，只保存轻量 server 配置，主要支持文本 `message/send`，缺少平台级绑定、凭据治理、协议版本治理、artifact 归一化和任务页可观测。
- 不把 A2A 作为 Planner 内部核心协议。
- 不把 MCP 直接暴露给 Planner。
- 不把单 Agent 内部 memory 系统复制到平台层。

`llmops` 和 agentic 的关系：

- `llmops` 做平台控制面、运行治理和多 Agent 编排。
- agentic 的 Planner/ReAct 思想作为运行面能力来源。
- `llmops` 中的 PlannerAgent 编排多个独立 WorkerAgent。
- agentic 中的 A2A 代码可作为 v2.2 的参考下限：能发现 Agent Card、能发起远程调用、能把失败作为结构化上下文返回。
- `llmops` 的定稿方向是把外部 A2A Agent 表达为外部 WorkerAgent，通过 `AgentBinding` 绑定给 Planner，而不是放入插件广场，也不是作为 Planner prompt 里的普通工具。
- agentic 中的工具、MCP、ReAct 执行经验后续可继续沉淀为 Worker executor 或 Worker capability。

## 13. 推荐推进顺序

1. v1 收尾：验收清单、任务页验证、Worker 模板、能力不足提示。
2. v2.1 能力感知地基：`capability_summary`、routing policy、preflight、错误 taxonomy、任务页展示。
3. v2.2 A2A 外部 Worker：Agent Card 同步、外部 WorkerAgent 映射、Planner 绑定、text `message/send` executor、调用 trace。
4. v2.3 动态重规划：`update_plan()`、失败后改派、原计划/新计划展示。
5. v3 等待用户输入和人工审批。
6. v4 并行 DAG。
7. v5 非 A2A executor 生态扩展。
8. v6 评估、治理和生产化。

当前不建议插入的大改：

- 不重做 AI 应用版本体系。
- 不新增独立 Planner 控制台。
- 不提前引入复杂 DAG UI。
- 不在 Planner 中直接执行工具。
- 不把 A2A 放进插件广场混管。
- 不把 A2A/MCP 做成 Planner 内部主协议。
