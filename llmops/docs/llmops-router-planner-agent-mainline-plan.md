# LLMOps Router Planner Agent 主线实施计划

本文档记录当前 Agent 增强完成后的下一条主线：实现 Router Planner Agent v1。

目标不是重新设计 Router/Worker 全链路，而是在现有 Worker Agent 执行底座、会话记录执行台、AgentTask/AgentPlan/AgentStep/WorkerCall/TraceEvent 数据结构之上，补上 LLM Planner 生成结构化计划的能力。

## 1. 当前状态

已完成的前置能力：

- Worker Agent 执行底座已完成。
- `WorkerRuntime -> ReActWorkerAgent -> AppExecutor` 已能调用 App Worker。
- `WorkerInvocation.context.input_files` 已支持输入文件引用。
- `WorkerResult.artifacts` 已支持产物文件引用和后续 step 传递。
- `WorkerResult.events` 已映射到 `TraceEvent`。
- 会话记录页已从只看任务，增强为按 `Conversation / Message` 组织。
- 每轮对话下已能展示关联的 `AgentTask`、plan、step timeline、WorkerCall、TraceEvent、输入文件和产物。

因此，Planner Agent 的调试和观测入口已经具备。后续 Planner 生成的 plan、step、Worker 调用和 trace 可以直接出现在会话记录中。

## 2. 主线目标

Router Planner Agent v1 的核心目标：

- 从用户输入、会话上下文、输入文件和可用 Worker 列表生成 `RouterPlan`。
- 用 LLM Planner 替代当前偏规则式的 `manager_rule_v1` 计划生成。
- 对 LLM 输出做严格 schema 校验，不能直接信任模型 JSON。
- 校验失败时使用规则 fallback，保证任务仍可执行。
- 将计划、步骤、Worker 调用和执行事件写入现有运行面表。
- 创建任务时写入 `conversation_id` 和 `user_input.message_id`，让每轮会话能精确关联 Planner 执行记录。

## 3. v1 非目标

第一版先控制范围，避免一次性做太大：

- 不做并行执行。
- 不做动态重规划。
- 不做审批流。
- 不做 Planner 专属新 UI。
- 不强依赖 SSE 实时推送。
- 不新增数据库迁移，优先使用现有 `AgentTask.user_input.message_id` 做消息关联。

v1 先做到“单轮计划 + 顺序执行 + 可观测 + 可回退”。

## 4. 目标运行链路

```text
Conversation Message
  -> PlannerInput
  -> AgentTask(conversation_id, user_input.message_id)
  -> planner.started TraceEvent
  -> PlannerAgent.create_plan()
  -> RouterPlan
  -> RouterPlanValidator
  -> fallback plan if needed
  -> AgentPlan / AgentStep
  -> sequential WorkerRuntime.invoke()
  -> WorkerCall / WorkerResult / ArtifactRef
  -> TraceEvent
  -> AgentTask.final_result
  -> 会话记录页展示每轮执行详情
```

## 5. PlannerInput

建议新增内部输入对象 `PlannerInput`，由 Router Manager 在创建任务前或创建任务时构造。

字段建议：

| 字段 | 含义 |
| --- | --- |
| `query` | 用户本轮输入 |
| `conversation_id` | 当前会话 ID |
| `message_id` | 当前消息 ID |
| `input_files` | 输入文件引用，来自请求或会话上下文 |
| `conversation_summary` | 长期记忆或会话摘要 |
| `history` | 必要的最近对话轮次 |
| `router_agent` | 当前 Router Agent 配置 |
| `workers` | 已绑定且可用的 Worker 列表 |
| `constraints` | 执行限制，如是否允许并行、最大 step 数、是否需要审批 |

Planner v1 的 `constraints` 应固定为：

- `allow_parallel = false`
- `allow_replan = false`
- `max_steps` 先给一个保守值，比如 5
- `execution_mode = sync`

## 6. RouterPlan 输出

Planner Agent 输出继续使用现有 `RouterPlan` 协议，不新增一套计划结构。

计划至少包含：

- `router_id`
- `user_intent`
- `risk_assessment`
- `steps`
- `final_response_policy`

每个 step 至少包含：

- `step_id`
- `worker_id`
- `task`
- `dependencies`
- `execution_mode`
- `required_approval`

v1 约束：

- `dependencies` 可以为空或只依赖前序 step。
- `execution_mode` 只允许 `sync`。
- `required_approval` 固定为 `false` 或校验后降级。

## 7. Planner Agent 组件

建议按以下组件落地：

### PlannerAgent

负责调用 LLM，生成结构化 `RouterPlan`。

职责：

- 接收 `PlannerInput`。
- 生成 planner prompt。
- 调用 Router Agent 的模型配置。
- 输出 JSON。
- 解析为 `RouterPlan`。

### PlannerPromptBuilder

负责把 Worker 能力、用户目标、文件输入和约束整理成提示词。

提示词必须明确：

- 只能使用给定 Worker。
- 不能发明 Worker ID。
- 每个 step 必须有明确业务任务。
- 输出必须符合 JSON schema。
- 不要输出解释性自然语言。

### RouterPlanValidator

可以优先复用或扩展现有 `RouterRuntime.validate_plan()`。

校验项：

- Worker ID 是否在绑定列表内。
- step 是否为空。
- step_id 是否唯一。
- dependencies 是否引用存在的 step。
- dependencies 是否成环。
- execution_mode 是否允许。
- required_approval 是否符合 v1 限制。
- risk_level 是否在允许范围内。

### FallbackPlanner

当 LLM 失败、JSON 解析失败或校验失败时，生成规则 fallback plan。

规则：

- 如果请求指定 Worker，则按指定 Worker 顺序生成 step。
- 否则选择所有已绑定 Worker，按 priority 或创建顺序生成 step。
- step task 使用用户 query。
- final policy 使用 `summarize_worker_results`。

### PlannerTraceRecorder

也可以不单独抽类，先直接在 `RouterAgentManagerService` 中记录 trace。

v1 应至少写入：

| 事件 | 含义 |
| --- | --- |
| `planner.started` | 开始规划 |
| `planner.generated` | LLM 生成原始计划 |
| `planner.validated` | 计划校验通过 |
| `planner.fallback` | 使用 fallback plan |
| `planner.failed` | Planner 失败 |
| `router.manager_run.created` | 任务和计划已落库 |

## 8. 落库策略

继续使用现有表：

- `AgentTask`：一次 Router Planner 任务。
- `AgentPlan`：Planner 输出的 `RouterPlan`。
- `AgentStep`：计划中的 Worker step。
- `WorkerCall`：每次 Worker 调用。
- `TraceEvent`：Planner、Router、Worker 事件。

关键要求：

- `AgentTask.conversation_id` 必须写入。
- `AgentTask.user_input.message_id` 必须写入。
- `AgentTask.user_input.query` 必须写入。
- `AgentPlan.plan_json` 保存最终可执行 plan，不保存未校验的脏输出。
- LLM 原始输出可以放在 `planner.generated` 的 trace payload 中。
- fallback 原因放在 `planner.fallback` 的 trace payload 中。

## 9. UI 承接

v1 不新增 Planner 专属页面。

当前会话记录页已经可以展示：

- 每轮用户输入和 Agent 回复。
- 每轮关联 AgentTask。
- AgentPlan JSON。
- Step timeline。
- WorkerInvocation / WorkerResult。
- TraceEvent。
- 输入文件和产物文件。

因此，Planner v1 完成后，应通过会话记录页验证：

- 本轮消息下是否出现 Planner 任务。
- 计划是否能展开看到。
- step 是否按顺序展示。
- WorkerCall 是否有 invocation/result。
- 失败原因是否能在 trace 和错误字段里看到。

## 10. 实施顺序

### Step 1：消息关联补强

确保所有入口创建 Router Planner 任务时都传入：

- `conversation_id`
- `message_id`
- `query`
- `input_file_ids`

优先改调用处，不先加 DB 字段。

### Step 2：定义 PlannerInput

在 `domain/agent_runtime` 或 Router Manager 内部新增输入对象。

同时补 Worker 描述：

- Worker ID
- name
- description
- runtime_type
- target_ref_type
- worker_config 摘要
- capability 摘要

### Step 3：实现 LLM PlannerAgent

新增 Planner Agent 生成 `RouterPlan` 的最小实现。

优先使用 Router Agent 当前模型配置，不引入新的模型配置来源。

### Step 4：校验和 fallback

LLM 输出必须经过 `RouterPlanValidator`。

失败时必须走 fallback，并写 trace。

### Step 5：接入 RouterAgentManagerService

把当前 `build_manager_plan()` 的规则生成改成：

```text
try planner.create_plan()
validate plan
except -> fallback plan
```

保留原规则计划函数作为 fallback。

### Step 6：执行和 trace 验证

保持现有顺序执行：

- 创建 `AgentTask`
- 创建 `AgentPlan`
- 创建 `AgentStep`
- 调用 `WorkerRuntime.invoke()`
- 写 `WorkerCall`
- 写 `TraceEvent`
- 合并 `WorkerResult`
- 写 `AgentTask.final_result`

### Step 7：测试

至少补以下测试：

- Planner 成功生成合法 plan。
- Planner 输出非法 Worker ID 时 fallback。
- Planner 输出非法 JSON 时 fallback。
- 计划落库后包含 `conversation_id` 和 `user_input.message_id`。
- 会话详情能把 Planner 任务挂到对应 message。
- WorkerResult artifacts 能进入 task final_result。
- TraceEvent 包含 planner started/generated/validated/fallback。

## 11. 验收标准

Router Planner Agent v1 完成后，应满足：

- 发布页或预览调试发起一次对话后，会话记录中能看到本轮执行。
- 本轮执行下能看到 Planner 生成的 plan。
- plan 中的 step 能被顺序执行。
- 每个 Worker 调用都有 invocation/result。
- 输入文件能进入 WorkerInvocation。
- 产物文件能从 WorkerResult 回到 final_result，并在会话记录中展示。
- Planner 失败不会导致任务不可执行，fallback 能继续生成规则 plan。
- 相关事件能在执行日志中看到。

## 12. 后续增强

v1 稳定后再进入下一阶段：

- 动态重规划。
- 多 Worker 并行。
- Worker 选择评分。
- 审批策略。
- 失败重试。
- SSE 实时推送。
- Planner 专属调试视图。
- 更细粒度的 `message_id` 数据库字段。

## 13. 当前结论

接下来可以进入 Router Planner Agent 主线。

最小可落地范围是：

```text
PlannerInput
  -> LLM PlannerAgent
  -> RouterPlan validate
  -> fallback plan
  -> AgentTask / AgentPlan / AgentStep / TraceEvent
  -> 顺序 WorkerRuntime.invoke()
  -> 会话记录页观测
```

这条路径复用现有 Worker Agent 执行底座和会话记录执行台，风险最小，也最适合作为 Planner Agent 的第一阶段。
