# 对话编辑、重新生成与会话分支实施计划

## 关联设计

- 设计文档：`agentic/docs/designs/chat-conversation-branching.zh-CN.md`
- 开发分支：`feature/chat-conversation-branching`

## 当前进度

- 整体状态：`BLOCKED`
- 当前阶段：final-verification
- 当前任务：Task 5
- 已完成：4 / 5
- 阻塞问题：Browser 运行时无可用浏览器连接，真实页面手工验收待补跑
- 最近更新时间：2026-07-24（Asia/Shanghai）

## 全局约束

- 历史事件、Memory、Trace 和工具执行记录不可原地修改。
- 分支是新的 Session；第一版不实现同 Session 消息树或 sibling 箭头切换。
- 只继承安全可见 user/assistant 上下文，不复制 Tool、Interaction、Error、Plan、Step、Done 或隐藏事件。
- edit/regenerate 输入必须先持久化为 queued next-message，再尝试一次性自动启动。
- 源 Session 必须 completed 且无 next-message；所有附件必须继续属于当前用户。
- 分支创建按客户端 request_id 幂等；权限错误不暴露资源存在性。
- 不自动提交、推送、创建 PR 或合并。

## 状态变更记录

| 日期时间 | 整体状态 | 当前任务 | 变更原因 |
| --- | --- | --- | --- |
| 2026-07-24 | `PLAN_READY` | 无 | 设计完成，任务、迁移、接口和验证边界已拆分；等待进入实施 |
| 2026-07-24 | `IN_PROGRESS` | Task 1 | 用户确认继续，已创建 `feature/chat-conversation-branching` 并开始领域模型与仓储状态机 |
| 2026-07-24 | `IN_PROGRESS` | Task 2 | Task 1 的领域模型、原子快照仓储、幂等冲突恢复和可逆迁移已验证通过 |
| 2026-07-24 | `IN_PROGRESS` | Task 3 | Task 2 的安全可见上下文首次注入、持久化去重和现有 Memory 兼容已验证通过 |
| 2026-07-24 | `IN_PROGRESS` | Task 4 | Task 3 的 branches API、错误契约、结构化日志和安全 lineage 详情已验证通过 |
| 2026-07-24 | `IN_PROGRESS` | Task 5 | Task 4 的消息操作、编辑弹窗、lineage 导航和一次性 queued 启动已通过前端测试与构建 |
| 2026-07-24 | `BLOCKED` | Task 5 | 自动化、构建、迁移和代码自审已通过；Browser 运行时无可用连接，真实页面手工验收待补跑 |

## Task 1：建立分支领域模型、迁移与原子快照仓储

状态：completed

### 目标

让仓储可以在不修改源 Session 的前提下，按目标 MessageEvent 原子创建幂等的新 Session 快照及 lineage/context seed。

### 涉及文件

- `agentic/api/app/core/entities/session.py`
- `agentic/api/app/core/entities/event.py`
- `agentic/api/app/models/session.py`
- `agentic/api/app/repositories/session_repository.py`
- `agentic/api/app/repositories/db_session_repository.py`
- `agentic/api/alembic/versions/20260724_0001_chat_conversation_branching.py`（新建）
- `agentic/api/tests/app/repositories/test_db_session_branching.py`（新建）

### 依赖与接口

- 前置任务：无。
- 输入：源 Session ID、用户 ID、目标事件 ID、operation、request ID、可选编辑文本。
- 输出：新 Session；`fork` 无 next-message，`edit/regenerate` 带 queued next-message。

### 实施步骤

1. 新增 `BranchOperation`、`BranchContextMessage`、lineage/context 字段及领域校验错误。
2. 为 SessionModel 和 Alembic migration 增加 source/event/operation/request/context 字段、唯一索引和来源索引。
3. 实现安全可见事件投影：生成新事件 ID，以 Session lineage 记录直接来源，并收集仍可访问附件。
4. 实现 `create_branch` 行锁事务，区分 fork/edit/regenerate 边界并构建 context seed。
5. 实现 request_id 幂等重放；并发唯一冲突后重新读取既有目标 Session。
6. 覆盖源不变、边界、角色、附件、状态冲突、幂等与旧 Session 兼容测试。

### 验证方式

- 运行：`uv run pytest tests/app/repositories/test_db_session_branching.py -q`
- 运行：`uv run python -m py_compile app/core/entities/session.py app/core/entities/event.py app/models/session.py app/repositories/db_session_repository.py alembic/versions/20260724_0001_chat_conversation_branching.py`
- 运行：`uv run alembic heads`
- 预期：测试和编译退出 0；Alembic 只有一个新 head。

### 完成条件

- 三种 operation 都能产生符合设计边界的新 Session；源 Session 字节级领域快照不变；重复 request_id 返回同一 Session。

### 执行结果

已新增分支领域模型、lineage/context seed 持久化字段和可逆迁移。`create_branch` 在锁定所属源 Session 后投影安全可见消息，校验附件当前所有权，为复制事件生成新 ID，并按 fork/edit/regenerate 构造快照或 durable queued next-message。request_id 既支持正常重放，也会在唯一索引并发竞争后通过嵌套事务重新读取胜出分支。

### 验证证据

```text
命令：uv run pytest tests/app/repositories/test_db_session_branching.py tests/app/repositories/test_db_session_next_message.py -q
退出状态：0
关键结果：17 passed；覆盖三种 operation、源快照不变、可见事件过滤、角色/状态/附件冲突、正常幂等和并发唯一冲突恢复
执行时间：2026-07-24

命令：uv run python -m py_compile app/core/entities/session.py app/core/entities/event.py app/models/session.py app/repositories/db_session_repository.py alembic/versions/20260724_0001_chat_conversation_branching.py；uv run alembic heads
退出状态：0
关键结果：编译通过；唯一 head 为 20260724_0001
执行时间：2026-07-24

命令：uv run alembic downgrade 20260721_0001；uv run alembic upgrade 20260724_0001；uv run pytest tests/app/repositories -q
退出状态：0
关键结果：迁移 downgrade/upgrade 成功，本地库回到 20260724_0001；仓储回归 26 passed
执行时间：2026-07-24
```

## Task 2：为新分支注入安全可见 Agent Memory 上下文

状态：completed

### 目标

确保分支首次 Planner/ReAct 模型调用继承可见历史上下文，同时不复制隐藏工具状态或重复注入 seed。

### 涉及文件

- `agentic/api/app/core/agent/base.py`
- `agentic/api/app/core/entities/memory.py`
- `agentic/api/app/repositories/session_repository.py`
- `agentic/api/app/repositories/db_session_repository.py`
- `agentic/api/tests/app/core/agent/test_branch_context_seed.py`（新建）

### 依赖与接口

- 前置任务：Task 1。
- 输入：Session.context_seed、空或已有的 Agent Memory。
- 输出：首次 Memory 顺序为 system → context seed → 当前消息；后续调用不重复 seed。

### 实施步骤

1. 在仓储协议中增加用户不可见的 context seed 读取接口。
2. 调整 BaseAgent 空 Memory 初始化：先加入自身 system prompt，再加入经过服务端校验的 user/assistant seed，最后加入当前调用消息。
3. 确保已存在 Memory、普通 Session 或空 context seed 沿用当前行为。
4. 测试 Planner/ReAct 各自首次注入、第二次不重复、附件只使用文件名、隐藏角色被拒绝。

### 验证方式

- 运行：`uv run pytest tests/app/core/agent/test_branch_context_seed.py tests/app/core/agent -q`
- 预期：退出 0；模型输入快照不含 tool/system/error 来源 seed。

### 完成条件

- 分支上下文在每个 Agent 的首次调用中准确出现一次；普通 Session 和恢复流程回归不变。

### 执行结果

为 SessionRepository 增加内部 context seed 读取接口，并在 BaseAgent 首次加载空 Memory 时读取经类型校验的 seed。首次写入顺序固定为 Agent system prompt、历史 user/assistant seed、当前消息；附件仅以文件名附加。seed 随 Memory 持久化后即清空临时缓存，后续调用和已存在 Memory 均不会重复注入。

### 验证证据

```text
命令：uv run pytest tests/app/core/agent/test_branch_context_seed.py -q
退出状态：0
关键结果：4 passed；Planner/ReAct 首次顺序、附件文件名、单次注入、普通/既有 Memory 和非法角色校验通过
执行时间：2026-07-24

命令：uv run pytest tests/app/core/agent -q
退出状态：0
关键结果：Agent 回归 19 passed
执行时间：2026-07-24

命令：uv run python -m py_compile app/core/agent/base.py app/repositories/session_repository.py app/repositories/db_session_repository.py
退出状态：0
关键结果：静态编译通过
执行时间：2026-07-24
```

## Task 3：开放分支 API、lineage 详情与服务错误映射

状态：completed

### 目标

提供用户隔离、幂等且可由前端稳定调用的 branches API，并在 Session 详情安全返回来源提示。

### 涉及文件

- `agentic/api/app/schemas/session.py`
- `agentic/api/app/controllers/session.py`
- `agentic/api/app/services/session_service.py`
- `agentic/api/tests/app/services/test_session_branching.py`（新建）
- `agentic/api/tests/app/interfaces/endpoints/test_session_branching_route.py`（新建）

### 依赖与接口

- 前置任务：Task 1。
- 输入：`POST /sessions/{session_id}/branches` 请求。
- 输出：branch response 和 Session detail lineage；404/409/422 契约。

### 实施步骤

1. 增加 CreateSessionBranchRequest/Response 与 lineage response schema。
2. 实现 SessionService 目标解析、错误映射和幂等结果返回。
3. 增加 branches controller；详情接口仅在来源仍属于当前用户时返回可导航 ID/标题。
4. 测试越权、不存在、角色冲突、运行状态、消息 trim、重复请求和来源删除后的安全响应。
5. 为 fork/edit/regenerate 增加结构化日志，不记录消息全文或附件路径。

### 验证方式

- 运行：`uv run pytest tests/app/services/test_session_branching.py tests/app/interfaces/endpoints/test_session_branching_route.py -q`
- 运行：`uv run python -m py_compile app/schemas/session.py app/controllers/session.py app/services/session_service.py`
- 预期：退出 0；公开 schema 与设计一致。

### 完成条件

- API 对三种操作、权限、幂等和冲突提供稳定响应；Session detail 不泄露其他用户来源信息。

### 执行结果

新增严格校验的 branches API：request_id 使用 UUID、目标事件自动 trim，edit 必须且仅能携带非空 message。SessionService 将无权访问/不存在映射为统一 404，将状态、角色、附件和幂等不匹配映射为 409，并记录不含消息全文的结构化 lineage 日志。Session 详情仅在来源仍属于当前用户时返回可导航的来源 ID/标题，否则保留 branch_operation 提示但隐藏来源身份。

### 验证证据

```text
命令：uv run pytest tests/app/services/test_session_branching.py tests/app/interfaces/endpoints/test_session_branching_route.py -q
退出状态：0
关键结果：8 passed；覆盖成功契约、认证用户归属、422、404、409 和来源隐藏
执行时间：2026-07-24

命令：uv run pytest tests/app/repositories/test_db_session_branching.py tests/app/services tests/app/interfaces/endpoints -q
退出状态：0
关键结果：仓储、服务与端点回归 112 passed
执行时间：2026-07-24

命令：uv run python -m py_compile app/schemas/session.py app/controllers/session.py app/services/session_service.py
退出状态：0
关键结果：静态编译通过
执行时间：2026-07-24
```

## Task 4：实现消息操作、编辑弹窗、分支导航与可靠启动

状态：completed

### 目标

在桌面和移动端提供可访问的 fork/edit/regenerate 交互，并确保编辑或重新生成在导航失败、刷新或断流后仍可恢复。

### 涉及文件

- `agentic/web/src/lib/api/types.ts`
- `agentic/web/src/lib/api/session.ts`
- `agentic/web/src/lib/session-events.ts`
- `agentic/web/src/lib/session-init.ts`
- `agentic/web/src/components/chat/MessageActions.vue`
- `agentic/web/src/components/chat/ChatMessage.vue`
- `agentic/web/src/components/chat/ChatEditBranchDialog.vue`（新建）
- `agentic/web/src/components/SessionDetailView.vue`
- `agentic/web/src/composables/useSessionDetail.ts`
- `agentic/web/src/components/chat/MessageActions.spec.ts`（新建）
- `agentic/web/src/components/chat/ChatEditBranchDialog.spec.ts`（新建）
- `agentic/web/src/composables/useSessionDetail.spec.ts`

### 依赖与接口

- 前置任务：Task 3。
- 输入：时间线 item.sourceEventId、消息 role/content、branch API。
- 输出：新 Session 路由；fork 静默打开，edit/regenerate 一次性启动 queued 输入。

### 实施步骤

1. 扩展前端类型/API 和 timeline turn 归属，确保 Assistant regenerate 能定位稳定目标事件。
2. 将 MessageActions 扩展为复制、分支，以及按 role 显示 edit/regenerate；运行中或 waiting 时禁用并解释原因。
3. 实现编辑弹窗：预填文本、展示只读附件/Skills、说明将在新分支重新执行。
4. 创建分支成功后导航到新 Session；使用一次性 session-init 导航令牌启动 queued 输入并立即消费令牌。
5. 自动启动失败时保留 queued 卡片；刷新不得再次自动执行。
6. 在 Session 头部显示“来自某会话的编辑/重新生成分支”与返回来源操作。
7. 增加键盘、焦点、aria-label、移动端菜单、暗色模式和错误回退测试。

### 验证方式

- 运行：`pnpm test:run -- src/components/chat/MessageActions.spec.ts src/components/chat/ChatEditBranchDialog.spec.ts src/composables/useSessionDetail.spec.ts`
- 运行：`pnpm type-check`
- 预期：退出 0；覆盖三种操作、角色可见性、一次性启动和失败保留。

### 完成条件

- 用户可从消息完成 fork/edit/regenerate；源页面不变化；新页面可靠启动或保留可恢复 queued 输入。

### 执行结果

消息操作现按角色提供 fork、edit 或 regenerate，并在 running/waiting/queued 状态给出禁用原因。编辑弹窗预填文本、只读展示沿用附件与 Skills；成功后导航到新 Session。edit/regenerate 使用 sessionStorage 中与目标 Session 绑定的一次性令牌启动 durable next-message，令牌在页面消费时立即删除，刷新不会重放；启动失败仍保留 queued 卡片供手工发送。页面同时显示安全来源提示与返回原对话入口。

### 验证证据

```text
命令：pnpm test:run -- src/components/chat/MessageActions.spec.ts src/components/chat/ChatEditBranchDialog.spec.ts src/composables/useSessionDetail.spec.ts
退出状态：0
关键结果：3 files、13 tests passed；覆盖角色操作、禁用、编辑提交、一次性令牌和 guarded queued SSE
执行时间：2026-07-24

命令：pnpm test:run
退出状态：0
关键结果：19 files、57 tests passed
执行时间：2026-07-24

命令：pnpm type-check；pnpm build
退出状态：0
关键结果：vue-tsc 通过；Vite production build 成功（3653 modules transformed）
执行时间：2026-07-24
```

## Task 5：完整迁移、回归、页面验收与代码审查

状态：in_progress

### 目标

以最新证据确认分支状态机、上下文安全、权限、幂等、迁移、页面交互和既有聊天能力可合并。

### 涉及文件

- 本计划涉及的全部代码、迁移和测试
- `agentic/docs/reviews/chat-conversation-branching-review.md`（新建）
- `agentic/docs/plans/chat-conversation-branching-plan.md`

### 依赖与接口

- 前置任务：Task 1–4。
- 输入：完整变更集和设计验收标准。
- 输出：最新验证证据、分级审查和 READY_TO_MERGE/BLOCKED/FAILED。

### 实施步骤

1. 运行分支、Agent、next-message、HITL、Session、文件、搜索和 Trace 相关后端回归。
2. 运行前端全量测试、类型检查和生产构建。
3. 在 PostgreSQL 执行 migration upgrade/downgrade/upgrade，并确认单一 head 和索引。
4. 运行 `git diff --check`，审阅实际差异和旧 Session 兼容。
5. 手工验证桌面、移动端、暗色模式、键盘、刷新、断网、多标签页重复点击和附件缺失。
6. 按 blocking/major/minor/suggestion 代码审查；整改后重新运行受影响验证。
7. 把实际证据、偏差和最终状态写回本计划与审查文档。

### 验证方式

- 后端：`uv run pytest tests/app/core/agent tests/app/repositories tests/app/services tests/app/interfaces/endpoints -q`
- 前端：`pnpm test:run && pnpm type-check && pnpm build`
- 迁移：`uv run alembic heads` 及真实数据库 upgrade/downgrade/upgrade
- 静态：`git diff --check`
- 手工：fork/edit/regenerate、来源返回、失败保留、幂等、多标签页、附件、移动端与暗色模式

### 完成条件

- 最新自动化与迁移通过；审查无 blocking/major；全部设计验收项有证据或以明确外部条件标记 BLOCKED。

### 执行结果

已完成全量自动化、迁移和同一 Agent 代码自审。审查中发现并修复了 sessionStorage 不可用时误报失败、网络响应丢失后重试未复用 request_id 两项可靠性问题，受影响验证已重新执行。当前仅缺少真实浏览器页面验收。

### 验证证据

```text
命令：uv run pytest tests/app/core/agent tests/app/repositories tests/app/services tests/app/interfaces/endpoints -q
退出状态：0
关键结果：147 passed，10 个既有 Pydantic 弃用警告
执行时间：2026-07-24

命令：pnpm test:run；pnpm type-check；pnpm build
退出状态：0
关键结果：19 files / 58 tests passed；vue-tsc 通过；Vite 生产构建成功，3653 modules transformed
执行时间：2026-07-24

命令：uv run alembic heads；uv run alembic current；此前执行 downgrade 20260721_0001 / upgrade 20260724_0001
退出状态：0
关键结果：唯一 head/current 均为 20260724_0001；真实 PostgreSQL 可逆迁移通过
执行时间：2026-07-24

命令：git diff --check
退出状态：0
关键结果：无 whitespace error；仅有 Windows LF/CRLF 提示
执行时间：2026-07-24

手工验收：未执行
原因：Browser 运行时没有可用连接，agent.browsers.list() 返回 []
```

## 计划变更

| 日期 | 变更内容 | 原因 | 影响任务 | 是否影响设计 |
| --- | --- | --- | --- | --- |
| 2026-07-24 | 初始计划 | 将新 Session 快照分支拆为数据、上下文、API、UI 和门禁五个可独立验证任务 | Task 1–5 | 否 |

## 最终验证

### 执行命令

```powershell
# agentic/api
uv run pytest tests/app/core/agent tests/app/repositories tests/app/services tests/app/interfaces/endpoints -q
uv run alembic heads

# agentic/web
pnpm test:run
pnpm type-check
pnpm build

# D:\AI\Think-Agentic
git diff --check
```

### 执行结果

- 单元测试：通过，前端 58 passed
- 集成测试：通过，后端 147 passed
- 静态检查：通过，`git diff --check` 无错误
- 类型检查：通过，`vue-tsc -b` 退出 0
- 构建：通过，Vite production build 退出 0
- 数据库迁移：通过，唯一 head/current 为 `20260724_0001`，downgrade/upgrade 已验证
- 手工验证：受阻，Browser 运行时无可用浏览器连接
- 代码审查：`APPROVED`，无未处理 blocking/major；详见审查文档

### 验收标准检查

- [x] Fork 打开独立新 Session 且源 Session 完全不变。
- [x] Edit 在新分支提交编辑文本并可靠启动或保留 queued 输入。
- [x] Regenerate 重放对应用户回合且不复制旧工具执行状态。
- [x] Context seed 只包含安全可见上下文并准确注入一次。
- [x] 权限、附件、状态和 request_id 幂等边界正确。
- [x] 旧 Session 与现有聊天、next-message、HITL、搜索、文件、Trace 回归通过。
- [ ] 页面桌面/移动端/暗色/键盘/刷新/断网/多标签页验收通过。

### 未通过项目

真实浏览器页面验收尚未执行：当前 Browser 运行时没有可用浏览器连接。

### 最终状态

`BLOCKED`：代码、自动化、构建、迁移和自审均已通过；等待可用浏览器连接完成最终页面验收。
