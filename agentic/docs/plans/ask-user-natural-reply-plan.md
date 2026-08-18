# Ask User 普通回复自动继续实施计划

## 关联设计

- 设计文档：`agentic/docs/designs/agent-runtime-hitl-provider-reliability.zh-CN.md`
- 调试记录：`agentic/docs/debug/ask-user-natural-reply.md`
- 开发分支：`feature/remove-tool-approval`
- 依赖批次：`remove-tool-approval-plan.md`（已完成、尚未提交）

## 当前进度

- 整体状态：`READY_TO_MERGE`
- 当前阶段：final_verification
- 当前任务：全部完成
- 已完成：4 / 4
- 阻塞问题：无
- 最近更新时间：2026-08-18 17:45（Asia/Shanghai）

## 全局约束

- `WAITING` 只表示等待业务输入；普通回复不得触发 Planner 重新猜测暂停前状态。
- 结构化表单和 Composer 文本必须复用同一个 `InteractionResolution` 与原 Tool Call 恢复路径。
- 普通回复只能自动解决最新 pending `ask_user`，且必须满足 `allow_text`、非空、长度和当前 Session 状态校验。
- Action 解决、Session 执行领取和历史审批收敛必须在同一 Session 行锁事务内串行化。
- 重复/并发输入不得启动第二次原 Tool Call；旧 `tool_approval` 继续只做安全收敛。
- 不新增数据库 Schema；不扩大到 `form_input`、MCP/A2A Provider Runtime 或通用 Durable Run。
- 保留用户已有 `agentic/api/.env` 修改，不读取、不输出、不覆盖。
- 不自动提交、推送、创建 PR 或合并。

## 状态变更记录

| 日期时间 | 整体状态 | 当前任务 | 变更原因 |
| --- | --- | --- | --- |
| 2026-08-18 17:06 | `IN_PROGRESS` | Task 1 | 设计已有明确 Interaction Router 目标，根因已通过代码路径确认，开始测试先行 |
| 2026-08-18 17:10 | `IN_PROGRESS` | Task 2 | Task 1 的 RED/GREEN 与局部静态检查通过，开始统一 Service 和恢复状态契约 |
| 2026-08-18 17:17 | `IN_PROGRESS` | Task 3 | Service/Lead 的 3 项 RED 已转为 GREEN，33 项恢复测试和 Ruff 通过；开始开放自然输入 UI |
| 2026-08-18 17:19 | `VERIFYING` | Task 4 | 自由文本/选项-only/历史审批的 UI 契约验证通过，进入文档收口和最终门禁 |
| 2026-08-18 17:34 | `REVIEWING` | Task 4 | 首轮后端全量通过；审查继续收紧并发重复回答、SSE 提交边界和消息长度契约 |
| 2026-08-18 17:45 | `READY_TO_MERGE` | 全部完成 | 审查发现均已整改；后端 469 项、前端 186 项、静态检查、类型和构建门禁通过 |

## Task 1：固定普通回复的领域与原子领取契约

状态：completed

### 目标

用 RED 测试固定 `WAITING + pending ask_user + 普通文本` 必须在行锁内一次性解决并领取执行权，同时保护非法文本、历史审批和重复领取语义。

### 涉及文件

- `agentic/api/app/core/entities/session.py`
- `agentic/api/app/repositories/session_repository.py`
- `agentic/api/app/repositories/db_session_repository.py`
- `agentic/api/tests/app/repositories/test_db_session_organization.py`
- `agentic/api/tests/app/services/test_agent_interactions.py`

### 依赖与接口

- 前置任务：无。
- 输入：Session 所有权、普通用户文本、最新 pending Interaction。
- 输出：领取后的 Session、领取前安全回退状态、可选 resolved `InteractionEvent`。

### 实施步骤

1. 增加 RED 测试：自由文本 Ask 原子解决并领取；选项-only Ask 拒绝且保持 WAITING；重复领取不重复解决。
2. 在 Session 聚合中抽取最新 pending Interaction 查询，避免审批收敛和输入路由各自猜测事件尾部。
3. Repository 增加普通用户输入领取命令，在同一 `FOR UPDATE` 事务内完成校验、追加 resolved 事件和状态切换。
4. 保持历史审批安全收敛与普通非 WAITING Run 的现有行为。

### 验证方式

- 运行：`cd agentic/api && uv run pytest tests/app/repositories/test_db_session_organization.py tests/app/services/test_agent_interactions.py -q`
- 预期：新增测试先 RED，最小实现后全部 GREEN。

### 完成条件

- 普通文本 Ask 的解决与领取为一个原子 Repository 命令。
- 非法回答不改变 Session/Interaction。
- 同一 Action 不产生第二个 resolved 事件或第二次恢复领取。

### 执行结果

- 新增 `Session.get_pending_interaction()`，让普通输入路由、Interaction 解决和历史审批收敛共享同一个追加式事件查询规则。
- 新增 `claim_execution_for_user_input()` Repository 契约；数据库实现使用既有 Session `FOR UPDATE`，在同一事务内校验/追加 resolved Ask 事件并切换 `RUNNING`。
- `allow_text=false` 的 pending Ask 继续复用领域校验，异常发生前不会修改数据库 Record；历史审批和非 WAITING 领取保持原行为。
- RED 测试在旧实现上稳定失败 2 项，原因均为缺少输入路由命令；最小实现后 25 项相关测试通过。

### 验证证据

```text
命令：uv run pytest tests/app/repositories/test_db_session_organization.py -q（RED）
退出状态：1
关键结果：20 项中 2 failed、18 passed；失败均为 claim_execution_for_user_input 不存在
执行时间：2026-08-18 17:08（Asia/Shanghai）

命令：uv run pytest tests/app/repositories/test_db_session_organization.py tests/app/services/test_agent_interactions.py -q（GREEN）
退出状态：0
关键结果：25 passed；11 个既有 Pydantic deprecation warnings
执行时间：2026-08-18 17:10（Asia/Shanghai）

命令：uv run ruff check app/core/entities/session.py app/repositories/session_repository.py app/repositories/db_session_repository.py tests/app/repositories/test_db_session_organization.py
退出状态：0
关键结果：All checks passed
执行时间：2026-08-18 17:10（Asia/Shanghai）
```

## Task 2：统一 Service 与 Lead/Legacy 恢复链路

状态：completed

### 目标

让普通回复由 Service 转换为 server-owned `InteractionResolution`，并确保 React、Plan 与 Legacy Flow 都能在已领取为 RUNNING 的状态下精确继续。

### 涉及文件

- `agentic/api/app/services/agent_service.py`
- `agentic/api/app/core/agent/lead.py`
- `agentic/api/app/core/flows/planner_react.py`
- `agentic/api/tests/app/services/test_agent_service_recovery.py`
- `agentic/api/tests/app/core/agent/test_lead_agent_react.py`
- `agentic/api/tests/app/core/agent/test_lead_agent_plan.py`
- `agentic/api/tests/app/core/agent/test_interaction_resume.py`

### 依赖与接口

- 前置任务：Task 1。
- 输入：Repository 返回的 resolved InteractionEvent。
- 输出：Task 输入中的非持久化 `InteractionResolution`，以及 resolved SSE 事件。

### 实施步骤

1. 抽取唯一的 resolved event → InteractionResolution 转换函数，结构化接口与普通回复共用。
2. 普通可见消息调用输入路由领取；命中 Ask 时传递持久化 Skills/Lead/Plan 上下文并输出 resolved 事件。
3. 修正 Lead 和 Legacy Flow 的恢复状态前置条件，使其兼容“服务层已原子领取为 RUNNING”，仍拒绝无合法 resolution 的恢复。
4. 增加 React、Plan、Legacy 和任务创建失败的回归测试。

### 验证方式

- 运行：`cd agentic/api && uv run pytest tests/app/services/test_agent_service_recovery.py tests/app/services/test_agent_interactions.py tests/app/core/agent/test_lead_agent_react.py tests/app/core/agent/test_lead_agent_plan.py tests/app/core/agent/test_interaction_resume.py -q`
- 预期：相关恢复测试全部通过，普通消息不会触发新的 Lead 决策。

### 完成条件

- 普通回复和卡片提交进入同一个 BaseAgent resume path。
- `interaction_response` 只进入 Task 输入和 Trace，不写入可见 MessageEvent 历史。
- 结构化提交现有契约保持兼容。

### 执行结果

- `AgentService` 的执行领取新增普通用户回答路由；命中 pending Ask 时，将 Repository 返回的 resolved 事件转换为唯一的 server-owned `InteractionResolution`，并复用持久化 Skills/Lead/Plan 上下文。
- 自动解决事件先通过 SSE 返回；用户可见 MessageEvent 正常写入历史，但内部 `interaction_response` 继续只存在于 Task 输入并在持久化前清除。
- 抽取 `_build_interaction_resolution()`，卡片提交和 Composer 回复不再各自组装恢复载荷。
- Lead React/Plan 与 Legacy PlannerReActFlow 允许 Service 已领取为 `RUNNING` 的合法恢复；有 resolution 时 Legacy 明确进入 `EXECUTING`，不会重新规划。
- Task 创建失败时不再把已解决 Action 恢复成无 pending 的 `WAITING`，而是安全收敛为 `COMPLETED`。
- RED 阶段分别证明普通消息未路由、React 恢复拒绝 RUNNING、Plan 恢复拒绝 RUNNING；修复后 33 项恢复相关测试通过。

### 验证证据

```text
命令：uv run pytest tests/app/services/test_agent_service_recovery.py tests/app/core/agent/test_lead_agent_react.py tests/app/core/agent/test_lead_agent_plan.py -q（RED）
退出状态：1
关键结果：3 failed、16 passed；失败分别命中普通消息未路由和 React/Plan 状态契约冲突
执行时间：2026-08-18 17:13（Asia/Shanghai）

命令：uv run pytest tests/app/services/test_agent_service_recovery.py tests/app/services/test_agent_interactions.py tests/app/core/agent/test_lead_agent_react.py tests/app/core/agent/test_lead_agent_plan.py tests/app/core/agent/test_interaction_resume.py -q（GREEN）
退出状态：0
关键结果：33 passed；覆盖普通回复、任务创建失败、React、Plan 和 BaseAgent 精确恢复
执行时间：2026-08-18 17:16（Asia/Shanghai）

命令：uv run ruff check app/services/agent_service.py app/core/agent/lead.py app/core/flows/planner_react.py tests/app/services/test_agent_service_recovery.py
退出状态：0
关键结果：All checks passed
执行时间：2026-08-18 17:16（Asia/Shanghai）
```

## Task 3：开放符合契约的 Composer 回复

状态：completed

### 目标

允许用户在可自由回答的 pending Ask 下直接使用 Composer；选项-only Ask 仍由结构化卡片处理。

### 涉及文件

- `agentic/web/src/components/SessionDetailView.vue`
- `agentic/web/src/components/SessionDetailView.spec.ts`
- `agentic/web/src/components/chat/InteractionCard.vue`（仅在文案需要同步时）

### 依赖与接口

- 前置任务：Task 2。
- 输入：pending Interaction 的 `allow_text`。
- 输出：一致的 Composer disabled 状态和用户提示。

### 实施步骤

1. 将 Composer 阻塞条件改为只阻塞不允许自由文本的 pending Ask。
2. 自由文本 Ask 下保留卡片输入，同时允许自然聊天回复；状态文案说明两种方式均可。
3. 增加允许文本、选项-only、历史审批三类组件测试。

### 验证方式

- 运行：`cd agentic/web && pnpm test:run -- src/components/SessionDetailView.spec.ts src/components/chat/InteractionCard.spec.ts`
- 预期：相关组件测试全部通过。

### 完成条件

- `allow_text=true` 时 Composer 可发送，`allow_text=false` 时继续阻塞。
- 历史审批仍不阻塞输入。
- 卡片结构化提交行为无回归。

### 执行结果

- Session Detail 新增明确的 Composer 阻塞计算：pending Ask 仅在 `allow_text=false` 时阻塞输入框；允许自由文本时用户可直接聊天回复。
- WAITING 状态文案区分“可直接输入或使用问题卡”与“请在问题卡中选择”，避免开放输入后仍暗示只能操作卡片。
- InteractionCard 同步说明两种回答方式；选项-only 卡片继续保持结构化选择与服务端校验。
- 历史 `tool_approval` 仍不阻塞 Composer。

### 验证证据

```text
命令：pnpm test:run -- src/components/SessionDetailView.spec.ts（RED）
退出状态：1
关键结果：17 项中 1 failed、16 passed；自由文本 Ask 的 Composer 仍被禁用
执行时间：2026-08-18 17:17（Asia/Shanghai）

命令：pnpm test:run -- src/components/SessionDetailView.spec.ts src/components/chat/InteractionCard.spec.ts（GREEN）
退出状态：0
关键结果：2 个测试文件、20 项全部通过
执行时间：2026-08-18 17:18（Asia/Shanghai）

命令：pnpm type-check
退出状态：0
关键结果：vue-tsc -b 通过
执行时间：2026-08-18 17:19（Asia/Shanghai）
```

## Task 4：文档、全量验证与代码审查

状态：completed

### 目标

更新当前架构实现状态，完成后端/前端全量门禁和分级代码审查，给出真实合并判断。

### 涉及文件

- `agentic/docs/designs/agent-runtime-hitl-provider-reliability.zh-CN.md`
- `agentic/docs/debug/ask-user-natural-reply.md`
- 本计划
- `agentic/docs/reviews/ask-user-natural-reply-review.md`

### 依赖与接口

- 前置任务：Task 1–3。
- 输入：全部实现 diff 和局部测试证据。
- 输出：设计状态、调试闭环、审查结论与最终门禁。

### 实施步骤

1. 全局检查所有普通消息、Interaction resolve、React/Plan/Legacy 恢复旁路。
2. 更新设计中的实现分析和验收项，补齐调试记录的 RED/GREEN 证据。
3. 执行后端全量、Ruff、前端全量、类型检查、构建和 diff 检查。
4. 分级代码审查；修复 blocking/major 后重新验证。

### 验证方式

- `cd agentic/api && uv run pytest -q`
- `cd agentic/api && uv run ruff check app tests`
- `cd agentic/web && pnpm test:run`
- `cd agentic/web && pnpm type-check`
- `cd agentic/web && pnpm build`
- `git diff --check`

### 完成条件

- 无开放 blocking/major。
- 普通回复只自动继续一次，表单路径保持兼容。
- 最新全量证据完整，结论为 `READY_TO_MERGE`、`BLOCKED` 或 `FAILED`。

### 执行结果

- 对普通 Composer 回答和问题卡提交统一了状态转换：Action 解决与 `WAITING → RUNNING` 在同一 Session 行锁事务内完成，结构化路径不会留下“已解决但未领取”的窗口。
- 显式解决接口在返回 SSE 响应前推进 continuation 到首个持久化点；客户端随后断线只关闭流生成器，不撤销已启动 Task。
- 运行态重复回答检查按最近 Interaction 判定，不会因随后写入用户 MessageEvent 而失效；React、Plan 和 Legacy 均使用原 Tool Call 的 `InteractionResolution` 精确继续。
- `ChatRequest.message` 与结构化回答统一为 10,000 字符上限；选项-only Ask 继续由服务端拒绝自由文本。
- 完成同一 Agent 分级自审，4 项 major 级可靠性缺口均在合并判断前修复；无开放 blocking/major。

### 验证证据

```text
命令：uv run pytest -q -o log_cli=false --disable-warnings
退出状态：0
关键结果：469 passed，11 个既有 Pydantic deprecation warnings
执行时间：2026-08-18 17:42（Asia/Shanghai）

命令：uv run ruff check app tests
退出状态：0
关键结果：All checks passed
执行时间：2026-08-18 17:42（Asia/Shanghai）

命令：pnpm test:run
退出状态：0
关键结果：44 个测试文件、186 项全部通过
执行时间：2026-08-18 17:43（Asia/Shanghai）

命令：pnpm type-check && pnpm build
退出状态：0
关键结果：vue-tsc -b 通过；Vite 生产构建通过
执行时间：2026-08-18 17:44（Asia/Shanghai）

命令：隔离 PostgreSQL 上 uv run alembic upgrade head
退出状态：0
关键结果：当前 migration head 可完整应用；本批无 Schema 变更
执行时间：2026-08-18 17:22（Asia/Shanghai）
```

## 计划变更

| 日期 | 变更内容 | 原因 | 影响任务 | 是否影响设计 |
| --- | --- | --- | --- | --- |
| 2026-08-18 | 新增独立 Ask User 自然回复批次 | 已完成通用审批移除后，用户确认继续实现设计中的 Interaction Router | Task 1–4 | 否，落实既有设计 |

## 最终验证

### 执行命令

见 Task 4。

### 执行结果

- 单元测试：后端 469 项、前端 186 项通过。
- 集成测试：隔离 PostgreSQL/Redis 条件下后端全量通过。
- 静态检查：Ruff 全量通过，`git diff --check` 无空白错误。
- 类型检查：`pnpm type-check` 通过。
- 构建：`pnpm build` 通过。
- 数据库迁移：本批不修改 Schema；隔离 PostgreSQL 上当前 migration head 通过。
- 手工验证：未重建/重启 8088 服务，真实模型浏览器冒烟留待部署后执行。
- 代码审查：`docs/reviews/ask-user-natural-reply-review.md`，结论 `APPROVED`。

### 验收标准检查

- [x] 普通文本可原子解决允许自由文本的最新 Ask 并继续原 Tool Call。
- [x] 选项-only Ask 仍只接受合法结构化值。
- [x] 重复/并发回答不重复启动恢复 Run。
- [x] React、Plan、Legacy 恢复路径兼容。
- [x] 前端自然回复和卡片回复均可用。
- [x] 全量测试、类型、构建和审查门禁通过。

### 未通过项目

无。

### 最终状态

`READY_TO_MERGE`
