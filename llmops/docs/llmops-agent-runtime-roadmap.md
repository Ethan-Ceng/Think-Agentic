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

必须验证：

- 创建 WorkerAgent。
- 创建 PlannerAgent。
- PlannerAgent 绑定一个或多个 WorkerAgent。
- AI 应用列表和详情页展示类型标签。
- WorkerAgent 仍能通过原调试流正常回复。
- PlannerAgent 通过“预览与调试”提交问题。
- PlannerAgent 调试请求使用 `/apps/{app_id}/debug-chat`。
- 多轮短追问能继承上下文。
- 多 Worker 场景下能选择合理 Worker。
- Planner 输出非法时 fallback 到 `manager_rule_v1`。
- Planner 试图调用未绑定 Worker 时 fallback 或拒绝。
- v1 出现 async / approval plan 时被校验拒绝。
- 停止调试可终止前端等待状态。
- 任务页能看到 plan、step、worker call、trace、fallback 原因和 artifact。

建议补充的 WorkerAgent 模板：

- 实时天气 Worker。
- 搜索 Worker。
- 通用问答 Worker。
- 数据分析 Worker。
- 文档总结 Worker。

用户提示口径：

- Planner 编排成功但 Worker 能力不足时，应提示“当前绑定 Worker 不具备该实时能力”，并建议绑定对应能力 Worker。
- 不应把这类问题描述为 Planner 上下文错误。

## 7. v2：动态重规划

目标：让 PlannerAgent 从“一次性任务拆分器”升级为“可根据执行结果调整后续步骤的编排 Agent”。

核心待办：

- 实现 `RouterPlannerAgent.update_plan()`。
- Step 执行后把 `WorkerResult`、错误、证据、artifact、trace 摘要传回 Planner。
- Planner 只能修改未执行 step，不能修改已完成 step。
- 重规划结果仍必须经过 `RouterPlan` schema 和 `RouterRuntime.validate_plan()`。
- 重规划失败时继续 fallback，不阻断已有任务。
- 新增 `planner.replan.started / planner.replan.generated / planner.replan.validated / planner.replan.fallback` trace。
- 任务页展示原计划、重规划原因和新计划。

典型场景：

- Worker 查询失败，Planner 改派搜索 Worker 或备用 Worker。
- Worker 输出不完整，Planner 增加补充步骤。
- 用户在对话中改变目标，Planner 调整后续步骤。

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

## 10. v5：Worker executor 扩展

目标：把 Worker 从当前 App Worker 扩展为统一执行器生态，同时保持 Planner 协议稳定。

候选执行类型：

| target_ref_type | 说明 |
| --- | --- |
| `app` | 现有 WorkerAgent |
| `workflow` | 直接调用工作流 |
| `mcp` | MCP 工具集合 Worker |
| `a2a` | 外部 Agent Worker |
| `sandbox` | 代码、浏览器、文件执行环境 |
| `api` | 外部服务封装 Worker |

规则：

- Planner 只面向 Worker descriptor 和 `WorkerResult`。
- WorkerRuntime 根据 `target_ref_type` 派发到不同 executor。
- 每个 executor 必须把输出归一化为 `WorkerResult`。
- A2A 和 MCP 不作为 Planner v1 的内部核心协议，而是 Worker executor 的扩展。

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

不建议直接迁移的部分：

- 不整体迁移 agentic 的 `PlannerReActFlow` 状态机。
- 不把 A2A 作为 Planner v1 内部核心协议。
- 不把 MCP 直接暴露给 Planner。
- 不把单 Agent 内部 memory 系统复制到平台层。

`llmops` 和 agentic 的关系：

- `llmops` 做平台控制面、运行治理和多 Agent 编排。
- agentic 的 Planner/ReAct 思想作为运行面能力来源。
- `llmops` 中的 PlannerAgent 编排多个独立 WorkerAgent。
- agentic 中的工具、A2A、MCP 思路后续可作为 Worker executor 或 Worker capability 接入。

## 13. 推荐推进顺序

1. v1 收尾：验收清单、任务页验证、Worker 模板、能力不足提示。
2. v2 动态重规划。
3. v3 等待用户输入和人工审批。
4. v4 并行 DAG。
5. v5 Worker executor 扩展。
6. v6 评估、治理和生产化。

当前不建议插入的大改：

- 不重做 AI 应用版本体系。
- 不新增独立 Planner 控制台。
- 不提前引入复杂 DAG UI。
- 不在 Planner 中直接执行工具。
- 不把 A2A/MCP 做成 Planner v1 的主协议。
