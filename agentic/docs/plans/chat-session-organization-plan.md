# 会话重命名、置顶与归档实施计划

## 关联设计

- 设计文档：`agentic/docs/designs/chat-session-organization.zh-CN.md`
- 开发分支：`feature/chat-session-organization`

## 当前进度

- 整体状态：`PLAN_READY`
- 当前阶段：planning
- 当前任务：无
- 已完成：0 / 5
- 阻塞问题：上一批实现已提交为 `17231e3`；实施前需获授权单独提交其计划/审查收口文档，再创建新功能分支
- 最近更新时间：2026-07-24（Asia/Shanghai）

## 全局约束

- 重命名、置顶和归档是用户导航元数据，不修改 Session 事件、Memory、Trace、文件、lineage 或 Agent 运行记录。
- 手工标题必须持续优先于后续 Agent 自动 TitleEvent。
- 默认 REST/SSE 列表和默认全局搜索只显示未归档 Session；归档 Session 仍允许按 ID 访问详情和 lineage。
- running、waiting 或存在 next-message 的 Session 不允许归档；归档自动清除置顶。
- 所有接口按 `session_id + user_id` 校验，无权与不存在统一 404。
- 不实现 Project、标签、批量操作、拖拽排序、软删除、分享、导出或导入。
- 不自动提交、推送、创建 PR 或合并。

## 状态变更记录

| 日期时间 | 整体状态 | 当前任务 | 变更原因 |
| --- | --- | --- | --- |
| 2026-07-24 | `PLAN_READY` | 无 | 设计已比较三种持久化方案并选择 Session 一等元数据；计划拆分完成，等待提交上一批两份收口文档并创建新分支 |

## Task 1：建立 Session 整理元数据、可逆迁移与原子仓储规则

状态：pending

### 目标

让 Session 能持久化手工标题标记、置顶和归档状态，并由仓储原子执行用户隔离、排序、冲突和幂等规则。

### 涉及文件

- `agentic/api/app/core/entities/session.py`
- `agentic/api/app/models/session.py`
- `agentic/api/app/repositories/session_repository.py`
- `agentic/api/app/repositories/db_session_repository.py`
- `agentic/api/alembic/versions/20260724_0002_chat_session_organization.py`（新建）
- `agentic/api/tests/app/repositories/test_db_session_organization.py`（新建）

### 依赖与接口

- 前置任务：无；但开始实施前必须处于普通分支 `feature/chat-session-organization`。
- 输入：Session ID、用户 ID、可选 title/pinned/archived 更新。
- 输出：更新后的 Session；active/archived 用户列表；generated/manual 标题更新接口。

### 实施步骤

1. 在领域和 ORM Session 增加 `title_is_manual=false`、`is_pinned=false`、`archived_at=null`。
2. 新建 Alembic migration，添加三个字段和覆盖用户、归档、置顶、最近消息排序的组合索引；downgrade 可逆删除。
3. 将仓储标题接口拆为 `update_generated_title` 与 `update_manual_title`；generated 路径只更新未手工锁定的记录。
4. 扩展用户列表查询：active 先置顶再按业务时间稳定排序，archived 按归档时间倒序。
5. 实现按所属 Session 行锁的元数据更新：归档清除置顶，归档冲突返回领域错误，同值更新幂等。
6. 覆盖历史默认值、手工标题锁定、排序、active/archived 过滤、运行/next-message 冲突、跨用户和并发测试。

### 验证方式

- 运行：`uv run pytest tests/app/repositories/test_db_session_organization.py tests/app/repositories/test_db_session_branching.py tests/app/repositories/test_db_session_next_message.py -q`
- 运行：`uv run python -m py_compile app/core/entities/session.py app/models/session.py app/repositories/session_repository.py app/repositories/db_session_repository.py alembic/versions/20260724_0002_chat_session_organization.py`
- 运行：`uv run alembic heads`
- 预期：退出 0；唯一 migration head；仓储测试证明状态规则和用户隔离。

### 完成条件

- 历史 Session 默认仍可见；三项元数据正确持久化；手工标题不被 generated 路径覆盖；active/archived 查询与冲突规则符合设计。

### 执行结果

待执行。

### 验证证据

```text
命令：待执行
退出状态：待执行
关键结果：待执行
执行时间：待执行
```

## Task 2：开放元数据 API、归档范围列表并统一搜索语义

状态：pending

### 目标

提供稳定、用户隔离且向后兼容的 Session 整理 API，并确保默认列表、SSE、搜索和自动标题使用同一语义。

### 涉及文件

- `agentic/api/app/schemas/session.py`
- `agentic/api/app/controllers/session.py`
- `agentic/api/app/services/session_service.py`
- `agentic/api/app/core/agent/agent_task_runner.py`
- `agentic/api/app/repositories/db_search_repository.py`
- `agentic/api/tests/app/services/test_session_organization.py`（新建）
- `agentic/api/tests/app/services/test_search_service.py`
- `agentic/api/tests/app/interfaces/endpoints/test_session_organization_route.py`（新建）
- `agentic/api/tests/app/core/agent/test_agent_task_runner_completion.py`

### 依赖与接口

- 前置任务：Task 1。
- 输入：`GET /sessions?scope=active|archived`、`PATCH /sessions/{session_id}`。
- 输出：新增 `is_pinned`、`archived_at` 的 Session 列表项和更新结果。

### 实施步骤

1. 新增严格 PATCH schema：title trim 后 1–100、pinned/archived 可选、至少一个字段、未知字段和互斥组合 422。
2. 为 GET sessions 增加默认 `active` scope，并让 SSE 固定只返回 active；列表响应增加整理元数据。
3. 实现 SessionService 元数据更新，映射领域 not-found/conflict 为 404/409，并记录不含消息正文的结构化日志。
4. 将 AgentTaskRunner 自动标题改用 `update_generated_title`，手工锁定导致未更新时不影响 Run。
5. 在默认搜索查询加入 `archived_at IS NULL`；归档详情和 lineage 所有权查询保持可访问。
6. 测试成功、422、404、409、重复同值、列表 scope、搜索排除归档和连续 Agent run 不覆盖手工标题。

### 验证方式

- 运行：`uv run pytest tests/app/services/test_session_organization.py tests/app/services/test_search_service.py tests/app/interfaces/endpoints/test_session_organization_route.py tests/app/core/agent/test_agent_task_runner_completion.py -q`
- 运行：`uv run python -m py_compile app/schemas/session.py app/controllers/session.py app/services/session_service.py app/core/agent/agent_task_runner.py app/repositories/db_search_repository.py`
- 预期：退出 0；API 错误契约、搜索过滤和标题优先级均有回归证据。

### 完成条件

- 默认客户端行为向后兼容；归档不会从直接详情/lineage 消失；手工标题、scope 和错误码符合设计。

### 执行结果

待执行。

### 验证证据

```text
命令：待执行
退出状态：待执行
关键结果：待执行
执行时间：待执行
```

## Task 3：实现侧栏原位重命名、置顶分组与归档操作

状态：pending

### 目标

让用户在现有侧栏中完成可访问、失败可恢复的重命名、置顶和归档，并保持列表 SSE 最终一致。

### 涉及文件

- `agentic/web/src/lib/api/types.ts`
- `agentic/web/src/lib/api/session.ts`
- `agentic/web/src/stores/sessions.ts`
- `agentic/web/src/components/SessionListItem.vue`
- `agentic/web/src/components/SessionList.vue`
- `agentic/web/src/components/SessionListItem.spec.ts`（新建）
- `agentic/web/src/components/SessionList.spec.ts`（新建）
- `agentic/web/src/stores/sessions.spec.ts`（新建）
- `agentic/web/src/assets/main.css` 或对应侧栏样式文件

### 依赖与接口

- 前置任务：Task 2。
- 输入：Session 列表元数据和 PATCH API。
- 输出：侧栏菜单、原位重命名、置顶组、归档后导航和 Toast。

### 实施步骤

1. 扩展前端 Session 类型、列表 scope 和 PATCH API。
2. 在 Store 增加 update/rename/pin/archive 操作；成功后立即更新本地列表，失败保留原状态，后续 SSE 使用服务端状态校准。
3. 在 SessionListItem 菜单加入重命名、置顶/取消置顶、归档和现有删除；运行/等待/queued 时禁用归档并解释原因。
4. 实现原位 RenameForm：聚焦全选、1–100 字、Enter 保存、Escape 取消、显式保存/取消、失败时保留文本。
5. 将置顶 Session 放入“已置顶”组；其余 Session 沿用日期分组，确保键盘和屏幕阅读器能识别。
6. 当前 Session 归档成功后返回首页；移动端完成操作后维持合理侧栏开合和焦点。
7. 覆盖菜单可见性、键盘、失败恢复、置顶排序、归档禁用和当前项导航测试。

### 验证方式

- 运行：`pnpm test:run -- src/components/SessionListItem.spec.ts src/components/SessionList.spec.ts src/stores/sessions.spec.ts`
- 运行：`pnpm type-check`
- 预期：退出 0；三种操作、键盘和失败回退均有测试。

### 完成条件

- 用户无需离开侧栏即可重命名、置顶和归档；操作不会误触打开 Session；失败后原状态和输入可恢复。

### 执行结果

待执行。

### 验证证据

```text
命令：待执行
退出状态：待执行
关键结果：待执行
执行时间：待执行
```

## Task 4：实现归档管理弹窗、恢复与永久删除闭环

状态：pending

### 目标

提供可发现的归档管理入口，使已归档 Session 能被过滤、打开、恢复或永久删除。

### 涉及文件

- `agentic/web/src/components/ArchivedSessionsDialog.vue`（新建）
- `agentic/web/src/components/ArchivedSessionsDialog.spec.ts`（新建）
- `agentic/web/src/components/SessionList.vue`
- `agentic/web/src/stores/sessions.ts`
- `agentic/web/src/components/settings/SettingsGeneralPanel.vue`（仅当最终入口复用设置中心）
- `agentic/web/src/components.d.ts`
- `agentic/web/src/assets/main.css` 或对应侧栏/弹窗样式文件
- `agentic/docs/librechat-ui-redesign.zh-CN.md`

### 依赖与接口

- 前置任务：Task 3。
- 输入：archived scope 列表、恢复 PATCH 和现有永久删除接口。
- 输出：归档管理入口与完整恢复/删除交互。

### 实施步骤

1. 在会话侧栏提供“已归档任务”入口并打开响应式 Dialog；避免新增无必要正式路由。
2. Dialog 加载 archived scope，提供标题/最近消息本地过滤、Loading、Empty、Filtered Empty 和 Error 状态。
3. 每项支持在当前页或新标签打开、恢复、永久删除；删除复用强确认文案，恢复后立即从归档列表移除。
4. 打开归档 Session 不自动恢复；详情仍显示真实 archived 状态，用户可返回归档管理。
5. 实现焦点进入/返回、Escape、移动端尺寸、Live Region 和每项明确 aria-label。
6. 更新 LibreChat UI 改造文档，记录选择性学习范围、实际文件和不包含的 Project/分享/导出能力。
7. 覆盖加载、过滤、恢复、删除、错误、焦点和移动视图结构测试。

### 验证方式

- 运行：`pnpm test:run -- src/components/ArchivedSessionsDialog.spec.ts src/components/SessionListItem.spec.ts src/components/SessionList.spec.ts src/stores/sessions.spec.ts`
- 运行：`pnpm type-check`
- 预期：退出 0；归档管理闭环和可访问状态通过。

### 完成条件

- 归档 Session 可发现、可打开、可恢复、可永久删除；入口、弹窗和错误状态在桌面与移动端可用。

### 执行结果

待执行。

### 验证证据

```text
命令：待执行
退出状态：待执行
关键结果：待执行
执行时间：待执行
```

## Task 5：完成迁移、全量回归、页面验收与代码审查

状态：pending

### 目标

用最新证据确认 Session 整理不会破坏聊天、分支、next-message、HITL、搜索、删除和 lineage，并达到合并门禁。

### 涉及文件

- 本计划涉及的全部代码、迁移、测试和文档
- `agentic/docs/reviews/chat-session-organization-review.md`（新建）
- `agentic/docs/plans/chat-session-organization-plan.md`

### 依赖与接口

- 前置任务：Task 1–4。
- 输入：完整变更集和设计验收标准。
- 输出：最新验证证据、分级代码审查和 `READY_TO_MERGE / BLOCKED / FAILED`。

### 实施步骤

1. 运行 Session、Agent、搜索、next-message、HITL、分支和 endpoint 相关后端回归。
2. 运行前端全量测试、类型检查和生产构建。
3. 在真实 PostgreSQL 执行 migration upgrade/downgrade/upgrade，确认唯一 head、默认值和组合索引。
4. 运行 `git diff --check`，审阅所有实际差异和旧客户端兼容。
5. 手工验证桌面、移动端、暗色、键盘、刷新、SSE 多标签页、失败重试和归档当前 Session。
6. 按 blocking/major/minor/suggestion 自审；整改后重跑受影响验证。
7. 将实际证据、偏差和最终状态写回计划和审查文档。

### 验证方式

- 后端：`uv run pytest tests/app/core/agent tests/app/repositories tests/app/services tests/app/interfaces/endpoints -q`
- 前端：`pnpm test:run; pnpm type-check; pnpm build`
- 迁移：`uv run alembic heads` 及真实数据库 upgrade/downgrade/upgrade
- 静态：`git diff --check`
- 手工：重命名标题锁定、置顶排序、归档门禁、恢复/删除、直接详情、lineage、搜索排除、SSE 多标签页

### 完成条件

- 最新自动化、构建和迁移通过；无未处理 blocking/major；所有设计验收项有证据或明确外部阻塞。

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
| 2026-07-24 | 初始计划 | 将 Session 元数据、API 搜索语义、侧栏交互、归档管理和最终门禁拆为五个可验证任务 | Task 1–5 | 否 |

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

- 单元测试：未执行
- 集成测试：未执行
- 静态检查：未执行
- 类型检查：未执行
- 构建：未执行
- 数据库迁移：未执行
- 手工验证：未执行
- 代码审查：未执行

### 验收标准检查

- [ ] 侧栏原位重命名支持 Enter/Escape、校验和失败保留。
- [ ] 手工标题刷新及后续 Agent run 后仍保持。
- [ ] 置顶分组、取消置顶和刷新持久化正确。
- [ ] running、waiting、next-message 归档门禁与 completed/pending 成功路径正确。
- [ ] 默认列表、SSE 和搜索排除归档；直接详情和 lineage 仍可访问。
- [ ] 归档弹窗支持过滤、打开、恢复和永久删除。
- [ ] 当前 Session 归档后导航安全，多标签页 SSE 最终一致。
- [ ] 跨用户操作统一 404。
- [ ] 可逆迁移和历史 Session 兼容通过。
- [ ] 全量后端、前端、构建、静态与手工门禁通过。

### 未通过项目

尚未实施和验证。

### 最终状态

`BLOCKED`：计划已就绪；上一批实现已提交，但其最终计划/审查状态尚未提交。需获授权单独提交这两份收口文档，再创建独立实施分支。
