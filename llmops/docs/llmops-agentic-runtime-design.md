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

## 10. 结论

`llmops` 的 Agent 应该平台化，`agentic` 的 Agent 应该能力化。

`llmops` 做控制面和治理面，`agentic` 的 Planner/ReAct 思想成为运行面的能力来源。这样既能获得自主规划和执行能力，又能保留企业平台需要的模型管理、文件资产、密钥治理、权限审批、审计和可观测性。
