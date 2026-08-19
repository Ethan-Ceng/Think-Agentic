# Run Trace 与页面思考执行链路实施计划

## 关联设计

- 设计文档：`docs/designs/run-trace-execution-chain-ux.zh-CN.md`
- 上位路线：`docs/designs/post-lead-foundation-system-roadmap.zh-CN.md`
- 开发分支：`feature/run-execution-view`
- 基线：`develop@4ed4fe9`
- 提交策略：计划文档单独提交；T1、T2、T3、T4 各形成一个独立提交；最终审查整改与证据按实际变更形成收尾提交；全部门禁通过后推送远端同名分支。

## 当前进度

- 整体状态：`IN_PROGRESS`
- 当前阶段：最终验证与代码审查
- 当前任务：Task 5
- 已完成：4 / 5
- 阻塞问题：无
- 最近更新时间：2026-08-19（Asia/Shanghai）

## 全局约束

- 页面展示的是结构化、公开的“思考与执行详情”，不是模型隐藏 chain-of-thought；不得保存或返回 `reasoning_content`、完整 Prompt、消息正文、凭据、完整 Provider URL 或未经策略处理的 Tool 原始参数/结果。
- Trace 是 best-effort 可观测投影，不是 Agent Runtime 状态权威；Trace 写入、投影或 SSE 通知失败不得把正常 Agent Run 伪装为失败。
- 一个用户输入对应一个 Agent Run 和一个 `RunProcessBlock`；历史归属使用 `input_event_id/run_id/node_id/parent_node_id`，不使用浏览器相邻事件猜测。
- `ingest_seq` 只表示 Trace 写入游标，不宣称是未来 Durable Runtime 的规范 `run_seq`。
- 新旧 Run API 保持兼容；新页面只消费安全的 `RunExecutionView`，旧 API 在兼容期内保留但不再返回敏感字段。
- Planner 是 Plan 模式的一等节点；`PlanEvent.UPDATED` 按稳定 `step_id` 更新，已完成步骤不因 Replan 被改写。
- `execution_update` 仅通过当前 SSE 传输，不写入 `sessions.events`；刷新和断线后以 execution API 为准。
- 数据库结构迁移在代码中提供并在隔离数据库验证；本次不会直接清理生产数据库。新写入立即停止保存敏感内容，公共 API 对历史数据强制安全投影。历史数据的物理清理由于不可逆，必须在用户明确授权、备份和保留周期确认后另行执行。
- 每个 Task 只推进对应 Stage，局部验证通过并回写证据后才能进入下一 Task。

## 状态变更记录

| 日期时间 | 整体状态 | 当前任务 | 变更原因 |
| --- | --- | --- | --- |
| 2026-08-19（Asia/Shanghai） | `PLAN_READY` | 无 | 最终设计已确认，分支、四阶段提交边界和验证命令已确定 |
| 2026-08-19（Asia/Shanghai） | `IN_PROGRESS` | Task 1 | 计划文档已提交，开始 Trace 安全、游标、分页与迁移实现 |
| 2026-08-19（Asia/Shanghai） | `IN_PROGRESS` | Task 2 | T1 安全投影、游标分页和非破坏性迁移已完成并验证，进入统一 Execution View 合同与 API |
| 2026-08-19（Asia/Shanghai） | `IN_PROGRESS` | Task 3 | T2 版本化节点合同、Planner 投影和增量 execution API 已完成，进入聊天页实时执行详情 |
| 2026-08-19（Asia/Shanghai） | `IN_PROGRESS` | Task 4 | T3 transport-only 实时更新和消息级执行卡已完成，进入 TracePanel 合同收敛与按需诊断 |
| 2026-08-19（Asia/Shanghai） | `IN_PROGRESS` | Task 5 | T4 TracePanel 已统一 Execution View，并完成按需诊断、独立游标与安全展示，进入全量验证和代码审查 |

## Task 1：T1 Trace 安全、游标、分页与迁移

状态：completed

### 目标

关闭现有 Trace 的敏感写入与公共返回风险，为 TraceEvent 增加稳定游标和安全节点字段，并让 Events、Tool Calls、Model Calls 子接口直接分页查询自身记录。

### 涉及文件

- `api/alembic/versions/20260819_0001_trace_execution_v2.py`（新增）
- `api/app/models/run_trace.py`
- `api/app/repositories/trace_repository.py`
- `api/app/repositories/db_trace_repository.py`
- `api/app/services/trace_service.py`
- `api/app/controllers/runs.py`
- `api/tests/app/services/test_trace_service.py`
- `api/tests/app/repositories/test_db_trace_repository.py`（如现有数据库测试夹具可复用则新增）
- `api/tests/app/controllers/test_runs.py`（新增或扩展现有 Controller 测试）
- `docs/plans/run-trace-execution-chain-plan.md`

### 依赖与接口

- 前置任务：无。
- 输入：现有 `agent_runs/run_steps/tool_calls/model_calls/trace_events` 与 TraceService 写入路径。
- 输出：TraceEvent v2 字段、稳定 `ingest_seq`、安全写入策略、`after/limit` 子接口和兼容的旧详情 API。

### 实施步骤

1. 先增加失败测试，覆盖 reasoning/message/base_url/raw Tool 数据不落库或不出 API、当前用户隔离、游标顺序、分页边界和子接口不触发全量详情查询。
2. 新增非破坏性迁移：为 `trace_events` 增加 `ingest_seq/schema_version/node_id/parent_node_id/visibility/summary` 及 `(run_id, ingest_seq)` 索引，并为历史记录生成稳定游标；不在未获明确授权时物理删除历史数据。
3. 将 TraceService 新写入改为白名单快照：Model 仅保留 provider/model、消息与 Tool 数量、schema bytes、token、TTFT、耗时和 finish reason；Tool 仅保留 descriptor、arguments hash 和受控摘要；TraceEvent payload 按事件类型构造。
4. 扩展 Repository 协议和数据库实现，使 `append_event` 返回持久化游标，并让 Events、Tool Calls、Model Calls 支持 `after/limit`、稳定二级排序和 `has_more/next_cursor`。
5. Controller 增加参数校验和分页 envelope；旧 `GET /runs/{id}` 使用安全投影并设置子集合上限与 `truncated`，不再被子接口间接调用。

### 验证方式

- 运行：`uv run pytest tests/app/services/test_trace_service.py tests/app/controllers/test_runs.py -q`
- 运行：`uv run ruff check app/models/run_trace.py app/repositories/trace_repository.py app/repositories/db_trace_repository.py app/services/trace_service.py app/controllers/runs.py tests/app/services/test_trace_service.py tests/app/controllers/test_runs.py`
- 运行：`uv run alembic upgrade head`（隔离 PostgreSQL）
- 运行：`uv run alembic downgrade 20260818_0001` 后再次 `uv run alembic upgrade head`（隔离 PostgreSQL）
- 预期：全部退出 0；敏感 fixture 不出现在 ORM 数据、API JSON 或迁移日志；相同时间记录仍按 cursor 稳定遍历。

### 完成条件

- 新 Trace 和公共 API 均不包含设计禁止字段。
- 结构迁移可前进、可回退；历史敏感字段即使仍在库内，也无法通过公共 API 返回。
- 三个子接口独立分页查询，用户越权统一返回 404。
- T1 局部测试、Ruff 和迁移往返通过，并形成独立提交。

### 执行结果

已完成 TraceEvent v2 结构与非破坏性迁移、稳定 `ingest_seq`、新写入白名单化、历史记录公共安全投影，以及 Events/Tool Calls/Model Calls 的独立分页查询。迁移不会物理清除历史数据；历史敏感字段只能在获得明确授权后另行治理。

### 验证证据

- `uv run pytest tests/app/services/test_trace_service.py tests/app/services/test_skill_trace.py tests/app/integration/test_skill_runtime_flow.py tests/app/controllers/test_runs.py -q`：16 passed。
- `uv run ruff check ... alembic/versions/20260819_0001_trace_execution_v2.py`：All checks passed。
- 隔离 PostgreSQL 17：`alembic upgrade head`、`downgrade 20260818_0001`、再次 `upgrade head` 均退出 0。
- 历史同时间戳事件回填验证：按 `(created_at, id)` 得到 `e1 -> ingest_seq 1`、`e2 -> ingest_seq 2`，且历史 `schema_version=1`。
- `git diff --check`：退出 0。

## Task 2：T2 RunExecutionView 合同与增量 API

状态：completed

### 目标

建立版本化 `RunExecutionView/ExecutionNode`，把 Lead、Planner、Step、Model、Tool、Interaction、Error 和 Completion 投影成同一条可分页、可覆盖更新的执行链。

### 涉及文件

- `api/app/schemas/run_execution.py`（新增）
- `api/app/schemas/__init__.py`
- `api/app/services/execution_view.py`（新增）
- `api/app/services/trace_service.py`
- `api/app/repositories/trace_repository.py`
- `api/app/repositories/db_trace_repository.py`
- `api/app/controllers/runs.py`
- `api/tests/app/services/test_execution_view.py`（新增）
- `api/tests/app/controllers/test_runs.py`
- `web/src/lib/api/types.ts`
- `web/src/lib/api/runs.ts`
- `docs/plans/run-trace-execution-chain-plan.md`

### 依赖与接口

- 前置任务：Task 1。
- 输入：TraceEvent v2、AgentRun 安全概览以及旧 schema_version=1 历史事件。
- 输出：`GET /runs/{run_id}/execution?after=&limit=&detail=summary|detail` 和前后端共享类型。

### 实施步骤

1. 先写纯 assembler 和 Controller 合同测试，覆盖 Direct、ReAct、Plan、Replan、Ask/Resume、Failure、重复节点更新、乱序同时间事件、历史 v1 降级和跨用户访问。
2. 定义严格枚举和模型：RunOverview、ExecutionNode、ExecutionMetrics、FailureInfo 引用、分页 cursor、`trace_complete` 与 schema_version。
3. 为 TraceService 的 Plan 投影补齐稳定 plan/step 节点、step_index、plan revision/replan_count；为 Strategy、Model、Tool、Interaction、Error、Completion 设置稳定 node/parent/phase/status/summary。
4. 实现 ExecutionViewAssembler：服务端按 cursor 排序，同一 `node_id` 取最新更新；Plan payload 可生成 Planner 与 pending Step 子节点，Tool/Model 使用明确 parent，不依赖时间邻接猜测。
5. 新增 execution API 和前端客户端类型；`after` 返回 cursor 更大的节点更新，客户端可按 `node_id + cursor` 幂等覆盖。

### 验证方式

- 运行：`uv run pytest tests/app/services/test_execution_view.py tests/app/services/test_trace_service.py tests/app/controllers/test_runs.py -q`
- 运行：`uv run ruff check app/schemas/run_execution.py app/services/execution_view.py app/services/trace_service.py app/controllers/runs.py tests/app/services/test_execution_view.py tests/app/controllers/test_runs.py`
- 运行：`pnpm test:run -- src/lib/api`
- 运行：`pnpm type-check`
- 预期：全部退出 0；所有 Lead 模式生成稳定树；重复和增量读取不会产生重复节点；API 不返回内部 payload。

### 完成条件

- Execution View 合同、Assembler 和 API 均有合同测试。
- Planner、Step、Tool、Model 的父子关系来自稳定 ID。
- v1 历史事件可安全降级，v2 支持 cursor 增量。
- T2 局部测试、Ruff、前端类型检查通过，并形成独立提交。

### 执行结果

已新增版本化 `RunExecutionView/ExecutionNode` 合同、纯 `ExecutionViewAssembler` 和 `GET /runs/{run_id}/execution`。Plan 事件生成稳定 Planner/Step 节点，重复 Tool/Model/Interaction 节点按 cursor 覆盖；历史 v1 安全降级并设置 `trace_complete=false`。前端已增加同构类型、增量 API 客户端和独立 cursor 参数。

### 验证证据

- `uv run pytest tests/app/services/test_execution_view.py tests/app/services/test_trace_service.py tests/app/services/test_skill_trace.py tests/app/integration/test_skill_runtime_flow.py tests/app/controllers/test_runs.py -q`：21 passed。
- `uv run ruff check`（T2 后端实现与测试文件）：All checks passed。
- `pnpm test:run -- src/lib/api/runs.spec.ts`：1 file / 2 tests passed。
- `pnpm type-check`：退出 0。

## Task 3：T3 聊天页思考与执行详情

状态：completed

### 目标

在每轮用户消息与最终回复之间显示 ChatGPT 式紧凑过程行，点击后展示 Lead 决策、Planner、Step/Tool、等待和失败；实现实时 `execution_update` 与历史按需加载。

### 涉及文件

- `api/app/core/entities/event.py`
- `api/app/schemas/event.py`
- `api/app/core/agent/agent_task_runner.py`
- `api/app/services/trace_service.py`
- `api/tests/app/core/agent/test_agent_task_runner.py` 或对应现有 Runner 测试
- `api/tests/app/services/test_trace_service.py`
- `web/src/lib/api/types.ts`
- `web/src/lib/session-events.ts`
- `web/src/composables/useSessionDetail.ts`
- `web/src/composables/useRunExecutions.ts`（新增）
- `web/src/components/chat/RunProcessBlock.vue`（新增）
- `web/src/components/chat/ExecutionTree.vue`（新增）
- `web/src/components/chat/PlannerNode.vue`（新增）
- `web/src/components/chat/ToolCallCard.vue`
- `web/src/components/chat/ToolPreviewPanel.vue`
- `web/src/components/SessionDetailView.vue`
- `web/src/components/chat/chat.css`
- 对应 `*.spec.ts` 测试
- `docs/plans/run-trace-execution-chain-plan.md`

### 依赖与接口

- 前置任务：Task 2。
- 输入：RunExecutionView、现有 Session SSE、Session 的 user/assistant 消息和 `input_event_id`。
- 输出：transport-only `execution_update`、消息级 RunProcessBlock 和可展开 ExecutionTree。

### 实施步骤

1. 先写测试覆盖：一轮一 Run、Direct/ReAct/Plan/Ask/Failure 文案、Planner 进度、Replan 次数、用户折叠偏好、历史刷新、SSE 重复/乱序覆盖和 execution_update 不进入 Session 持久化。
2. 增加 ExecutionUpdateEvent 的领域/SSE schema；AgentTaskRunner 在 Trace 成功投影后按 cursor 排出更新并作为 transient event 写入输出流，Trace/SSE 失败不终止 Agent。
3. 新增 `useRunExecutions`：用 Session runs 的 `input_event_id` 建立消息归属，紧凑头部先用 Run summary，首次展开或实时更新时读取/合并 Execution View；断线后按 cursor 补拉。
4. 实现 RunProcessBlock、ExecutionTree、PlannerNode；运行中显示当前动作，完成后默认收起；用户手动状态不被更新重置；Ask 表单与恢复动作仍在正文。
5. 将现有 ThinkingBlock/PlanPanel 数据入口迁移到 RunProcessBlock；Plan 不再固定在 Composer 上方；保留兼容 fallback，确认新链稳定后移除旧渲染路径。

### 验证方式

- 运行：`uv run pytest tests/app/core/agent tests/app/services/test_trace_service.py -q`
- 运行：`uv run ruff check app/core/entities/event.py app/schemas/event.py app/core/agent/agent_task_runner.py app/services/trace_service.py tests/app/core/agent tests/app/services/test_trace_service.py`
- 运行：`pnpm test:run -- src/lib/session-events.spec.ts src/composables/useRunExecutions.spec.ts src/components/chat/RunProcessBlock.spec.ts src/components/chat/ExecutionTree.spec.ts src/components/SessionDetailView.spec.ts`
- 运行：`pnpm type-check`
- 预期：全部退出 0；过程块与消息稳定绑定；实时与刷新结果一致；旧客户端可忽略未知 SSE 事件。

### 完成条件

- Planner 在对应 Run 内展示，不再作为 Composer 全局面板。
- Direct/ReAct/Plan/Ask/Failure 的折叠头和展开树符合设计。
- `execution_update` 不持久化、可去重、可断线补拉且失败不影响 Agent。
- T3 局部测试、Ruff、前端类型检查通过，并形成独立提交。

### 执行结果

已新增 transport-only `execution_update` 领域/SSE 合同，AgentTaskRunner 在 Trace 投影后按 cursor 排出安全更新，并对 Token Delta 路径做 250ms 节流；通知失败不影响 Agent。聊天页新增 `useRunExecutions`、`RunProcessBlock`、`ExecutionTree` 和 `PlannerNode`，按 `input_event_id` 固定绑定到用户消息，首次展开才加载完整历史，刷新/终态按 execution API 补拉。Composer 全局 PlanPanel 已移除；有 Execution View 的 Run 不再重复渲染旧 Step/Tool 链，旧记录仍保留 fallback。

### 验证证据

- `uv run pytest tests/app/core/agent tests/app/schemas/test_execution_update_event.py tests/app/services/test_trace_service.py -q`：147 passed。
- `uv run ruff check`（T3 后端实现与测试文件）：All checks passed。
- `pnpm test:run -- src/lib/session-events.spec.ts src/composables/useRunExecutions.spec.ts src/components/chat/RunProcessBlock.spec.ts src/components/chat/ExecutionTree.spec.ts src/components/SessionDetailView.spec.ts`：5 files / 32 tests passed。
- `pnpm type-check`：退出 0。

## Task 4：T4 TracePanel 统一执行链重构

状态：completed

### 目标

让 TracePanel 使用与聊天页相同的 ExecutionNode 合同，改为概览、执行链和按需诊断页签，删除原始 JSON dump、重复全量请求和浏览器端因果排序。

### 涉及文件

- `web/src/components/TracePanel.vue`
- `web/src/components/TracePanel.spec.ts`
- `web/src/components/chat/ExecutionTree.vue`
- `web/src/components/chat/ToolPreviewPanel.vue`
- `web/src/components/skills/RunSkillsPanel.vue`
- `web/src/lib/api/runs.ts`
- `web/src/lib/api/types.ts`
- `web/src/components/chat/chat.css` 或 TracePanel 对应样式文件
- `api/app/controllers/runs.py`
- `api/app/services/trace_service.py`
- `api/tests/app/controllers/test_runs.py`
- `docs/plans/run-trace-execution-chain-plan.md`

### 依赖与接口

- 前置任务：Task 3。
- 输入：RunExecutionView、独立分页 Tool/Model/Event/Skill API。
- 输出：概览、执行链、工具、模型、Skills、技术事件六类视图及增量刷新。

### 实施步骤

1. 先扩充 TracePanel 测试，覆盖无重复 Skills 请求、首屏只读 execution summary、页签按需加载、TTFT/总耗时分离、安全事件展示和 cursor 增量。
2. 将默认页签改为概览与执行链；复用 ExecutionTree 的节点行，在诊断模式显示 node/cursor/父子关系和完整安全摘要。
3. Tool、Model、Skills、技术事件在切换页签时独立分页读取；Model 仅显示 provider/model、计数、token、TTFT、耗时和 finish reason；技术事件只渲染白名单字段。
4. 移除 `getRun + listSkills` 重复请求、原始 payload JSON dump和浏览器端跨表时间排序；保留旧 API fallback 到一个兼容版本窗口。
5. 增加运行中 cursor 刷新与终态最后一次补拉，失败时显示“执行记录暂不完整”，不伪造 Run 失败。

### 验证方式

- 运行：`pnpm test:run -- src/components/TracePanel.spec.ts src/components/chat/ExecutionTree.spec.ts src/components/chat/RunProcessBlock.spec.ts`
- 运行：`pnpm type-check`
- 运行：`pnpm build`
- 运行：`uv run pytest tests/app/controllers/test_runs.py tests/app/services/test_execution_view.py -q`
- 预期：全部退出 0；首屏无重复请求；所有详细页签按需加载；页面不存在 raw reasoning/prompt/tool payload 展示入口。

### 完成条件

- 聊天页和 TracePanel 共用 ExecutionTree/ExecutionNode，不再维护两套组装规则。
- TracePanel 支持安全、分页、增量诊断，旧接口兼容。
- T4 局部测试、类型检查、生产构建和后端合同测试通过，并形成独立提交。

### 执行结果

TracePanel 已改为以 `RunExecutionView` 为唯一首屏数据源，并复用聊天页 `ExecutionTree` 展示执行链。工具、模型、Skills 和技术事件均在切换页签后按需加载；工具、模型和事件各自维护独立 cursor，Skills 在同一 Run 生命周期内只请求一次。模型视图分别展示 TTFT 与总耗时，技术事件仅展示事件类型、cursor、摘要、节点关系与时间，不再渲染原始 payload JSON。旧的 `getRun + listSkills` 首屏并发请求已移除，Skills API 客户端已按后端 envelope 解包，Skills 组件不再显示内部 reason 或 sandbox path。

### 验证证据

- `pnpm test:run -- src/components/TracePanel.spec.ts src/components/chat/ExecutionTree.spec.ts src/components/chat/RunProcessBlock.spec.ts src/components/skills/RunSkillsPanel.spec.ts src/lib/api/runs.spec.ts`：5 files / 12 tests passed。
- `pnpm type-check`：退出 0。
- `pnpm build`：退出 0，Vite production build 成功。
- `uv run pytest tests/app/controllers/test_runs.py tests/app/services/test_execution_view.py -q`：5 passed。
- `git diff --check`：退出 0。

## Task 5：完整验证、代码审查、整改与远端推送

状态：in_progress

### 目标

验证四阶段整体正确性、安全性、迁移兼容和页面构建，完成正式代码审查与整改，把可合并分支推送到 `origin/feature/run-execution-view`。

### 涉及文件

- Task 1–4 的全部实现和测试文件
- `docs/plans/run-trace-execution-chain-plan.md`
- `docs/reviews/run-trace-execution-chain-review.md`（新增）

### 依赖与接口

- 前置任务：Task 1–4。
- 输入：相对 `develop@4ed4fe9` 的完整 diff 和四阶段验证证据。
- 输出：最终验证记录、`APPROVED` 审查、`READY_TO_MERGE` 状态和远端功能分支。

### 实施步骤

1. 在隔离 PostgreSQL/Redis 环境从空库执行 Alembic 到 head，并验证 downgrade/upgrade；运行后端全量测试、Ruff 和 compileall。
2. 运行前端全量测试、类型检查和生产构建；执行 `git diff --check`、敏感字段扫描和 API/页面手工结构核对。
3. 按 blocking/major/minor/suggestion 审查完整 diff，保存审查记录；修复 blocking/major，记录 minor 处理决定。
4. 审查后重新运行受影响测试和全部门禁，把最新命令、退出码和结果回写本计划。
5. 确认每个 Stage 独立提交、工作区干净、分支不是 develop；推送 `feature/run-execution-view` 到 origin 并核对 upstream。

### 验证方式

- 后端：`uv run pytest -o addopts="" -q --tb=short --basetemp=.pytest_tmp`
- 后端静态：`uv run ruff check app tests`
- 后端编译：`uv run python -m compileall -q app tests`
- 数据库：隔离环境执行 `uv run alembic upgrade head`、目标 downgrade、再次 upgrade head。
- 前端：`pnpm test:run`
- 前端类型：`pnpm type-check`
- 前端构建：`pnpm build`
- Git：`git diff --check`、`git status --short --branch`、`git log --oneline develop..HEAD`
- 推送：`git push -u origin feature/run-execution-view`
- 预期：全部命令退出 0；审查无 blocking/major；远端分支指向本地 HEAD。

### 完成条件

- 全部设计验收项有最新证据，迁移在隔离数据库完成往返验证。
- 审查结论 `APPROVED`，无未处理 blocking/major。
- 计划状态为 `READY_TO_MERGE`，工作区干净。
- 四个 Stage 可独立回滚，远端同名分支已建立且与本地同步。

### 执行结果

四阶段实现已完成全量验证和正式代码审查。首次无隔离依赖的后端全量测试中，590 项通过、24 项失败和 1 项错误均由 `.env` 指向未启动的 PostgreSQL/Redis 测试端口导致；在独立 PostgreSQL 数据库与 Redis DB 15 中重跑后全部通过。审查发现并修复节点生命周期字段丢失、异步诊断请求串 Run、TracePanel 缺少运行中/终态补拉、Lead 失败被投影成功、历史 failure 子对象透传，以及 SSE cursor 提前推进问题。审查结论为 `APPROVED`，当前仅剩提交、远端推送与 upstream 核对。

### 验证证据

- 后端全量：隔离 PostgreSQL/Redis 下 `uv run pytest -o addopts="" -q --tb=short --basetemp=.pytest_tmp_final`，618 passed。
- 后端静态：`uv run ruff check app tests`，All checks passed。
- 后端编译：`uv run python -m compileall -q app tests`，退出 0。
- 前端全量：`pnpm test:run`，53 files / 222 tests passed。
- 前端类型与构建：`pnpm type-check`、`pnpm build`，均退出 0。
- 数据库：隔离 PostgreSQL 17 从空库 upgrade 到 head，随后 downgrade `20260818_0001`、re-upgrade，最终 `20260819_0001 (head)`。
- 安全与 Git：公共字段扫描和 `git diff --check` 通过。
- 代码审查：`docs/reviews/run-trace-execution-chain-review.md`，结论 `APPROVED`，无未处理 blocking/major/minor。

## 计划变更

| 日期 | 变更内容 | 原因 | 影响任务 | 是否影响设计 |
| --- | --- | --- | --- | --- |
| 2026-08-19 | 初始计划按 T1–T4 和最终门禁拆分 | 与最终设计和独立 Stage 提交要求对齐 | 全部 | 否 |
| 2026-08-19 | 历史物理清理由自动迁移改为显式授权的运维步骤 | 自动清空历史数据不可逆；当前授权只覆盖功能实施与推送 | Task 1、Task 5 | 否，公共安全边界不变 |

## 最终验证

### 执行命令

```bash
uv run pytest -o addopts="" -q --tb=short --basetemp=.pytest_tmp
uv run ruff check app tests
uv run python -m compileall -q app tests
uv run alembic upgrade head
pnpm test:run
pnpm type-check
pnpm build
git diff --check
git status --short --branch
git log --oneline develop..HEAD
```

### 执行结果

- 单元测试：待执行。
- 集成测试：待执行。
- 静态检查：待执行。
- 类型检查：待执行。
- 构建：待执行。
- 数据库迁移：待执行。
- 手工验证：待执行。
- 代码审查：待执行。

### 验收标准检查

- [ ] Direct、ReAct、Plan 和 Ask/Resume 生成稳定、可增量恢复的 Execution View。
- [ ] Planner 在对应消息 Run 内展示，Plan 更新按稳定 Step 覆盖并显示 Replan 次数。
- [ ] 新 Trace 与公共 API 不保存或返回隐藏 reasoning、完整 Prompt/响应、完整 URL、凭据或未治理 Tool 原始数据。
- [ ] 历史敏感字段不再通过 API 暴露；物理清理已明确标记为需单独授权的运维步骤。
- [ ] execution API 支持 cursor、limit、幂等节点覆盖和当前用户隔离。
- [ ] 聊天页与 TracePanel 使用相同 ExecutionNode 合同，实时、断线和历史加载一致。
- [ ] Trace 故障不终止 Agent，页面能区分 Run 失败与记录不完整。
- [ ] 迁移、全量测试、静态检查、类型检查、构建和审查全部通过。

### 未通过项目

待执行。

### 最终状态

`READY_TO_MERGE / BLOCKED / FAILED`
