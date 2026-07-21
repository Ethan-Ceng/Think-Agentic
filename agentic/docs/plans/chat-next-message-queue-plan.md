# 对话“下一条消息”持久化队列实施计划

## 关联设计

- 设计文档：`agentic/docs/designs/chat-next-message-queue.zh-CN.md`
- 开发分支：`feature/chat-human-in-the-loop`

## 当前进度

- 整体状态：`BLOCKED`
- 当前阶段：verification
- 当前任务：Task 5
- 已完成：5 / 5
- 阻塞问题：应用内浏览器不可用，无法完成真实页面和完整 SSE 端到端手工验收
- 最近更新时间：2026-07-21 15:35（Asia/Shanghai）

## 全局约束

- 每个 Session 最多一条 next-message，不扩展为通用多消息队列。
- 排队消息不得进入正在运行的 Redis 输入流或中断当前 flow。
- Session 行锁是排队、替换、取消、认领和完成竞争的唯一并发边界。
- waiting、error、显式 stop 不自动执行 queued 消息。
- 保留工作区已有修改，不提交、不推送、不清理无关变更。

## 状态变更记录

| 日期时间 | 整体状态 | 当前任务 | 变更原因 |
| --- | --- | --- | --- |
| 2026-07-21 | `PLAN_READY` | Task 1 | 设计完成，开始领域模型、迁移与仓储状态机 |
| 2026-07-21 10:36 | `IN_PROGRESS` | Task 2 | 仓储状态机 6 项测试与编译检查通过，开始开放服务和 API |
| 2026-07-21 12:27 | `IN_PROGRESS` | Task 3 | API、恢复和孤儿收敛测试通过，开始运行器自然接续消费 |
| 2026-07-21 14:57 | `IN_PROGRESS` | Task 4 | 运行器接续、恢复和终止分支测试通过，开始前端交互 |
| 2026-07-21 15:02 | `VERIFYING` | Task 5 | 前端排队、失败保留和恢复流测试通过，开始完整验证与审查 |
| 2026-07-21 15:35 | `BLOCKED` | Task 5 | 自动化、构建、真实迁移和 Redis 检查通过；仅浏览器端到端验收受环境阻塞 |

## Task 1：建立 next-message 领域模型、迁移与原子仓储

状态：completed

### 目标

建立一槽式持久化结构和可独立验证的并发状态机，使 queued 消息可以安全创建、替换、取消、认领和清理。

### 涉及文件

- `agentic/api/app/core/entities/session.py`
- `agentic/api/app/models/session.py`
- `agentic/api/app/repositories/session_repository.py`
- `agentic/api/app/repositories/db_session_repository.py`
- `agentic/api/alembic/versions/20260721_0001_chat_next_message.py`（新建）
- `agentic/api/tests/app/repositories/test_db_session_next_message.py`（新建）

### 实施步骤

1. 新增 `NextMessage`、状态枚举和领域冲突异常。
2. 为 Session 领域模型与 ORM 增加可空 JSONB 字段及迁移。
3. 在仓储协议中定义 queue/replace/cancel/claim/consume/reset 操作。
4. DB 仓储使用 `SELECT ... FOR UPDATE` 实现所有权、状态与 task_id 校验。
5. 用 fake 或 SQL 语句级测试覆盖核心状态转换和并发条件。

### 验证方式

- `uv run pytest tests/app/repositories/test_db_session_next_message.py -q`
- `uv run python -m py_compile app/core/entities/session.py app/models/session.py app/repositories/db_session_repository.py alembic/versions/20260721_0001_chat_next_message.py`

### 完成条件

- 领域、ORM、迁移和仓储接口一致；所有权与 processing 冲突均有测试，迁移可被 Alembic 导入。

### 执行结果

新增 `NextMessage`/`NextMessageState` 领域对象、Session 与 ORM JSONB 字段、Alembic migration，以及使用 `SELECT ... FOR UPDATE` 的 create/replace/cancel/claim/consume/reset 仓储状态机。模型转换明确把 `next_message` 作为 JSON 序列化，避免把 Pydantic 对象直接写入 JSONB。

### 验证证据

```text
命令：uv run pytest tests/app/repositories/test_db_session_next_message.py -q
退出状态：0
关键结果：6 passed；覆盖替换、completed/processing 冲突、幂等取消、原子认领或完成、消费清槽和孤儿重置。

命令：uv run python -m py_compile app/core/entities/session.py app/models/session.py app/repositories/db_session_repository.py alembic/versions/20260721_0001_chat_next_message.py
退出状态：0
执行时间：2026-07-21 10:35 Asia/Shanghai
```

## Task 2：开放队列 API、详情恢复与孤儿收敛

状态：completed

### 目标

让客户端能够持久化、替换、取消和恢复 next-message，并确保服务重启后的 processing 状态可再次使用。

### 涉及文件

- `agentic/api/app/schemas/session.py`
- `agentic/api/app/controllers/session.py`
- `agentic/api/app/services/session_service.py`
- `agentic/api/app/services/agent_service.py`
- `agentic/api/tests/app/services/test_agent_next_message.py`（新建）
- 相关 controller/schema 测试

### 实施步骤

1. 增加排队请求/响应 schema，并在 Session 详情返回 next_message。
2. 实现 queue/replace/cancel service，映射 404/409/422。
3. 新增 run queued SSE 路径，为 completed + queued 创建 Task 并启动空输入运行器。
4. 孤儿运行收敛时把 processing 重置为 queued。
5. 测试所有权、状态冲突、恢复和重复请求。

### 验证方式

- `uv run pytest tests/app/services/test_agent_next_message.py tests/app/services/test_agent_service_recovery.py -q`

### 完成条件

- 三个公开接口与详情快照契约可用，越权和状态竞态返回明确错误，孤儿恢复不丢消息。

### 执行结果

新增排队、取消和恢复执行接口；Session 详情返回 next-message 快照。SessionService 统一映射 404/409，AgentService 可原子重开 completed + queued 会话，并在孤儿收敛或显式停止时释放 processing 槽位。

### 验证证据

```text
命令：uv run pytest tests/app/services/test_agent_next_message.py tests/app/interfaces/endpoints/test_session_next_message_route.py tests/app/services/test_agent_service_recovery.py tests/app/repositories/test_db_session_next_message.py -q
退出状态：0
关键结果：19 passed；覆盖 API 路由、schema trim、服务错误映射、恢复启动、孤儿重置和既有恢复回归。

命令：uv run python -m py_compile app/schemas/session.py app/controllers/session.py app/services/session_service.py app/services/agent_service.py
退出状态：0
执行时间：2026-07-21 12:26 Asia/Shanghai
```

## Task 3：运行器自然接续消费且不打断当前 flow

状态：completed

### 目标

在当前 flow 自然结束后自动执行 next-message，并保持终止事件、等待、错误和停止语义正确。

### 涉及文件

- `agentic/api/app/core/agent/agent_task_runner.py`
- `agentic/api/tests/app/core/agent/test_agent_task_runner_completion.py`

### 实施步骤

1. 先写失败测试，证明现有 Redis 输入检测会打断当前 flow 且无法消费 DB next-message。
2. 移除运行中输入导致的提前 break；每个 flow 独立缓存 DoneEvent。
3. 当前轮正常结束时，通过仓储原子“认领 next-message 或完成 Session”。
4. 把认领消息转换为可见用户 MessageEvent，持久化并输出后再启动下一轮 flow。
5. Wait/Error/Cancelled 路径不认领 queued；processing 在用户事件被持久化后清空。

### 验证方式

- `uv run pytest tests/app/core/agent/test_agent_task_runner_completion.py -q`

### 完成条件

- 当前 flow 不被排队打断；有 queued 时自动接续；整个连续运行只产生一个最终 DoneEvent；终止分支回归通过。

### 执行结果

重构 AgentTaskRunner 为逐轮自然完成状态机：每轮独立缓存 DoneEvent；仅在 Redis 输入和 DB next-message 都为空时原子写 completed 并输出最终 Done。新增持久化消息接收路径，把用户事件写入输出、Session 历史与 latest_message 后再运行 flow；Wait/Error/Cancelled 不认领 queued 消息。

### 验证证据

```text
命令：uv run pytest tests/app/core/agent/test_agent_task_runner_completion.py tests/app/services/test_agent_next_message.py tests/app/services/test_agent_service_recovery.py tests/app/repositories/test_db_session_next_message.py -q
退出状态：0
关键结果：25 passed；覆盖自然接续、空输入恢复、单一最终 done、旧 Redis 输入不截断及 Wait/Error/Stop 保留队列。

命令：uv run python -m py_compile app/core/agent/agent_task_runner.py
退出状态：0
执行时间：2026-07-21 14:56 Asia/Shanghai
```

## Task 4：实现 Composer 排队、取消与刷新恢复交互

状态：completed

### 目标

运行中可以通过 Enter/按钮保存下一条消息，停止动作保持独立，刷新后恢复排队卡片并允许用户显式继续。

### 涉及文件

- `agentic/web/src/lib/api/types.ts`
- `agentic/web/src/lib/api/session.ts`
- `agentic/web/src/composables/useSessionDetail.ts`
- `agentic/web/src/composables/useSessionDetail.spec.ts`
- `agentic/web/src/components/chat/ChatComposer.vue`
- `agentic/web/src/components/chat/ChatComposer.runtime.spec.ts`
- `agentic/web/src/components/chat/ChatInput.vue`
- `agentic/web/src/components/chat/ChatInput.spec.ts`
- `agentic/web/src/components/SessionDetailView.vue`

### 实施步骤

1. 增加 next-message 类型与 queue/cancel/run API。
2. composable 暴露 next-message 和排队/取消/恢复方法，并以流代次防止旧请求覆盖。
3. Composer 运行中 Enter 改为 queue，发送与停止按钮并列；queued/processing 提示可访问。
4. ChatInput 仅在 API 成功后清草稿和附件；失败保留；queued 卡片允许取消。
5. SessionDetailView 在最终状态与刷新后提供显式 run queued 操作，409 时刷新收敛。

### 验证方式

- `pnpm test:run -- src/composables/useSessionDetail.spec.ts src/components/chat/ChatComposer.runtime.spec.ts src/components/chat/ChatInput.spec.ts`
- `pnpm type-check`

### 完成条件

- 运行中排队、独立停止、取消、失败保留和刷新恢复均有组件/组合式测试；类型检查通过。

### 执行结果

新增 next-message API 类型和客户端方法；composable 支持排队、取消与独立恢复流，并在用户事件到达或恢复流完成时清理本地排队快照。Composer 在运行中把 Enter/发送按钮定义为“加入下一条”，同时保留独立停止按钮。SessionDetailView 显示排队卡片、支持取消、处理 409 行锁竞态，并在 completed + queued 时提供显式“发送”恢复；Wait/Error/Stop 均不会自动启动 queued 消息。

### 验证证据

```text
命令：pnpm test:run -- src/components/chat/ChatComposer.runtime.spec.ts src/components/chat/ChatInput.spec.ts src/composables/useSessionDetail.spec.ts
退出状态：0
关键结果：3 files，18 passed；覆盖运行中 Enter 排队、独立停止、失败保留草稿、queue/cancel 和 guarded run SSE。

命令：pnpm type-check
退出状态：0
执行时间：2026-07-21 15:01 Asia/Shanghai
```

## Task 5：完整验证、审查与门禁结论

状态：completed

### 目标

运行与声明匹配的完整检查，审查并发、迁移、恢复和 UI 状态机，给出可合并门禁结论。

### 涉及文件

- 本计划涉及的全部代码、测试和迁移
- `agentic/docs/reviews/chat-next-message-queue-review.md`（新建）
- `agentic/docs/plans/chat-next-message-queue-plan.md`

### 实施步骤

1. 运行后端定向与相关回归测试。
2. 运行前端全量测试、类型检查和生产构建。
3. 检查 Alembic revision 链和 upgrade/downgrade SQL。
4. 运行 `git diff --check` 并审阅实际差异范围。
5. 按 blocking/major/minor/suggestion 审查并整改。
6. 尝试真实 PostgreSQL、Redis 和浏览器端到端验收；不可用则记录精确阻塞。

### 验证方式

- 后端：`uv run pytest tests/app/core/agent tests/app/services -q`
- 前端：`pnpm test:run && pnpm type-check && pnpm build`
- 迁移：Alembic heads/history 与可用数据库上的 upgrade/downgrade
- 静态：`git diff --check`
- 手工：运行中排队、替换、取消、自动接续、停止保留、刷新/重启恢复、多标签页冲突

### 完成条件

- 自动化通过且审查无 blocking/major；若仅真实依赖不可用，则以 `BLOCKED` 明确记录解除条件，否则 `READY_TO_MERGE`。

### 执行结果

完成后端相关回归、前端全量测试、类型检查、生产构建、Alembic revision/离线 SQL/真实数据库往返、Redis 健康检查与 `git diff --check`。代码审查发现两项 major 与一项 minor，均已整改并补充回归测试。应用内浏览器不可用，页面端到端验收作为唯一外部阻塞项记录在审查文档。

### 验证证据

```text
后端：100 passed，10 warnings（既有 Pydantic 弃用警告）
前端：17 files，53 passed
类型：pnpm type-check，退出码 0
构建：pnpm build，退出码 0，3651 modules transformed
迁移：单一 head；真实 PostgreSQL 20260715 -> 20260721 -> 20260715 -> 20260721 成功
Redis：PONG
差异：git diff --check，退出码 0
审查：无未处理 blocking/major/minor
浏览器：No browser is available
执行日期：2026-07-21 Asia/Shanghai
```

## 最终验证

### 执行命令

```powershell
# agentic/api
uv run pytest tests/app/core/agent tests/app/services -q

# agentic/web
pnpm test:run
pnpm type-check
pnpm build

# D:\AI\Think-Agentic
git diff --check
```

### 验收标准

- [x] 运行中提交不会打断当前 flow。
- [x] 每会话最多一条消息可持久排队、替换和取消。
- [x] 正常完成后自动接续，且只产生一个最终 DoneEvent。
- [x] Wait/Error/Stop 不会意外自动启动 queued 消息。
- [x] 刷新与孤儿运行恢复不丢 queued 消息。
- [x] 前后端测试、类型检查、构建、迁移与差异检查通过。

### 最终状态

`BLOCKED`：代码与自动化范围已通过；解除条件是可用浏览器中的真实页面/SSE 端到端验收。
