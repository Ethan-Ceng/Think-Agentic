# Lead Agent 统一运行时与执行链路优化设计

## 文档状态

- 状态：`DESIGN_READY`
- 负责人：Agentic Runtime
- 创建日期：2026-08-17
- 最近更新：2026-08-18

## 当前实现状态

- 已在 `feature/lead-agent-runtime-unification` 分支完成 Lead 顶层门面、严格决策契约以及 Direct、React、Plan 三策略实现。
- `AgentTaskRunner` 只构造 `LeadAgent`；Legacy `PlannerReActFlow` 仅作为 Feature Flag 关闭或决策异常时的内部回退策略保留。
- Direct 复用首轮决策答案；React 无 Plan/Step；Plan 成功步骤只做确定性状态投影，失败或 `needs_replan` 才调用 Planner，且只在 Plan 终止时 Finalize。
- React 与 Plan 的 Interaction 均持久化最小恢复上下文，恢复时跳过 Decide 并校验原 Tool Call。
- 当前 `lead_agent_enabled` 默认关闭。离线契约任务集与自动化回归已通过，但尚未使用目标生产模型执行线上/预发布路由准确率与延迟评测；在该证据完成前不默认切流。
- 本文的 Token Delta Streaming、Durable Runtime 与 Child Agent/A2A 内部委派仍为独立后续工作。
- 2026-08-18 后续修订：通用 Tool Approval 已移除，`WAITING` 只用于 `ask_user` 等业务输入；正文若提及 Tool Approval，仅表示该设计落地时的历史基线。

## 一句话结论

用一个面向用户且唯一拥有运行状态的 `LeadAgent` 替代当前固定的 `PlannerAgent + ReActAgent + PlannerReActFlow` 三段式心智；Lead 根据任务显式选择 `direct`、`react` 或 `plan` 策略，简单问答一次模型调用直接完成，单目标工具任务跳过计划更新与总结，只有真正复杂的多步骤任务才创建计划、按需重新规划并最终汇总。

“统一”为统一入口、身份、状态机和策略选择，不是把现有三个模块机械拼接成一个巨型类。迁移期允许复用 Planner/ReAct 代码作为 Lead 的内部策略适配器，但它们不再是并列的长期 Agent 身份，也不能继续独立拥有顶层运行状态。

## 背景

当前 Chat 的核心执行链路由以下三部分组成：

- `PlannerAgent`：创建计划，并在每个步骤结束后更新计划；不接收完整 Tool Schema，也不调用工具。
- `ReActAgent`：执行步骤、运行 Tool Loop、处理 HITL 恢复并生成最终总结。
- `PlannerReActFlow`：在规划、执行、更新计划、总结和完成状态之间切换。

当前主链路对所有用户消息使用相同流程：

```text
Planner 创建计划
  -> ReAct 执行步骤
  -> Planner 更新计划
  -> 重复执行与更新
  -> ReAct 总结
```

该流程适合复杂任务，但对普通问答、文本解释、单次查询和单个文件操作过重。一个无需工具的简单问题也会先生成至少一个步骤；一个单目标工具请求正常完成后仍会进入计划更新和最终总结，带来额外模型调用、延迟、Token 成本和重复回复。

现有 Planner Prompt 允许 `steps=[]`，但其语义是“任务不可行”，不是“已经直接回答”。如果只靠提示词把简单问题改成零步骤，将把直接回答、不可行和规划失败三种状态混在一起，导致 Flow、Trace、UI 和错误处理无法稳定判断真实语义。

产品需要从“固定 Planner/ReAct 工作流”升级为“一个 Lead Agent 按任务复杂度选择最小充分执行策略”。

## 目标

- 所有普通用户请求只通过一个 `LeadAgent.run()` 入口进入 Agent 运行时。
- Lead 对每次新请求显式选择 `direct`、`react` 或 `plan`，不得通过 `steps` 长度隐式猜测模式。
- 无需工具的简单问答只进行一次模型调用，不产生 Plan、Step、Tool、Replan 或 Finalize 调用。
- 单目标工具任务进入 ReAct Tool Loop，但不创建正式 Plan、不调用 Planner Update、不额外调用 Summarizer。
- 多步骤复杂任务才创建 Plan；成功步骤默认直接进入下一步，只有满足明确条件时才 Replan。
- 保持现有 Message、Plan、Step、Tool、Interaction、Wait、Error、Done 事件对前端的兼容语义。
- 保持 Skills、Capability Scope、工具审批、结构化询问、暂停恢复、附件和 Trace 能力不回归。
- Trace 能明确记录本次运行采用的策略、策略选择耗时、模型调用次数和发生 Replan 的原因。
- 迁移完成后，`PlannerReActFlow` 不再是顶层状态所有者；Planner/ReAct 若保留，只能作为 Lead 的内部策略组件。

## 功能范围

本设计包含：

1. 新增唯一的 Lead Agent 运行入口。
2. 定义显式的 `DirectDecision`、`ReactDecision`、`PlanDecision` 输出契约。
3. 定义 Direct、ReAct、Plan 三种执行策略及其服务端校验规则。
4. 将每步无条件更新计划改为按条件 Replan。
5. 将无条件最终总结改为仅 Plan 策略 Finalize。
6. 修正步骤成功与状态的确定性映射，禁止 `success=false` 被标记为 `completed`。
7. 保持不同阶段的 Tool Schema 和 Capability Scope 裁剪。
8. 定义现有 Planner/ReAct/Flow 向 Lead 的渐进迁移和回滚方式。
9. 增加策略路由、调用次数、兼容性和异常回退测试。

## 非功能范围

本设计明确不包含：

- Sandbox 隔离、网络、权限和资源限制整改。
- Durable Runtime、Execution Lease、Outbox、进程重启自动恢复和状态表迁移。
- 内部 Child Agent、Researcher、Reviewer、Worker 或多 Agent 调度。
- Agent Profile、Agent CRUD、发布和 Marketplace。
- Project Memory、Knowledge、RAG 或 ContextCompiler。
- 模型 Provider Registry、模型分级路由和按策略选择不同模型。
- 工具副作用 Ledger、Provider 幂等键和完整重试策略重构。
- Planner/React 历史 Memory 的数据迁移或 Session JSONB 正规化。
- 真正的 Token Delta Streaming。

Token Delta Streaming 是仍需解决的用户体验问题，但它会同时改变 `LLM` 协议、OpenAI Provider、BaseAgent、事件类型、SSE、Trace 和前端消息合并。本设计先消除不必要的模型调用并建立单一 Lead 运行边界；Streaming 应作为下一份独立设计，在 Lead 接口稳定后实施。

## 业务流程

### 总体流程

```text
User Message / Interaction Resolution
                |
                v
          LeadAgent.run()
                |
       +--------+--------+
       |                 |
Interaction Resume   Lead Decide
                         |
             +-----------+-----------+
             |           |           |
           direct      react        plan
             |           |           |
        final answer   tool loop   create plan
             |           |           |
             |       final answer  execute step
             |           |           |
             |           |      replan only if needed
             |           |           |
             |           |        finalize
             +-----------+-----------+
                         |
                       Done
```

### Direct 流程

1. Lead 接收普通用户消息和当前可用的轻量上下文。
2. 决策结果为 `DirectDecision`。
3. 服务端校验 Direct 不包含 Steps、Goal、Capability 或 Tool Call。
4. 输出标题和最终 Assistant Message。
5. 更新 Session/Run 完成状态并输出 Done。
6. 不创建 PlanEvent，不启动 ReAct，不激活 Sandbox，不调用 Finalizer。

### ReAct 流程

1. Lead 判断请求需要环境事实或工具，但目标明确，不值得建立多步骤计划。
2. 决策结果为 `ReactDecision`，包含一个 Goal 和最小 Capability Scope。
3. Lead 使用现有 ToolFactory、FilteredTool 和 RuntimeToolScope 构建本次可见工具。
4. Tool Loop 交替执行模型调用和工具调用，必要时进入结构化询问或审批等待。
5. 模型产生面向用户的最终回答后直接完成。
6. 不创建正式 Plan，不调用 `update_plan()`，不再增加一次 Summarizer 调用。

### Plan 流程

1. Lead 判断请求包含两个以上相互依赖的工作阶段、多个中间产物或需要显式进度展示。
2. 决策结果为 `PlanDecision`，包含 Goal、Title 和不少于两个 Step。
3. Lead 发出 Plan Created 事件并按顺序执行待处理 Step。
4. Step 成功且没有 Replan Signal 时直接进入下一个 Step。
5. Step 失败、用户 Steering、关键前提失效或执行策略明确请求重新规划时进入 Replanning。
6. 所有步骤结束后进行一次 Finalize，整合结果、附件和用户可行动的失败说明。
7. 输出 Plan Completed 和 Done。

### HITL 恢复流程

1. Interaction Resolution 不重新执行 Lead Decide。
2. Lead 使用原 Tool Call ID、Function、Arguments 和 Interaction Resolution 恢复原 Tool Loop。
3. 恢复时继续沿用创建 Interaction 时的策略和 Capability Scope。
4. 用户拒绝工具后，将拒绝结果交回模型；不得把拒绝直接转换成 Step 成功。
5. 等待中的旧会话仍可通过现有 React Memory 尾部恢复，迁移期不强制转换 Memory Key。

## 核心规则

1. `LeadAgent` 是新运行唯一的顶层入口和状态机所有者。
2. `direct`、`react`、`plan` 必须由显式判别字段确定，不能以 `steps=[]`、`steps=1` 等派生规则作为唯一事实。
3. `DirectDecision` 必须包含非空最终答案，不得包含 Steps、Capabilities 或 Tool Call。
4. 有附件但附件正文尚未进入模型上下文时，不允许 Direct。
5. 涉及当前/最新事实、URL、文件读写、Shell、Browser、外部 API 或其他环境状态时，不允许无工具 Direct。
6. `ReactDecision` 只表达一个目标和最小 Capability Scope，不产生用户可见任务列表。
7. `PlanDecision` 正常情况下至少包含两个 Step；只有一个 Step 时服务端确定性降级为 React。
8. Plan 中每个 Step 只能声明 Capability Catalog 中存在且实际需要的能力组。
9. 决策和规划阶段只看 Capability Catalog，不看完整 Tool Schema；执行阶段只看当前策略或 Step 允许的 Tool Schema。
10. Step 只有在执行结果 `success=true` 时才能标记 `completed`；`success=false` 必须进入 `failed` 或明确的等待/取消状态。
11. Step 成功本身不是 Replan 条件；正常成功后默认执行下一个 Step。
12. Replan 只允许由失败、用户 Steering、关键观察变化或显式 `needs_replan` 信号触发，并记录原因。
13. Direct 和 React 不调用 Finalizer；Plan 在全部步骤到达终态后最多调用一次 Finalizer。
14. Interaction Resume 不重新路由，避免审批后从 React/Plan 错误切换到 Direct。
15. Lead 的统一身份不意味着合并所有 Prompt 或始终暴露全部工具。
16. 迁移期旧组件只能被 Lead 调用；同一个 Run 不允许 Lead 和 Legacy Flow 同时推进状态。
17. 本设计不持久化隐藏推理；Trace 只记录策略、公开计划、调用、观察、Replan 原因和最终结果。

## 策略选择规则

### Direct 候选

- 普通知识解释，但问题不要求当前或外部可验证事实。
- 对用户在消息正文中提供的文本进行改写、翻译、摘要或格式转换。
- 创意讨论、方案发散和不依赖工具的对话。
- 能在一次模型回答内完整交付且不需要产生外部副作用的请求。

### ReAct 候选

- 查询当前信息、访问一个或少量 URL。
- 读取、修改或生成一个目标明确的文件。
- 执行一个目标明确的 Shell、Browser、MCP、A2A 或 API 操作。
- 虽然可能发生多次 Tool Call，但无需向用户展示稳定的多步骤计划。

### Plan 候选

- 存在两个以上有依赖关系的工作阶段。
- 需要多个中间产物、多个数据来源或显式进度。
- 任务会跨较长时间执行，且用户需要看见可追踪的 Step。
- 后续步骤依赖前面步骤的产物或验证结果。

### 服务端硬约束

模型决策之后，服务端必须进行确定性校验：

- Direct 出现附件引用、工具需求、Capabilities 或 Steps：拒绝该决策并重试一次；仍失败则回退 Legacy Plan。
- React Goal 为空或 Capability 未知：清理未知 Capability；Goal 仍为空则回退 Legacy Plan。
- Plan 没有 Step：视为无效决策，不等同于 Direct。
- Plan 只有一个 Step：转换为 React，使用该 Step 的 description 和 capabilities。
- Plan 中所有 Step 均被 Capability 过滤为空并不自动转为 Direct；无工具的多阶段写作仍可保持 Plan。
- 决策 JSON 无法解析、模式未知或互斥字段同时出现：记录路由错误并回退 Legacy Plan。

## Lead 状态机

```text
IDLE
  -> DECIDING
      -> DIRECT
      -> ACTING
      -> PLANNING

DIRECT
  -> COMPLETED

ACTING
  -> WAITING
  -> FAILED
  -> COMPLETED

PLANNING
  -> ACTING_STEP

ACTING_STEP
  -> WAITING
  -> REPLANNING
  -> ACTING_STEP
  -> FINALIZING

REPLANNING
  -> ACTING_STEP
  -> FAILED

FINALIZING
  -> COMPLETED
  -> FAILED

COMPLETED / FAILED
  -> IDLE
```

第一阶段该状态仍是进程内运行状态，沿用当前 Session/Run 状态投影。本设计不把它宣称为 Durable State Machine。

## 现有实现分析

### 相关代码与文档

- `api/app/core/agent/planner.py`：Planner 创建和更新 Plan，禁用 Tool Choice，仅消费 Capability Catalog。
- `api/app/core/agent/react.py`：ReAct 执行 Step、恢复 Interaction、调用工具并总结。
- `api/app/core/flows/planner_react.py`：当前顶层 Flow，无条件经过 Planning，并在每个 Step 后进入 Updating，最终进入 Summarizing。
- `api/app/core/agent/base.py`：提供 Memory、模型调用、Tool Loop、审批和 Interaction Resume 基础能力。
- `api/app/core/agent/agent_task_runner.py`：直接实例化 `PlannerReActFlow`，装配 Tool、Skill、Trace 和 Sandbox Runtime。
- `api/app/core/prompts/planner.py`：当前约定不可拆分任务返回一个 Step，空 Steps 表示不可行。
- `api/app/core/prompts/react.py`：定义 Step Execution 和 Summarize 输出契约。
- `api/app/core/entities/plan.py`：Plan/Step 状态和 `get_next_step()`。
- `api/app/core/entities/event.py`：前后端共享的 Plan、Step、Tool、Message、Interaction、Done 等事件契约。
- `api/tests/app/core/agent/test_plan_capabilities.py`：Planner Capability 过滤回归。
- `api/tests/app/core/agent/test_runtime_tool_scope.py`：Planner 无 Tool Schema、ReAct Tool Scope 回归。
- `api/tests/app/core/agent/test_interaction_resume.py`：HITL 原 Tool Call 恢复回归。
- `api/tests/app/core/agent/test_skill_runtime_context.py`：Skill Prompt 和资源在 Planner/ReAct 中的运行上下文回归。
- `api/tests/app/core/agent/test_agent_task_runner_completion.py`：Done 与 Session 完成顺序回归。

### 可复用能力

- `BaseAgent._invoke_llm()`、`_continue_tool_loop()` 和 `resume_interaction()` 可作为 Lead 内部执行能力的第一阶段实现。
- ToolFactory、FilteredTool、RuntimeToolScope 和 Capability Catalog 可以直接用于模式/Step 级工具裁剪。
- 现有 Planner 的 Capability 校验逻辑可以抽成 Lead PlanPolicy 的确定性校验。
- 现有 ReAct Tool Loop、InteractionEvent、WaitEvent 和审批策略可以直接复用。
- 现有 Event、AgentTaskRunner 输出队列、Session 投影和 TraceService 可以保持对外兼容。
- 现有 Skill Runtime Context 可以继续注入决策、计划和执行阶段，但各阶段只读取所需部分。

### 当前约束

- Planner 与 ReAct 当前各自拥有持久化 Memory，HITL Resume 依赖 React Memory 尾部的唯一 Tool Call。
- Planner/ReAct Prompt 都拼接了当前全局 System Prompt，不能在合并时简单再次拼接，否则会造成 Prompt 重复和冲突。
- 当前 LLM 接口返回完整 Message，不支持 Token Delta；Direct 虽能减少到一次调用，但仍需等待完整响应。
- 当前 Trace 是运行时投影而非状态权威源，本设计只增加观测字段，不改变其职责。
- 当前 Session 和前端已依赖既有事件类型，首版不应同时引入全新公开事件协议。

## 可选方案

### 方案 A：只修改 Planner Prompt，用空 Steps 直接回答

- 实现方式：修改 `CREATE_PLAN_PROMPT`，允许简单问题把最终答案写入 `message` 并返回 `steps=[]`；现有 Flow 发现无 Step 后直接完成。
- 数据流：Planner -> Message -> Completed。
- 迁移方式：只改 Prompt、少量 Flow 分支和测试。
- 优点：改动最小；简单问答可从多次模型调用下降到一次。
- 缺点：`steps=[]` 同时表示 Direct、不可行和规划异常；无法表达单目标 ReAct 快路径；Planner/React/Flow 三套身份与状态继续存在。
- 风险：模型输出稍有偏差就会直接结束任务；Trace 和 UI 无法区分直接回答与规划失败；后续 Streaming 仍需再次改变契约。

### 方案 B：LeadAgent 统一入口，内部采用显式策略（推荐）

- 实现方式：新增 `LeadAgent` 和判别联合 `LeadDecision`；Lead 统一拥有策略选择和状态转换，Direct/React/Plan 分支分别复用现有 Planner/ReAct 能力，逐步收回 Legacy Flow 状态。
- 数据流：Lead Decide -> Direct / React / Plan -> 既有事件投影。
- 迁移方式：Feature Flag 下先接入 Direct/React，Plan 暂由 Legacy Flow Adapter 执行；再把 Plan Loop 迁入 Lead，最后移除顶层 Legacy Flow。
- 优点：显式语义、调用链最短、保持现有能力、可渐进迁移；为后续 Streaming、Durable Runtime 和 ContextCompiler 提供单一运行边界。
- 缺点：迁移期仍保留旧组件；需要严格防止双状态所有者；测试范围较大。
- 风险：如果只增加 Lead 外壳却不切断无条件 Planner/Update/Summarize，可能形成只有命名变化的“伪合并”。

### 方案 C：一次性重写为单体 LeadAgent

- 实现方式：删除 PlannerAgent、ReActAgent 和 PlannerReActFlow，把决策、计划、Tool Loop、HITL、Memory 和 Finalize 全部移入一个新类。
- 数据流：所有行为由一个大类完成。
- 迁移方式：一次切换全部 Run，旧实现只保留 Git 回滚。
- 优点：目标结构表面最直接，没有迁移适配层。
- 缺点：形成 God Object 的概率高；HITL、Skill、Tool Scope、Trace、分支 Memory 和恢复行为都需要同时重写。
- 风险：回归面过大，难以判断性能提升来自路由还是行为丢失，出现问题时难以局部回滚。

## 方案对比

| 维度 | 方案 A：空 Steps | 方案 B：Lead + 策略 | 方案 C：一次性重写 |
| --- | --- | --- | --- |
| 实现复杂度 | 低 | 中 | 高 |
| 维护成本 | 高，语义债务持续累积 | 中，目标边界清晰 | 高，单体类持续膨胀 |
| 调用链优化 | 只优化无工具问答 | 同时优化 Direct、React、Plan | 可以优化，但需重写全部行为 |
| 兼容性 | 表面高，语义存在冲突 | 高，可逐策略切换 | 低 |
| 测试难度 | 低到中 | 中 | 高 |
| 回滚能力 | 简单 | 可按 Feature Flag 回滚新 Run | 只能整体回滚 |
| 后续 Streaming 适配 | 差 | 好，已有单一 Lead 边界 | 中，受单体耦合影响 |
| 主要风险 | Direct 与失败混淆 | 迁移期双状态所有者 | 大面积行为回归和 God Object |

## 推荐方案

选择方案 B：LeadAgent 统一入口，内部采用显式策略并渐进迁移。

选择理由：

1. 它直接解决用户体验根因：不同复杂度的任务不再强制走同一链路。
2. 它把产品中的“一个 Agent”落实为代码中的一个顶层运行身份和状态所有者。
3. 它可以复用已经经过测试的 Tool Loop、HITL、Skill、Capability 和 Event 能力，不需要一次性重写。
4. 它为后续 Token Streaming 和 Durable Runtime 提供稳定的 Lead 边界，但不在本批提前实现这些独立子系统。
5. 它避免使用空 Steps 承担多个语义，也避免将所有行为塞进一个难以维护的巨型类。

不选择方案 A，因为它只能作为短期 Prompt Hack，不能解决 React 快路径、无条件 Replan、无条件 Finalize 和顶层状态分裂。

不选择方案 C，因为现有 HITL、Skill、Tool Scope、Trace 和恢复逻辑已经有较多回归测试，一次性重写的风险和验证成本明显高于收益。

## 目标结构

```text
AgentTaskRunner
  |
  v
LeadAgent                           # 唯一顶层 Agent / 状态所有者
  |-- LeadDecisionPolicy            # 选择 direct/react/plan
  |-- DirectPolicy                  # 一次回答
  |-- ReactPolicy                   # Tool Loop + HITL
  |-- PlanPolicy                    # 创建/校验/按需更新计划
  |-- FinalizePolicy                # 仅复杂 Plan 使用
  |
  |-- ToolFactory / RuntimeToolScope
  |-- SkillRuntimeContext
  |-- TraceService
  `-- Session/Event Projection
```

首个实现不要求为每个 Policy 建立独立抽象基类。可以先使用 `LeadAgent` 的私有方法和现有 Planner/ReAct 适配器；只有当相同策略出现第二种实现或测试隔离确有价值时再抽取接口。

## 数据结构

### LeadMode

```python
class LeadMode(str, Enum):
    DIRECT = "direct"
    REACT = "react"
    PLAN = "plan"
```

### DirectDecision

| 字段 | 类型 | 必填 | 说明 | 约束/默认值 |
| --- | --- | --- | --- | --- |
| `mode` | `Literal["direct"]` | 是 | 判别字段 | 固定 direct |
| `title` | `str` | 是 | Session 标题候选 | 去空白后非空 |
| `language` | `str` | 是 | 回复语言 | 跟随用户 |
| `answer` | `str` | 是 | 最终用户答案 | 非空；不得包含内部计划 JSON |

### ReactDecision

| 字段 | 类型 | 必填 | 说明 | 约束/默认值 |
| --- | --- | --- | --- | --- |
| `mode` | `Literal["react"]` | 是 | 判别字段 | 固定 react |
| `title` | `str` | 是 | Session 标题候选 | 去空白后非空 |
| `language` | `str` | 是 | 工作与回复语言 | 跟随用户 |
| `goal` | `str` | 是 | 单一执行目标 | 非空 |
| `capabilities` | `list[str]` | 是 | 最小能力范围 | 未知值由服务端过滤 |

### PlanDecision

| 字段 | 类型 | 必填 | 说明 | 约束/默认值 |
| --- | --- | --- | --- | --- |
| `mode` | `Literal["plan"]` | 是 | 判别字段 | 固定 plan |
| `title` | `str` | 是 | Session 标题候选 | 去空白后非空 |
| `language` | `str` | 是 | 工作与回复语言 | 跟随用户 |
| `goal` | `str` | 是 | 多步骤目标 | 非空 |
| `message` | `str` | 否 | 启动复杂任务时对用户的简短说明 | 不得伪装成最终答案 |
| `steps` | `list[Step]` | 是 | 用户可见计划 | 正常至少 2 项 |

### StepExecutionOutcome

内部结构，不新增公开 API：

| 字段 | 类型 | 必填 | 说明 | 约束/默认值 |
| --- | --- | --- | --- | --- |
| `success` | `bool` | 是 | 当前 Step 是否成功 | 决定 completed/failed |
| `result` | `str | None` | 否 | 结果摘要 | 不保存隐藏推理 |
| `attachments` | `list[str]` | 是 | 产物路径 | 默认空数组 |
| `needs_replan` | `bool` | 是 | 是否要求重新规划 | 默认 false |
| `replan_reason` | `str | None` | 否 | 可观测原因摘要 | needs_replan=true 时非空 |

### LeadRunContext

第一阶段为进程内对象，不新增数据库表：

| 字段 | 类型 | 必填 | 说明 | 约束/默认值 |
| --- | --- | --- | --- | --- |
| `mode` | `LeadMode` | 是 | 本次 Run 策略 | 决策后固定；HITL 恢复沿用 |
| `phase` | `LeadPhase` | 是 | 当前状态机阶段 | 由 Lead 唯一更新 |
| `plan` | `Plan | None` | 否 | Plan 策略当前计划 | Direct/React 为 None |
| `current_step` | `Step | None` | 否 | 当前执行步骤 | 非 Plan 时为空 |
| `replan_count` | `int` | 是 | 重新规划次数 | 默认 0，受 Agent 限制 |

现有 `sessions.memories` 中的 `planner` 和 `react` Key 在第一阶段继续保留，作为内部策略兼容存储。统一 Lead Memory 属于后续 ContextCompiler 设计，不在本批迁移历史数据。

## 内部接口设计

### LeadAgent.run

```python
async def run(self, message: Message) -> AsyncGenerator[BaseEvent, None]:
    ...
```

- 输入：普通用户消息或 Interaction Resolution。
- 输出：现有 `BaseEvent` 异步事件流。
- 权限：沿用 AgentTaskRunner 已解析的 user/session 所有权。
- 幂等/并发：沿用当前 Session/Task 门禁；本设计不新增 Durable 幂等能力。
- 兼容性：替代 AgentTaskRunner 对 `PlannerReActFlow.invoke()` 的直接调用。

### LeadAgent.decide

```python
async def decide(self, message: Message) -> LeadDecision:
    ...
```

- 输入：用户消息、附件元数据、Skill Prompt Block、Capability Catalog 和必要会话上下文。
- 输出：`DirectDecision | ReactDecision | PlanDecision`。
- 工具：不接收完整 Tool Schema，`tool_choice=none`。
- 校验：使用 Pydantic 判别联合和服务端硬约束。
- 错误：格式错误允许一次纠正重试；仍失败回退 Legacy Plan。

### LeadAgent.run_direct

```python
async def run_direct(self, decision: DirectDecision) -> AsyncGenerator[BaseEvent, None]:
    ...
```

- 输出：TitleEvent、MessageEvent、DoneEvent。
- 禁止：PlanEvent、StepEvent、ToolEvent、Finalizer 模型调用。

### LeadAgent.run_react

```python
async def run_react(
    self,
    decision: ReactDecision,
    message: Message,
) -> AsyncGenerator[BaseEvent, None]:
    ...
```

- 复用：现有 BaseAgent Tool Loop、Ask User、RuntimeToolScope 与历史 Interaction 读取兼容。
- 输出：Tool/Interaction/Wait/Message/Error/Done 等既有事件。
- 禁止：创建用户可见 Plan、调用 Planner Update、调用 Summarizer。

### LeadAgent.run_plan

```python
async def run_plan(
    self,
    decision: PlanDecision,
    message: Message,
) -> AsyncGenerator[BaseEvent, None]:
    ...
```

- 复用：现有 Plan/Step/Event 和 ReAct Step Execution。
- 变化：由 Lead 状态机决定是否 Replan；不再每步无条件更新。
- Finalize：所有 Step 终止后最多一次。

### LeadAgent.resume_interaction

```python
async def resume_interaction(
    self,
    resolution: InteractionResolution,
) -> AsyncGenerator[BaseEvent, None]:
    ...
```

- 不执行 Decide。
- 复用现有 Tool Call 三元校验和 React Memory 恢复。
- 恢复后继续原策略；Plan 策略恢复到原 Step，React 策略恢复到原 Goal。

## Prompt 设计

统一 Lead 身份，但按阶段拆分 Prompt：

```text
lead_base
  + lead_decide
  + selected Skill prompt block
  + capability catalog

lead_base
  + lead_react
  + selected Skill prompt block
  + scoped tool schemas

lead_base
  + lead_plan_update
  + plan/step outcome

lead_base
  + lead_finalize
  + completed outcomes/artifacts
```

规则：

- 不创建一个同时包含所有路由、计划、工具、总结细则的超级 Prompt。
- Decide 发生在可靠工作语言产生之前，因此使用精简的中英双语规则，不通过字符启发式在 `prompts/` 与 `prompts/en/` 之间切换；用户消息、附件和 Capability Catalog 仍只注入一次，控制首轮 Token。
- 所有用户可见字段优先遵循用户明确指定的输出语言；未明确指定时使用最新用户消息的主要语言。React Goal 同样接收已决策的 `language` 并保留双语兜底说明。
- Decide Prompt 只负责选择最小充分策略并生成对应判别结构。
- Direct 的 `answer` 是最终答案；Plan 的 `message` 只是复杂任务启动说明，两者不得复用同一字段语义。
- Prompt 不再规定“不可拆分必须返回一个 Step”；不可拆分但需要工具应返回 React。
- Prompt 不再使用空 Steps 表示不可行。不可行请求应返回 Direct 解释、可行动错误，或在需要更多信息时进入明确询问路径。

### Prompt Locale 路由补充设计

对照 `mooc-manus/api` 后确认，其 `prompts/en` 只是平行英文资产；Planner/ReAct 仍固定导入主目录中文 Prompt，配置、UI 和启动脚本不存在运行时 locale 选择。Agentic 不照搬这一未接线状态，而是把 Prompt Locale 纳入 Lead Runtime。

可选方案：

| 方案 | 实现 | 优点 | 缺点 |
| --- | --- | --- | --- |
| A. 所有活跃 Prompt 中英并列 | 每次调用都发送双语规则 | 无选择状态，改动小 | 执行阶段 Token 稳定增加；两套目录仍无职责 |
| B. Runtime Prompt Catalog | Decide 双语；得到 language 后选择 `zh/en` Prompt Pack | 真正使用英文资产；执行 Prompt 更短；同实例支持中英会话 | 需要处理持久化 Memory 中的 System Prompt |
| C. 部署期全局 Locale | 环境变量决定整套 imports | 最简单、Token 最小 | 一个实例不能同时服务中英文用户；切换需重启 |

推荐方案 B。Lead Decide 发生在可靠语言产生前，继续使用精简双语规则；`DirectDecision/ReactDecision/PlanDecision.language` 产生后，Planner、React Goal、Step 和 Finalizer 通过 Prompt Catalog 选择模板。Legacy Planner 首轮只在尚无 Plan language 时根据用户消息选择 Prompt，随后也使用 Plan language。

BaseAgent 不重写持久化 Memory，而是在每次构造 LLM messages 时，用当前 Runtime System Prompt 替换消息视图中的第一个 system content。这样不会迁移历史 Memory，也不会因同一 Session 前一轮使用另一种语言而拿到错误 System Prompt。HITL Resume 不做新语言检测，直接使用 Interaction 中持久化的 `lead_language` 或 Plan `language`。

首期只支持两个 Prompt Locale：中文标签（`zh`、`zh-CN`、`Chinese`、中文/汉语）映射 `zh`；英文标签（`en`、`en-US`、`English`、英文/英语）映射 `en`。其他语言使用英文指令模板，但用户可见输出仍遵循原始 `language` 字段，不把 Prompt Locale 当作输出语言。

## 事件与前端兼容

本设计不新增前端必须理解的公开事件类型。

| 模式 | 对外事件 |
| --- | --- |
| Direct | Title、Message、Done |
| React | Title、Tool/Interaction/Wait、Message/Error、Done |
| Plan | Title、Message（可选启动说明）、Plan、Step、Tool/Interaction/Wait、Message、Done |

Direct 不发送空 Plan。前端必须允许一个 Run 只有 User Message、Assistant Message 和 Done，而不要求 PlanEvent 存在。

策略选择写入 Trace 内部事件：

```text
lead.strategy_selected
```

建议字段：

- `mode`
- `decision_latency_ms`
- `decision_model`
- `capability_count`
- `step_count`
- `fallback_reason`
- `replan_count`

不得记录隐藏推理或完整敏感 Prompt。

## 错误处理与可观测性

- 决策解析失败：纠正重试一次；仍失败记录 `decision_invalid`，回退 Legacy Plan。
- Direct 硬约束失败：不得直接输出可能缺少事实依据的答案；回退 React/Legacy Plan。
- React 找不到声明的 Capability：过滤未知值；没有可执行能力时把缺失能力作为可行动错误返回模型。
- Tool/HITL 异常：沿用现有 Error/Interaction 事件，不由 Lead 吞掉。
- Step `success=false`：标记 Failed；是否 Replan 由确定性规则和 Outcome 信号共同决定。
- Replan 超过限制：停止重新规划，Finalize 已有结果并明确未完成部分，或者输出 Error。
- Finalize 失败：不得把已完成 Step 回滚；输出可恢复错误并保留已有事件。

关键指标：

- `lead_strategy_total{mode}`
- `lead_decision_latency_ms`
- `lead_model_calls_per_run`
- `lead_replan_total{reason}`
- `lead_fallback_total{reason}`
- `lead_run_latency_ms{mode}`
- `lead_token_usage{mode}`

## 测试设计

### 决策契约

- Direct、React、Plan 三种合法 JSON 可正确解析为判别联合。
- Direct 混入 Steps/Capabilities 被拒绝。
- Plan 零 Step 被拒绝，不被误判成 Direct。
- Plan 单 Step 被确定性转换为 React。
- 未知 Capability 被过滤且顺序稳定。
- 模式未知、字段冲突和 JSON 损坏会纠正重试并回退。

### 调用次数

- 简单问答：恰好一次模型调用，零 Plan Update，零 Finalize。
- 单目标工具任务：决策后进入 Tool Loop；零 Plan Update，零 Finalize。
- 两步复杂任务：一次 Decide，按步骤执行，正常成功时零 Replan，最后一次 Finalize。
- Step 失败且要求调整：只触发一次 Replan，并记录原因。

### 事件兼容

- Direct 产生 Title、Message、Done，不产生 Plan/Step。
- React 的 Tool、Interaction、Wait、Resume 事件与现有前端契约兼容。
- Plan 的 Created/Updated/Completed 与 Step 事件顺序保持稳定。
- Done 仍在 Session 最终状态提交之后输出且不重复。

### 行为回归

- Skill 自动/手动选择仍影响 Lead 的 Decide/React/Plan 上下文。
- Planner 阶段仍不接收完整 Tool Schema。
- React 只看到当前 Capability Scope 内的工具。
- 高风险工具审批、拒绝和结构化 Ask User 可继续恢复。
- Branch Context Seed、附件、Next Message、Stop/Resume 行为不回归。
- Trace 的 model_calls、tool_calls 和 strategy event 可关联到同一 Run。

### 最小代表任务集

至少覆盖：

1. 打招呼和普通问答。
2. 解释代码或概念。
3. 改写用户提供的文本。
4. 查询最新信息。
5. 读取一个文件并回答。
6. 修改一个文件。
7. 单次 Shell 操作。
8. 需要工具审批的操作。
9. 需要 Ask User 的任务。
10. 两到四步的研究或产物任务。
11. 中途 Step 失败并 Replan。
12. 用户 Steering 和 Interaction Resume。

## 迁移与回滚

### 阶段 1：Lead 门面与显式决策

1. 新增 LeadDecision 数据结构和 Decide Prompt。
2. 新增 LeadAgent，统一由 AgentTaskRunner 装配 Tool、Skill、Trace 和现有 Agent 依赖。
3. 在 Feature Flag 下启用 Direct 快路径。
4. React/Plan 暂时分别委托现有 ReActAgent 和 PlannerReActFlow。
5. 同一个 Run 只允许被一个分支推进；委托 Legacy Flow 时 Lead 不再同步修改其内部状态。

### 阶段 2：React 快路径

1. Lead 直接调用现有 Tool Loop 完成 React Goal。
2. 跳过 PlanEvent、Planner Update 和 Summarizer。
3. 将 Interaction Resume 接到 Lead，内部继续复用旧 React Memory。
4. 通过工具、HITL、Skill 和附件回归后扩大 Feature Flag。

### 阶段 3：Plan 状态收归 Lead

1. 把 Plan Loop 从 PlannerReActFlow 移入 Lead。
2. 把 PlannerAgent 的创建/更新能力降级为 PlanPolicy。
3. 引入 StepExecutionOutcome 和按条件 Replan。
4. Finalize 只保留在 Plan 分支。
5. PlannerReActFlow 变为短期兼容适配器，不再用于新 Run。

### 阶段 4：移除旧顶层身份

1. 删除 AgentTaskRunner 对 PlannerReActFlow 的直接依赖。
2. PlannerAgent/ReActAgent 若仍有价值，重命名或重构为 Lead 内部 Policy/Executor；否则在测试迁移完成后删除。
3. 清理只为无条件 Updating/Summarizing 服务的 Flow 状态。
4. 更新 `current-state.zh-CN.md`、`roadmap.zh-CN.md` 和运行架构说明。

### 历史数据

- 不迁移 Session Events、Run Trace 和历史 Plan。
- 不删除 `sessions.memories.planner` 或 `sessions.memories.react`。
- 旧 pending Interaction 继续通过 React Memory 恢复。
- 新 Lead Memory 的统一由后续 ContextCompiler 设计决定。

### 回滚

- Feature Flag 只影响新创建的普通 Run。
- 出现策略误判、HITL 无法恢复或事件兼容问题时，关闭 Flag，使新 Run 回到 PlannerReActFlow。
- 已在 Lead 中运行的 Task 不在中途切换到 Legacy Flow。
- 回滚不删除 Lead Trace Event，不修改历史 Session Events。

## 风险

| 风险 | 可能性 | 影响 | 缓解措施 | 验证方式 |
| --- | --- | --- | --- | --- |
| Lead 只成为外壳，内部仍无条件走旧链路 | 中 | 高 | 为每种模式增加模型调用次数断言 | Fake LLM 调用计数测试 |
| Lead 与 Legacy Flow 同时拥有状态 | 中 | 高 | 单 Run 单状态所有者；委托后 Lead 不推进内部阶段 | 状态转换与事件顺序测试 |
| Direct 误判需要工具的请求 | 中 | 高 | 模型决策后服务端硬约束和回退 | 最新信息、附件、URL、文件任务测试 |
| 空 Steps 继续被当作 Direct | 中 | 中 | 判别联合；Plan 零 Step 直接无效 | Schema 单元测试 |
| 合并后 Prompt 体积更大 | 中 | 中 | 按阶段组合 Prompt，不创建超级 Prompt | Prompt 快照与 Token 指标 |
| Tool Schema 在 Decide 阶段泄漏或膨胀 | 低 | 中 | Decide 只使用 Capability Catalog | Runtime Tool Scope 测试 |
| React 快路径破坏 HITL Resume | 中 | 高 | 首期复用 ReAct Memory 和原 Tool Call 校验 | Interaction Resume 全量回归 |
| 旧 Session 上下文与新 Lead 不连续 | 中 | 中高 | 第一阶段保留 planner/react Memory Key，不做强制迁移 | 多轮旧 Session 回归 |
| Step 失败被错误标记完成 | 中 | 高 | Outcome 到状态的确定性映射 | success=false 状态测试 |
| Direct 仍无 Token 流式，用户感知改善有限 | 高 | 中 | 明确下一独立 Streaming 设计；先以调用次数和总延迟验收 | TTFT/总延迟基线对比 |
| 一次性删除旧类造成大范围回归 | 中 | 高 | 四阶段迁移，最后才删除旧顶层身份 | Feature Flag 与全量回归 |

## 重要假设

- 产品对外仍只有一个 Agent，用户不需要选择 Planner、ReAct 或 Lead。
- Direct、React、Plan 首期使用同一个用户配置模型，不引入模型分级路由。
- 当前 Event/SSE 接口足以表达无 Plan 的 Direct/React Run。
- 现有 ToolFactory、RuntimeToolScope、Skill Runtime 和 HITL 语义继续作为兼容基线。
- 本批以减少无效调用和统一运行边界为目标，不以真正 Token Streaming 作为完成条件。
- 本批不要求服务进程重启后自动恢复，Durable Runtime 仍是独立后续工作。
- 迁移期间允许保留 Planner/ReAct Memory Key；“一个 Lead”指运行身份和状态所有权统一，不要求立即改变存储格式。

## 待决策项

无影响核心设计的待决策项。

已采用以下范围决策：

1. Lead 是单 Agent 的统一运行入口，不在本批增加 Child Agent。
2. 选择显式 `direct/react/plan`，不使用 Step 数量表示模式。
3. 选择渐进迁移，不一次性重写 Planner/ReAct/HITL。
4. Token Delta Streaming 单独设计，不与本批绑定实施。
5. Memory 结构本批保持兼容，不做数据库迁移。

## 验收标准

- [ ] `AgentTaskRunner` 对新运行只调用一个 `LeadAgent` 顶层入口。
- [ ] Direct、React、Plan 使用显式判别联合，Plan 零 Step 不会被当作 Direct。
- [ ] 普通问答恰好一次模型调用，不产生 PlanEvent、StepEvent、ToolEvent、Planner Update 或 Finalize。
- [ ] 单目标工具请求不产生 PlanEvent，不调用 Planner Update 和 Finalize。
- [ ] Plan 单 Step 被确定性降级为 React；两个以上有效 Step 才进入 Plan 流程。
- [ ] 正常成功的 Plan Step 不触发 Replan；失败、Steering、前提失效或显式信号才触发。
- [ ] 每次 Replan 都在 Trace 中记录公开原因和计数。
- [ ] `success=false` 的 Step 不会被标记为 `completed`。
- [ ] Plan 策略最多调用一次 Finalize；Direct/React 零 Finalize。
- [ ] Decide/Plan 阶段不接收完整 Tool Schema，React/Step 只看到 Scope 内工具。
- [ ] Lead Decide 与 React Goal 的关键模式、语言和输出约束中英对齐；英文输入不会因只有中文新增规则而丢失路由或回复语言约束。
- [ ] `prompts/en` 被生产代码通过 Prompt Catalog 使用；英文 Plan/React 的 LLM messages 不包含整套中文执行 Prompt。
- [ ] 同一 Agent Memory 先后执行中英文 Run 时，每次 LLM 调用看到与当前 Run 匹配的 System Prompt；HITL Resume 保持暂停前语言。
- [ ] 高风险审批、Ask User、拒绝、刷新和 Interaction Resume 回归通过。
- [ ] Skill 自动/手动选择、Capability 过滤、附件、Branch Context Seed 和 Trace 回归通过。
- [ ] Direct 事件流只包含必要的 Title、Message、Done，前端不依赖空 Plan。
- [ ] 正常完成时 Done 在 Session 最终状态提交后发送且不重复。
- [ ] Feature Flag 关闭后，新 Run 可完整回退到现有 PlannerReActFlow。
- [ ] 代表任务集记录改造前后模型调用次数、Token 和总延迟；Direct/React 的调用次数达到本设计目标，Plan 质量无显著回归。
- [ ] 相关后端定向测试、全量测试、Ruff 和前端受影响回归通过后，才进入实施完成状态。
