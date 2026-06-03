# LLMOps Planner Agent 调研与接入设计

本文基于当前 `llmops/docs` 中的 Agent Runtime、企业自主 Agent 平台规划、Router Planner 主线计划，以及 `agentic` 项目的 PlannerAgent 代码，整理在 `llmops` 上新增 Planner Agent 的最小破坏方案。

目标不是把 `agentic` 的自主执行流整体搬进 `llmops`，而是在现有 Router/Worker/Task/Trace 基础上吸收其 Planner 思路，让 Router Agent 能用 LLM 生成可校验、可落库、可观测、可回退的 `RouterPlan`。

## 1. 总结结论

Planner Agent 第一阶段建议按下面边界落地：

```text
Conversation Message
  -> PlannerInput
  -> AgentTask
  -> planner.* TraceEvent
  -> RouterPlannerAgent.create_plan()
  -> RouterPlan
  -> RouterRuntime.validate_plan()
  -> fallback RouterPlan if needed
  -> AgentPlan / AgentStep
  -> existing WorkerRuntime.invoke()
  -> WorkerCall / TraceEvent / ArtifactRef / final_result
  -> 会话记录页展示
```

核心原则：

- 复用 `llmops` 现有 `RouterPlan / RouterPlanStep / WorkerInvocation / WorkerResult / ArtifactRef / AgentEvent` 协议。
- 复用现有 `AgentTask / AgentPlan / AgentStep / WorkerCall / TraceEvent` 表，不新增迁移。
- 复用现有 Worker Agent 执行底座，不改 `WorkerRuntime -> ReActWorkerAgent -> AppExecutor` 主链路。
- 复用当前会话记录页作为 Planner 观测入口，不先新增 Planner 专属 UI。
- 只吸收 `agentic` 的 Planner 思路，不直接复用其 `Plan / Step / PlannerReActFlow / BaseAgent / memory / event stream`。
- Planner 输出必须经过 Pydantic 和 Router 运行时校验；失败后走规则 fallback，不能信任模型 JSON。
- v1 不做 Agent 版本管理改造，不调整发布/草稿链路，不新增 Agent 表字段。
- v1 不接 A2A，只支持平台内部已绑定 Worker Agent；A2A 后续作为外部 Worker executor 增强。

## 2. 当前 llmops 基础

已经具备的基础：

- `WorkerRuntime` 已能执行 App Worker / ReAct Worker。
- `WorkerInvocation.context.input_files` 已支持输入文件引用。
- `WorkerResult.artifacts` 已能承载产物文件引用。
- `WorkerResult.events` 已能映射为 `TraceEvent`。
- 任务执行数据已经落在 `AgentTask / AgentPlan / AgentStep / WorkerCall / TraceEvent`。
- 会话记录已经按 `Conversation / Message` 组织，能展示每轮关联的 task、plan、step、worker call、trace、输入文件和产物文件。
- 当前 Router Manager 已有规则式 `build_manager_plan()`，生成 `manager_rule_v1` 风格的 `RouterPlan`，并能顺序执行。

因此 Planner Agent 不需要重做执行台。它主要替换或增强当前规则式 plan 生成，并把 planner 生命周期写进 trace。

## 3. agentic PlannerAgent 调研

### 3.1 关键代码

参考路径：

- `agentic/api/app/core/agent/planner.py`
- `agentic/api/app/core/entities/plan.py`
- `agentic/api/app/core/entities/event.py`
- `agentic/api/app/core/prompts/planner.py`
- `agentic/api/app/core/flows/planner_react.py`
- `agentic/api/app/core/agent/base.py`

### 3.2 agentic 的实现特点

`PlannerAgent` 的核心行为：

- 继承 `BaseAgent`。
- 使用 system prompt + planner prompt。
- `response_format` 使用 JSON object。
- `tool_choice = none`，Planner 不调用工具。
- `create_plan(message)` 根据用户消息和附件生成计划。
- 输出经过 JSON parser 修复/解析。
- 解析后用 `Plan.model_validate()` 做结构校验。
- 成功后产出 `PlanEvent(status=created)`。
- `update_plan(plan, step)` 会根据上一步执行结果更新未完成步骤。

`PlannerReActFlow` 的核心行为：

- 状态机包括 planning、executing、updating、summarizing。
- Planner 生成计划。
- ReAct Agent 执行当前 step。
- Planner 根据 step 结果更新计划。
- 最后由 ReAct Agent 总结。

### 3.3 可以吸收的部分

适合吸收到 `llmops` 的是方法论和局部机制：

- Planner 是 model-only，不直接调用工具。
- Planner 输出必须是结构化 JSON。
- Prompt 明确列出输出 schema、可用能力和限制。
- JSON 解析后必须再做业务校验。
- 需要保留 fallback，不能让模型失败阻断任务。
- Planner 生命周期要形成事件：started、generated、validated、fallback、failed。
- 后续可以增加 `update_plan()`，支持动态重规划。

### 3.4 不建议直接复用的部分

不建议直接搬运：

- `agentic` 的 `Plan / Step` 实体，因为缺少 `worker_id / dependencies / execution_mode / approval` 等 llmops Router 执行字段。
- `PlannerReActFlow` 整体状态机，因为 `llmops` 已经有 TaskEngine、RouterManagerService、WorkerRuntime 和执行记录 UI。
- `BaseAgent` 的 memory、uow、tool loop，因为这些和 `llmops` 的账号、模型、文件、权限、审计边界不一致。
- `agentic` 的事件模型，因为 `llmops` 已有 `TraceEvent` 和 `WorkerResult.events`。

## 4. 与 llmops 协议的映射

| agentic 概念 | llmops 对应 | 处理方式 |
| --- | --- | --- |
| `PlannerAgent.create_plan()` | `RouterPlannerAgent.create_plan()` | 吸收思路，重新实现 |
| `Plan` | `RouterPlan` | 不复用 agentic 结构 |
| `Step.description` | `RouterPlanStep.task` | 转换为 Worker 子任务 |
| `PlanEvent` | `TraceEvent(planner.*)` | 写入现有 trace |
| `Message.attachments` | `PlannerInput.input_files` | 使用现有文件引用 |
| `RepairJSONParser` | strict JSON + 可选轻量修复 + fallback | v1 不强制新增依赖 |
| `PlannerReActFlow` | `RouterAgentManagerService + WorkerRuntime` | 不整体迁移 |
| `update_plan()` | v2 replan 能力 | v1 预留接口，不启用 |

## 5. PlannerInput 设计

建议新增内部对象，放在 `llmops/api/app/domain/agent_runtime/planner.py` 或相近模块：

```python
@dataclass(frozen=True)
class PlannerWorkerDescriptor:
    worker_id: str
    name: str
    description: str
    runtime_type: str
    product_category: str
    target_ref_type: str
    target_ref_id: str
    capabilities: dict[str, Any]
    config_summary: dict[str, Any]


@dataclass(frozen=True)
class PlannerInput:
    router_id: str
    query: str
    conversation_id: str | None
    message_id: str | None
    input_files: list[dict[str, Any]]
    recent_history: list[dict[str, Any]]
    workers: list[PlannerWorkerDescriptor]
    constraints: dict[str, Any]
```

v1 的 `constraints` 固定为：

```json
{
  "allow_parallel": false,
  "allow_replan": false,
  "allow_required_approval": false,
  "execution_mode": "sync",
  "max_steps": 5
}
```

注意：Planner 只能看到已绑定、已发布或 active 的 Worker，不应该看到租户外、未绑定、禁用、草稿 Worker。

## 6. RouterPlan 输出约束

Planner 必须输出现有协议：

```json
{
  "schema_version": "router_plan_v1",
  "router_id": "router uuid",
  "user_intent": "用户目标",
  "risk_assessment": {
    "risk_level": "low",
    "source": "llm_planner_v1"
  },
  "steps": [
    {
      "step_id": "step_1",
      "worker_id": "worker uuid",
      "task": "交给该 Worker 的明确子任务",
      "dependencies": [],
      "execution_mode": "sync",
      "required_approval": false
    }
  ],
  "final_response_policy": "summarize_worker_results"
}
```

v1 校验要求：

- `schema_version` 必须是 `router_plan_v1`。
- `router_id` 必须等于当前 Router Agent ID。
- `steps` 不能为空，数量不能超过 `max_steps`。
- `step_id` 唯一，建议固定 `step_1 / step_2`。
- `worker_id` 必须是当前 Router 已绑定 Worker。
- `dependencies` 只能引用已存在 step，且不能成环。
- v1 只允许 `execution_mode = sync`。
- v1 不允许 `required_approval = true`。
- `task` 必须非空，且是给对应 Worker 的可执行子任务。
- `risk_assessment.source` 使用 `llm_planner_v1`；fallback 使用 `manager_rule_v1`。

## 7. Prompt 设计

Planner prompt 应明确告诉模型：

- 你是 Router Planner，不是执行 Worker。
- 只能选择给定 Worker，不能发明 Worker ID。
- 不要调用工具，不要输出自然语言解释。
- 输出必须是单个 JSON object。
- 只生成同步顺序计划。
- 如果任务很简单，可以只选一个最合适 Worker。
- 如果需要多个 Worker，后续 step 的 task 应包含前序结果如何被使用。
- 输入文件只能作为上下文引用，不要假装已经读取文件内容。

Prompt 输入建议包括：

- 当前用户问题。
- 最近少量会话历史或摘要。
- 输入文件引用：file_id、name、mime_type、size、summary。
- Worker 列表：worker_id、name、description、能力摘要、适用范围。
- `RouterPlan` JSON schema 或紧凑示例。
- v1 constraints。

## 8. Runtime 接入方案

### 8.1 最小服务改动点

当前 `RouterAgentManagerService.build_manager_plan()` 是规则式 plan 生成点。Planner Agent 落地后，它不再是可选开关，而是 Router/Planner App 的默认规划能力。现有规则计划只保留为失败 fallback：

```text
build_manager_plan()
  -> try RouterPlannerAgent.create_plan()
  -> try RouterRuntime.validate_plan()
  -> return llm plan
  -> except: return build_rule_manager_plan()
```

为了记录 `planner.started` 等 trace，推荐把 `create_manager_run()` 调整为 task-first 流程：

```text
create_manager_run()
  -> use current router context
  -> list bound workers
  -> TaskEngine.create_task()
  -> TraceEvent planner.started
  -> build planner input
  -> call planner or fallback
  -> TraceEvent planner.generated / planner.validated / planner.fallback
  -> TaskEngine.create_plan()
  -> TaskEngine.create_step()
  -> router.manager_run.created
```

现有 `create_manager_task_from_plan()` 可以保留，用于测试、内部兼容和已经有 plan 的调用方。新增一个私有 helper，例如 `_persist_manager_plan_for_task()`，避免重复创建 `AgentPlan / AgentStep` 的代码。

### 8.2 本期不做版本管理和 Planner 开关

用户当前诉求是把 `agentic` 的 Planner 能力逐步进化到 `llmops`，不希望先在 Agent 版本体系上做大改。因此 v1 明确不做以下事情：

- 不新增版本管理模型。
- 不修改 `Agent / AgentVersion / AgentBinding` 表结构。
- 不重做发布、草稿、预览、线上版本切换策略。
- 不要求 Worker Agent 的执行配置在本期完全按 published/draft 收口。
- 不因为某个 Worker 版本配置不完整而阻断 Planner 主链路。
- 不新增 `planner.enabled` 产品开关。
- 不在 UI 上提供 Planner 开启/关闭配置。

v1 的处理方式：

- Planner 可以读取现有可用的 Router 模型配置；如果读取不到，则使用平台默认模型配置。
- Planner Agent 运行时默认先走 LLM Planner。
- Planner 参数使用代码默认值，例如 `max_steps=5`、`fallback=manager_rule_v1`。
- Worker 列表只读取现有绑定关系和 Worker 元数据，不要求新增 Worker 版本选择逻辑。
- Worker 执行仍交给现有 `WorkerRuntime`，不在 Planner v1 中修复 App draft/published 配置收口问题。
- 所有配置读取失败都应进入 fallback，而不是让用户任务失败。

如果后续确实需要运维级 kill switch，应优先放在服务内部或环境配置，不进入产品 UI，也不作为 Planner Agent 的业务配置。

### 8.3 LLM 调用

`ChatCompletionRuntime` 当前能从模型参数透传 `response_format`，但没有显式调用参数。建议做一个小扩展：

```python
create_response(
    ...,
    response_format: dict[str, Any] | None = None,
)
```

构造 payload 时：

- 如果传入 `response_format`，优先使用它。
- 否则继续使用 `model.parameters` 里的 `response_format`。
- Planner 调用优先传 `{"type": "json_object"}`。
- 如果提供商不支持 JSON mode 或请求失败，Planner 记录失败并走 fallback。

v1 不强制引入 `json_repair` 新依赖。解析策略：

- 先 `json.loads()`。
- 可做轻量 fence stripping，例如去掉 ```json 包裹。
- 解析失败直接 fallback。
- 后续如果模型输出质量不足，再评估引入 JSON repair。

## 9. Trace 事件

Planner v1 建议写入：

| event_type | payload |
| --- | --- |
| `planner.started` | router_id、message_id、worker_count、max_steps、has_input_files |
| `planner.generated` | model、usage、latency_ms、raw_plan 或 raw_plan 摘要 |
| `planner.validated` | step_count、worker_ids、risk_level |
| `planner.fallback` | reason、source=`manager_rule_v1`、selected_worker_ids |
| `planner.failed` | error_code、error_message |
| `router.manager_run.created` | task_id、plan_id、step_count、plan_source |

注意：

- `AgentPlan.plan_json` 只保存最终可执行计划，不保存未校验通过的脏 JSON。
- 原始 LLM 输出可以进入 trace，但要控制长度，避免日志过大。
- fallback 原因要保留，方便会话记录页定位为什么没用 LLM plan。

## 10. UI 承接

v1 不新增页面，不新增配置页，不新增 Planner 专属 tab，不重做执行记录/会话记录主布局。

当前会话记录页应该能自然展示：

- 每轮 message 关联的 `AgentTask`。
- `AgentPlan.plan_json` 中的 Planner 计划。
- `AgentStep` timeline。
- 每步 `WorkerCall` 的 invocation/result。
- `TraceEvent` 中的 `planner.*`、`router.*`、`worker.*` 事件。
- 输入文件和产物文件。

最小 UI 改动只做展示增强：

- 在现有 plan 区域显示 `risk_assessment.source`，区分 `llm_planner_v1` 和 `manager_rule_v1`。
- 在现有 trace 列表中展示 `planner.started / planner.generated / planner.validated / planner.failed / planner.fallback`。
- 在现有 step timeline 上显示 Worker 名称，保留 UUID 作为次要信息或 tooltip。
- 在 fallback 时展示一条简短原因，例如“Planner 输出无效，已使用规则计划”。

v1 不做：

- 不新增 Planner 调试页。
- 不新增 SSE 实时事件面板。
- 不新增可视化 DAG/流程图。
- 不新增复杂筛选器。
- 不新增 Worker 选择/排序交互。
- 不新增计划编辑器。
- 不新增审批 UI。

UI 验收标准：

- 发起一轮对话后，会话记录中仍按原来的会话/消息结构查看。
- 本轮消息下能看到关联 `AgentTask`。
- 展开任务后能看到 Planner plan、step timeline、Worker 调用和 trace。
- LLM plan 与 fallback plan 能通过 source 区分。
- Planner fallback 原因能在 trace 中看到。
- 不影响现有输入文件、产物文件展示。

## 11. 实施步骤

### Step 1：新增 Planner domain 模块

新增：

- `PlannerInput`
- `PlannerWorkerDescriptor`
- `PlannerResult`
- `RouterPlannerAgent`
- `PlannerPromptBuilder`
- JSON parse helper

`PlannerResult` 建议包含：

```python
@dataclass(frozen=True)
class PlannerResult:
    plan: RouterPlan | None
    raw_output: str
    usage: dict[str, Any]
    latency_ms: int | None
    error: str
```

### Step 2：扩展 ChatCompletionRuntime

增加显式 `response_format` 参数。

同时补测试，保证：

- 默认调用行为不变。
- 显式 `response_format` 能进入 payload。
- 显式参数优先于 `model.parameters.response_format`。

### Step 3：扩展 RouterRuntime.validate_plan()

补充校验：

- steps 不能为空。
- step 数不能超过 max_steps。
- router_id 必须匹配。
- execution_mode 必须在 v1 允许范围。
- required_approval 必须符合 v1 策略。
- dependencies 不成环。

### Step 4：拆出规则 fallback

把当前 `build_manager_plan()` 的规则生成逻辑抽成：

```python
_build_rule_manager_plan(
    router_agent,
    workers,
    user_input,
    requested_worker_ids,
) -> RouterPlan
```

原行为保持不变，但只作为 Planner 失败或校验失败时的 fallback。

### Step 5：接入 RouterAgentManagerService

在 `create_manager_run()` 里：

- 使用当前 `router_agent` 和现有可读配置，不做版本切换改造。
- 创建 `AgentTask` 并写入 `conversation_id`、`user_input.message_id`、`input_files`。
- 写 `planner.started`。
- 调 `RouterPlannerAgent.create_plan()`。
- 校验成功写 `planner.validated`。
- 失败写 `planner.failed` 和 `planner.fallback`。
- 持久化最终 plan 和 steps。
- 继续使用现有 `execute_manager_run_steps()`。

### Step 6：测试

至少覆盖：

- Planner 成功生成合法 `RouterPlan`。
- Planner 输出非法 JSON 时 fallback。
- Planner 输出未绑定 Worker ID 时 fallback。
- Planner 输出 `async` 或 `required_approval=true` 时 fallback。
- Planner 调用失败或校验失败时走 `manager_rule_v1`。
- 任务落库后包含 `conversation_id` 和 `user_input.message_id`。
- `TraceEvent` 包含 `planner.started / planner.validated`。
- fallback 时 `AgentPlan.plan_json.risk_assessment.source = manager_rule_v1`。
- `WorkerResult.artifacts` 仍能进入 `AgentTask.final_result.artifacts`。

## 12. 风险与约束

主要风险：

- 模型编造 Worker ID。
- 模型输出 JSON 不合法。
- 模型生成过多 step 或依赖环。
- 现有 Agent/App 配置本身存在 draft/published 差异，但 v1 不解决版本一致性问题。
- trace payload 保存过大。

控制方式：

- 所有 Worker ID 必须来自绑定列表。
- 所有 plan 必须经过 `RouterPlan` Pydantic 校验和 `RouterRuntime` 业务校验。
- Planner 失败不阻断任务，统一 fallback。
- v1 固定 sync 顺序执行。
- v1 不启用动态重规划、并行、审批。
- trace raw output 做长度限制。

## 13. 延后能力

以下能力不进入 v1：

- Agent 版本管理改造。
- Worker published/draft 执行配置收口。
- A2A 外部 Agent 接入。
- `update_plan()` 动态重规划。
- Worker 执行失败后的自动重试和跳过策略。
- 多 Worker 并行 DAG 调度。
- 审批流。
- SSE 实时推送。
- Planner 专属调试页。
- 多 Planner 策略评分。
- 长期记忆和复杂会话摘要。

这些能力可以在 v1 稳定后，基于同一套 `PlannerInput -> RouterPlan -> validate -> TaskEngine -> TraceEvent` 主链路逐步增强。

## 14. 建议的落地切口

第一版最小可落地范围：

```text
RouterPlannerAgent.create_plan()
  + PlannerPromptBuilder
  + response_format support
  + RouterRuntime stronger validation
  + manager_rule_v1 fallback
  + planner.* TraceEvent
  + small create_manager_run orchestration adjustment
```

这条路径对现有系统破坏最小：

- 不改数据库结构。
- 不改 Worker 执行底座。
- 不改执行记录 UI 主结构。
- 不改文件和 artifact 协议。
- 不做 Agent 版本管理。
- 不接 A2A。
- 不要求 SSE。
- 不直接引入 `agentic` 运行时依赖。

完成后，Planner Agent 的效果可以直接通过发布应用或预览调试发起对话，并在会话记录页查看本轮 `AgentTask`、Planner plan、step timeline、Worker 调用和 trace 事件。

## 15. 收敛后的阶段计划

结合当前约束，后续实施按“小步吸收 agentic 能力”的节奏推进。

### Phase 1：Planner 最小内核

目标：把 `agentic` 的创建计划能力变成 `llmops` 的 `RouterPlan` 生成器。

实施内容：

- 新增 `RouterPlannerAgent`。
- 新增 `PlannerPromptBuilder`。
- 新增 `PlannerInput / PlannerWorkerDescriptor / PlannerResult`。
- Prompt 从 `agentic` 的 `CreatePlanResponse` 改造成 `RouterPlan` schema。
- Planner 使用 JSON mode 或严格 JSON prompt。
- JSON 解析失败直接 fallback。

不做：

- 不接 `update_plan()`。
- 不接 `PlannerReActFlow`。
- 不接 memory。
- 不接工具调用。

### Phase 2：校验与 fallback

目标：保证 Planner 失败不会破坏现有 Router 任务。

实施内容：

- 增强 `RouterRuntime.validate_plan()`。
- 抽出当前 `manager_rule_v1` 为 `_build_rule_manager_plan()`。
- LLM plan 校验失败时回退规则计划。
- `risk_assessment.source` 标识 `llm_planner_v1` 或 `manager_rule_v1`。

验收重点：

- 非法 JSON 能 fallback。
- 编造 Worker ID 能 fallback。
- 空 steps 能 fallback。
- async/approval 能 fallback。

### Phase 3：接入 Router Manager

目标：在现有任务链路中插入 Planner，不重写执行底座。

实施内容：

- 在 `create_manager_run()` 中构造 `PlannerInput`。
- 调用 `RouterPlannerAgent.create_plan()`。
- 持久化最终 `RouterPlan` 到 `AgentPlan`。
- 按现有方式创建 `AgentStep`。
- 继续调用现有 `execute_manager_run_steps()`。

约束：

- 不修改 Agent 表结构。
- 不做 Agent 版本管理。
- 不改变 WorkerRuntime 行为。
- 不改变会话记录页主结构。
- 不新增 Planner 配置页或专属 tab。

### Phase 4：Trace 与会话记录验证

目标：Planner 过程能被会话记录页看见。

实施内容：

- 写入 `planner.started`。
- 写入 `planner.generated`。
- 写入 `planner.validated`。
- 写入 `planner.failed`。
- 写入 `planner.fallback`。

验收重点：

- 每轮会话能看到关联任务。
- 能看到 Planner 生成的 plan。
- 能看到每个 step 的 Worker 调用。
- fallback 原因能在 trace 中看到。
- UI 只在现有会话记录/任务详情区域做轻量展示增强。

### Phase 5：逐步吸收 agentic 进化能力

Planner v1 稳定后，再逐步吸收 `agentic` 的后续能力：

- `update_plan()`：根据 WorkerResult 更新未完成步骤。
- 失败后重规划：Worker 失败时由 Planner 生成后续补救计划。
- 多 Worker DAG：从顺序 sync 执行扩展到依赖图调度。
- A2A/MCP：作为新的 Worker executor/capability，而不是内部核心协议。
- Planner 调试视图：在现有会话记录页稳定后再增强。

这个阶段计划的核心是：先让 Planner 成为 `llmops` Router 的一个可回退计划生成器，再逐步把 `agentic` 的动态规划能力接进来。

## 16. agentic 深度调研补充

本节补充对 `agentic` 自主 Agent 全链路的调研，避免后续演进方向因为只看 Planner prompt 而反复推翻。

### 16.1 agentic 的自主 Agent 运行链路

关键代码：

- `agentic/api/app/services/agent_service.py`
- `agentic/api/app/core/agent/agent_task_runner.py`
- `agentic/api/app/core/task/redis_stream_task.py`
- `agentic/api/app/core/flows/planner_react.py`
- `agentic/api/app/core/agent/planner.py`
- `agentic/api/app/core/agent/react.py`
- `agentic/api/app/core/agent/base.py`

agentic 的对外自主 Agent 不是单个 Planner，而是一条完整链路：

```text
Session chat API
  -> AgentService.chat()
  -> RedisStreamTask(input_stream/output_stream)
  -> AgentTaskRunner
  -> PlannerReActFlow
  -> PlannerAgent.create_plan()
  -> ReActAgent.execute_step()
  -> PlannerAgent.update_plan()
  -> ReActAgent.summarize()
  -> EventMapper
  -> SSE
```

核心机制：

- `AgentService.chat()` 接收用户消息，把 `MessageEvent` 写入 task input stream。
- `RedisStreamTask` 提供 input/output stream，并用后台 async task 运行 `AgentTaskRunner`。
- `AgentTaskRunner` 初始化 sandbox、browser、MCP、A2A，并负责附件同步、工具事件增强、会话状态更新和资源清理。
- `PlannerReActFlow` 是真正的自主状态机，状态包括 `planning / executing / updating / summarizing / completed`。
- `PlannerAgent` 只负责生成和更新全局计划。
- `ReActAgent` 负责执行单个 step，能调用工具。
- 每个 Agent 有自己的 memory，Planner 和 ReAct 的记忆分开持久化。
- 所有运行过程以事件形式输出，前端通过 SSE 接收。

对 `llmops` 的启发：

- 自主性来自“计划、执行、反馈、再规划、总结”的闭环，不只是第一次生成 plan。
- Planner 和 Worker 必须分层：Planner 管全局计划，Worker 执行局部任务。
- 下级执行者可以是平台内部 Worker Agent，也可以后续是 A2A 远程 Agent。
- v1 可以只做 `create_plan()`，但结构必须给 `update_plan()` 留空间。

### 16.2 PlannerReActFlow 的关键行为

`PlannerReActFlow` 的状态机：

```text
IDLE
  -> PLANNING
  -> EXECUTING
  -> UPDATING
  -> EXECUTING
  -> SUMMARIZING
  -> COMPLETED
```

关键行为：

- 初始消息进入后，Planner 创建 `Plan`。
- 创建计划后输出 `TitleEvent`、`MessageEvent`、`PlanEvent`。
- 每次从 `plan.get_next_step()` 取下一个未完成 step。
- ReAct 执行 step，完成后压缩 ReAct memory。
- Planner 根据已执行 step 的结果调用 `update_plan()`。
- `update_plan()` 只替换第一个未完成 step 之后的步骤，不修改已完成步骤。
- 所有 step 完成后，ReAct 做最终总结。

对 `llmops` 的映射：

| agentic | llmops 目标映射 |
| --- | --- |
| `Plan` | `RouterPlan` |
| `Step` | `RouterPlanStep` / `AgentStep` |
| `PlannerAgent.create_plan()` | `RouterPlannerAgent.create_plan()` |
| `PlannerAgent.update_plan()` | v2 `RouterPlannerAgent.update_plan()` |
| `ReActAgent.execute_step()` | `WorkerRuntime.invoke()` |
| `ReActAgent.summarize()` | Router final response policy |
| `PlanEvent / StepEvent / ToolEvent` | `TraceEvent` + 可选 SSE |

关键差异：

- agentic 的 step 只有 `id / description / status / result / attachments`。
- llmops 的 step 必须有 `worker_id / dependencies / execution_mode / required_approval`。
- 因此不能直接复用 agentic 的 `Plan`，必须让 Planner 输出 `RouterPlan`。

### 16.3 Planner prompt 与 ReAct prompt 的分工

agentic 的 Planner prompt 重点：

- 使用用户消息语言。
- 计划简洁。
- 步骤原子、独立。
- 可拆分则多步，不可拆分则单步。
- 不可行时返回空 steps 和空 goal。
- 输出 JSON。

agentic 的 ReAct prompt 重点：

- 执行者必须自己完成任务，不指导用户。
- 每次迭代原则上只调用一个工具。
- 使用 `message_notify_user` 简短通报进度。
- 需要用户输入时使用 `message_ask_user`。
- step 结果输出 JSON：`success / attachments / result`。
- 最终总结输出 JSON：`message / attachments`。

对 `llmops` 的结论：

- Planner prompt 应吸收“语言、简洁、原子 step、JSON 输出”的思想。
- Planner prompt 必须改造成 `RouterPlan` schema，不能继续使用 agentic 的 `CreatePlanResponse`。
- ReAct prompt 的“自己执行、工具迭代、结构化结果”已经更接近 Worker Agent，后续可继续增强 `ReActWorkerAgent`。
- Planner 不应该直接调用工具；工具执行属于 Worker。

### 16.4 BaseAgent、memory 与工具调用

agentic `BaseAgent` 的机制：

- 每个 Agent 独立读取和保存 memory。
- 首次写 memory 时加入 system prompt。
- LLM 调用时传入 memory、tools、response_format 和 tool_choice。
- Planner 设置 `_format="json_object"`、`_tool_choice="none"`。
- ReAct 设置 JSON 输出，但允许工具调用。
- 每次 LLM 最多处理一个 tool call，避免多工具并发失控。
- 执行工具后把 tool result 写回 memory，再让 LLM 继续迭代。
- ReAct 执行完 step 后会 `compact_memory()`，移除重型浏览器/工具结果，降低上下文腐化和 token 消耗。
- 当用户在运行中插入新消息或等待输入后恢复时，会 `roll_back()` 修正 memory 的 tool call 状态。

对 `llmops` 的结论：

- v1 Planner 不需要复制 memory 系统，只构造一次性 `PlannerInput`。
- 后续动态重规划需要保存 Planner 上下文，但应优先复用 `AgentTask / AgentPlan / AgentStep / TraceEvent / conversation`，不要直接搬 agentic memory 表达。
- Worker Agent 的工具迭代、memory compact、等待用户输入，是后续增强点。
- llmops 应保持“Planner 不调用工具、Worker 调用工具”的边界。

### 16.5 事件流与前端

agentic 的事件类型：

- `PlanEvent`
- `TitleEvent`
- `StepEvent`
- `MessageEvent`
- `ToolEvent`
- `WaitEvent`
- `ErrorEvent`
- `DoneEvent`

事件传输方式：

- `AgentTaskRunner` 把事件写入 task output stream。
- `AgentService.chat()` 从 output stream 读取事件。
- `EventMapper` 把领域事件转成 SSE event。
- `session/{session_id}/chat` 使用 `EventSourceResponse` 推送给前端。
- 会话列表也支持 SSE 流式刷新。

对 `llmops` 的结论：

- v1 不需要接 SSE，继续用 DB `TraceEvent` + 手动刷新/短轮询即可。
- 但事件类型应提前对齐：`planner.* / router.* / worker.* / tool.* / wait / done / error`。
- 后续接 SSE 时，可以从 `TraceEvent` 或任务运行事件流映射到前端，不需要推翻 plan/step/worker 数据结构。

### 16.6 A2A 在 agentic 中的位置

关键代码：

- `agentic/api/app/core/tools/a2a.py`
- `agentic/api/app/core/entities/app_config.py`
- `agentic/api/app/controllers/app_config.py`

agentic 的 A2A 是工具，不是内部计划协议：

- A2A 配置包含 `id / base_url / enabled`。
- 初始化时拉取 `{base_url}/.well-known/agent-card.json`。
- 缓存 agent card，避免每次工具调用都重新请求。
- 向 LLM 暴露两个工具：
  - `get_remote_agent_cards`
  - `call_remote_agent(id, query)`
- 调远程 Agent 时使用 JSON-RPC，method 为 `message/send`。
- A2A 客户端每个任务初始化一次，任务结束后清理 http client 和缓存。

对 `llmops` 的结论：

- A2A 不应作为 v1 内部核心协议。
- A2A 最适合作为后续 `external_worker` 或 `a2a_worker` executor。
- 对 Planner 来说，A2A Agent 后续应表现为一个 Worker descriptor：有 id、name、description、skills、endpoint、policies。
- 对 RouterPlan 来说，内部 Worker 和 A2A Worker 都应该被统一成 `RouterPlanStep.worker_id`。
- 对执行链来说，A2A 调用结果必须归一化成 `WorkerResult`。

### 16.7 MCP 在 agentic 中的位置

关键代码：

- `agentic/api/app/core/tools/mcp.py`
- `agentic/api/app/core/entities/app_config.py`

agentic 的 MCP 是外部工具接入：

- 支持 `stdio / sse / streamable_http`。
- 初始化时连接所有配置的 MCP server。
- 缓存 `ClientSession` 和工具 schema。
- 对工具名加 `mcp_{server}_{tool}` 前缀，避免冲突。
- LLM 调用工具后，MCP manager 找到对应 server 和 tool，执行 `session.call_tool()`。
- 任务结束后清理 session、tool schema 和上下文。

对 `llmops` 的结论：

- MCP 更适合作为 Worker Agent 的 capability/tool，不是 Planner v1 的能力。
- 后续可把 MCP 工具接入平台 Capability 管理，受权限、密钥、审计、审批约束。
- Planner 只需要知道某个 Worker 具备哪些能力摘要，不直接拿 MCP tool schema。

### 16.8 最终目标对齐

用户希望的最终形态：

```text
对外暴露的自主 Agent App
  -> Planner/Router Agent
  -> 生成和维护全局 RouterPlan
  -> 调用多个独立 Worker Agent
       -> 内部 App Worker
       -> Workflow Worker
       -> ReAct Worker
       -> A2A Remote Agent Worker
       -> MCP/Tool Capability Worker
  -> 收集 WorkerResult
  -> 必要时重规划
  -> 汇总最终结果
```

这与 agentic 的方向一致，但 llmops 的实现边界不同：

- agentic 是单个自主 Agent 内部持有 Planner + ReAct + tools。
- llmops 应是平台化 Router Agent 编排多个独立 Worker Agent。
- agentic 的 A2A 是 ReAct 工具；llmops 中 A2A 应升级为一种外部 Worker Agent 接入方式。
- agentic 的事件是 SSE-first；llmops v1 先 DB trace-first，后续再 SSE。

### 16.9 不应推翻的架构约束

为了避免后续返工，应固定以下约束：

- Planner/Router Agent 是对外暴露的自主 Agent App。
- Worker Agent 是独立执行单元，可以被多个 Planner 绑定和调用。
- 全局计划只能由 Planner/Router 生成和更新。
- Worker 不修改全局计划，只返回 `WorkerResult`。
- Planner 不直接执行工具，只选择 Worker 和维护计划。
- 内部 Worker、A2A Worker、Workflow Worker 后续都统一表现为 Worker descriptor。
- 所有 Worker 输出都必须归一化成 `WorkerResult`。
- 所有运行事件都必须归一化成 `TraceEvent`。
- UI 优先复用会话记录和任务详情，不提前做复杂调试台。

### 16.10 对当前 v1 的影响

这轮深度调研不推翻当前 v1，反而确认 v1 的最小路线是正确的：

```text
RouterPlannerAgent.create_plan()
  -> RouterPlan
  -> validate
  -> fallback
  -> AgentTask / AgentPlan / AgentStep
  -> WorkerRuntime.invoke()
  -> WorkerResult
  -> TraceEvent
```

但 v1 实现时必须给后续留出以下扩展点：

- `RouterPlannerAgent.update_plan()` 方法位置可以预留，但不启用。
- `PlannerInput` 要能容纳 Worker capability 摘要，后续支持 A2A agent card。
- `RouterPlanStep` 继续保留 `dependencies / execution_mode / required_approval`。
- `WorkerRuntime` 后续可以按 `target_ref_type` 扩展 `app / workflow / a2a / mcp / sandbox`。
- `TraceEvent` 的 event_type 命名要能覆盖 planner、router、worker、tool、wait、done、error。

因此，当前落地不应扩大到 A2A、SSE、动态重规划或版本管理；但数据结构和模块边界必须按最终自主 Agent 平台来设计。
