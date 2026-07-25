# 分支版本导航与气泡内编辑增强实施计划

## 关联设计

- 设计文档：`agentic/docs/designs/chat-branch-version-navigation.zh-CN.md`
- 开发分支：`feature/chat-branch-version-navigation`

## 当前进度

- 整体状态：`IN_PROGRESS`
- 当前阶段：implementation
- 当前任务：Task 5：完成全量回归、页面验收和代码审查
- 已完成：4 / 5
- 阻塞问题：无
- 最近更新时间：2026-07-25（Asia/Shanghai）

## 全局约束

- 继续以 Session 隔离 Agent Run、Trace、Memory、文件和工具副作用，不引入同 Session 消息树。
- 版本族只包含一个直接来源 Session 及其同一 `forked_from_event_id` 下的直接子分支。
- 原 Session 和既有分支不可被版本导航或内联编辑修改。
- 编辑用户消息仍创建 edit 分支；不提供原地保存，不允许人工编辑 Assistant 内容。
- 版本切换不得携带 `runQueued`、启动 Run、恢复归档任务或改变 next-message。
- 所有查询按当前用户过滤；来源删除或越权时不得泄露标题、ID 或存在性。
- 复用现有 lineage 字段和 `ix_sessions_source_session_id`，本批无数据库迁移。
- 不实现递归分支树、分支合并、消息 diff、分享、导出或分支重命名。
- 不自动提交、推送、创建 PR 或合并。

## 状态变更记录

| 日期时间 | 整体状态 | 当前任务 | 变更原因 |
| --- | --- | --- | --- |
| 2026-07-25 | `PLAN_READY` | 无 | 发现第一阶段 edit/regenerate/fork 已完成，转为直接分支族版本导航与气泡内编辑增强；设计和五项任务拆分完成 |
| 2026-07-25 | `IN_PROGRESS` | Task 1 | 已创建 `feature/chat-branch-version-navigation` 普通功能分支，开始仓储查询测试先行实施 |
| 2026-07-25 | `IN_PROGRESS` | Task 2（pending） | Task 1 的仓储契约、用户隔离、锚点解析、来源降级和稳定排序已实现并通过 22 项组合测试 |
| 2026-07-25 | `IN_PROGRESS` | Task 2 | 开始 branch-family 响应投影、只读路由和错误契约的测试先行实施 |
| 2026-07-25 | `IN_PROGRESS` | Task 3（pending） | Task 2 的轻量响应、只读 API、404/409/422 映射与安全日志已实现并通过 32 项扩大回归 |
| 2026-07-25 | `IN_PROGRESS` | Task 3 | 开始前端 API 客户端、版本导航组件和 branchEvent 路由恢复的测试先行实施 |
| 2026-07-25 | `IN_PROGRESS` | Task 4（pending） | Task 3 的 `1 / N` 导航、版本列表、失败降级和 branchEvent 路由恢复已实现，8 项组件测试与类型检查通过 |
| 2026-07-25 | `IN_PROGRESS` | Task 4 | 开始气泡内编辑组件、单编辑态与现有 edit 分支提交链路的测试先行迁移 |
| 2026-07-25 | `IN_PROGRESS` | Task 5（pending） | Task 4 已完成气泡内编辑迁移并删除旧 Dialog；目标组件测试 20 项与类型检查通过 |

## Task 1：建立用户隔离的直接分支族仓储查询

状态：completed

### 目标

在不修改数据库结构的情况下，可靠查询一个来源事件对应的来源 Session 和所有直接子分支，并保证用户隔离、锚点校验与稳定排序。

### 涉及文件

- `agentic/api/app/repositories/session_repository.py`
- `agentic/api/app/repositories/db_session_repository.py`
- `agentic/api/tests/app/repositories/test_db_session_branch_family.py`（新建）
- `agentic/api/tests/app/repositories/test_db_session_branching.py`

### 依赖与接口

- 前置任务：无。
- 输入：当前 Session ID、用户 ID、可选 target event ID。
- 输出：来源 Session 可用性、规范 target event ID、当前 Session 和直接子分支 Session 列表。

### 实施步骤

1. 在仓储接口定义直接分支族只读查询结果和方法，避免 controller 拼接权限逻辑。
2. 当前 Session 为子分支且没有显式本地锚点时，从自身 `source_session_id + forked_from_event_id` 推导族；非法显式 target 返回冲突。
3. 当前 Session 作为来源时要求 target event ID，并验证该事件是 visible user/assistant MessageEvent；本身也是分支的 Session 可以通过自身可见锚点作为下一级来源。
4. 查询相同 user、source_session_id 和 forked_from_event_id 的直接子分支；来源仍属于用户时置于首位。
5. 子分支按 `created_at ASC, id ASC` 排序；确保当前 Session 必须存在于结果中。
6. 覆盖来源删除、跨用户、不同锚点、嵌套分支、归档子分支和同时间排序。

### 验证方式

- 运行：`uv run pytest tests/app/repositories/test_db_session_branch_family.py tests/app/repositories/test_db_session_branching.py -q`
- 预期：退出 0；组合过滤、权限、排序、删除来源和二级分支断言通过。

### 完成条件

- 仓储能从来源或子分支两种入口返回同一个直接分支族，且不会合并不同用户、锚点或层级。

### 执行结果

已增加不可变 `SessionBranchFamily` 仓储结果和 `get_branch_family` 协议，实现来源/子分支双入口、来源不可用降级、用户隔离、同锚点直接子分支查询、归档项保留与 `created_at + id` 稳定排序。测试先行覆盖普通来源、分支作为下一级来源、二级分支、删除/越权来源、隐藏/缺失消息、锚点冲突和当前项一致性。

### 验证证据

```text
命令：uv run pytest tests/app/repositories/test_db_session_branch_family.py tests/app/repositories/test_db_session_branching.py -q
退出状态：0
关键结果：22 passed；新分支族测试 11 项和既有分支创建回归 11 项全部通过
执行时间：2026-07-25 09:02（Asia/Shanghai）

命令：uv run ruff check app/core/entities/session.py app/repositories/session_repository.py app/repositories/db_session_repository.py tests/app/repositories/test_db_session_branch_family.py
退出状态：0
关键结果：All checks passed
执行时间：2026-07-25 09:02（Asia/Shanghai）
```

## Task 2：提供 branch-family 只读 API 与错误契约

状态：completed

### 目标

向前端提供安全、稳定的直接分支族响应，并在来源不可用、锚点非法和 lineage 冲突时返回明确且不泄密的结果。

### 涉及文件

- `agentic/api/app/schemas/session.py`
- `agentic/api/app/services/session_service.py`
- `agentic/api/app/controllers/session.py`
- `agentic/api/tests/app/services/test_session_branch_family.py`（新建）
- `agentic/api/tests/app/interfaces/endpoints/test_session_branch_family_route.py`（新建）

### 依赖与接口

- 前置任务：Task 1。
- 输入：仓储直接分支族查询。
- 输出：`GET /sessions/{session_id}/branch-family` 和 `BranchFamilyResponse`。

### 实施步骤

1. 定义 `BranchFamilyVariantResponse` 和 `BranchFamilyResponse`，operation 包含 `original/fork/edit/regenerate`。
2. Service 将来源与直接子分支投影为轻量导航元数据，不返回 events、files、Memory 或正文。
3. Controller 接受可选 `target_event_id`，复用统一 404/409/422 异常映射。
4. 来源删除或不再属于用户时返回 `source_session_id=null`，仍允许当前用户拥有的直接兄弟分支导航。
5. 增加结构化日志字段：user、current、source、target、variant_count；禁止记录标题和消息内容。
6. 测试 schema、权限、归档标记、稳定顺序和错误契约。

### 验证方式

- 运行：`uv run pytest tests/app/services/test_session_branch_family.py tests/app/interfaces/endpoints/test_session_branch_family_route.py -q`
- 预期：退出 0；成功响应、404、409、422 和不泄露来源断言通过。

### 完成条件

- API 只返回当前用户可见的轻量版本列表，来源与子分支入口语义一致，错误码与设计一致。

### 执行结果

已增加 `BranchFamilyVariantResponse` 和 `BranchFamilyResponse`，由 SessionService 将仓储领域结果投影为不含 events、files、Memory 或消息正文的轻量版本元数据。新增 `GET /sessions/{session_id}/branch-family`，支持可选 target_event_id、认证用户透传、来源隐藏降级、归档标记与 original/fork/edit/regenerate operation；仓储异常稳定映射为 404/409/422，并记录不含标题或正文的结构化加载日志。

### 验证证据

```text
命令：uv run pytest tests/app/services/test_session_branch_family.py tests/app/interfaces/endpoints/test_session_branch_family_route.py -q
退出状态：0
关键结果：13 passed；成功响应、来源隐藏、归档版本、参数校验、404、409、422 和日志字段断言通过
执行时间：2026-07-25 09:36（Asia/Shanghai）

命令：uv run pytest tests/app/repositories/test_db_session_branch_family.py tests/app/services/test_session_branch_family.py tests/app/services/test_session_branching.py tests/app/interfaces/endpoints/test_session_branch_family_route.py tests/app/interfaces/endpoints/test_session_branching_route.py -q
退出状态：0
关键结果：32 passed；Task 1 仓储、新旧分支 Service 与新旧路由扩大回归通过
执行时间：2026-07-25 09:36（Asia/Shanghai）

命令：uv run ruff check app/schemas/session.py app/services/session_service.py app/controllers/session.py tests/app/services/test_session_branch_family.py tests/app/interfaces/endpoints/test_session_branch_family_route.py
退出状态：0
关键结果：All checks passed
执行时间：2026-07-25 09:36（Asia/Shanghai）
```

## Task 3：实现分支版本导航和路由恢复

状态：completed

### 目标

在分支来源区域提供稳定的上一版、下一版、`当前位置 / 总数` 和版本列表导航，并保证刷新、归档和来源删除时安全降级。

### 涉及文件

- `agentic/web/src/lib/api/types.ts`
- `agentic/web/src/lib/api/session.ts`
- `agentic/web/src/components/chat/BranchVersionNavigator.vue`（新建）
- `agentic/web/src/components/chat/BranchVersionNavigator.spec.ts`（新建）
- `agentic/web/src/components/SessionDetailView.vue`
- `agentic/web/src/components/SessionDetailView.spec.ts`
- `agentic/web/src/components/chat/chat.css`

### 依赖与接口

- 前置任务：Task 2。
- 输入：branch-family API、当前 Session 详情和 route query。
- 输出：可刷新恢复的 Session 级版本导航。

### 实施步骤

1. 增加 branch-family 前端类型和 API 客户端，保持与服务端字段一一对应。
2. 新建导航组件，展示操作类型、归档标记、上一版、下一版、计数和可键盘访问的版本列表。
3. 分支 Session 自动加载自身 family；来源 Session 仅在存在 `branchEvent` 时加载。
4. 切换到来源时写入 `branchEvent`；切换到子分支时不生成 `runQueued`。
5. 加载失败时保留会话详情和现有来源返回能力，提供重试与关闭导航上下文。
6. 路由变化、刷新、来源删除、归档版本和 50 个变体布局纳入组件测试。

### 验证方式

- 运行：`pnpm test:run -- src/components/chat/BranchVersionNavigator.spec.ts src/components/SessionDetailView.spec.ts`
- 运行：`pnpm type-check`
- 预期：退出 0；版本顺序、路由 query、无 runQueued、失败降级和键盘标签通过。

### 完成条件

- 用户可以在直接分支族中往返并刷新恢复，导航不会触发执行或修改任何 Session。

### 执行结果

已增加与后端一一对应的 branch-family 类型和 GET 客户端，新建 `BranchVersionNavigator` 展示 original/fork/edit/regenerate、归档状态、上一版、下一版、`当前位置 / 总数` 与原生可访问版本列表。SessionDetail 对子分支自动加载 family，对来源页按 branchEvent 恢复；切回来源保留 branchEvent，切换子分支显式清空 query，不携带 runQueued。加载失败时保留对话详情、返回来源、重试和关闭无效来源上下文；分支创建成功路径同时保留 branchEvent 与既有一次性 runQueued 意图。

### 验证证据

```text
命令：pnpm test:run -- src/components/chat/BranchVersionNavigator.spec.ts src/components/SessionDetailView.spec.ts
退出状态：0
关键结果：2 files passed，8 tests passed；覆盖 50 个版本、边界按钮、版本列表、归档标签、自动加载、branchEvent 刷新恢复、无 runQueued 切换和失败降级
执行时间：2026-07-25 09:48（Asia/Shanghai）

命令：pnpm type-check
退出状态：0
关键结果：vue-tsc -b 通过
执行时间：2026-07-25 09:48（Asia/Shanghai）
```

## Task 4：将用户消息编辑迁移为气泡内分支编辑

状态：completed

### 目标

用原消息位置的内联编辑器替代 Dialog，同时保持现有 edit 分支、附件/Skills 沿用、request ID 幂等和 queued 恢复语义。

### 涉及文件

- `agentic/web/src/components/chat/ChatInlineBranchEditor.vue`（新建）
- `agentic/web/src/components/chat/ChatInlineBranchEditor.spec.ts`（新建）
- `agentic/web/src/components/chat/ChatMessage.vue`
- `agentic/web/src/components/chat/ChatMessage.spec.ts`
- `agentic/web/src/components/chat/MessageActions.vue`
- `agentic/web/src/components/chat/MessageActions.spec.ts`
- `agentic/web/src/components/SessionDetailView.vue`
- `agentic/web/src/components/chat/ChatEditBranchDialog.vue`（删除或停止使用）
- `agentic/web/src/components/chat/ChatEditBranchDialog.spec.ts`（随实现删除或迁移）
- `agentic/web/src/components/chat/chat.css`

### 依赖与接口

- 前置任务：Task 3。
- 输入：现有 branchAction 事件、createBranch 和 pendingBranchRequest。
- 输出：单消息内联编辑状态及 edit 分支提交。

### 实施步骤

1. 新建内联编辑组件，预填消息，显示不可编辑的附件和 Skills，并明确“原对话不会改变”。
2. 支持 `Escape`、取消、`Ctrl/Cmd + Enter` 和提交按钮；空白文本不可提交，最大长度 10000。
3. 将编辑状态提升到 SessionDetail，保证同一时刻只有一个编辑项。
4. ChatMessage 在编辑目标处替换用户气泡，不隐藏其他历史消息。
5. 提交继续复用现有 createBranch('edit')、稳定 request ID、runQueued 和失败保留逻辑。
6. 运行开始、Session 路由改变、归档或消息不再可分支时取消未提交编辑。
7. 删除或停止渲染旧 Dialog，避免两套编辑入口并存。

### 验证方式

- 运行：`pnpm test:run -- src/components/chat/ChatInlineBranchEditor.spec.ts src/components/chat/ChatMessage.spec.ts src/components/chat/MessageActions.spec.ts src/components/SessionDetailView.spec.ts`
- 运行：`pnpm type-check`
- 预期：退出 0；内联显示、快捷键、附件/Skills、单编辑态、失败保留和成功导航通过。

### 完成条件

- 用户消息编辑只在原气泡位置进行，提交仍创建不可变新 Session，且现有分支可靠性没有退化。

### 执行结果

已新增原消息位置的内联分支编辑器，支持自动聚焦、取消、Escape、Ctrl/Cmd + Enter、空白/长度校验和忙碌态；附件及 Skills 作为只读继承上下文展示。SessionDetail 只维护一个编辑目标，继续复用现有 edit 分支、稳定 request ID 和 queued-run 意图；失败保留编辑态，运行、归档、Session 变化或消息失效时取消。旧 `ChatEditBranchDialog` 及其测试已删除，queued-run 可靠性测试已迁移到 SessionDetail。

### 验证证据

```text
命令：pnpm test:run -- src/components/chat/ChatInlineBranchEditor.spec.ts src/components/chat/ChatMessage.spec.ts src/components/chat/MessageActions.spec.ts src/components/SessionDetailView.spec.ts
退出状态：0
关键结果：4 个测试文件、20 项测试全部通过
执行时间：2026-07-25 11:08（Asia/Shanghai）

命令：pnpm type-check
退出状态：0
关键结果：vue-tsc -b 通过
执行时间：2026-07-25 11:09（Asia/Shanghai）

命令：git diff --check
退出状态：0
关键结果：无空白错误；仅显示仓库既有的 LF/CRLF 转换提示
执行时间：2026-07-25 11:10（Asia/Shanghai）
```

## Task 5：完成全量回归、页面验收和代码审查

状态：pending

### 目标

以最新证据确认分支族导航和内联编辑不会破坏既有聊天、运行、审批、HITL、归档、搜索、文件、Trace 和第一阶段分支能力。

### 涉及文件

- 本计划涉及的全部代码和测试
- `agentic/docs/librechat-ui-redesign.zh-CN.md`
- `agentic/docs/reviews/chat-branch-version-navigation-review.md`（新建）
- `agentic/docs/plans/chat-branch-version-navigation-plan.md`

### 依赖与接口

- 前置任务：Task 1–4。
- 输入：完整变更集和设计验收标准。
- 输出：最新验证证据、分级审查和 `READY_TO_MERGE / BLOCKED / FAILED`。

### 实施步骤

1. 运行 branch、Session、next-message、HITL、Agent、搜索、文件、Trace 和 endpoint 相关后端回归。
2. 运行前端全量测试、类型检查和生产构建。
3. 确认 Alembic heads/current 未变化，本批没有意外迁移。
4. 运行 `git diff --check` 并审阅完整 diff、旧客户端兼容和不相关工作区修改。
5. 手工验证桌面、390px 移动端、暗色、键盘、刷新、版本切换、来源删除模拟、归档版本和编辑失败重试。
6. 按 blocking/major/minor/suggestion 代码审查；整改后重跑受影响验证。
7. 将实际证据、限制和最终状态写回计划、审查和 LibreChat 学习文档。

### 验证方式

- 后端：`uv run pytest tests/app/core/agent tests/app/repositories tests/app/services tests/app/interfaces/endpoints -q`
- 前端：`pnpm test:run`
- 类型：`pnpm type-check`
- 构建：`pnpm build`
- 迁移：`uv run alembic heads` 和 `uv run alembic current`
- 静态：`git diff --check`
- 手工：edit/regenerate/fork、版本切换、branchEvent 刷新、无 runQueued、归档只读、移动端、暗色和键盘焦点。

### 完成条件

- 自动化、类型、构建、迁移头检查和页面验收通过；审查无未处理 blocking/major；全部设计验收项有证据。

### 执行结果

待执行。

### 验证证据

```text
命令：待执行
退出状态：待执行
关键结果：待执行
执行时间：待执行
```

## 计划变更

| 日期 | 变更内容 | 原因 | 影响任务 | 是否影响设计 |
| --- | --- | --- | --- | --- |
| 2026-07-25 | 初始计划 | 将直接分支族查询、API、版本导航、内联编辑和最终门禁拆为五个独立任务 | Task 1–5 | 否 |
| 2026-07-25 | 明确分支 Session 的双重角色解析 | 分支既可能属于上一级版本族，也可能作为下一级直接来源；显式本地消息锚点必须进入来源模式，才能在二级分支切回后恢复导航 | Task 1–3 | 否，补充既有直接分支族语义 |

## 最终验证

### 执行命令

```powershell
# agentic/api
uv run pytest tests/app/core/agent tests/app/repositories tests/app/services tests/app/interfaces/endpoints -q
uv run alembic heads
uv run alembic current

# agentic/web
pnpm test:run
pnpm type-check
pnpm build

# D:\AI\Think-Agentic
git diff --check
```

### 执行结果

- 单元测试：待执行。
- 集成测试：待执行。
- 静态检查：待执行。
- 类型检查：待执行。
- 构建：待执行。
- 数据库迁移：不适用；仍需确认没有新增 migration 且 head/current 不变。
- 手工验证：待执行。
- 代码审查：待执行。

### 验收标准检查

- [ ] 已有分支显示稳定版本位置和总数。
- [ ] 来源与同锚点直接子分支可以前后切换和列表跳转。
- [ ] branchEvent 刷新恢复正确，不合并错误分支族。
- [ ] 版本导航不启动 Run、不恢复归档任务。
- [ ] 来源删除或越权不泄露信息。
- [ ] 用户消息气泡内编辑、取消和快捷键正确。
- [ ] 编辑仍创建新 Session，附件/Skills、request ID 和 queued 恢复正确。
- [ ] regenerate 新版本可与原始回复比较。
- [ ] running、waiting、queued、processing、archived 门禁无回归。
- [ ] 后端用户隔离、锚点校验、稳定排序和错误契约通过。
- [ ] 聊天、分支、next-message、HITL、审批、搜索、文件和 Trace 回归通过。
- [ ] 桌面、移动端、暗色和键盘焦点通过页面验收。

### 未通过项目

待执行。

### 最终状态

`IN_PROGRESS`：Task 1–4 已完成并有局部验证证据，等待开始 Task 5。
