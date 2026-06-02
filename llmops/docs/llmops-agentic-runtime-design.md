# LLMOps Agentic Runtime 设计说明

本文记录 `llmops` 接入 `agentic` 自主规划执行能力的架构判断和落地边界。

## 1. 核心判断

目标不是把 `agentic` 整体复制进 `llmops`，而是把 `agentic` 的 Planner/ReAct/工具执行/事件流思想吸收到 `llmops` 的平台模型里。

建议方向：

```text
llmops = 企业 Agent 平台控制面 + 运行治理
agentic = 自主规划 / ReAct 执行能力来源
```

也就是说：

- `llmops` 负责资产、账号、模型、密钥、文件、知识库、工具、工作流、审计、任务生命周期和 UI。
- `agentic` 的思想用于补强 Planner Agent、ReAct Worker、沙箱执行、事件流和动态重规划。

## 2. Planner 与 Worker 边界

不要把 `agentic` 的完整 `PlannerReActFlow` 直接作为 `llmops` Worker。否则会变成“全局 Planner 调用另一个 Planner”，容易导致计划层级失控、审计困难和审批边界不清。

推荐结构：

```text
用户任务
  -> PlannerAgent 生成 RouterPlan
  -> AutonomousAgentRuntime 校验计划
  -> WorkerAgent 执行每个 step
      -> AppWorker / WorkflowWorker / ReActWorker
  -> WorkerResult + ArtifactRef
  -> PlannerAgent 根据结果更新或重规划
  -> 最终汇总
```

关键原则：

- 全局规划只能由 `PlannerAgent` 负责。
- `WorkerAgent` 只负责专业子任务执行，不修改全局计划。
- `ReActWorkerAgent` 可以做局部推理和工具调用，但输出必须收敛为 `WorkerResult`。
- 重规划由 `PlannerAgent` 基于 `WorkerResult`、错误、证据和 Artifact 决定。

## 3. 推荐组件

### PlannerAgent

职责：

- 根据用户任务、可用 Worker、文件输入、工具能力生成 `RouterPlan`。
- 根据步骤执行结果更新计划。
- 判断是否需要重试、跳过、人工审批或动态重规划。
- 生成最终答案策略。

来源参考：

- 吸收 `agentic/api/app/core/agent/planner.py` 的 create/update plan 思路。
- 输出结构必须改成 `llmops` 的 `RouterPlan`，不能直接使用 `agentic` 的 Plan。

### AutonomousAgentRuntime

职责：

- 创建 `AgentTask`。
- 调用 Planner 生成计划。
- 校验计划中的 Worker、依赖、审批策略和执行模式。
- 调度 Worker。
- 持久化 task、plan、step、worker call、event、artifact。
- 处理失败、重试、等待审批和重规划。

### WorkerAgent

职责：

- 接收 `WorkerInvocation`。
- 执行单个子任务。
- 返回 `WorkerResult`。
- 产生 `AgentEvent`。
- 登记 Artifact。

第一批 Worker 建议：

- `AppWorkerAdapter`：把现有 `llmops` App 适配成 Worker。
- `WorkflowWorkerAdapter`：后续把 Workflow 适配成 Worker。
- `ReActWorkerAgent`：吸收 `agentic` ReActAgent 的局部工具执行能力。

### ReActWorkerAgent

职责：

- 对单个步骤进行局部思考和工具调用。
- 可调用浏览器、shell、文件、搜索、HTTP、平台工具等能力。
- 不拥有全局计划修改权。
- 最终输出 `WorkerResult`，包括 summary、data、evidence、artifacts、errors。

来源参考：

- 吸收 `agentic/api/app/core/agent/react.py` 的 step execution 思路。
- 工具调用必须接入 `llmops` 的权限、审批、沙箱和审计机制。

## 4. 协议优先级

Agent Runtime 先统一内部协议，再考虑 Planner 或 Worker 具体实现。

优先定义：

- `WorkerInvocation`
- `WorkerResult`
- `AgentEvent`
- `ArtifactRef`
- `RouterPlan`
- `RouterPlanStep`

当前 `llmops/api/app/domain/agent_runtime/protocols.py` 已有雏形，但需要调整：

- 将 `tenant_id` 改成 `account_id`，或兼容当前账号级隔离边界。
- 在 `WorkerInvocation.context` 中加入输入文件引用。
- 在 `WorkerResult.artifacts` 中使用 `ArtifactRef`，不要传二进制。
- 明确 `AgentEvent` 的事件类型、状态字段和前端展示字段。

## 5. Artifact 与文件

Files 模块已经具备进入 Agent 的基础：

- 文件资产表。
- 分页列表。
- 目录树。
- 批量移动 / 删除。
- 知识库来源。
- 来源字段 `source`。

下一步需要补：

- 文件作为 Agent task 输入。
- Agent 输出登记为 Artifact。
- Worker 步骤之间通过 `ArtifactRef` 传递文件。
- 任务页展示输入文件、产物文件、执行日志和证据。

建议 Artifact 最小结构：

```json
{
  "artifact_id": "uuid",
  "file_id": "uuid",
  "name": "result.xlsx",
  "type": "table",
  "source": "agent",
  "task_id": "uuid",
  "step_id": "uuid",
  "worker_id": "uuid",
  "summary": "销售数据分析结果",
  "metadata": {}
}
```

## 6. 建议落地顺序

1. 修改内部协议：`account_id`、`ArtifactRef`、输入文件、事件类型。
2. 实现 Agent task 输入文件绑定。
3. 实现 Artifact 登记和 Files 页面展示 `source=agent`。
4. 实现 `AppWorkerAdapter`，让现有 App 先成为 Worker。
5. 实现 `WorkerRuntime.invoke()` 最小版本。
6. 实现 `PlannerAgent`，输出 `RouterPlan`。
7. 实现 `AutonomousAgentRuntime` 的计划、执行、事件、重规划循环。
8. 实现 `ReActWorkerAgent`，吸收 `agentic` 的 ReAct 执行能力。
9. 增加前端 Router/Worker Agent 页面和 Agent Task 执行台。
10. 再考虑 A2A/MCP 外部 Agent 接入。

## 7. 风险与约束

- 不要让多个 Planner 同时修改全局计划。
- 高风险工具必须经过权限、沙箱和审批。
- Planner 输出必须做 schema 校验，不能直接信任 LLM JSON。
- Worker 失败要可重试、可审计、可回放。
- Agent 自主性必须受到预算、最大步骤数、最大工具调用次数和人工审批策略约束。

## 8. 两边 Agent 实现调研

### 8.1 `agentic` 当前实现

`agentic` 已经是一个完整的自主执行运行时，核心入口不是单个 Agent 类，而是 `AgentTaskRunner + PlannerReActFlow`：

- `agentic/api/app/services/agent_service.py` 为会话准备 sandbox、browser、LLM、JSON parser、搜索、MCP/A2A 工具，并创建 `AgentTaskRunner`。
- `agentic/api/app/core/agent/agent_task_runner.py` 负责 Redis Stream 输入输出、用户附件同步到 sandbox、Agent 生成附件回存储、工具内容补全和任务生命周期。
- `agentic/api/app/core/flows/planner_react.py` 是主循环，状态包括 `IDLE`、`PLANNING`、`EXECUTING`、`UPDATING`、`SUMMARIZING`、`COMPLETED`。
- `PlannerReActFlow` 同时持有 `PlannerAgent` 和 `ReActAgent`，并把 File、Shell、Browser、Search、Message、MCP、A2A 等工具注入两个 Agent。

执行流程可以概括为：

```text
用户消息
  -> PlannerAgent.create_plan()
  -> ReActAgent.execute_step(next_step)
  -> ReActAgent.compact_memory()
  -> PlannerAgent.update_plan(plan, finished_step)
  -> 循环执行下一个 step
  -> ReActAgent.summarize()
  -> DoneEvent
```

关键实现特点：

- `PlannerAgent` 使用 LLM 直接输出 JSON plan，不调用工具；`create_plan()` 生成初始计划，`update_plan()` 根据已完成 step 更新未完成部分。
- `ReActAgent` 针对单个 step 执行工具调用，输出 `StepEvent`、`ToolEvent`、`MessageEvent`、`WaitEvent`、`ErrorEvent` 等事件。
- `message_ask_user` 工具会让任务进入等待用户输入状态，用户继续输入后通过 `roll_back()` 修复 LLM tool-call 消息链。
- `BaseAgent` 按 `session_id + agent.name` 维护长期 memory，并在工具执行后把 tool result 写回模型上下文。
- `Plan`、`Step`、`Event` 都是运行时 Pydantic 实体，适合流式执行，但不是企业平台的持久化任务模型。

### 8.2 `llmops` 当前实现

`llmops` 目前更像企业 Agent 平台的控制面和治理骨架，已经有 Router/Worker 的数据模型，但自主规划和 ReAct 执行尚未完成：

- `llmops/api/app/domain/agent_runtime/protocols.py` 已有 `RouterPlan`、`RouterPlanStep`、`WorkerInvocation`、`WorkerResult` 雏形。
- `llmops/api/app/domain/agent_runtime/router_runtime.py` 已能校验 step id、worker id、worker 白名单和 step dependency。
- `llmops/api/app/domain/agent_runtime/worker_runtime.py` 还是占位实现，当前只返回 `not_implemented`。
- `llmops/api/app/models/task.py` 已有 `AgentTask`、`AgentPlan`、`AgentStep`、`WorkerCall`、`CapabilityCall` 持久化表。
- `llmops/api/app/services/task_engine_service.py` 负责 deterministic 状态流转，包括 task、step、worker call、capability call 的 created/running/waiting/succeeded/failed/cancelled。
- `llmops/api/app/services/trace_service.py` 能把 task、plan、step、worker call、capability call、approval 串到 trace event。

Router Manager 已经有最小闭环：

- `llmops/api/app/services/router_agent_manager_service.py` 能创建 router agent、把现有 App 转成 worker agent、绑定 worker。
- `build_manager_plan()` 目前是规则式计划生成：对选中的 worker 逐个生成 step，`risk_assessment.source = manager_rule_v1`。
- `execute_manager_run_steps()` 会创建 step、worker call、trace event，并调用 `_invoke_worker()` 执行 worker。
- 当前 `_invoke_worker()` 只支持 `target_ref_type = app`，内部调用 `AppService.debug_chat()`，再从 SSE chunks 中拼出 answer。

现有 App 执行链路已经有 Worker 能力基础：

- `llmops/api/app/services/app_service.py` 的 `debug_chat()` 支持模型调用、流式输出、工具调用、知识库检索和工作流执行。
- `llmops/api/app/services/agent_adapter_service.py` 的 `LegacyAppWorkerAdapter` 已能把 App 配置转换成 `WorkerAgentDescriptor`，包括模型配置、提示词配置、工具、工作流、知识库绑定。

当前缺口：

- 没有真正的 LLM PlannerAgent。
- 没有 `AutonomousAgentRuntime` 的规划、执行、重规划循环。
- `WorkerRuntime.invoke()` 未接入真实 worker。
- `AgentEvent` 和 `ArtifactRef` 还没有形成标准协议。
- task/plan/step/call 模型仍使用 `tenant_id`，需要和当前账号模型的 `account_id` 边界对齐。
- 文件还没有作为 Agent task 输入和 Worker artifact 输出贯通。

### 8.3 实现差异矩阵

| 维度 | `agentic` | `llmops` | 对 `llmops` 的含义 |
| --- | --- | --- | --- |
| 系统定位 | 自主执行运行时 | 企业 Agent 平台控制面 | 不要整体复制 runtime，要吸收能力并接入平台协议 |
| 计划生成 | LLM Planner 输出 `Plan` | RouterPlan 协议已有，但当前 manager plan 是规则生成 | 需要新增 `PlannerAgent` 输出 `RouterPlan` |
| 计划更新 | 每个 step 后由 Planner 动态更新未完成计划 | 目前没有重规划循环 | `AutonomousAgentRuntime` 必须持有 plan update/replan 责任 |
| Step 执行 | `ReActAgent.execute_step()` 直接调用工具 | 当前 worker 主要是 App debug chat 适配 | 第一版先落 `AppWorkerAdapter`，再做 `ReActWorkerAgent` |
| 工具体系 | File/Shell/Browser/Search/Message/MCP/A2A 直接暴露给 LLM | 工具、知识库、工作流、模型、密钥由平台管理 | ReAct 工具必须包装成平台 Capability，并接入权限/审批/审计 |
| 事件 | `PlanEvent`、`StepEvent`、`ToolEvent`、`WaitEvent` 等运行时事件 | `TraceEvent` 持久化已有，前端 runtime event 协议缺失 | 需要定义 `AgentEvent`，并映射到 trace 和前端执行台 |
| 状态持久化 | session memory、session files、Redis stream event | SQL task/plan/step/call/trace | 保留 llmops 持久化模型，event stream 只做传输层 |
| 文件/产物 | 附件同步到 sandbox，生成文件再回存储 | Files 模块已具备网盘式管理 | 用 `ArtifactRef` 连接 task/step/worker/files |
| 用户中断 | `message_ask_user` + `WaitEvent` + `roll_back()` | task/step/capability 有 waiting_approval，但缺用户追问协议 | 需要区分“等待用户补充”和“等待人工审批” |
| 并发/异步 | async generator + Redis Stream | FastAPI/SQLAlchemy/Celery/SSE 混合 | Runtime 层建议内部事件化，外部可通过 SSE/DB trace 展示 |

### 8.4 可复用与不可直接复用的边界

可以吸收：

- `PlannerAgent.create_plan()` 和 `PlannerAgent.update_plan()` 的双阶段思路。
- `ReActAgent.execute_step()` 的单步执行、工具调用、等待用户、错误事件模型。
- `PlannerReActFlow` 的状态机顺序：规划、执行、更新、总结。
- `AgentTaskRunner` 的文件输入进 sandbox、产物回存储、工具内容补全思路。
- `BaseAgent` 的 per-session/per-agent memory 管理和 tool-call 回滚思路。

必须改造：

- `agentic` 的 `Plan/Step` 要改成 `llmops` 的 `RouterPlan/RouterPlanStep`。
- `ReActAgent` 要封装为 `ReActWorkerAgent`，入口是 `WorkerInvocation`，出口是 `WorkerResult`。
- 工具不能直接暴露给 LLM，必须通过 `llmops` Capability、密钥、权限、审批、审计和 sandbox 策略包装。
- `agentic` 的附件路径要改成 `llmops` Files + `ArtifactRef`。
- `agentic` 的事件要映射为 `AgentEvent`，再写入 `TraceEvent` 并提供给前端执行台。
- `tenant_id` 要统一迁移或兼容到当前 `account_id` 隔离模型。

不建议直接复用：

- 不建议把完整 `PlannerReActFlow` 作为一个 llmops Worker，否则会形成 Planner 嵌套 Planner。
- 不建议照搬 Redis Stream 作为唯一任务总线，llmops 已有 SQL task/trace 和 Celery/SSE 基础。
- 不建议绕过 App/Workflow/Tool/Model Provider 的平台配置直接调用外部模型或工具。
- 不建议把 sandbox 文件路径直接暴露给前端，前端应该只看到 Files/Artifact 引用。

### 8.5 基于调研后的落地判断

落地优先级可以保持第 6 节的顺序，但实现上要先补齐协议边界，再接入 autonomous 能力：

1. 先把 `WorkerInvocation`、`WorkerResult`、`AgentEvent`、`ArtifactRef`、`account_id` 统一掉。
2. 把现有 App debug chat 正式包装成 `AppWorkerAdapter`，通过 `WorkerRuntime.invoke()` 返回标准 `WorkerResult`。
3. 让 `RouterAgentManagerService` 不再只做规则式 `manager_rule_v1`，新增 LLM PlannerAgent 生成 `RouterPlan`。
4. 实现 `AutonomousAgentRuntime`：创建 task、保存 plan、调度 worker、写 trace、等待审批、失败重试、调用 Planner 更新计划。
5. 在 AppWorker 可用后再做 `ReActWorkerAgent`，把 sandbox、浏览器、shell、文件、搜索能力逐步接入平台 Capability。
6. 最后补 Agent Task 执行台 UI：展示 plan、step、worker call、tool/capability call、trace、输入文件和 artifact。

## 9. 聚焦：llmops Worker Agent 对齐 ReActWorkerAgent

当前阶段先不新增 Planner Agent 类型，目标只完成一件事：

```text
llmops Worker Agent
  -> ReActWorkerAgent 执行引擎
  -> WorkerInvocation
  -> WorkerResult / AgentEvent / ArtifactRef
```

也就是说，`ReActWorkerAgent` 不应该被设计成新的全局规划者，而应该是 `runtime_type = worker` 的执行引擎。后续新增 Planner Agent 时，只需要让 Planner 生成 `RouterPlan` 并调度这些 Worker，不再重写 Worker 执行协议。

### 9.1 概念对齐

`llmops` 里的 Agent 和 `agentic` 里的 ReActAgent 不是同一层对象：

| 对象 | 在 `llmops` 中的含义 | 对齐到 ReActWorkerAgent 后的含义 |
| --- | --- | --- |
| `Agent` 表 | 平台侧 Agent 资产，区分 router/worker，管理名称、状态、可见范围、target ref | 仍然是平台资产，不直接执行 LLM loop |
| `AgentVersion` | 保存模型、prompt、worker_config、capability_bindings | 增加执行引擎配置，例如 `execution_agent_type = react_worker` |
| App Worker | 当前把 App 转成 Worker Agent，`target_ref_type = app` | 第一批 ReActWorkerAgent 的执行对象 |
| `WorkerRuntime` | 当前 placeholder | 负责加载 worker 配置并派发给 `ReActWorkerAgent` |
| `ReActWorkerAgent` | 当前未实现 | 执行单个 `WorkerInvocation`，不修改全局计划 |

推荐约束：

- `Agent.runtime_type = worker` 表示它是可被 Router/Planner 调度的 Worker。
- `AgentVersion.worker_config.execution_agent_type = react_worker` 表示它由 ReActWorkerAgent 执行。
- `Agent.target_ref_type` 表示执行对象来源，第一阶段支持 `app`，后续扩展 `workflow`、`sandbox`、`external_agent`。
- `ReActWorkerAgent` 只执行单步任务，输出 `WorkerResult`，不创建或更新 `RouterPlan`。

### 9.2 当前差异

| 维度 | 当前 `llmops` | 目标 ReActWorkerAgent 对齐 |
| --- | --- | --- |
| Worker 调用入口 | `RouterAgentManagerService._invoke_worker()` 直接调用 `AppService.debug_chat()` | `RouterAgentManagerService` 只构造 `WorkerInvocation`，交给 `WorkerRuntime.invoke()` |
| 执行结果 | 从 SSE chunks 中拼 `answer`，其余事件大多丢失 | 标准 `WorkerResult`，包含 summary、data、actions、evidence、artifacts、errors |
| 事件 | App debug chat 输出 `QueueEvent` 风格 SSE | 转成 `AgentEvent`，同时写入 `TraceEvent` |
| 工具调用 | AppService 内部已经支持 tool_call 和 JSON ReAct 工具调用 | ReActWorkerAgent 复用这条能力，但工具必须来自平台 Capability |
| 文件 | App debug chat 当前主要面向聊天请求 | `WorkerInvocation.context.input_files` 输入，`WorkerResult.artifacts` 输出 |
| 运行上下文 | 依赖 debug conversation/message | Worker 运行应独立于“调试聊天”，必要时再桥接 conversation |
| 错误处理 | 异常进入 task/step failed，工具错误信息不完整 | WorkerResult 结构化表达 failed/cancelled/waiting、retryable、error_code |
| 审计 | 有 task/step/worker_call/trace，但 worker call 中不是标准 invocation/result | worker_call 保存标准 invocation/result，trace 保存关键 AgentEvent |

最关键的问题不是“有没有 ReAct 能力”。`AppService._run_iterative_agent()` 已经具备 ReAct 雏形：能识别 provider tool_call，也能解析 JSON 文本工具调用，并把工具结果追加回上下文。真正缺的是把这条能力从 debug chat 中抽出来，挂到标准 Worker 协议上。

### 9.3 第一阶段落地方案

第一阶段只做执行 agent 对齐，不做 Planner：

1. 协议先定稿。
   - `WorkerInvocation` 增加 `account_id` 兼容字段、`context.input_files`、`context.artifacts`、`execution_policy`。
   - `WorkerResult` 明确状态枚举：`succeeded`、`failed`、`cancelled`、`waiting_user`、`waiting_approval`。
   - 新增 `AgentEvent`，承接 `agent_thought`、`agent_action`、`dataset_retrieval`、`agent_message`、`error`、`timeout`。
   - 新增 `ArtifactRef`，用于 Worker 输出文件和步骤间传递。

2. 标记 Worker 执行引擎。
   - App 转 Worker 时，在 `AgentVersion.worker_config` 中记录 `execution_agent_type = react_worker`。
   - `target_ref_type = app` 保持不变，表示这个 ReActWorkerAgent 背后执行的是一个 App 配置。
   - UI 后续可展示为“Worker Agent / ReAct 执行”，但这一步不需要改 Planner 类型。

3. 抽出 App-backed ReAct 执行入口。
   - 不建议长期通过 `debug_chat()` 的 SSE 字符串反解析结果。
   - 建议从 `AppService` 抽出内部方法，例如 `run_app_worker(...) -> Iterator[AgentThought]`。
   - `debug_chat()` 和 `ReActWorkerAgent` 都复用这个方法。
   - 这样可以保留现有 App 的模型、prompt、工具、工作流、知识库能力，同时避免 WorkerRuntime 依赖前端调试接口。

4. 实现 `ReActWorkerAgent` 执行接口。
   - 输入：`WorkerInvocation`、Worker Agent、AgentVersion、Account、DB session。
   - 执行：根据 `target_ref_type` 加载 App/Workflow/Sandbox 等实际执行对象。
   - 输出：`WorkerResult`。
   - 事件：把 `AgentThought/QueueEvent` 映射成 `AgentEvent`。
   - 约束：不能创建或修改全局 Plan。

5. 改造 `WorkerRuntime.invoke()`。
   - 根据 `AgentVersion.worker_config.execution_agent_type` 派发执行引擎。
   - 第一阶段只支持 `react_worker`。
   - 对不支持的 `target_ref_type` 返回结构化失败，不直接抛给 Router。

6. 让当前 Router Manager 走标准 WorkerRuntime。
   - `build_manager_plan()` 仍可保留规则式 `manager_rule_v1`。
   - `execute_manager_run_steps()` 改成构造 `WorkerInvocation`，记录 `WorkerCall.invocation_json`，调用 `WorkerRuntime.invoke()`，记录 `WorkerCall.result_json`。
   - 这一步完成后，即使没有 Planner Agent，Worker 执行协议也已经统一。

7. Trace 和前端展示准备。
   - `worker.call.started/succeeded/failed` 保留。
   - ReAct 过程事件写为 `agent.event.*` 或 `worker.event.*`。
   - 前端 Agent Task 执行台后续可以直接展示 plan、step、worker call、tool action、artifact。

### 9.4 文件与 Artifact 的处理

第一阶段 ReActWorkerAgent 不直接传二进制文件：

```json
{
  "context": {
    "input_files": [
      {
        "file_id": "uuid",
        "name": "sales.xlsx",
        "mime_type": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
      }
    ],
    "artifacts": []
  }
}
```

输出使用 `ArtifactRef`：

```json
{
  "artifacts": [
    {
      "file_id": "uuid",
      "name": "analysis.md",
      "type": "report",
      "source": "agent",
      "task_id": "uuid",
      "step_id": "uuid",
      "worker_id": "uuid",
      "summary": "销售数据分析报告"
    }
  ]
}
```

如果执行过程中需要 sandbox，应该由 ReActWorkerAgent 内部把 Files 同步进 sandbox，完成后再把 sandbox 产物登记回 Files，并只在 `WorkerResult` 中返回引用。

### 9.5 这一步的验收标准

完成“Worker Agent 对齐 ReActWorkerAgent”后，应满足：

- 现有 App Worker 可以不经过 Planner，直接通过 `WorkerRuntime.invoke()` 执行。
- Router Manager 的规则式计划仍可运行，但 Worker 调用入口已经统一。
- `WorkerCall.invocation_json` 保存标准 `WorkerInvocation`。
- `WorkerCall.result_json` 保存标准 `WorkerResult`。
- ReAct 执行过程中的工具调用、知识库检索、模型回答、错误都能映射为 `AgentEvent`。
- Worker 不修改全局计划，不调度其他 Worker。
- 后续新增 Planner Agent 时，只需要生成 `RouterPlan` 并调用同一套 WorkerRuntime。

### 9.6 暂不做的事项

这一阶段明确不做：

- 不实现 LLM PlannerAgent。
- 不迁移完整 `agentic` 的 `PlannerReActFlow`。
- 不让 Worker 递归调用 Planner。
- 不把 A2A 作为内部核心协议。
- 不直接暴露 shell/browser/file 工具给 LLM，必须先经过平台 Capability、权限和审计设计。

### 9.7 更细代码调研：llmops 已有能力

进一步看代码后，`llmops` 当前已经具备不少 ReActWorkerAgent 所需的执行能力。第一阶段不应重做这些能力，而应该把它们从 App 调试链路中抽成 Worker 执行链路。

已有能力如下：

| 能力 | 当前代码位置 | 当前实现 | 对 ReActWorkerAgent 的意义 |
| --- | --- | --- | --- |
| ReAct 式迭代执行 | `llmops/api/app/services/app_service.py::_run_iterative_agent()` | 支持 provider tool_call；也支持从模型文本中解析 JSON 工具调用；工具结果会追加回 messages | 可以作为 App-backed ReAct 执行内核，不需要从 `agentic` 重写一套 |
| 工具 schema 构建 | `AppService._capabilities_to_openai_tools()`、`ToolCapabilityAdapter` | 把 runtime capability 转成 LLM tools schema | 可直接服务 ReActWorkerAgent 的工具声明 |
| 工具执行 | `AppService._invoke_runtime_capability()` | 支持 builtin tool、api tool、dataset/knowledge_base、workflow、create_app | 第一阶段 ReActWorkerAgent 可以复用这些平台工具 |
| Builtin Tool | `llmops/api/app/core/tools/builtin_tools/runtime.py` | `google_serper`、`duckduckgo_search`、`wikipedia_search`、`dalle3` 等通过 runtime tool 调用 | 已有基础搜索/生成类工具，不必搬 `agentic` SearchTool |
| API Tool | `llmops/api/app/core/tools/api_tools/providers/api_provider_manager.py` | 按 API Tool 配置发起调用 | 外部 API 能力已是平台工具 |
| RAG | `AppService._retrieve_dataset_context()`、`DatasetService.hit()` | 支持 semantic/full_text/hybrid，向量检索失败可回退词法检索 | 已可作为 knowledge_base capability |
| Workflow | `WorkflowService.validate_publish_graph()`、`_ordered_nodes()`、`_execute_node()` | 支持 start、llm、tool、dataset_retrieval、code、end 等节点执行 | Workflow 可作为 ReActWorkerAgent 的一个 capability 或独立 target executor |
| App -> Worker 描述 | `LegacyAppWorkerAdapter.app_to_worker_descriptor()` | 已把 App 的 model/prompt/tools/workflows/datasets 转成 WorkerAgentDescriptor | 已有 Worker Agent 资产化入口 |
| Router manager 最小闭环 | `RouterAgentManagerService` | 可创建 router/worker、绑定 worker、生成规则计划、执行 app worker、写 task/step/worker_call/trace | 只需把 `_invoke_worker()` 换成标准 WorkerRuntime 入口 |

因此，`llmops` 当前缺的不是“有没有工具调用/RAG/workflow”，而是：

- App 调试执行和 Worker 执行没有分离。
- `WorkerRuntime` 仍是 placeholder。
- `WorkerCall.invocation_json/result_json` 还不是标准 `WorkerInvocation/WorkerResult`。
- App 的 `QueueEvent/AgentThought` 还没有标准映射为 `AgentEvent`。
- 文件输入和产物输出还没有进入 `WorkerInvocation.context` 和 `WorkerResult.artifacts`。

### 9.8 更细代码调研：agentic 可借鉴能力

`agentic` 的 ReAct 执行能力更完整，但它是围绕会话型自主 Agent 构建的，不适合整体搬进 `llmops`。

| 能力 | 当前代码位置 | 实现特点 | 对 llmops 的处理 |
| --- | --- | --- | --- |
| ReAct 单步执行 | `agentic/api/app/core/agent/react.py::execute_step()` | 输入 plan/step/message，输出 StepEvent/ToolEvent/MessageEvent/WaitEvent/ErrorEvent | 借鉴事件语义，不直接复用 Plan/Step |
| LLM/tool 循环 | `agentic/api/app/core/agent/base.py::invoke()` | LLM 每次最多取一个 tool_call；工具结果写回 memory；支持 max_iterations | llmops 已有类似循环，可补 max_tool_calls/execution_policy |
| Memory | `BaseAgent._ensure_memory()`、`compact_memory()`、`roll_back()` | 按 session_id + agent.name 维护 memory；用户追问时处理未完成 tool_call | llmops 第一阶段可先不做长期 memory，只预留 waiting_user/roll_back 策略 |
| 用户追问 | `MessageTool.message_ask_user()` + `WaitEvent` | 工具调用可中断任务等待用户输入 | llmops 需要区分 `waiting_user` 和 `waiting_approval` |
| 文件/sandbox | `AgentTaskRunner._sync_message_attachments_to_sandbox()`、`_sync_message_attachments_to_storage()` | 用户附件进 sandbox，产物文件回存储 | llmops 应改成 Files + ArtifactRef，不暴露 sandbox path |
| Browser/Shell/File 工具 | `agentic/api/app/core/tools/browser.py`、`shell.py`、`file.py` | 直接给 LLM 操作 sandbox/browser/shell/file | llmops 后续作为 SandboxExecutor/Capability 接入，需权限和审计 |
| MCP | `agentic/api/app/core/tools/mcp.py` | 支持 stdio/sse/streamable_http，缓存 ClientSession 和 tool schema | llmops 可借鉴 manager/executor 结构，但配置和密钥要走平台 |
| A2A | `agentic/api/app/core/tools/a2a.py` | 缓存 agent card，调用远程 agent | llmops 当前只预留 A2AExecutor，不把 A2A 放进内部核心协议 |
| 事件流 | `PlannerReActFlow` + `AgentTaskRunner` | Redis Stream 输入输出，会话保存事件 | llmops 保留 SQL task/trace，SSE 只是展示传输 |

`agentic` 最值得吸收的是四类结构：

- ReAct 单步事件语义。
- 用户等待/中断恢复语义。
- sandbox 文件同步和产物回存储流程。
- MCP/A2A 的 executor 管理思路。

但 `agentic` 的 `PlannerReActFlow`、session memory、Redis Stream 任务模型、Plan/Step 实体都不应该直接替换 `llmops` 当前的平台模型。

### 9.9 最小改动判断

如果当前阶段只做 ReActWorkerAgent 对齐，`llmops` 改动应当是小到中等，且集中在少数后端文件。

最小改动路径：

1. 在 `protocols.py` 补齐协议字段和新实体。
   - `WorkerInvocation.account_id` 或明确 `tenant_id` 兼容策略。
   - `WorkerInvocation.context.input_files/artifacts`。
   - `WorkerResult.events/artifacts/actions/evidence/errors`。
   - `AgentEvent`、`ArtifactRef`。

2. 从 `AppService.debug_chat()` 抽出可复用执行内核。
   - 当前 `debug_chat()` 负责建 conversation/message、格式化 SSE、保存消息。
   - 应新增内部执行方法，例如 `run_app_agent(...) -> list/iterator[AgentThought]`。
   - `debug_chat()` 继续做 SSE 包装。
   - `ReActWorkerAgent` 直接消费 `AgentThought`，不反解析 SSE。

3. 新增 `ReActWorkerAgent` 和 executor 分层。

```text
WorkerRuntime
  -> ReActWorkerAgent
      -> AppExecutor        第一阶段真实实现
      -> A2AExecutor        只预留接口和 target_ref_type
      -> MCPToolExecutor    只预留接口和 target_ref_type
      -> SandboxExecutor    后续接 browser/shell/file
```

4. 改 `WorkerRuntime.invoke()`。
   - 从 placeholder 改为读取 `execution_agent_type`。
   - 第一阶段只派发 `react_worker`。
   - 错误返回结构化 `WorkerResult`。

5. 改 `RouterAgentManagerService.execute_manager_run_steps()`。
   - 保留当前 `manager_rule_v1` 规则计划。
   - 把旧 `_invoke_worker()` 直接调用 AppService 的逻辑替换成 `WorkerInvocation -> WorkerRuntime.invoke()`。
   - 保存标准 invocation/result 到 `WorkerCall`。
   - 继续写现有 trace event。

6. App 转 Worker 时增加执行配置。
   - 在 `LegacyAppWorkerAdapter` 的 `worker_config` 中加 `execution_agent_type = react_worker`。
   - 不需要新增 Agent 类型。

不建议现在改：

- 不改 Router plan 生成逻辑。
- 不新建 PlannerAgent。
- 不改 UI 大结构。
- 不做完整 A2A/MCP/sandbox 实现。
- 不迁移数据库表；优先使用现有 JSONB 字段承载 invocation/result/config。

所以你的判断基本成立：`llmops` 已有不少能力，当前这一步改动不应大。真正要避免的是把 `ReActWorkerAgent` 做成“新的一整套 agentic runtime”。正确做法是把现有 `AppService` 的 ReAct 能力抽象为 Worker 执行内核，再把 `agentic` 的 sandbox/A2A/MCP 能力作为后续 executor 插件补进来。

### 9.10 对后续 Planner 的影响

如果当前阶段按上述方式完成，后续新增 Planner Agent 时，对 ReActWorkerAgent 的核心改动会很小：

- Planner 只生成 `RouterPlan`。
- Runtime 只把 plan step 转成 `WorkerInvocation`。
- ReActWorkerAgent 继续只执行单步。
- A2A/MCP/sandbox 只作为新的 executor/capability 增加。
- WorkerResult 仍是 Planner 判断重试、跳过、重规划、汇总的唯一输入。

也就是说，当前阶段只要把 `WorkerInvocation/WorkerResult/AgentEvent/ArtifactRef` 定稳，后续 Planner 接入不会推翻 ReActWorkerAgent。

## 10. 当前阶段待执行落地计划

本阶段目标只聚焦一件事：把 `llmops` 现有 Worker Agent 对齐到标准 ReActWorkerAgent 执行入口。Planner Agent 后续再做。

### 10.1 产品与对外类型确认

对外暴露的 AI 应用类型保持两类核心 Agent：

```text
AI 应用
  -> Planner Agent App
  -> Worker Agent App
```

其中：

- `Planner Agent` 是面向用户的规划型 App，可发布、调试、调用，负责生成计划、调度 Worker、汇总结果。
- `Worker Agent` 也是一种 App，可单独对外暴露，也可作为 Planner Agent 绑定的能力被调度。
- `ReActWorkerAgent` 不作为第三类产品暴露，只作为 Worker Agent 背后的执行引擎。
- 当前阶段不改 UI，先完成后端执行协议和运行入口。

### 10.2 本阶段实施范围

本阶段实施：

1. 补齐 Worker 执行协议。
2. 从现有 App 调试链路中抽出可复用执行内核。
3. 新增 ReActWorkerAgent 执行层。
4. 让 WorkerRuntime 从 placeholder 变成真实派发入口。
5. 让 RouterAgentManagerService 通过标准 WorkerRuntime 调用 Worker。
6. App 转 Worker 时标记执行引擎类型。
7. 增加后端测试，保证现有 App Worker 行为兼容。

本阶段不实施：

- 不做 Planner Agent。
- 不做 AutonomousAgentRuntime。
- 不做 Agent Task 执行台 UI。
- 不接完整 A2A/MCP/Sandbox。
- 不改现有 AI 应用 UI。
- 不新增大规模 DB migration；优先使用现有 JSONB 字段。

### 10.3 后端任务清单

#### 任务 1：协议补齐

修改 `llmops/api/app/domain/agent_runtime/protocols.py`：

- `WorkerInvocation` 增加或明确：
  - `account_id`
  - `context.input_files`
  - `context.artifacts`
  - `execution_policy.timeout`
  - `execution_policy.max_tool_calls`
  - `execution_policy.approval_policy`
- `WorkerResult` 增加或明确：
  - `status`
  - `summary`
  - `data`
  - `actions`
  - `evidence`
  - `artifacts`
  - `events`
  - `retryable`
  - `error_code`
  - `errors`
- 新增 `AgentEvent`。
- 新增 `ArtifactRef`。

状态建议：

```text
succeeded
failed
cancelled
waiting_user
waiting_approval
```

#### 任务 2：抽出 App 执行内核

修改 `llmops/api/app/services/app_service.py`：

- 保留 `debug_chat()` 作为 SSE 调试入口。
- 从 `debug_chat()` / `_run_debug_agent()` 中抽出可复用内部方法，例如：

```text
run_app_agent(...) -> Iterator[AgentThought]
```

- `debug_chat()` 继续负责：
  - 创建 debug conversation/message。
  - 把 `AgentThought` 格式化为 SSE。
  - 保存调试消息。
- ReActWorkerAgent 直接消费 `AgentThought`，避免反解析 SSE 字符串。

#### 任务 3：新增 ReActWorkerAgent

新增执行层文件，建议路径：

```text
llmops/api/app/domain/agent_runtime/react_worker_agent.py
```

职责：

- 接收 `WorkerInvocation`。
- 加载 Worker Agent 与 AgentVersion。
- 根据 `target_ref_type` 选择 executor。
- 第一阶段只真实支持 `target_ref_type = app`。
- 把 `AgentThought / QueueEvent` 映射为 `AgentEvent`。
- 返回标准 `WorkerResult`。
- 不创建、不修改、不重排全局计划。

建议内部结构：

```text
ReActWorkerAgent
  -> AppExecutor        第一阶段实现
  -> A2AExecutor        只预留
  -> MCPToolExecutor    只预留
  -> SandboxExecutor    后续实现
```

#### 任务 4：改造 WorkerRuntime

修改 `llmops/api/app/domain/agent_runtime/worker_runtime.py`：

- 从 placeholder 改为真实派发。
- 根据 `AgentVersion.worker_config.execution_agent_type` 选择执行引擎。
- 第一阶段支持：

```text
execution_agent_type = react_worker
```

- 不支持的执行类型返回结构化失败 `WorkerResult`，不要让异常直接穿透 Router。

#### 任务 5：改造 RouterAgentManagerService 调用路径

修改 `llmops/api/app/services/router_agent_manager_service.py`：

- 保留 `build_manager_plan()` 的 `manager_rule_v1` 规则计划。
- `execute_manager_run_steps()` 中：
  - 构造 `WorkerInvocation`。
  - 保存到 `WorkerCall.invocation_json`。
  - 调用 `WorkerRuntime.invoke()`。
  - 保存 `WorkerResult` 到 `WorkerCall.result_json`。
  - 将 `WorkerResult.status` 映射为 step/task 状态。
  - 将关键 `AgentEvent` 写入 `TraceEvent`。

保留兼容字段：

- `output["answer"]` 继续存在，避免现有测试和调用方被破坏。

#### 任务 6：App 转 Worker 标记执行引擎

修改 `llmops/api/app/services/agent_adapter_service.py`：

- 在 `LegacyAppWorkerAdapter._worker_config()` 中增加：

```json
{
  "execution_agent_type": "react_worker"
}
```

- `target_ref_type = app` 保持不变。
- `runtime_type = worker` 保持不变。

#### 任务 7：测试覆盖

建议新增或更新测试：

- `test_agent_adapter.py`
  - App 转 Worker 后 `worker_config.execution_agent_type = react_worker`。
- `test_worker_runtime.py`
  - `WorkerRuntime` 能派发到 ReActWorkerAgent。
  - AppExecutor 能把 `AgentThought` 转成 `WorkerResult`。
- `test_router_agent_manager_service.py`
  - `WorkerCall.invocation_json` 是标准 `WorkerInvocation`。
  - `WorkerCall.result_json` 是标准 `WorkerResult`。
  - 旧的 `answer` 字段仍兼容。
- `test_agent_debug_runtime.py`
  - `debug_chat()` 仍能正常 SSE 输出，避免抽内核破坏现有调试。

### 10.4 验收标准

本阶段完成后应满足：

- 现有 App Worker 能通过 `WorkerRuntime.invoke()` 执行。
- `RouterAgentManagerService` 不再直接调用 `AppService.debug_chat()` 执行 Worker。
- `WorkerCall.invocation_json` 保存标准 `WorkerInvocation`。
- `WorkerCall.result_json` 保存标准 `WorkerResult`。
- App 调试入口 `debug_chat()` 行为保持兼容。
- 工具调用、RAG、Workflow 调用事件能映射为 `AgentEvent`。
- `WorkerResult` 中保留 `answer` 兼容字段。
- 不改 UI 也能通过现有测试和后端调用完成执行闭环。

### 10.5 实施顺序

推荐按以下顺序实施：

1. 协议补齐。
2. 抽出 App 执行内核。
3. 新增 ReActWorkerAgent 与 AppExecutor。
4. 改 WorkerRuntime 派发。
5. 改 RouterAgentManagerService 调用路径。
6. App 转 Worker 增加 `execution_agent_type`。
7. 补测试。
8. 跑后端相关测试。

### 10.6 风险点

- 抽出 App 执行内核时不要破坏 `debug_chat()`、WebApp、OpenAPI、Assistant Agent 现有链路。
- 不要把 `ReActWorkerAgent` 写成只会反解析 SSE 的包装器。
- 不要让 Worker 修改全局计划。
- 不要在本阶段把 A2A/MCP/Sandbox 做实，避免范围膨胀。
- `tenant_id` 与 `account_id` 需要先兼容处理，避免牵出大规模迁移。

## 11. 结论

`llmops` 的 Agent 应该平台化，`agentic` 的 Agent 应该能力化。

`llmops` 做控制面和治理面，`agentic` 的 Planner/ReAct 思想成为运行面的能力来源。这样既能获得自主规划和执行能力，又能保留企业平台需要的模型管理、文件资产、密钥治理、权限审批、审计和可观测性。
