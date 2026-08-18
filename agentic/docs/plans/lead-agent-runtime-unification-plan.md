# Lead Agent Runtime Unification 实施计划

> 后续边界修订：本计划中的 Tool Approval 测试是实施当时的历史基线。当前新 Run 不再产生工具审批，`WAITING` 只用于用户业务输入；有效迁移见 `remove-tool-approval-plan.md`。

## 关联设计

- 设计文档：`agentic/docs/designs/lead-agent-runtime-unification.zh-CN.md`
- 开发分支：`feature/lead-agent-runtime-unification`
- 实施基线：最新 `develop`
- 后续计划：`agentic/docs/plans/durable-solo-lead-runtime-plan.md`
- 约束：本批不实现 Durable Runtime、Child Agent/A2A 内部委派、真正 Token Delta Streaming 或 Sandbox 重构。

## 当前进度

- 整体状态：`READY_TO_MERGE`
- 当前阶段：completed
- 当前任务：无
- 已完成：9 / 9
- 阻塞问题：无
- 最近更新时间：2026-08-18（Asia/Shanghai）

## 本批交付边界

本计划把 `PlannerAgent + ReActAgent + PlannerReActFlow` 的顶层身份统一为一个 `LeadAgent`。`PlannerAgent` 与 `ReActAgent` 在迁移期只作为 Lead 内部策略实现，不再由 `AgentTaskRunner` 直接编排。Lead 每个普通 Run 只做一次首轮结构化决策，并在 `direct`、`react`、`plan` 三条路径中选择最轻的充分路径。

本批必须实现：

- 判别联合 `LeadDecision` 与服务端确定性校验；
- Direct 单模型调用快路径；
- 无用户可见 Plan 的 React Tool Loop；
- Lead 持有的 Plan Loop 与失败/阻塞时条件重规划；
- 现有 Tool、Skill、附件、HITL、Session Event 和 Trace 投影兼容；
- Feature Flag 回滚到 Legacy Planner-ReAct；
- 决策、调用次数、事件顺序和代表任务集回归测试。

本批明确不做：

- Durable Run/Execution/Lease/Outbox 数据库状态机；
- Lead 到本地 Child Agent 的 fan-out/fan-in；
- A2A 协议重构；A2A 继续作为现有外部 Tool Adapter；
- 流式接口从 Event Streaming 升级为 Token Delta Streaming；
- 删除 Legacy `PlannerReActFlow`；它在本批作为关闭开关后的回退实现保留。

## 全局约束

- `AgentTaskRunner` 在新代码路径中只面向一个 Lead 顶层接口，不根据模式自行编排 Planner/ReAct。
- Direct 必须无 Tool Call、无 Plan/Step Event，并直接复用决策调用的答案，禁止再调用 Summarizer。
- React 必须无 Plan/Step Event；需要工具或 HITL 时继续复用现有 ReAct Memory、Tool Loop 和审批语义。
- Plan 只有在复杂任务中出现；成功步骤不得固定触发 Planner 更新，只有失败、阻塞或明确的新事实信号才允许重规划。
- 一个 Step 的 Plan 在服务端确定性降级为 React；空 Plan 或非法 Capability 不得静默进入执行。
- Feature Flag 关闭时，新 Run 完整回到现有 `PlannerReActFlow` 行为。
- 不自动提交、推送、创建 PR 或合并；所有状态变化、执行结果和验证证据即时写回本计划。

## 状态变更记录

| 日期时间 | 整体状态 | 当前任务 | 变更原因 |
| --- | --- | --- | --- |
| 2026-08-18（Asia/Shanghai） | `PLAN_READY` | 无 | 设计已确认；将行为路由改造从 Durable Runtime 中拆为独立前置批次 |
| 2026-08-18（Asia/Shanghai） | `IN_PROGRESS` | Task 1 | 已创建 `feature/lead-agent-runtime-unification` 分支，开始测试先行实现决策契约 |
| 2026-08-18 09:00（Asia/Shanghai） | `IN_PROGRESS` | Task 2 | Task 1 契约、硬约束和单步降级验证通过，进入 Lead 门面接线 |
| 2026-08-18 09:04（Asia/Shanghai） | `IN_PROGRESS` | Task 3 | Runner 已只面向 Lead，Direct 与关闭开关回退通过验证 |
| 2026-08-18 09:08（Asia/Shanghai） | `IN_PROGRESS` | Task 4 | React Goal、Tool/HITL 恢复和 Skill Runtime 回归通过 |
| 2026-08-18 09:13（Asia/Shanghai） | `IN_PROGRESS` | Task 5 | Plan 状态已收归 Lead，成功零模型重规划、失败条件重规划和 Plan HITL 恢复通过 |
| 2026-08-18 09:16（Asia/Shanghai） | `IN_PROGRESS` | Task 6 | Lead 策略、回退、重规划和完成 Trace 已通过投影测试 |
| 2026-08-18 09:21（Asia/Shanghai） | `VERIFYING` | Task 7 | 10 项代表路由契约、74 项 Agent 核心回归、Skill 集成和全量 Ruff 通过；因缺少目标生产模型在线评测，默认开关保持关闭 |
| 2026-08-18 09:22（Asia/Shanghai） | `REVIEWING` | Task 7 | 最终验证首轮 103 项通过，进入独立代码审查；尚不能标记 READY_TO_MERGE |
| 2026-08-18 09:34（Asia/Shanghai） | `READY_TO_MERGE` | 无 | 自审发现的 3 个恢复连续性 major 已修复；修复后 106 项回归、Ruff、编译与差异检查通过，无未解决 blocking/major |
| 2026-08-18 09:39（Asia/Shanghai） | `IN_PROGRESS` | Task 8 | 用户审查指出新增 Lead/Goal Prompt 只有中文，而现有 `prompts/en` 镜像未同步；开始双语对齐和回归验证 |
| 2026-08-18 09:44（Asia/Shanghai） | `READY_TO_MERGE` | 无 | Lead Decide、React Goal 与全局语言策略已中英对齐，英文 React 镜像已同步；修复后 107 项回归与全部静态检查通过 |
| 2026-08-18 10:00（Asia/Shanghai） | `IN_PROGRESS` | Task 9 | 对照 `mooc-manus/api` 确认中英 Prompt 资产均未接入运行时 locale；根因定位为模块级 Prompt 与持久化 System Memory 绑定，开始 Catalog 修复 |
| 2026-08-18 10:14（Asia/Shanghai） | `VERIFYING` | 最终验证与增量代码审查 | Prompt Catalog、跨 Run System Prompt 视图覆盖、Legacy/Lead/HITL 语言选择已实现；19 项 Locale 回归和 96 项 Agent 核心回归通过 |
| 2026-08-18 10:18（Asia/Shanghai） | `READY_TO_MERGE` | 无 | 增量审查发现并修复非中文 CJK 标签误选中文 Pack；21 项 Locale 回归、128 项最终聚焦回归、Ruff、编译与差异检查通过，审查 `APPROVED` |

## Task 1：建立 Lead 决策契约、Prompt 与确定性边界

状态：completed

### 目标

建立稳定的 `direct | react | plan` 判别联合，使首轮模型输出可以被严格解析、校验和降级，不让“空任务列表代表直接回答”成为隐含协议。

### 涉及文件

- `agentic/api/app/core/entities/lead.py`（新建）
- `agentic/api/app/core/prompts/lead.py`（新建）
- `agentic/api/app/core/agent/lead_decision.py`（新建）
- `agentic/api/app/core/agent/planner.py`
- `agentic/api/tests/app/core/agent/test_lead_decision.py`（新建）

### 实施步骤

1. 定义 `LeadMode`、`DirectDecision`、`ReactDecision`、`PlanDecision` 和判别联合 `LeadDecision`；字段禁止额外输入。
2. 定义只接收 Capability Catalog 摘要、不接收 Tool Schema 的 Decide Prompt，明确三种模式的充分必要条件和输出 JSON。
3. 实现 `LeadDecisionPolicy`，复用现有 LLM、Memory 和 JSON Parser，但不暴露 Planner 顶层身份。
4. 服务端过滤未知 Capability；附件、显式外部动作、时效信息等硬约束不能进入 Direct。
5. 将单步 `PlanDecision` 确定性转换为 `ReactDecision`；拒绝空 Plan、空 Answer、空 Goal 等非法输出。
6. 增加契约、非法输出、Capability 过滤和单步降级单元测试。

### 验证方式

- `uv run pytest tests/app/core/agent/test_lead_decision.py -q`
- `uv run ruff check app/core/entities/lead.py app/core/prompts/lead.py app/core/agent/lead_decision.py tests/app/core/agent/test_lead_decision.py`
- `uv run python -m py_compile app/core/entities/lead.py app/core/prompts/lead.py app/core/agent/lead_decision.py`

### 完成条件

- 任意决策只能属于一种模式；非法或越权输出被稳定拒绝或按规定降级，且无需 Tool Schema 即可决策。

### 执行结果

已新增严格的 Lead 决策领域模型、独立 Decide Prompt 和 `LeadDecisionPolicy`。决策阶段不接收 Tool Schema；Direct 硬约束、Capability 过滤以及单步 Plan 降级均在服务端执行。测试先确认模块缺失，再完成最小实现并通过。

### 验证证据

```text
2026-08-18 09:00 +08:00
- uv run pytest tests/app/core/agent/test_lead_decision.py -q
  Exit 0: 8 passed。
- uv run ruff check app/core/entities/lead.py app/core/prompts/lead.py app/core/agent/lead_decision.py tests/app/core/agent/test_lead_decision.py
  Exit 0: All checks passed。
- uv run python -m py_compile app/core/entities/lead.py app/core/prompts/lead.py app/core/agent/lead_decision.py
  Exit 0。
```

## Task 2：建立 LeadAgent 门面、Direct 快路径与 Legacy 回退

状态：completed

### 目标

让 `AgentTaskRunner` 只调用 `LeadAgent`，在开关开启时运行 Direct 快路径，在开关关闭或策略初始化失败时按明确规则委派 Legacy Flow。

### 涉及文件

- `agentic/api/app/core/agent/lead.py`（新建）
- `agentic/api/app/core/agent/agent_task_runner.py`
- `agentic/api/app/core/config.py`
- `agentic/api/tests/app/core/agent/test_lead_agent_direct.py`（新建）
- `agentic/api/tests/app/core/agent/test_agent_task_runner_completion.py`

### 实施步骤

1. 定义与现有 Flow 调用面兼容的 `LeadAgent.run()`、Skill Runtime、Tool 刷新和可用 Tool 查询接口。
2. Lead 开关关闭时封装并调用 Legacy `PlannerReActFlow`，避免 Runner 出现双编排分支。
3. 开关开启时执行一次 `decide()`；Direct 直接发出唯一用户可见 `MessageEvent` 和 `DoneEvent`。
4. Direct 不创建 `PlanEvent/StepEvent/ToolEvent`，不进入 ReAct，不执行 Summarizer。
5. 保持 Session 状态、连续消息领取、附件同步和 Trace Run 生命周期由现有 Runner/Repository 负责。
6. 增加调用次数与事件序列测试，证明 Direct 只有一次模型调用且可通过开关回退。

### 验证方式

- `uv run pytest tests/app/core/agent/test_lead_agent_direct.py tests/app/core/agent/test_agent_task_runner_completion.py -q`
- `uv run ruff check app/core/agent/lead.py app/core/agent/agent_task_runner.py app/core/config.py tests/app/core/agent/test_lead_agent_direct.py`

### 完成条件

- Runner 只认识 Lead 顶层入口；Direct 任务不再承担 Planner → ReAct → Planner Update → Summarizer 链路。

### 执行结果

已新增 `LeadAgent` 顶层门面，`AgentTaskRunner` 不再直接构造 `PlannerReActFlow`。开关关闭时由 Lead 内部委派 Legacy；开关开启且命中 Direct 时只输出 Title、最终 Message 和 Done，不进入 ReAct、Plan 或 Summarizer。配置默认关闭，等待代表任务评测后再决定默认切流。

### 验证证据

```text
2026-08-18 09:04 +08:00
- uv run pytest tests/app/core/agent/test_lead_agent_direct.py tests/app/core/agent/test_lead_decision.py tests/app/core/agent/test_agent_task_runner_completion.py -q
  Exit 0: 22 passed。
- uv run ruff check app/core/agent/lead.py app/core/agent/agent_task_runner.py app/core/config.py tests/app/core/agent/test_lead_agent_direct.py
  Exit 0: All checks passed。
```

## Task 3：实现 React 快路径并保持 Tool、Skill 与 HITL 兼容

状态：completed

### 目标

对一个 Goal 可以完成、但需要一个或多个工具调用的任务直接运行 ReAct Tool Loop，不创建用户可见 Plan，同时保持暂停、审批和恢复语义。

### 涉及文件

- `agentic/api/app/core/agent/lead.py`
- `agentic/api/app/core/agent/react.py`
- `agentic/api/app/core/prompts/react.py`
- `agentic/api/app/core/entities/event.py`
- `agentic/api/tests/app/core/agent/test_lead_agent_react.py`（新建）
- `agentic/api/tests/app/core/agent/test_interaction_resume.py`
- `agentic/api/tests/app/integration/test_skill_runtime_flow.py`

### 实施步骤

1. 为 ReAct 增加 Goal 执行入口，复用现有 Tool Loop、Runtime Tool Scope、附件和 Skill Instructions。
2. React 最终响应直接转换为用户可见 `MessageEvent`，不再经过 Step 总结或 Plan 总结。
3. 为持久化 Interaction 增加最小执行上下文，使恢复时可以确定回到 React Goal，而不是错误读取历史 Plan。
4. 审批/提问恢复继续验证原 Tool Call，并沿用相同 Memory；拒绝、错误和等待事件原样上送。
5. 增加工具成功、工具失败、Ask User、历史 Interaction 读取、Skill 选中和附件输入回归。

### 验证方式

- `uv run pytest tests/app/core/agent/test_lead_agent_react.py tests/app/core/agent/test_interaction_resume.py tests/app/integration/test_skill_runtime_flow.py -q`
- `uv run ruff check app/core/agent/lead.py app/core/agent/react.py app/core/prompts/react.py app/core/entities/event.py tests/app/core/agent/test_lead_agent_react.py`

### 完成条件

- React 任务只有 Decision + Tool Loop 所需模型调用；无 Plan/Step Event，并且 HITL 暂停后可沿原策略恢复。

### 执行结果

已为 ReAct 增加无 Plan 的 Goal 执行与恢复入口。Lead 为 Interaction 持久化 `lead_mode/goal/language/capabilities`，恢复任务据此跳过 Decide，并继续由现有 ReAct Memory 校验原 Tool Call。公共事件类型保持不变，新增字段均为可选。

### 验证证据

```text
2026-08-18 09:08 +08:00
- uv run pytest tests/app/core/agent/test_lead_agent_react.py tests/app/core/agent/test_lead_agent_direct.py tests/app/core/agent/test_interaction_resume.py -q
  Exit 0: 14 passed。
- uv run pytest tests/app/integration/test_skill_runtime_flow.py -q
  Exit 0: 2 passed。
- uv run ruff check app/core/agent/lead.py app/core/agent/react.py app/core/prompts/react.py app/core/entities/event.py app/services/agent_service.py tests/app/core/agent/test_lead_agent_react.py
  Exit 0: All checks passed。
```

## Task 4：将 Plan 状态机收归 Lead 并实现条件重规划

状态：completed

### 目标

让 Lead 拥有 Plan/Step 生命周期，保留复杂任务的可见进度，但取消每个成功 Step 后的固定 Planner Update，并修正“执行失败却标记 completed”的语义。

### 涉及文件

- `agentic/api/app/core/agent/lead.py`
- `agentic/api/app/core/agent/planner.py`
- `agentic/api/app/core/agent/react.py`
- `agentic/api/app/core/entities/lead.py`
- `agentic/api/app/core/entities/plan.py`
- `agentic/api/tests/app/core/agent/test_lead_agent_plan.py`（新建）
- `agentic/api/tests/app/core/agent/test_planner_react_tool_scope.py`

### 实施步骤

1. 将 `PlanDecision` 转换为现有 `Plan`，由 Lead 发出 Title、初始 Message 和 CREATED Plan Event。
2. Lead 顺序执行 Step，持续发出兼容的 STARTED/COMPLETED/FAILED Step Event 与 Tool/Interaction Event。
3. 成功 Step 直接进入下一步；失败、阻塞或显式 `needs_replan` 才调用 Planner 更新后续计划。
4. 修正 Step 终态：`success=false` 必须为 FAILED；失败步骤保留历史，重规划只替换后续未执行部分。
5. 只有 Plan 模式在所有步骤结束后调用一次 Finalizer；Direct/React 禁止进入该路径。
6. 增加成功零重规划、失败一次重规划、无后续步骤失败、最终总结和事件顺序测试。

### 验证方式

- `uv run pytest tests/app/core/agent/test_lead_agent_plan.py tests/app/core/agent/test_planner_react_tool_scope.py -q`
- `uv run ruff check app/core/agent/lead.py app/core/agent/planner.py app/core/agent/react.py app/core/entities/lead.py app/core/entities/plan.py tests/app/core/agent/test_lead_agent_plan.py`

### 完成条件

- 多步复杂任务保留 Plan UX；N 个成功步骤不再产生 N 次 Planner Update；失败状态和条件重规划可由测试稳定证明。

### 执行结果

Lead 现在直接拥有 Plan/Step 循环：成功步骤只做确定性 Plan 状态投影，不调用 Planner；`success=false` 会标记 FAILED，并在失败或 `needs_replan` 时有界调用 Planner 更新后续步骤。Plan Interaction 持久化 Plan/Step ID，恢复时定位原步骤。Plan 模式只在终止时调用一次 Finalizer。

### 验证证据

```text
2026-08-18 09:13 +08:00
- uv run pytest tests/app/core/agent/test_lead_agent_plan.py tests/app/core/agent/test_interaction_resume.py tests/app/core/agent/test_lead_agent_react.py tests/app/core/agent/test_lead_agent_direct.py -q
  Exit 0: 18 passed。
- uv run pytest tests/app/core/agent/test_runtime_tool_scope.py tests/app/core/agent/test_plan_capabilities.py -q
  Exit 0: 12 passed。
- uv run ruff check app/core/agent/lead.py app/core/agent/planner.py app/core/agent/react.py app/core/entities/lead.py app/core/entities/plan.py app/core/prompts/react.py tests/app/core/agent/test_lead_agent_plan.py tests/app/core/agent/test_interaction_resume.py
  Exit 0: All checks passed。
```

## Task 5：补齐策略可观测性、Feature Flag 与兼容投影

状态：completed

### 目标

使每个 Run 可以回答“选了什么模式、为什么、调用了多少次、是否发生回退/重规划”，同时不破坏现有前端事件协议。

### 涉及文件

- `agentic/api/app/core/agent/lead.py`
- `agentic/api/app/core/config.py`
- `agentic/api/app/services/trace_service.py`
- `agentic/api/app/core/entities/event.py`
- `agentic/api/tests/app/services/test_trace_service.py`
- `agentic/api/tests/app/core/agent/test_lead_agent_observability.py`（新建）

### 实施步骤

1. 增加 `lead_agent_enabled` 配置，默认值与切流策略在测试和文档中固定；关闭后只影响新 Run。
2. 记录 mode、reason code、decision latency、model calls、tool calls、replan count、fallback reason 和 final status。
3. 复用现有 Trace Event/Run Step 扩展字段，不新增前端必须理解的公共 Event 类型。
4. 验证旧前端可以忽略新增可选字段；Plan/Step/Message/Tool/Interaction/Wait/Error/Done 形状继续兼容。
5. 增加 Direct/React/Plan/Fallback 的 Trace 投影单元测试。

### 验证方式

- `uv run pytest tests/app/core/agent/test_lead_agent_observability.py tests/app/services/test_trace_service.py -q`
- `uv run ruff check app/core/agent/lead.py app/core/config.py app/services/trace_service.py app/core/entities/event.py tests/app/core/agent/test_lead_agent_observability.py`

### 完成条件

- 可按 Run 比较三种策略的调用与耗时，且开关关闭后无需代码回滚即可恢复 Legacy 行为。

### 执行结果

已新增 `lead.strategy_selected`、`lead.fallback`、`lead.replanned` 与 `lead.completed` Trace 事件，记录模式、Reason Code、决策耗时、重规划次数和终态；模型与工具调用次数继续使用现有 Model Call/Tool Call 投影。`lead_agent_enabled` 当前默认关闭，Runner 实例创建后固定，不在同一运行中热切换。

### 验证证据

```text
2026-08-18 09:16 +08:00
- uv run pytest tests/app/core/agent/test_lead_agent_direct.py tests/app/core/agent/test_lead_agent_react.py tests/app/core/agent/test_lead_agent_plan.py tests/app/services/test_trace_service.py -q
  Exit 0: 17 passed。
- uv run ruff check app/core/agent/lead.py app/core/config.py app/services/trace_service.py app/core/entities/event.py tests/app/core/agent/test_lead_agent_direct.py tests/app/services/test_trace_service.py
  Exit 0: All checks passed。
```

## Task 6：运行代表任务评测与全量行为回归

状态：completed

### 目标

用固定代表任务集验证路由正确性、调用预算、事件兼容和现有 Tool/Skill/HITL 行为，形成是否默认启用 Lead 的证据。

### 涉及文件

- `agentic/api/tests/app/core/agent/test_lead_agent_routing_eval.py`（新建）
- `agentic/api/tests/app/core/agent/`
- `agentic/api/tests/app/integration/`
- `agentic/docs/designs/lead-agent-runtime-unification.zh-CN.md`
- `agentic/docs/plans/durable-solo-lead-runtime-plan.md`

### 实施步骤

1. 固定至少 10 个简单问答、单目标工具、多步骤复杂、附件、时效信息和 HITL 代表任务。
2. 验证 Direct 1 次、React 不含 Plan 更新、Plan 成功路径零重规划，失败路径按信号重规划。
3. 运行现有 Agent、Tool Scope、Skill、附件、Interaction Resume、Branch Context 和完成状态回归。
4. 根据评测结果决定默认开关；若未达到设计阈值，保持默认关闭并记录差距，不以人工判断替代证据。
5. 更新设计文档“当前实现状态”，并把 Durable 计划的 Harness 输入改为稳定后的 Lead 顶层接口。

### 验证方式

- `uv run pytest tests/app/core/agent tests/app/integration/test_skill_runtime_flow.py -q`
- `uv run pytest tests/app/core/agent/test_lead_agent_routing_eval.py -q`
- `uv run ruff check app tests/app/core/agent tests/app/integration/test_skill_runtime_flow.py`

### 完成条件

- 代表任务集和现有关键回归通过；默认开关有量化依据；Durable 计划不再与本计划争夺顶层状态机职责。

### 执行结果

已建立 10 项离线代表路由契约，覆盖 3 个 Direct、4 个 React 和 3 个 Plan 场景；完整 Agent 核心回归 74 项通过。评测同时发现并修正了“翻译文本中出现今天/天气被误判为时效请求”的硬约束误报。当前环境未提供目标生产模型凭据和预发布延迟基线，因此没有把离线契约测试冒充真实模型路由准确率；按计划保持 Feature Flag 默认关闭，并在设计文档明确切流前证据缺口。Durable 计划已改为消费稳定后的 Lead 顶层接口。

### 验证证据

```text
2026-08-18 09:21 +08:00
- uv run pytest tests/app/core/agent/test_lead_agent_routing_eval.py tests/app/core/agent/test_lead_decision.py -q
  Exit 0: 19 passed。
- uv run pytest tests/app/core/agent -q
  Exit 0: 74 passed。
- uv run pytest tests/app/integration/test_skill_runtime_flow.py -q
  Exit 0: 2 passed。
- uv run ruff check app tests/app/core/agent tests/app/integration/test_skill_runtime_flow.py
  Exit 0: All checks passed。
- git diff --check
  Exit 0；仅输出 Windows 工作区 LF/CRLF 转换警告，无 whitespace error。
- 限制：未运行目标生产模型在线路由准确率、TTFT/总延迟评测；因此 `lead_agent_enabled` 保持默认 false。
```

## Task 7：最终验证、代码审查与合并判断

状态：completed

### 目标

对本批设计一致性、正确性、兼容性、安全性、测试质量和文档状态做最终门禁，只在最新证据支持时给出 `READY_TO_MERGE`。

### 涉及文件

- 本计划涉及的全部代码、测试与文档
- `agentic/docs/plans/lead-agent-runtime-unification-plan.md`

### 实施步骤

1. 运行目标测试、Agent 核心回归、Ruff、编译检查和仓库已有适用构建检查。
2. 依据设计验收项逐条核验 Direct/React/Plan、HITL、Feature Flag、事件兼容与调用次数。
3. 执行独立代码审查，按 blocking/major/minor/suggestion 分级并修复 blocking/major。
4. 修复后重新运行受影响验证，不复用修复前结果。
5. 将实际命令、退出码、关键输出、未覆盖风险、最终状态和时间写回本计划。

### 验证方式

- `uv run pytest tests/app/core/agent -q`
- `uv run pytest tests/app/integration/test_skill_runtime_flow.py -q`
- `uv run ruff check app tests/app/core/agent tests/app/integration/test_skill_runtime_flow.py`
- `uv run python -m compileall -q app/core/agent app/core/entities app/core/prompts`
- `git diff --check`

### 完成条件

- 最新验证全部通过；无未解决 blocking/major；计划状态明确为 `READY_TO_MERGE`、`BLOCKED` 或 `FAILED`。

### 执行结果

- 完成最终设计一致性、正确性、兼容性、安全性和测试质量自审；审查记录见 `agentic/docs/reviews/lead-agent-runtime-unification-review.md`。
- 审查发现并修复 3 个 major：在途 Lead 恢复被开关切到 Legacy、HITL 恢复丢失 Skill、Plan 重规划次数在恢复后重置。
- 修复后无未解决 blocking/major；保留一个 Legacy 私有 Runtime 成员耦合的 minor 迁移债务。
- 目标生产模型在线准确率与延迟尚未验证，因此 Feature Flag 默认关闭，不阻止代码合并但阻止默认启用。

### 验证证据

```text
uv run pytest tests/app/core/agent tests/app/core/test_interaction_events.py tests/app/core/test_config.py tests/app/services/test_trace_service.py tests/app/services/test_agent_interactions.py tests/app/services/test_agent_service_recovery.py tests/app/interfaces/endpoints/test_session_interactions.py tests/app/integration/test_skill_runtime_flow.py -q
Exit 0: 106 passed，10 个既有 Pydantic deprecation warnings。

uv run ruff check app tests/app/core/agent tests/app/core/test_interaction_events.py tests/app/core/test_config.py tests/app/services/test_trace_service.py tests/app/services/test_agent_interactions.py tests/app/services/test_agent_service_recovery.py tests/app/interfaces/endpoints/test_session_interactions.py tests/app/integration/test_skill_runtime_flow.py
Exit 0: All checks passed。

uv run python -m compileall -q app/core/agent app/core/entities app/core/prompts app/services
Exit 0。

git diff --check
Exit 0；仅输出 Windows 工作区 LF/CRLF 转换警告，无 whitespace error。
```

## Task 8：Lead 双语 Prompt 对齐

状态：completed

### 目标

修正本批新增 Lead/React Prompt 只有中文以及全局默认中文规则与英文输入冲突的问题，使中英文用户输入都能稳定获得同语言的路由字段、工具自然语言参数和最终回复。

### 涉及文件

- `agentic/api/app/core/prompts/lead.py`
- `agentic/api/app/core/prompts/react.py`
- `agentic/api/app/core/prompts/en/react.py`
- `agentic/api/app/core/prompts/system.py`
- `agentic/api/app/core/prompts/en/system.py`
- `agentic/api/tests/app/core/agent/test_lead_decision.py`
- 关联设计、计划与审查文档

### 执行结果

- Lead Decide 采用精简中英双语规则；Decide 前不使用字符启发式切换 Prompt，用户消息、附件和 Capability Catalog 只注入一次。
- 语言策略改为：明确指定的输出语言优先；否则使用最新用户消息的主要语言；无法判断时才使用默认回退语言。
- React Goal 的执行、进度、询问和最终 JSON 约束中英对齐；`prompts/en/react.py` 同步 `needs_replan`、`replan_reason` 与 Goal Prompt。
- 增加 Prompt 双语契约测试；不改变 Lead Runtime 状态机、Tool Scope、事件或持久化协议。

### 验证证据

```text
uv run pytest tests/app/core/agent/test_lead_decision.py tests/app/core/agent/test_lead_agent_react.py tests/app/core/agent/test_lead_agent_plan.py -q
Exit 0: 17 passed。

最终聚焦回归：107 passed。
Ruff、compileall、git diff --check：Exit 0。
```

## Task 9：恢复 Prompt Locale 运行时路由

状态：completed

### 目标

把现有 `prompts/en` 从静态镜像接入生产运行链路；Lead Decide 保持双语，决策后的 Planner/ReAct/Finalizer 按当前 Run 的工作语言选择中文或英文 Prompt，并允许同一持久化 Memory 跨 Run 正确切换。

### 涉及文件

- `agentic/api/app/core/prompts/catalog.py`（新建）
- `agentic/api/app/core/prompts/planner.py`
- `agentic/api/app/core/prompts/react.py`
- `agentic/api/app/core/prompts/system.py`
- `agentic/api/app/core/prompts/en/planner.py`
- `agentic/api/app/core/prompts/en/react.py`
- `agentic/api/app/core/prompts/en/system.py`
- `agentic/api/app/core/agent/base.py`
- `agentic/api/app/core/agent/planner.py`
- `agentic/api/app/core/agent/react.py`
- `agentic/api/app/core/agent/lead.py`
- `agentic/api/app/core/flows/planner_react.py`
- `agentic/api/tests/app/core/agent/test_prompt_locale_routing.py`（新建）
- 关联设计、调试、计划与审查文档

### 实施步骤

1. 测试先行覆盖 locale 标签/首轮文本解析、中文与英文 Prompt Pack、用户输入只注入一次以及跨 Run System Prompt 视图覆盖。
2. 建立只包含 `zh/en` 的 Prompt Catalog；未知非中文 language 使用英文指令模板，不修改输出 language。
3. 为 BaseAgent 增加本次调用的 Runtime System Prompt 覆盖，只修改 LLM messages 副本，不迁移或污染持久化 Memory。
4. Planner 首轮按用户消息选择 Pack，Update 按 `plan.language`；React Goal/Step/Resume/Finalize 按已决策或持久化 language。
5. 同步英文 Planner 的 Capability Catalog 契约以及英文 System 的品牌/A2A 能力，删除执行阶段主 Prompt 中临时重复的英文规则。
6. 运行聚焦回归、完整 Agent 回归、Ruff、compileall 和 diff 检查，再做增量代码审查。

### 验证方式

- `uv run pytest tests/app/core/agent/test_prompt_locale_routing.py -q`
- `uv run pytest tests/app/core/agent tests/app/core/test_interaction_events.py tests/app/core/test_config.py tests/app/services/test_trace_service.py tests/app/services/test_agent_interactions.py tests/app/services/test_agent_service_recovery.py tests/app/interfaces/endpoints/test_session_interactions.py tests/app/integration/test_skill_runtime_flow.py -q`
- `uv run ruff check app tests/app/core/agent`
- `uv run python -m compileall -q app/core/agent app/core/flows app/core/prompts`
- `git diff --check`

### 完成条件

- 英文 Prompt 有生产调用者；中英 Pack 契约一致；跨 Run 与 HITL 恢复选择正确；最新验证通过且无未解决 blocking/major。

### 执行结果

- 新增 `PromptLocale`、Planner/React Prompt Pack 与语言解析；`prompts/en` 现在由生产 Catalog 导入。
- Lead Decide 改用独立的精简双语 System Prompt，不再拼接与决策无关的完整 Tool/Browser/Sandbox 规则。
- BaseAgent 在每次 LLM messages 副本中覆盖当前 System Prompt，持久化 Memory 保持原样；同一 Agent 连续中英 Run 与重建 Agent 后 HITL Resume 均已回归。
- Planner 首轮按用户消息选择 Pack、Update 按 Plan language；React Goal/Step/Resume/Finalizer 按 Lead/Plan 持久化 language。
- 英文 System、Planner、React 已同步品牌、A2A、Capability、重规划和 Goal 契约，并修复英文 JSON 示例尾逗号；中文/英文 Planner 用户消息都只注入一次。

### 验证证据

```text
RED: uv run pytest tests/app/core/agent/test_prompt_locale_routing.py -q
Exit 1: 测试收集失败，ModuleNotFoundError: app.core.prompts.catalog；确认当前没有 Prompt Locale 运行时抽象。

GREEN: uv run pytest tests/app/core/agent/test_prompt_locale_routing.py -q
Exit 0: 21 passed；包含增量审查新增的非中文 CJK 标签回归。

uv run pytest tests/app/core/agent -q
Exit 0: 96 passed，10 个既有 Pydantic deprecation warnings。

uv run ruff check app/core/agent app/core/flows app/core/prompts tests/app/core/agent
Exit 0: All checks passed。

git diff --check
Exit 0；仅 Windows LF/CRLF 转换警告。

最终聚焦单元/集成回归
Exit 0: 128 passed，10 个既有 Pydantic deprecation warnings。
```

## 最终验证结论

- 状态：`READY_TO_MERGE`
- 执行时间：2026-08-18 10:18 +08:00
- 单元/集成回归：`uv run pytest tests/app/core/agent tests/app/core/test_interaction_events.py tests/app/core/test_config.py tests/app/services/test_trace_service.py tests/app/services/test_agent_interactions.py tests/app/services/test_agent_service_recovery.py tests/app/interfaces/endpoints/test_session_interactions.py tests/app/integration/test_skill_runtime_flow.py -q`，Exit 0，128 passed，10 个既有 Pydantic deprecation warnings。
- 静态检查：`uv run ruff check app/core/agent app/core/flows app/core/prompts tests/app/core/agent`，Exit 0，All checks passed。
- 编译检查：`uv run python -m compileall -q app/core/agent app/core/entities app/core/flows app/core/prompts app/services`，Exit 0。
- 差异检查：`git diff --check`，Exit 0；只有 Windows LF/CRLF 转换警告。
- Git：当前分支 `feature/lead-agent-runtime-unification`；工作区改动范围已知。`app/core/prompts/system.py` 的品牌文案行不是本计划产生，原样保留；Task 8 只修改其 `<language_settings>`。未跟踪的 `mooc-manus/` 是用户提供的只读参考目录，不属于本批交付且未修改。
- 未验证项：目标生产模型的真实路由准确率、TTFT 和总延迟；因此 Feature Flag 默认关闭。
- 代码审查：`agentic/docs/reviews/lead-agent-runtime-unification-review.md`，结论 `APPROVED`；3 个恢复连续性 major 与 2 个 Prompt Locale major 均已修复，无未解决 blocking/major。
- 当前结论：`READY_TO_MERGE`。9 个 Task 全部完成，最新完整验证与增量复审通过；等待用户明确授权后再提交、推送、创建 PR 或合并。
