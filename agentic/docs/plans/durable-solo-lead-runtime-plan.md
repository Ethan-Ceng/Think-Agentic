# Durable Solo Lead Runtime 实施计划

## 关联设计

- 设计文档：`docs/autonomous-agent-upgrade-architecture.zh-CN.md`
- 前置计划：`agentic/docs/plans/agent-runtime-lazy-sandbox-plan.md`
- 开发分支：`feature/durable-solo-lead-runtime`（实施开始时从最新 `develop` 创建）
- 实施基线：当前 `develop`；保留用户已有改动，不混入本批
- 后续计划：本地 Child Execution 与有界并行、Project Memory 与 ContextCompiler

## 当前进度

- 整体状态：`PLAN_READY`
- 当前阶段：planning
- 当前任务：无
- 已完成：0 / 10
- 阻塞问题：无
- 最近更新时间：2026-08-17（Asia/Shanghai）

## 本批交付边界

本计划交付一个可以独立完成现有任务、配置冻结、状态耐久、可从数据库 Safe Point 恢复并经过 Runtime Verification 才结束的唯一 Lead Agent。完成本计划后，即使关闭所有本地 Child 能力，Lead 仍必须是完整可用的 Solo Agent。

本批包含：

- 代码内置的四 Profile Registry，以及新 Run 的只读 Effective Snapshot；只允许 `lead` 创建 Execution。
- 统一 `AgentHarness` 门面；第一阶段用适配器承载现有 `PlannerReActFlow`，保持用户行为稳定。
- Durable Run、初始 Goal Revision、Root Lead Execution、规范 Event、Outbox、Lease、Interaction、Tool Side-effect Ledger 和 Verification Attempt。
- RunCoordinator 唯一状态写入、数据库 Worker、Safe Point 恢复、可重放 SSE 和现有 Session/Trace 单向投影。
- 现有 Tool、Skill、Lazy Sandbox、附件、HITL、MCP、外部 A2A、下一条消息、分支与文件行为的兼容验证。

本批明确不包含：

- 创建或调度 `general_worker`、`researcher`、`reviewer` Child Execution。
- Lead 的 fan-out/fan-in、多线并行、Child Result Adoption 或 Reviewer 模型调用。
- Project Memory、Candidate 审阅、ContextCompiler 全量四层上下文。
- Agent Definition CRUD、发布、版本运营、Root Agent 选择或多 Agent 管理页面。
- Lead、Worker 或 Specialist 之间使用 A2A；A2A 仅继续作为外部 Tool Adapter。
- Steering 的多 Revision 产品交互；本批只创建不可覆盖的初始 Goal Revision，并为后续追加 Revision 保留数据契约。
- 基于评测的 Direct/ReAct 自动路由优化；本批先让 Harness 适配现有 Plan-ReAct 行为，避免把行为变化与耐久性切换混在一起。

## 全局约束

- 对外永远只有一个 Agent；每个 Durable Root Run 自动创建且只能创建一个 `lead` Root Execution。
- Registry 只能包含 `lead`、`general_worker`、`researcher`、`reviewer`；本批运行时必须拒绝创建非 `lead` Execution。
- `AgentService` 只保留认证后的 HTTP/SSE 兼容门面和 DTO 映射，不得拥有 Durable Task 生命周期或直接写 Run/Execution 终态。
- RunCoordinator 是 Durable Run、Execution、Interaction、Verification 和规范 Event 的唯一状态转换入口。
- PostgreSQL 是规范事实源；Redis 只用于唤醒和传输优化，Redis 丢失不得造成 Run 丢失或状态回退。
- HTTP/SSE 断开不得取消 Run；只有带稳定 Command ID 的显式 Cancel 才能取消。
- 新 Run 在进入 `ready` 前必须固定 Profile、模型、Tool、Skill、Knowledge、Sandbox、Memory 和 Verification Snapshot；配置变化只影响后续 Run。
- Snapshot 不保存 API Key、明文凭据、完整动态 Tool Schema或隐藏推理，只保存必要的脱敏配置、版本、引用和 Hash。
- 低信任 Tool、Knowledge、Memory 和 A2A 内容只能作为带来源 Observation，不得覆盖 Runtime Policy、用户目标或 Profile Instructions。
- 模型产生的 `DoneEvent` 或 finalize 建议不能直接把 Run 标为 completed；必须先进入 verifying 并通过确定性检查。
- Tool 在执行前必须有稳定幂等键和 Effect 状态；崩溃后处于 `unknown` 的副作用不得自动重试。
- 现有 Lazy Sandbox 语义保持不变：普通文本/Knowledge/Context Run 不创建 Sandbox，首次 Sandbox/Browser Tool 才激活，VNC 查询不诱发创建。
- `sessions.events` 和现有 Trace 仅作为 `agent_run_events` 的兼容投影；不得从投影反向恢复 Durable 状态。
- Legacy Run 与 Durable Run 通过 Runtime Kind 和 Feature Flag 隔离；Feature Flag 只影响新 Run，已创建 Run 按其 Runtime Version 恢复。
- 切流期间允许两种 Runtime 并存，但同一个 Run 只能有一个状态权威；不得长期双写两套状态机。
- 不持久化或展示模型隐藏思维链；只持久化 Public Plan、Decision Summary、Command、Observation、Evidence 和 Verification。
- 不自动提交、推送、创建 PR 或合并；实施、验证和审查结果必须即时写回本计划。

## 基线事实

- `AgentService._create_task()` 当前创建 `AgentTaskRunner` 和 `RedisStreamTask`，并把 `task_id` 写入 Session。
- `AgentService._get_task()` 依赖 `RedisStreamTask._task_registry`；数据库为 running 但进程内 Task 丢失时会终止孤儿 Run。
- `PlannerReActFlow.invoke()` 当前直接读取和更新 `SessionStatus`，并在进程内保存 Flow 状态与 Plan 引用。
- `AgentTaskRunner` 当前负责启动 Trace Run、初始化 Tool/Skill、投影事件、修改 Session 状态和资源清理。
- `TraceService` 当前创建 `agent_runs` 并把 Flow Event 投影到 `run_steps/tool_calls/model_calls/trace_events`；这些表尚不是恢复事实。
- `agent_runs` 已保存部分 Tool/Agent/LLM Snapshot，但缺少 Runtime Version、Root Execution、Goal Revision、状态版本、规范事件序号和完整有效配置快照。
- Lazy Sandbox、按需附件物化和按 Step Tool Scope 已完成；该能力必须作为新 Harness/Execution Adapter 的复用基线。

## 状态变更记录

| 日期时间 | 整体状态 | 当前任务 | 变更原因 |
| --- | --- | --- | --- |
| 2026-08-17（Asia/Shanghai） | `PLAN_READY` | 无 | 总体架构已确认，按 Lead 优先原则拆出 Durable Solo Lead 独立批次 |

## Task 1：建立内置 Profile Registry 与不可变 Effective Snapshot

状态：pending

### 目标

建立代码拥有的四 Profile Registry，并能在新 Run 进入可调度状态前生成确定、脱敏、带版本和 Hash 的 Effective Snapshot Map；本批只允许 `lead` 创建 Root Execution。

### 涉及文件

- `agentic/api/app/core/entities/agent_runtime.py`（新建）
- `agentic/api/app/core/agent/profiles/registry.py`（新建）
- `agentic/api/app/core/agent/profiles/registry.json`（新建）
- `agentic/api/app/core/agent/profiles/lead.json`（新建）
- `agentic/api/app/core/agent/profiles/general-worker.json`（新建）
- `agentic/api/app/core/agent/profiles/researcher.json`（新建）
- `agentic/api/app/core/agent/profiles/reviewer.json`（新建）
- `agentic/api/app/core/agent/profiles/instructions/`（新建随应用打包的只读 Instructions）
- `agentic/api/app/services/profile_resolver.py`（新建）
- `agentic/api/app/core/config.py`
- `agentic/api/tests/app/core/agent/test_builtin_profile_registry.py`（新建）
- `agentic/api/tests/app/services/test_profile_resolver.py`（新建）

### 依赖与接口

- 前置任务：无。
- 输入：用户当前 AppConfig、Tool Registry 摘要、Skill 选择结果、Sandbox/Memory/Verification Policy、Runtime Version。
- 输出：`BuiltinProfileRegistry`、严格 Profile Schema、`EffectiveProfileSnapshot`、`RunSnapshotMap`、稳定 `snapshot_hash` 和 `durable_runtime_enabled` Feature Flag。

### 实施步骤

1. 定义 Profile Key、Role、Capability Ceiling、Tool/Skill/Delegation/Context/Memory/Verification Policy、Runtime Limit 和输出契约的严格领域模型；拒绝未知字段、重复 Key、非法 Child Ref 和拓扑环。
2. 打包且只读注册 `lead/general_worker/researcher/reviewer`；Registry 加载失败时应用启动或 Run 准备必须明确失败，不得从数据库补出第五种 Profile。
3. 将 `lead.allowed_child_refs` 固定为三个内置 Child Ref，但在本批 Runtime Policy 中设置 `local_child_execution=false`；请求、模型输出和数据库内容均不能扩大拓扑。
4. 实现 Snapshot Materializer：解析 Provider、Model、参数、Fallback、能力检查、Tool Policy、精确 Skill 版本/Hash、Knowledge Ref、Sandbox Policy、Memory Ref 和 Verification Policy。
5. 在 Snapshot 中移除凭据、Secret、完整 Tool Schema、用户内容和隐藏推理；对规范化 JSON 计算稳定 Hash，并保存 Profile/Registry/Runtime Version。
6. 明确 Run 准备顺序：创建 pending 聚合 → 完成 Skill 选择与配置解析 → 原子写入 Snapshot Map → Root Execution 进入 ready；准备失败不得留下可领取 Execution。
7. 增加测试证明相同输入产生相同 Hash、配置修改只影响新 Snapshot、资源文件不可由请求覆盖、Registry 恰好四项且本批只能激活 Lead。

### 验证方式

- 运行：`uv run pytest tests/app/core/agent/test_builtin_profile_registry.py tests/app/services/test_profile_resolver.py -q`
- 运行：`uv run ruff check app/core/entities/agent_runtime.py app/core/agent/profiles/registry.py app/services/profile_resolver.py tests/app/core/agent/test_builtin_profile_registry.py tests/app/services/test_profile_resolver.py`
- 运行：`uv run python -m py_compile app/core/entities/agent_runtime.py app/core/agent/profiles/registry.py app/services/profile_resolver.py`
- 预期：退出 0；Registry 只能加载四个内置 Profile，Snapshot Hash 稳定且不含 Secret，非 Lead Execution 在本批被拒绝。

### 完成条件

- 任意新 Durable Run 都能在没有 Agent CRUD 或用户选择的情况下得到唯一 Lead Effective Snapshot，并且运行中配置变化不能修改该 Snapshot。

### 执行结果

待执行；完成后记录实际资源格式、Snapshot 字段、偏差与兼容处理。

### 验证证据

```text
待 Task 1 执行后填写实际命令、退出状态、关键结果和 Asia/Shanghai 时间。
```

## Task 2：建立统一 AgentHarness 与现有 Planner-ReAct 适配器

状态：pending

### 目标

让 Lead 的模型决策和执行策略统一经过 `AgentHarness`，同时用纯适配器承载现有 `PlannerReActFlow`，不在本任务改变现有用户行为。

### 涉及文件

- `agentic/api/app/core/agent/runtime/commands.py`（新建）
- `agentic/api/app/core/agent/runtime/observations.py`（新建）
- `agentic/api/app/core/agent/runtime/ports.py`（新建）
- `agentic/api/app/core/agent/runtime/harness.py`（新建）
- `agentic/api/app/core/agent/runtime/planner_react_adapter.py`（新建）
- `agentic/api/app/core/agent/agent_task_runner.py`
- `agentic/api/app/core/flows/planner_react.py`
- `agentic/api/tests/app/core/agent/test_agent_harness.py`（新建）
- `agentic/api/tests/app/core/agent/test_planner_react_harness_adapter.py`（新建）
- `agentic/api/tests/app/core/agent/test_agent_task_runner_completion.py`
- `agentic/api/tests/app/core/agent/test_skill_runtime_context.py`

### 依赖与接口

- 前置任务：Task 1。
- 输入：Lead Snapshot、Goal、公开 Plan/Step、Tool/Skill/Interaction Observation、预算与取消状态。
- 输出：`AgentHarness.observe_decide()`、结构化 Decision/Command、`PlanReActStrategyAdapter` 和不依赖 ORM/Provider SDK 的 Harness Port。

### 实施步骤

1. 定义可持久化的 Observation、Decision Summary 和 Command 类型；类型中不得出现隐藏推理字段或 Provider SDK 对象。
2. 定义 Direct、ReAct、Plan-ReAct、Verify 和 Repair 模式接口；本批兼容策略固定选择 Plan-ReAct，非兼容模式在未实现时必须明确拒绝而不是静默降级。
3. 用 `PlanReActStrategyAdapter` 包装现有 Flow；只有该适配器可直接构造 `PlannerAgent/ReActAgent`，Lead/Profile 不形成新的运行类层次。
4. 将 `AgentTaskRunner` 的 Flow 调用改为依赖 Harness Port；保留 Skill Runtime、Tool Scope、Lazy Sandbox、附件与事件形状。
5. 禁止 Harness 导入 ORM、Session Repository、FastAPI、Redis Client 或具体 LLM Provider；所有外部动作只返回 Command。
6. 增加架构测试，限制 Planner/ReAct 的直接构造位置，并证明 `lead` Snapshot 驱动同一 Harness。
7. 运行现有 Planner、ReAct、Skill、分支上下文和完成路径回归，确认适配器没有改变 Plan/Step/Message/Tool 事件顺序。

### 验证方式

- 运行：`uv run pytest tests/app/core/agent/test_agent_harness.py tests/app/core/agent/test_planner_react_harness_adapter.py tests/app/core/agent/test_agent_task_runner_completion.py tests/app/core/agent/test_skill_runtime_context.py tests/app/core/agent/test_branch_context_seed.py -q`
- 运行：`uv run ruff check app/core/agent/runtime app/core/agent/agent_task_runner.py app/core/flows/planner_react.py tests/app/core/agent/test_agent_harness.py tests/app/core/agent/test_planner_react_harness_adapter.py`
- 运行：`uv run python -m py_compile app/core/agent/runtime/commands.py app/core/agent/runtime/observations.py app/core/agent/runtime/ports.py app/core/agent/runtime/harness.py app/core/agent/runtime/planner_react_adapter.py`
- 预期：退出 0；现有 Flow 行为不回归，Harness 无基础设施依赖，Planner/ReAct 只作为内部策略适配器存在。

### 完成条件

- Lead 的所有后续耐久执行都可以通过同一个 Harness Port 驱动，而不要求重写现有 Planner/ReAct 行为。

### 执行结果

待执行；完成后记录适配边界、保留行为和任何必须延后的策略模式。

### 验证证据

```text
待 Task 2 执行后填写实际命令、退出状态、关键结果和 Asia/Shanghai 时间。
```

## Task 3：建立 Durable Run、Execution、Event 与 Outbox 数据契约

状态：pending

### 目标

把现有 Trace Run 提升为可恢复的运行聚合，并建立 Root Lead Execution、初始 Goal Revision、规范 Event、Outbox、Interaction 和 Verification 的数据库事实。

### 涉及文件

- `agentic/api/app/models/run_trace.py`
- `agentic/api/app/models/agent_runtime.py`（新建）
- `agentic/api/app/models/__init__.py`
- `agentic/api/app/repositories/runtime_repository.py`（新建）
- `agentic/api/app/repositories/db_runtime_repository.py`（新建）
- `agentic/api/app/repositories/uow.py`
- `agentic/api/app/repositories/db_uow.py`
- `agentic/api/alembic/versions/20260817_0001_durable_solo_lead_runtime.py`（新建，实际 Revision 以实施时迁移头为准）
- `agentic/api/tests/app/repositories/test_db_runtime_repository.py`（新建）
- `agentic/api/tests/app/models/test_agent_runtime_models.py`（新建）

### 依赖与接口

- 前置任务：Task 1。
- 输入：Effective Snapshot Map、初始 Goal、Run/Execution 状态机、Command ID。
- 输出：事务型 Runtime Repository，以及兼容历史 `agent_runs` 的可逆迁移。

### 实施步骤

1. 升级 `agent_runs`，增加 `runtime_kind/runtime_version/root_execution_id/current_goal_revision/profile_snapshot_map/budget_snapshot/verification_snapshot/version/next_run_seq`；历史记录回填为 `legacy`，不得伪造 Root Execution。
2. 新增 `agent_goal_revisions`，本批创建 revision 1 并保存 objective、success criteria、constraints 和 verification policy；禁止覆盖历史 Revision。
3. 新增 `agent_executions`，包含 root/parent、profile key/hash、role、state、lease owner/expiry/heartbeat、attempt、checkpoint、task brief、result、adoption、version 和时间字段；本批数据库约束和 Service Policy 只允许一个 Root Lead。
4. 新增 append-only `agent_run_events`，保证 `run_id + run_seq` 唯一，并为稳定 `command_id` 建立幂等唯一约束；Event Payload 必须通过脱敏验证。
5. 新增 `agent_outbox`，保存 event/topic/status/attempt/next_attempt_at；规范 Event 与 Outbox 必须在同一事务提交。
6. 新增 `agent_interactions` 和 `agent_verification_attempts`；前者保存 action、status、resolution 和 version，后者保存 goal revision、checks、evidence、outcome 和 attempt。
7. 升级 `run_steps/tool_calls/model_calls` 增加 nullable `execution_id` 与 Snapshot/Plan Revision 关联；历史 Trace 保持可读。
8. 为 `tool_calls` 增加 `idempotency_key/effect_status/approval_status/result_ref`；`arguments_hash` 保持脱敏审计用途。
9. 实现事务 Repository：创建聚合、追加顺序 Event、CAS 状态更新、领取 Execution、续租、释放/过期重领、Outbox 领取与完成；业务状态写入不继续扩展 TraceRepository。
10. 在一次性测试数据库执行 upgrade、数据回填检查、downgrade、再次 upgrade；验证历史 Run/Trace 查询不丢失。

### 验证方式

- 运行：`uv run pytest tests/app/models/test_agent_runtime_models.py tests/app/repositories/test_db_runtime_repository.py tests/app/services/test_trace_service.py -q`
- 运行：`uv run alembic upgrade head`
- 手工：在一次性测试数据库执行本迁移的 downgrade/upgrade 往返，并核对历史 `agent_runs/run_steps/tool_calls/model_calls/trace_events` 行数和关键字段。
- 运行：`uv run ruff check app/models/run_trace.py app/models/agent_runtime.py app/repositories/runtime_repository.py app/repositories/db_runtime_repository.py app/repositories/uow.py app/repositories/db_uow.py tests/app/models/test_agent_runtime_models.py tests/app/repositories/test_db_runtime_repository.py`
- 预期：退出 0；并发追加 Event 不产生重复序号，历史记录保持 legacy 可读，事务失败不留下半个 Run、Execution 或 Outbox。

### 完成条件

- PostgreSQL 已具备恢复一个 Solo Lead Run 所需的全部规范事实，且 `sessions.events`、Redis 和 Trace 均不是反向恢复依赖。

### 执行结果

待执行；完成后记录实际 Revision、Schema 偏差、回填统计和迁移往返结果。

### 验证证据

```text
待 Task 3 执行后填写实际命令、退出状态、迁移结果和 Asia/Shanghai 时间。
```

## Task 4：实现 RunCoordinator 与单一状态写入门禁

状态：pending

### 目标

让所有 Durable Run/Execution 状态变化都由 RunCoordinator 在数据库事务中通过幂等 Command 和规范 Event 完成，切断 Controller、AgentService、Flow、Worker 和 Trace 对 Durable 终态的直接写入。

### 涉及文件

- `agentic/api/app/core/agent/runtime/state_machine.py`（新建）
- `agentic/api/app/core/agent/runtime/commands.py`
- `agentic/api/app/services/run_coordinator.py`（新建）
- `agentic/api/app/services/agent_service.py`
- `agentic/api/app/services/trace_service.py`
- `agentic/api/app/core/flows/planner_react.py`
- `agentic/api/app/dependencies/services.py`
- `agentic/api/app/core/config.py`
- `agentic/api/tests/app/services/test_run_coordinator.py`（新建）
- `agentic/api/tests/app/architecture/test_runtime_state_ownership.py`（新建）
- `agentic/api/tests/app/services/test_agent_service_recovery.py`

### 依赖与接口

- 前置任务：Task 1–3。
- 输入：Create Run、Record Observation、Wait、Resume、Cancel、Begin Verification、Complete、Fail Command。
- 输出：RunCoordinator、显式 Run/Execution 状态机、稳定错误码、状态版本和规范 Event。

### 实施步骤

1. 编码 Run 与 Execution 合法转换表；任何非法跳转、过期 version、重复 Command 或跨用户访问必须返回稳定领域错误。
2. 实现 `create_run`：持久化初始 Goal Revision、Snapshot Map、Root Lead Execution 和 `run.created/execution.ready` Event；只有完整准备成功后才允许领取。
3. 实现 Observation、Wait/Resume、Cancel、Verification 和终态 Command；每次转换用 CAS version、追加 Event 并写 Outbox。
4. 让 `AgentService` 在 `durable_runtime_enabled` 且新消息开始新 Run 时只提交 Coordinator Command；Legacy Run 继续走旧 Task 路径。
5. Durable 路径不再调用 `_finalize_orphaned_run()`，也不根据 `_task_registry` 判定运行是否存活；旧逻辑必须被 Runtime Kind 隔离。
6. 移除或隔离 `PlannerReActFlow` 对 Durable Session/Run 状态的直接写入；Flow 只能返回 Observation/Command。
7. 将 TraceService 的 Run 状态写入限制为 legacy 或投影，禁止其决定 Durable Run 状态。
8. 增加 AST/依赖守卫，扫描 Durable 路径中对 `AgentRunModel.status`、`AgentExecutionModel.state` 和 Durable Repository 私有更新原语的越权写入。
9. 覆盖重复提交、并发 Cancel/Complete、Wait/Resume、准备失败和用户隔离测试。

### 验证方式

- 运行：`uv run pytest tests/app/services/test_run_coordinator.py tests/app/architecture/test_runtime_state_ownership.py tests/app/services/test_agent_service_recovery.py tests/app/services/test_agent_interactions.py -q`
- 运行：`uv run ruff check app/core/agent/runtime/state_machine.py app/services/run_coordinator.py app/services/agent_service.py app/services/trace_service.py app/core/flows/planner_react.py tests/app/services/test_run_coordinator.py tests/app/architecture/test_runtime_state_ownership.py`
- 预期：退出 0；同一 Command 重放不重复创建事实，并发状态竞争只有一个合法结果，Durable 路径不存在 Coordinator 之外的终态写入。

### 完成条件

- RunCoordinator 成为 Durable Runtime 的唯一状态裁决者，AgentService 和 Flow 只负责门面与决策适配。

### 执行结果

待执行；完成后记录实际 Command 集、状态转换和被移除或隔离的旧写入点。

### 验证证据

```text
待 Task 4 执行后填写实际命令、退出状态、竞争测试结果和 Asia/Shanghai 时间。
```

## Task 5：实现数据库 Execution Scheduler、Lease 与 Redis 可丢失唤醒

状态：pending

### 目标

用数据库可领取的 Root Lead Execution 和 Lease 替代进程内 Task Registry 对 Durable 生命周期的所有权，并在 Redis 不可用时仍能通过周期扫描继续执行。

### 涉及文件

- `agentic/api/app/core/agent/runtime/scheduler.py`（新建）
- `agentic/api/app/core/agent/runtime/worker.py`（新建）
- `agentic/api/app/core/agent/runtime/wakeup.py`（新建）
- `agentic/api/app/services/execution_scheduler.py`（新建）
- `agentic/api/app/core/task/redis_stream_task.py`
- `agentic/api/app/main.py`
- `agentic/api/app/dependencies/services.py`
- `agentic/api/tests/app/core/agent/test_execution_scheduler.py`（新建）
- `agentic/api/tests/app/core/agent/test_execution_lease_recovery.py`（新建）
- `agentic/api/tests/app/core/task/test_redis_stream_task_lifecycle.py`

### 依赖与接口

- 前置任务：Task 3–4。
- 输入：ready Execution、Worker ID、Lease TTL、Heartbeat Interval、数据库扫描与可选 Redis Wake-up。
- 输出：原子领取、Heartbeat、Lease Expiry 重领、取消检查和应用生命周期启动/关闭。

### 实施步骤

1. 使用数据库原子领取或 `FOR UPDATE SKIP LOCKED`，保证多个 Worker 竞争同一 Execution 时只有一个 Lease Owner。
2. 实现 Heartbeat 和带 version 的续租；失去 Lease 的 Worker 必须停止提交 Observation，不能写成功终态。
3. 实现过期 Lease 扫描和 `lease_expired → ready`；记录 Recovery Event、attempt 和旧 Owner，不删除历史。
4. Outbox Dispatcher 向 Redis 发送 Wake-up；发送失败保持 pending 并重试，Scheduler 周期扫描数据库作为最终补偿。
5. 在应用 lifespan 中启动和优雅关闭 Scheduler/Outbox Dispatcher；关闭时停止领取新任务，当前任务在 Safe Point 退出或让 Lease 自然过期。
6. Durable Execution 不创建 `RedisStreamTask`，不注册 `_task_registry`；Legacy Runtime 保留旧实现直到恢复 Gate 通过。
7. 增加两个 Scheduler 竞争、Heartbeat 丢失、Worker 取消、Redis 启停和服务关闭测试；验证事件不重不漏且不会并发执行同一 Lease。

### 验证方式

- 运行：`uv run pytest tests/app/core/agent/test_execution_scheduler.py tests/app/core/agent/test_execution_lease_recovery.py tests/app/core/task/test_redis_stream_task_lifecycle.py -q`
- 集成：在真实 PostgreSQL/Redis 上启动两个 Scheduler，领取同一 ready Execution；停止当前 Owner 并等待 Lease 过期后确认另一实例重领。
- 集成：执行期间停止 Redis，确认数据库扫描仍可领取；恢复 Redis 后 Outbox 最终清空且 Event 序号不重复。
- 运行：`uv run ruff check app/core/agent/runtime/scheduler.py app/core/agent/runtime/worker.py app/core/agent/runtime/wakeup.py app/services/execution_scheduler.py app/main.py tests/app/core/agent/test_execution_scheduler.py tests/app/core/agent/test_execution_lease_recovery.py`
- 预期：退出 0；进程内 Registry 不再拥有 Durable Run，Redis 丢失仅影响唤醒延迟。

### 完成条件

- Root Lead Execution 可以在没有原进程 Task 对象的情况下被领取、续租、取消和重新领取。

### 执行结果

待执行；完成后记录 Lease 参数、扫描周期、Redis 故障行为和资源清理结果。

### 验证证据

```text
待 Task 5 执行后填写实际命令、退出状态、故障注入结果和 Asia/Shanghai 时间。
```

## Task 6：接通 Durable Lead 执行适配器与可恢复 Safe Point

状态：pending

### 目标

让 Worker 能从 Snapshot 和 Durable Checkpoint 重建 Lead Harness，并在计划、模型、步骤和结果边界提交足够恢复的公开状态，而不依赖进程内 Flow 对象或 `sessions.events`。

### 涉及文件

- `agentic/api/app/core/agent/runtime/execution_adapter.py`（新建）
- `agentic/api/app/core/agent/runtime/checkpoint.py`（新建）
- `agentic/api/app/core/agent/runtime/harness.py`
- `agentic/api/app/core/agent/runtime/planner_react_adapter.py`
- `agentic/api/app/core/agent/agent_task_runner.py`
- `agentic/api/app/core/agent/base.py`
- `agentic/api/app/core/flows/planner_react.py`
- `agentic/api/app/services/trace_service.py`
- `agentic/api/tests/app/core/agent/test_durable_lead_execution.py`（新建）
- `agentic/api/tests/app/core/agent/test_durable_checkpoint_recovery.py`（新建）
- `agentic/api/tests/app/core/agent/test_hidden_reasoning_redaction.py`（新建）

### 依赖与接口

- 前置任务：Task 2、4、5。
- 输入：Leased Root Execution、Run/Goal/Profile Snapshot、规范 Event、Checkpoint 和当前 Session 输入。
- 输出：可重建的 Lead Harness、公开 Observation、Checkpoint 和 Safe Point 恢复协议。

### 实施步骤

1. 从 `AgentTaskRunner` 提取可复用的 Durable Lead Execution Adapter；它接收固定 Snapshot 和 Execution ID，不自行创建 Run 或修改 Durable 状态。
2. 定义首版 Safe Point：Run 准备完成、计划已提交、模型 Decision 已脱敏提交、Tool Command 已准备、Tool Observation 已提交、Interaction 已持久化、Step 已完成、Verification 已请求。
3. Checkpoint 只保存公开 Plan/Step、已提交 Observation 引用、预算、当前模式和重建游标；不得序列化 LLM/Sandbox/Browser/MCP/A2A SDK 对象。
4. 将 Planner/ReAct 的 Session Memory 使用调整为执行可重建的公开记忆；保存模型响应前删除 `reasoning_content` 和等价隐藏思维字段。
5. Durable 路径中的 Model Call 绑定 Execution 和 Profile Snapshot Hash；可以重试未产生副作用的模型调用，但必须记录 attempt 和预算消耗。
6. Worker 每次提交 Observation 前验证 Lease 和 Execution version；失租后的迟到结果只能记录诊断，不能推进状态。
7. 从最新 Checkpoint、规范 Event 和待处理 Command 重建 Harness；禁止读取 `sessions.events` 决定下一状态。
8. 故障注入覆盖计划提交前后、模型调用前后、Step 完成前后和 Summary 前后；验证已提交步骤不会被错误回退，事件不会重复投影。

### 验证方式

- 运行：`uv run pytest tests/app/core/agent/test_durable_lead_execution.py tests/app/core/agent/test_durable_checkpoint_recovery.py tests/app/core/agent/test_hidden_reasoning_redaction.py tests/app/core/agent/test_agent_task_runner_completion.py tests/app/core/agent/test_skill_runtime_context.py -q`
- 运行：`uv run ruff check app/core/agent/runtime/execution_adapter.py app/core/agent/runtime/checkpoint.py app/core/agent/runtime/harness.py app/core/agent/runtime/planner_react_adapter.py app/core/agent/agent_task_runner.py app/core/agent/base.py app/core/flows/planner_react.py tests/app/core/agent/test_durable_lead_execution.py tests/app/core/agent/test_durable_checkpoint_recovery.py tests/app/core/agent/test_hidden_reasoning_redaction.py`
- 预期：退出 0；在每个声明的 Safe Point 杀死并重建 Worker 后，Lead 从数据库继续，且持久化内容不含隐藏推理。

### 完成条件

- Lead 的执行进度可以由新进程仅凭数据库事实和固定 Snapshot 重建，进程内 Flow/Harness 丢失不再终止 Run。

### 执行结果

待执行；完成后记录实际 Safe Point、可接受的模型重试边界和恢复演练结果。

### 验证证据

```text
待 Task 6 执行后填写实际命令、退出状态、各 Safe Point 恢复结果和 Asia/Shanghai 时间。
```

## Task 7：建立 Tool Side-effect Ledger 与可恢复 HITL

状态：pending

### 目标

让所有 Durable Tool 调用先经过 Coordinator 的权限、Scope、预算、Approval、幂等和副作用状态检查，并让 ask-user/审批在进程重启后精确恢复。

### 涉及文件

- `agentic/api/app/core/agent/runtime/commands.py`
- `agentic/api/app/services/run_coordinator.py`
- `agentic/api/app/services/tool_execution_service.py`（新建）
- `agentic/api/app/core/agent/base.py`
- `agentic/api/app/core/tools/filter.py`
- `agentic/api/app/core/tools/scope.py`
- `agentic/api/app/services/agent_service.py`
- `agentic/api/app/controllers/session.py`
- `agentic/api/app/repositories/runtime_repository.py`
- `agentic/api/app/repositories/db_runtime_repository.py`
- `agentic/api/tests/app/services/test_durable_tool_execution.py`（新建）
- `agentic/api/tests/app/services/test_durable_interactions.py`（新建）
- `agentic/api/tests/app/services/test_agent_interactions.py`
- `agentic/api/tests/app/core/agent/test_interaction_resume.py`
- `agentic/api/tests/app/core/agent/test_runtime_tool_scope.py`

### 依赖与接口

- 前置任务：Task 3–6。
- 输入：Tool Command、Function/Arguments Hash、Risk/Approval Policy、Execution Snapshot、Interaction Resolution。
- 输出：稳定 Idempotency Key、Effect 状态机、Durable Interaction、Tool Observation 和恢复/对账规则。

### 实施步骤

1. 将 Durable Tool Loop 从 `BaseAgent` 的直接 `tool.invoke()` 改为提交 Tool Command；ToolExecutionService 只能执行 Coordinator 已批准且与当前 Snapshot/Scope 匹配的调用。
2. 以 `run_id/execution_id/plan_revision/step_id/tool_call_id/function_name/arguments_hash` 生成稳定 Idempotency Key；重复 Command 返回既有结果或当前状态。
3. 定义 Effect 状态：`prepared → approval_pending → executing → succeeded|failed|unknown → reconciled`；只读/幂等 Tool 可按策略重试，外部副作用为 unknown 时必须等待对账或用户处理。
4. 在真实执行前重新检查 ToolConfig、Runtime Scope、Profile Ceiling、预算和取消状态；Scope 只能缩小 Snapshot 能力。
5. 将 `message_ask_user` 和高风险 Tool Approval 写入 `agent_interactions`；Session JSONB 只接收兼容投影。
6. Interaction Resolution 使用 action version 和稳定 Command ID；批准、拒绝或回答只能消费一次，并精确匹配原 Tool Call、Function 和 Arguments Hash。
7. 保持 Lazy Sandbox 行为：审批前不创建 Sandbox，批准后首次真实调用才激活；附件仍按需物化且不重复。
8. 保持 MCP/API/外部 A2A 为 Tool Adapter；测试证明它们不会创建本地 Child Execution 或扩大 Profile Catalog。
9. 在 Tool 执行请求发送前、发送后未回包、结果提交前分别杀死 Worker，验证已知结果不重复执行，unknown 不盲目重试。

### 验证方式

- 运行：`uv run pytest tests/app/services/test_durable_tool_execution.py tests/app/services/test_durable_interactions.py tests/app/services/test_agent_interactions.py tests/app/core/agent/test_interaction_resume.py tests/app/core/agent/test_runtime_tool_scope.py tests/app/core/agent/test_lazy_attachment_materialization.py tests/app/core/sandbox/test_lazy_sandbox_runtime.py -q`
- 集成：使用可计数的副作用 Fake Tool 和真实 Lazy Sandbox 执行批准、进程终止、恢复与重复 Resolution，确认副作用最多一次或进入 unknown 待对账。
- 运行：`uv run ruff check app/services/tool_execution_service.py app/services/run_coordinator.py app/core/agent/base.py app/core/tools/filter.py app/core/tools/scope.py app/services/agent_service.py app/controllers/session.py tests/app/services/test_durable_tool_execution.py tests/app/services/test_durable_interactions.py`
- 预期：退出 0；审批恢复精确一次，unknown 不自动重试，外部 A2A 仍是 Tool Call 而不是本地 Execution。

### 完成条件

- Durable Lead 的所有 Tool 副作用都可审计、可恢复且不会因 Worker 重领而被盲目重复执行。

### 执行结果

待执行；完成后记录 Effect 分类、对账策略、兼容投影和故障注入结果。

### 验证证据

```text
待 Task 7 执行后填写实际命令、退出状态、副作用计数和 Asia/Shanghai 时间。
```

## Task 8：实现确定性 Verification 与有限 Solo Repair

状态：pending

### 目标

让模型的完成建议只能触发 verifying，由 VerificationService 根据目标、计划、交互、Tool、Artifact 和证据决定完成、有限修复或失败。

### 涉及文件

- `agentic/api/app/services/verification_service.py`（新建）
- `agentic/api/app/core/agent/runtime/verification.py`（新建）
- `agentic/api/app/core/agent/runtime/harness.py`
- `agentic/api/app/services/run_coordinator.py`
- `agentic/api/app/repositories/runtime_repository.py`
- `agentic/api/app/repositories/db_runtime_repository.py`
- `agentic/api/tests/app/services/test_verification_service.py`（新建）
- `agentic/api/tests/app/core/agent/test_durable_lead_verification.py`（新建）
- `agentic/api/tests/app/core/agent/test_agent_task_runner_completion.py`

### 依赖与接口

- 前置任务：Task 4、6–7。
- 输入：Goal Revision、Success Criteria、Plan/Step、Pending Interaction、Tool Ledger、Artifact/Evidence、预算和 Repair Attempt。
- 输出：Verification Attempt、`passed/repair_required/failed` Outcome、Evidence Ref 和受限 Repair Observation。

### 实施步骤

1. 实现确定性检查：存在最终公开结果、必要 Plan Step 终态、无 pending Interaction、无 executing/unknown 副作用、要求的 Artifact 可访问、预算和取消状态一致。
2. `DoneEvent` 或 Harness finalize 只提交 BeginVerification Command；Coordinator 将 Run 从 running 转为 verifying。
3. 将每次检查、证据引用、Outcome 和 Goal Revision 写入 `agent_verification_attempts` 与规范 Event，不保存敏感 Artifact 明文。
4. 对可修复失败生成结构化 Repair Observation，返回同一个 Lead Harness；按 Snapshot 中的 `max_repair_attempts` 和剩余预算限制次数。
5. 对 unknown 副作用、取消、授权失败或修复预算耗尽返回明确 failed/waiting_user，不能让模型覆盖。
6. 本批 `reviewer` Profile 保持不可调度；Verification Snapshot 明确 `reviewer_mode=disabled`，后续计划可增加 Reviewer Execution 而不改变完成状态机。
7. 测试模型自报完成、缺 Artifact、Pending Approval、Tool unknown、修复成功和修复耗尽路径。

### 验证方式

- 运行：`uv run pytest tests/app/services/test_verification_service.py tests/app/core/agent/test_durable_lead_verification.py tests/app/core/agent/test_agent_task_runner_completion.py -q`
- 运行：`uv run ruff check app/services/verification_service.py app/core/agent/runtime/verification.py app/core/agent/runtime/harness.py app/services/run_coordinator.py tests/app/services/test_verification_service.py tests/app/core/agent/test_durable_lead_verification.py`
- 预期：退出 0；没有 Verification Attempt 通过时 Run 无法 completed，Repair 次数和预算受 Snapshot 限制。

### 完成条件

- Durable Solo Lead 的完成语义由 Runtime Verification 决定，而不是由模型、Flow、Worker 或 SSE 决定。

### 执行结果

待执行；完成后记录实际 Check 集、Repair 上限和失败分类。

### 验证证据

```text
待 Task 8 执行后填写实际命令、退出状态、Verification 路径和 Asia/Shanghai 时间。
```

## Task 9：完成 Outbox 投影、可重放 SSE 与运行查询兼容

状态：pending

### 目标

把规范 Event 单向投影到现有 Session/Trace/UI，并提供按 `run_seq` 补拉的 SSE、Root Execution 和 Verification 查询，使客户端断线不影响执行且重连不重不漏。

### 涉及文件

- `agentic/api/app/services/runtime_projection_service.py`（新建）
- `agentic/api/app/services/trace_service.py`
- `agentic/api/app/services/agent_service.py`
- `agentic/api/app/controllers/session.py`
- `agentic/api/app/controllers/runs.py`
- `agentic/api/app/schemas/run.py`（新建或扩展现有 Run Schema）
- `agentic/api/app/dependencies/services.py`
- `agentic/api/app/main.py`
- `agentic/api/tests/app/services/test_runtime_projection_service.py`（新建）
- `agentic/api/tests/app/interfaces/endpoints/test_durable_run_routes.py`（新建）
- `agentic/api/tests/app/interfaces/endpoints/test_durable_session_stream.py`（新建）
- `agentic/api/tests/app/services/test_trace_service.py`
- `agentic/web/src/lib/api/session.ts`
- `agentic/web/src/lib/api/run.ts`
- `agentic/web/src/lib/api/types.ts`
- `agentic/web/src/composables/useSessionDetail.ts`
- `agentic/web/src/composables/useSessionDetail.spec.ts`
- `agentic/web/src/components/TracePanel.vue`
- `agentic/web/src/components/TracePanel.spec.ts`（存在则修改，否则新建）

### 依赖与接口

- 前置任务：Task 3–8。
- 输入：规范 Event/Outbox、`after_seq`、现有 Session Event/SSE/Trace DTO。
- 输出：幂等投影、`run_id:run_seq` SSE ID、缺口补拉、Root Execution/Verification 查询和脱敏 Runtime Profile Overview。

### 实施步骤

1. 实现 Outbox Projector，将公开 Runtime Event 幂等投影到 `sessions.events`、`run_steps/tool_calls/model_calls/trace_events`；投影失败重试，不回写规范状态。
2. TraceService 改为投影与查询服务；Durable Run 不再由 `start_run/update_run/finalize_interrupted_run` 创建或结束。
3. 保留 `POST /api/sessions/{session_id}/chat` 的 SSE 行为；Durable 路径提交 Command 后订阅数据库事件，连接关闭只停止订阅。
4. SSE `id` 使用 `run_id:run_seq`；服务端支持 `after_seq`/cursor，客户端按 ID 去重，发现序号缺口时调用 Run Events 查询补拉。
5. 增加 `GET /api/runs/{run_id}/executions`、`GET /api/runs/{run_id}/events?after_seq=N`、`GET /api/runs/{run_id}/verifications` 和脱敏 `GET /api/runtime/profile`。
6. 将现有 stop/resume/interaction/next-message 行为映射为 Durable Command；Legacy 请求保持兼容错误和旧事件形状。
7. 现有 Chat Timeline 继续接收 Message/Plan/Step/Tool/Interaction/Wait/Done/Error；Root Lead/Profile Hash、Recovery 和 Verification 只在 TracePanel 中按需展开。
8. 覆盖 SSE 首连、断线、从旧 cursor 重连、重复投影、事件缺口、Run 已完成后补拉、用户隔离和 Legacy/Durable 混合历史。

### 验证方式

- 后端运行：`uv run pytest tests/app/services/test_runtime_projection_service.py tests/app/interfaces/endpoints/test_durable_run_routes.py tests/app/interfaces/endpoints/test_durable_session_stream.py tests/app/services/test_trace_service.py tests/app/interfaces/endpoints/test_session_interactions.py tests/app/interfaces/endpoints/test_session_next_message_route.py tests/app/interfaces/endpoints/test_session_recovery_route.py -q`
- 前端运行：`pnpm test:run -- src/composables/useSessionDetail.spec.ts src/components/TracePanel.spec.ts`
- 前端运行：`pnpm type-check`
- 预期：退出 0；SSE 断线期间 Run 继续，重连后事件按 run_seq 恢复且 UI 不重复，Session/Trace 只由规范 Event 单向投影。

### 完成条件

- 客户端和现有查询可以在不拥有执行生命周期的情况下完整观察 Durable Solo Lead，并能从任意已知序号恢复事件流。

### 执行结果

待执行；完成后记录最终 DTO、SSE cursor、投影延迟和前端兼容偏差。

### 验证证据

```text
待 Task 9 执行后填写实际命令、退出状态、断线补拉结果和 Asia/Shanghai 时间。
```

## Task 10：执行全量回归、故障演练、切流门禁和代码审查

状态：pending

### 目标

以真实 PostgreSQL、Redis、Lazy Sandbox 和前后端环境证明 Durable Solo Lead 的恢复、一致性、兼容性和完成语义，并完成启用 Feature Flag 前的合并门禁。

### 涉及文件

- `agentic/docs/plans/durable-solo-lead-runtime-plan.md`
- `agentic/docs/reviews/durable-solo-lead-runtime-review.md`（新建）
- 本计划实际修改的代码、迁移和测试

### 依赖与接口

- 前置任务：Task 1–9。
- 输入：完整 Durable Solo Lead 实现与 Legacy Runtime。
- 输出：最新自动化证据、迁移往返、真实故障演练、前后端构建、分级代码审查和最终结论。

### 实施步骤

1. 启动仓库开发 PostgreSQL/Redis，升级到迁移头并运行后端全量测试、Ruff、核心模块编译和 diff 检查。
2. 运行前端全量测试、类型检查和生产构建；验证 Durable/Legacy 会话混合历史、SSE cursor 和 TracePanel。
3. 执行简单文本、Search、Shell/File、Browser、Skill、MCP、外部 A2A、ask-user、Tool Approval 和 next-message 的真实路径。
4. 在 Run 准备、计划提交、模型调用、Tool prepared、Tool executing、Tool result、waiting_user、verifying 等边界终止 Worker/API 进程并恢复。
5. 停止并恢复 Redis，验证数据库扫描、Outbox 重试和 SSE 补拉；客户端断线时确认 Run 不被取消。
6. 修改用户模型/Tool/Skill 配置后恢复旧 Run，验证继续使用原 Snapshot；新 Run 使用新 Snapshot。
7. 检查普通文本 Run 仍为零 Sandbox；Sandbox Tool 只激活一个实例，附件按需同步，Browser cleanup 后无孤儿资源。
8. 检查所有持久化表和日志不存在 API Key、凭据、完整动态 Tool Schema、隐藏推理和未脱敏用户敏感内容。
9. 运行架构守卫，确认 Durable 状态单写、Redis 非事实源、无本地 Child、A2A 只走 Tool Adapter、Trace/Session 只做投影。
10. 执行分级代码审查；处理全部 blocking/major 后重新运行受影响测试和最终门禁，将结果写回计划与 Review 文档。

### 验证方式

- 基础设施：`docker compose -f docker/docker-compose.dev.yml up -d manus-postgres manus-redis`
- 后端：`uv run alembic upgrade head`
- 后端：`uv run pytest -q --disable-warnings`
- 后端：`uv run ruff check app tests`
- 后端：`uv run python -m py_compile app/core/entities/agent_runtime.py app/core/agent/runtime/harness.py app/core/agent/runtime/execution_adapter.py app/core/agent/runtime/scheduler.py app/services/run_coordinator.py app/services/execution_scheduler.py app/services/tool_execution_service.py app/services/verification_service.py app/services/runtime_projection_service.py`
- 前端：`pnpm test:run`
- 前端：`pnpm type-check`
- 前端：`pnpm build`
- 仓库根目录：`git diff --check`
- 手工/故障注入：按实施步骤 3–9 逐项记录 Run ID、终止位置、恢复 Worker、事件序号、Tool effect、Sandbox 数和最终 Verification。
- 预期：全部退出 0；无未处理 blocking/major；每类故障均从已声明 Safe Point 恢复，未知副作用不重试，现有用户功能无回归。

### 完成条件

- 自动化、真实依赖、故障演练、迁移、构建和代码审查共同证明 Durable Solo Lead 达到启用门槛。

### 执行结果

待执行；完成后记录所有命令、测试数量、资源数据、故障演练 Run ID、审查整改和最终状态。

### 验证证据

```text
待 Task 10 执行后填写实际命令、退出状态、关键结果和 Asia/Shanghai 时间。
```

## 计划变更

| 日期 | 变更内容 | 原因 | 影响任务 | 是否影响设计 |
| --- | --- | --- | --- | --- |
| 2026-08-17 | 从总体自主 Agent 架构中拆出 Durable Solo Lead 首批计划 | 先建立唯一 Lead、状态权威与恢复基础，再引入 Child 并行和 Project Memory | Task 1–10 | 否 |
| 2026-08-17 | Harness 首批固定适配现有 Plan-ReAct，不同时启用自动 Direct/ReAct 路由 | 隔离行为优化与耐久性迁移风险，确保可比较和可回滚 | Task 2、6、10 | 否 |
| 2026-08-17 | Registry 包含四个固定 Profile，但本批只允许 Root Lead Execution | 提前固定产品拓扑，同时避免在状态权威建立前引入并行 Child | Task 1、3–5、10 | 否 |

## 最终验证

### 执行命令

```bash
# agentic/api
uv run alembic upgrade head
uv run pytest -q --disable-warnings
uv run ruff check app tests
uv run python -m py_compile app/core/entities/agent_runtime.py app/core/agent/runtime/harness.py app/core/agent/runtime/execution_adapter.py app/core/agent/runtime/scheduler.py app/services/run_coordinator.py app/services/execution_scheduler.py app/services/tool_execution_service.py app/services/verification_service.py app/services/runtime_projection_service.py

# agentic/web
pnpm test:run
pnpm type-check
pnpm build

# D:\AI\Think-Agentic
git diff --check
```

迁移 downgrade/upgrade 往返只能在明确的一次性测试数据库执行，并记录迁移前后关键表行数；不得对用户数据或未确认环境执行破坏性回退。

### 执行结果

- 单元测试：待执行。
- 集成测试：待执行。
- 静态检查：待执行。
- 类型检查：待执行。
- 构建：待执行。
- 数据库迁移：待执行。
- 手工验证：待执行。
- 故障演练：待执行。
- 代码审查：未执行；目标文档 `agentic/docs/reviews/durable-solo-lead-runtime-review.md`。

### 验收标准检查

- [ ] UI/API 中不存在 Agent Definition、Agent Publish、Agent Version 或 Root Agent 选择入口。
- [ ] Registry 恰好包含 `lead/general_worker/researcher/reviewer`，所有新 Durable Run 自动使用唯一 `lead` Root Execution。
- [ ] 四个 Profile 共享 AgentHarness 契约；本批运行时拒绝创建任何本地 Child Execution。
- [ ] MCP/API/外部 A2A 仍作为 Tool Adapter，测试证明没有通过 A2A 创建或通信本地 Child。
- [ ] Run 进入 ready 后固定 Profile、模型、Tool、Skill、Knowledge、Sandbox、Memory 和 Verification Snapshot。
- [ ] RunCoordinator 是 Durable Run/Execution/Interaction/Verification 状态的唯一写入者。
- [ ] PostgreSQL 是规范事实源；进程内 Task 丢失、Worker Kill、Redis Loss 和 SSE 断线后 Run 能从 Safe Point 恢复。
- [ ] 规范 Event 的 `run_seq` 连续唯一，Outbox 最终投影到 Session/Trace，重连补拉不重不漏。
- [ ] 高风险 Tool 经 Approval 和 Side-effect Ledger；unknown 副作用不会盲目重试。
- [ ] 模型自报完成不能直接结束 Run；确定性 Verification 通过后 Coordinator 才能 completed。
- [ ] 持久化和日志不包含 API Key、明文凭据、完整动态 Tool Schema或隐藏思维链。
- [ ] 普通文本、Knowledge 和 Context Run 保持零 Sandbox；Shell/Browser/File 首次需要时只激活一个实例。
- [ ] 现有聊天、文件、Skill、Tool、Sandbox、MCP、外部 A2A、HITL、下一条消息、分支和 SSE 行为通过非回归测试。
- [ ] Durable Runtime Feature Flag 只影响新 Run；Legacy 历史保持可读且关闭 Flag 可以安全回退新流量。
- [ ] 数据库迁移往返、前后端全量测试、类型/静态检查、生产构建、真实故障演练和代码审查通过，无未处理 blocking/major。

以下总体架构验收项明确留给后续计划，不作为本批失败项：

- General Worker 产生多个独立 Execution，以及 Lead 的 fan-out/fan-in 并行。
- Child Result 的 adopt/reject/conflict resolution 和 Execution Tree 多节点展示。
- Reviewer Profile 的按需执行与模型验证。
- Project Memory Candidate、Published Revision、纠正、删除和跨用户隔离。
- Steering 追加 Goal Revision 的完整用户接口。

### 未通过项目

尚未执行；实施过程中逐项记录失败、阻塞、已尝试内容和解除条件。

### 最终状态

`READY_TO_MERGE / BLOCKED / FAILED`（尚未判定；完成 Task 1–10 和最终验证后填写）
