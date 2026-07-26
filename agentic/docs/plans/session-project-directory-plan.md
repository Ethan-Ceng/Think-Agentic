# Session 单层项目目录管理实施计划

## 关联设计

- 设计文档：`agentic/docs/designs/session-project-directory.zh-CN.md`
- 开发分支：`feature/session-project-directory`
- 实施基线：`c8ab3c4`（用户已提交并验收的 A1 附件体验）以及进入分支时保留的路线/设计文档

## 当前进度

- 整体状态：`BLOCKED`
- 当前阶段：verification
- 当前任务：Task 6
- 已完成：5 / 6
- 阻塞问题：当前会话没有可用浏览器实例；仓库既有 Ruff 两项和 `readme.md:3` 尾空格不属于本批且尚未获准修改
- 最近更新时间：2026-07-27（Asia/Shanghai）

## 全局约束

- Project 首期只管理 Session 单层目录；数据库、API 和 UI 均不得出现 `parent_id` 或递归目录。
- 一个 Session 最多属于一个 Project；`project_id = null` 表示“未分组”。
- Project 不向 Agent、Planner、Prompt、Memory、Knowledge、Skills、Tools 或文件附件注入任何上下文。
- Project 删除只解除 active/archived Session 归属，不删除、归档、停止、恢复或修改任务内容。
- Project 和 Session 必须属于同一用户；跨用户与不存在统一 404。
- Project 名称 trim 后 1–100 字符，当前用户内大小写不敏感唯一。
- Session 项目移动是导航元数据更新，不改变 `updated_at`、`latest_message_at`、状态、未读数、置顶、事件或 next-message。
- running、waiting 和存在 next-message 的 Session 允许移动。
- 归档保留 Project；恢复回到原 Project；Project 已删除时恢复到“未分组”。
- fork/edit/regenerate 新分支继承来源 Project，之后可独立移动且不联动 branch family。
- 首页只有发送第一条消息时才创建 Session；项目内新建不得产生空 Session。
- 侧栏只呈现 Project → Session 两层；不做项目详情页、拖拽排序、项目归档、协作、颜色或图标配置。
- 置顶只在所属 Project 或“未分组”内影响排序。
- Session REST/SSE、归档、搜索、分支、消息、审批、队列、文件和 Trace 现有协议除新增 nullable `project_id` 外保持兼容。
- 不新增第三方依赖，不修改 lockfile。
- 不自动提交、推送、创建 PR 或合并。
- `agentic/web/src/components.d.ts` 与 `auto-imports.d.ts` 的生成扫描差异不得混入本批。
- 一次只推进一个 Task；状态变化、执行结果、偏差和验证证据必须立即写回本计划。

## 状态变更记录

| 日期时间 | 整体状态 | 当前任务 | 变更原因 |
| --- | --- | --- | --- |
| 2026-07-26 | `PLAN_READY` | 无 | 设计完成并拆分为六项可恢复、可独立验证的实施任务 |
| 2026-07-26 | `IN_PROGRESS` | Task 1 | 已创建独立功能分支，开始建立 Project 数据模型、迁移和 Repository |
| 2026-07-26 | `IN_PROGRESS` | 无（Task 2 待开始） | Task 1 的模型、Repository、UOW、迁移与定向验证已完成 |
| 2026-07-26 | `IN_PROGRESS` | Task 2 | 开始实现 Project CRUD Service、API、稳定错误与认证用户绑定 |
| 2026-07-26 | `IN_PROGRESS` | 无（Task 3 待开始） | Task 2 的 Project CRUD Service、API、认证、输入与错误契约验证已完成 |
| 2026-07-26 | `IN_PROGRESS` | Task 3 | 开始接入 Session 创建、项目移动、REST/SSE、归档与分支继承 |
| 2026-07-26 | `IN_PROGRESS` | 无（Task 4 待开始） | Task 3 的 Session 创建、项目移动、REST/SSE、归档与分支继承已完成并通过联合回归 |
| 2026-07-26 | `IN_PROGRESS` | Task 4 | 开始建立前端 Project API、Stores 与创建/重命名/移动 Dialog |
| 2026-07-26 | `IN_PROGRESS` | 无（Task 5 待开始） | Task 4 的前端 Project API、Stores、创建/重命名 Dialog 与移动 Dialog 已完成并通过类型及相关组件回归 |
| 2026-07-26 | `IN_PROGRESS` | Task 5 | 开始实现侧栏单层 Project 目录、项目内首次创建、Session 移动与归档归属显示 |
| 2026-07-26 | `IN_PROGRESS` | 无（Task 6 待开始） | Task 5 的侧栏 Project 目录、项目内首次创建、移动、归档归属和响应式集成已完成并通过前端全量回归与生产构建 |
| 2026-07-27 | `IN_PROGRESS` | Task 6 | 开始执行迁移升降级、前后端全量回归、真实页面验收和最终代码审查 |
| 2026-07-27 | `BLOCKED` | Task 6 | 自动化、迁移、真实 API 和代码审查已完成；浏览器实例不可用，且全仓 Ruff/静态门禁仍有本批外既有问题 |

## Task 1：建立 Project 数据模型、迁移和 Repository

状态：completed

### 目标

建立用户拥有、无层级的 Project 持久化模型和 Repository，并通过 nullable 外键让历史 Session 安全进入“未分组”。

### 涉及文件

- `agentic/api/app/core/entities/project.py`（新建）
- `agentic/api/app/models/project.py`（新建）
- `agentic/api/app/models/session.py`
- `agentic/api/app/models/__init__.py`
- `agentic/api/app/core/entities/session.py`
- `agentic/api/app/repositories/project_repository.py`（新建）
- `agentic/api/app/repositories/db_project_repository.py`（新建）
- `agentic/api/app/repositories/uow.py`
- `agentic/api/app/repositories/db_uow.py`
- `agentic/api/alembic/versions/20260726_0001_session_projects.py`（新建，实际 revision 以 Alembic 唯一 head 为准）
- `agentic/api/tests/app/repositories/test_db_project_repository.py`（新建）
- `agentic/api/tests/app/repositories/test_db_uow.py`

### 依赖与接口

- 前置任务：无。
- 输入：当前用户 ID、Project ID/name、现有 Session 表。
- 输出：
  - `Project` 领域实体；
  - `ProjectModel`；
  - Project Repository list/get/create/rename/delete；
  - `Session.project_id: Optional[str]`；
  - 可升级/降级的 Alembic 迁移。
- 数据约束：
  - `projects` 不含 `parent_id`；
  - `sessions.project_id` FK `ON DELETE SET NULL`；
  - 历史 Session 默认 null；
  - 用户内小写名称唯一。

### 实施步骤

1. 先增加 Repository/UOW 失败测试，覆盖用户隔离、创建、稳定排序、大小写同名、重命名、删除和缺失项目。
2. 定义最小 `Project` 领域实体，仅包含 ID、user_id、name、created_at、updated_at。
3. 新建 `ProjectModel`，增加主键、用户/创建时间索引和用户内 `lower(name)` 唯一索引，不添加未来扩展字段。
4. 向 Session 领域和 ORM 增加 nullable `project_id`，更新 domain/model 转换字段。
5. 新建 Project Repository 协议与 PostgreSQL 实现，所有读写显式按 `user_id` 限制。
6. 将 Project Repository 接入 `IUnitOfWork` 和 `DBUnitOfWork`。
7. 编写 Alembic 迁移：先建 projects，再加 sessions.project_id、FK 和索引；downgrade 逆序删除。
8. 验证删除 Project 只把 active/archived Session 的 `project_id` 置 null，其他列逐字段保持。
9. 验证历史 Session 不回填、无 parent_id、迁移为单 head。

### 验证方式

- 运行：`uv run pytest tests/app/repositories/test_db_project_repository.py tests/app/repositories/test_db_uow.py -q`
- 运行：`uv run python -m py_compile app/core/entities/project.py app/models/project.py app/models/session.py app/repositories/project_repository.py app/repositories/db_project_repository.py app/repositories/uow.py app/repositories/db_uow.py alembic/versions/20260726_0001_session_projects.py`
- 运行：`uv run ruff check app/core/entities/project.py app/models/project.py app/models/session.py app/repositories/project_repository.py app/repositories/db_project_repository.py app/repositories/uow.py app/repositories/db_uow.py tests/app/repositories/test_db_project_repository.py`
- 运行：`uv run alembic heads`
- 预期：退出 0；Repository、用户隔离、唯一性、外键删除语义、UOW 和单 head 通过。

### 完成条件

- 数据库可以可靠表达空 Project 和 Session 可空归属，删除目录不删除 Session，且不存在任何层级字段。

### 执行结果

- 已新增最小 `Project` 领域实体和 `ProjectModel`，仅包含 ID、用户、名称与创建/更新时间，不含任何层级字段。
- 已为 Session 领域与 ORM 增加 nullable `project_id`，数据库外键使用 `ON DELETE SET NULL`，历史 Session 无需回填。
- 已实现用户范围的 Project list/get/create/rename/delete Repository，并将大小写不敏感唯一冲突映射为稳定领域异常。
- 已将 Project Repository 接入 `IUnitOfWork` 和 `DBUnitOfWork`。
- 已新增单 head Alembic 迁移；离线 upgrade/downgrade SQL 均可生成，删除 Project 只由外键解除 Session 归属。
- 测试优先证据：首次定向测试因 `app.core.entities.project` 尚不存在而在收集阶段失败；实现后 9 项测试全部通过。

### 验证证据

```text
uv run pytest tests/app/repositories/test_db_project_repository.py tests/app/repositories/test_db_uow.py -q
9 passed, 10 warnings in 0.04s

uv run pytest tests/app/repositories/test_db_session_organization.py -q
12 passed, 10 warnings in 0.05s

uv run python -m py_compile app/core/entities/project.py app/models/project.py app/models/session.py app/repositories/project_repository.py app/repositories/db_project_repository.py app/repositories/uow.py app/repositories/db_uow.py alembic/versions/20260726_0001_session_projects.py
exit 0

uv run ruff check app/core/entities/project.py app/models/project.py app/models/session.py app/repositories/project_repository.py app/repositories/db_project_repository.py app/repositories/uow.py app/repositories/db_uow.py tests/app/repositories/test_db_project_repository.py tests/app/repositories/test_db_uow.py
All checks passed!

uv run alembic heads
20260726_0001 (head)

uv run alembic upgrade 20260724_0002:20260726_0001 --sql
exit 0；生成 projects、lower(name) 唯一索引、nullable sessions.project_id 与 ON DELETE SET NULL 外键。

uv run alembic downgrade 20260726_0001:20260724_0002 --sql
exit 0；按索引、外键、列、projects 表的逆序生成降级 SQL。

git diff --check
exit 0（仅有仓库既有的 LF/CRLF 转换提醒，无空白错误）。
```

## Task 2：实现 Project CRUD 服务和 API

状态：completed

### 目标

提供当前用户隔离、错误稳定、可供侧栏使用的 Project 列表、创建、重命名和删除 API。

### 涉及文件

- `agentic/api/app/schemas/project.py`（新建）
- `agentic/api/app/services/project_service.py`（新建）
- `agentic/api/app/controllers/project.py`（新建）
- `agentic/api/app/controllers/__init__.py`
- `agentic/api/app/dependencies/__init__.py`
- `agentic/api/app/dependencies/services.py`
- `agentic/api/app/service_dependencies.py`
- `agentic/api/tests/app/services/test_project_service.py`（新建）
- `agentic/api/tests/app/interfaces/endpoints/test_project_routes.py`（新建）

### 依赖与接口

- 前置任务：Task 1。
- 输入：认证用户、Project name/ID。
- 输出：
  - `GET /api/projects`
  - `POST /api/projects`
  - `PATCH /api/projects/{project_id}`
  - `DELETE /api/projects/{project_id}`
- 错误：
  - 非法名称 422；
  - 当前用户内同名 409；
  - 不存在/跨用户 404。

### 实施步骤

1. 先增加 Service 和路由失败测试，固定认证用户绑定、响应字段、排序和错误契约。
2. 定义 forbid-extra 的创建/重命名 schema；名称 trim、1–100，不接受 user_id、parent_id 或其他字段。
3. 实现 Project Service，映射 Repository not-found/duplicate 为稳定 404/409。
4. 实现 Project Controller 并注册路由，返回现有统一 `Response` 包装。
5. 接入 service dependency，不绕过 UOW 或直接在 Controller 操作数据库。
6. 删除 Project 时仅调用 Project Repository；通过 Task 1 外键语义解除 Session 归属。
7. 记录 project_id、user_id、动作和结果，不记录对话内容。
8. 覆盖同名并发、重命名为自身、二次删除、跨用户读取/修改/删除和额外字段拒绝。

### 验证方式

- 运行：`uv run pytest tests/app/services/test_project_service.py tests/app/interfaces/endpoints/test_project_routes.py -q`
- 运行：`uv run ruff check app/schemas/project.py app/services/project_service.py app/controllers/project.py app/controllers/__init__.py app/service_dependencies.py tests/app/services/test_project_service.py tests/app/interfaces/endpoints/test_project_routes.py`
- 运行：`uv run python -m py_compile app/schemas/project.py app/services/project_service.py app/controllers/project.py app/service_dependencies.py`
- 预期：退出 0；CRUD、认证、输入校验、409/404 和删除安全语义通过。

### 完成条件

- 前端可以只通过稳定 API 管理当前用户的单层 Project，无法创建层级或访问其他用户目录。

### 执行结果

- 已新增 forbid-extra 的创建/重命名请求 schema：名称在长度校验前 trim，空白、null、超过 100 字符、`user_id`、`parent_id` 和其他额外字段统一由 FastAPI 返回 422。
- 已新增公开 Project 响应契约，仅返回 `id`、`name`、`created_at`、`updated_at`，不暴露所有者字段。
- 已实现 Project Service 的 list/create/rename/delete；所有操作绑定认证用户，通过 UOW 调用 Project Repository，并将重复名称与缺失/跨用户分别映射为稳定 409/404。
- 已注册 `GET/POST /api/projects` 与 `PATCH/DELETE /api/projects/{project_id}`，统一使用现有 `Response` 包装；未认证的四个入口均返回 401。
- 删除路径只调用 Project Repository，由 Task 1 的 `ON DELETE SET NULL` 外键负责解除 Session 归属，不读取或修改 Session 内容。
- 日志只记录 action、user_id、project_id、result 和列表数量，不记录对话内容。
- 对照设计将 Project Repository 排序从误写的升序校正为 `created_at DESC, id DESC`，并把重命名写入移动到 savepoint 内，保证并发唯一冲突可安全回滚。
- 测试优先证据：首次定向测试因 `project_service` 和 `get_project_service` 尚不存在而在收集阶段失败；实现后 Task 2 定向测试 14 项全部通过。

### 验证证据

```text
uv run pytest tests/app/services/test_project_service.py tests/app/interfaces/endpoints/test_project_routes.py -q
14 passed, 10 warnings in 0.43s

uv run pytest tests/app/repositories/test_db_project_repository.py tests/app/services/test_project_service.py tests/app/interfaces/endpoints/test_project_routes.py -q
21 passed, 10 warnings in 0.46s

uv run pytest tests/app/interfaces/endpoints/test_session_organization_route.py tests/app/interfaces/endpoints/test_marketplace_routes.py -q
7 passed, 10 warnings in 0.32s

uv run ruff check app/schemas/project.py app/services/project_service.py app/controllers/project.py app/controllers/__init__.py app/dependencies/__init__.py app/dependencies/services.py app/service_dependencies.py app/repositories/db_project_repository.py tests/app/services/test_project_service.py tests/app/interfaces/endpoints/test_project_routes.py tests/app/repositories/test_db_project_repository.py
All checks passed!

uv run python -m py_compile app/schemas/project.py app/services/project_service.py app/controllers/project.py app/controllers/__init__.py app/dependencies/__init__.py app/dependencies/services.py app/service_dependencies.py
exit 0

git diff --check
exit 0（仅有仓库既有的 LF/CRLF 转换提醒，无空白错误）。
```

## Task 3：接入 Session 创建、移动、归档、SSE 与分支继承

状态：completed

### 目标

让 Project 归属贯穿 Session 创建、列表、详情、organization、归档恢复和分支创建，同时保证运行状态与时间字段不受移动影响。

### 涉及文件

- `agentic/api/app/core/entities/session.py`
- `agentic/api/app/models/session.py`
- `agentic/api/app/repositories/session_repository.py`
- `agentic/api/app/repositories/db_session_repository.py`
- `agentic/api/app/schemas/session.py`
- `agentic/api/app/services/session_service.py`
- `agentic/api/app/controllers/session.py`
- `agentic/api/tests/app/repositories/test_db_session_organization.py`
- `agentic/api/tests/app/repositories/test_db_session_branching.py`
- `agentic/api/tests/app/services/test_session_organization.py`
- `agentic/api/tests/app/services/test_session_branching.py`
- `agentic/api/tests/app/interfaces/endpoints/test_session_organization_route.py`
- `agentic/api/tests/app/interfaces/endpoints/test_session_branching_route.py`

### 依赖与接口

- 前置任务：Task 1–2。
- 输入：
  - `POST /sessions { project_id?: string | null }`
  - `PATCH /sessions/{id} { project_id: string | null }`
- 输出：
  - Session list/detail/SSE 的 `project_id`;
  - 归档保留归属；
  - 新分支继承来源归属。
- 兼容：省略 `project_id` 的现有创建和 organization 请求行为不变。

### 实施步骤

1. 先增加失败测试，覆盖创建到自有/跨用户/不存在 Project，显式 null、字段省略和响应契约。
2. 新增 `CreateSessionRequest`；现有 `{}` 和无 body 兼容创建未分组 Session。
3. 扩展 `UpdateSessionOrganizationRequest`：只允许 `project_id` 显式 null，其他字段 null 仍拒绝。
4. 在 Session Service/Repository 的同一 UOW 中校验目标 Project 所有权，跨用户/不存在统一 404。
5. 扩展 row-locked `update_organization` 写入 project_id，并显式保持 `updated_at` 和所有运行/消息字段。
6. 允许 running、waiting、queued、active、archived Session 移动；不得复用归档冲突限制。
7. 在 ListSessionItem、GetSessionResponse、REST 列表和 SSE 中返回 nullable project_id。
8. 归档/恢复路径不清空或重新推断 project_id。
9. `create_branch` 显式复制 source.project_id；fork/edit/regenerate 逐项覆盖，后续移动不联动其他版本。
10. 覆盖 Project 删除后 Session 列表/详情为 null，active/archived 内容和运行状态保持。
11. 重跑现有 title/pin/archive/next-message/branch 回归，确认 public payload 除新增字段外不变。

### 验证方式

- 运行：`uv run pytest tests/app/repositories/test_db_session_organization.py tests/app/repositories/test_db_session_branching.py tests/app/services/test_session_organization.py tests/app/services/test_session_branching.py tests/app/interfaces/endpoints/test_session_organization_route.py tests/app/interfaces/endpoints/test_session_branching_route.py -q`
- 运行：`uv run ruff check app/core/entities/session.py app/models/session.py app/repositories/session_repository.py app/repositories/db_session_repository.py app/schemas/session.py app/services/session_service.py app/controllers/session.py`
- 运行：`uv run python -m py_compile app/core/entities/session.py app/models/session.py app/repositories/session_repository.py app/repositories/db_session_repository.py app/schemas/session.py app/services/session_service.py app/controllers/session.py`
- 预期：退出 0；创建、移动、用户隔离、归档、SSE、分支继承和回归通过。

### 完成条件

- Project 归属成为安全的 Session 导航字段，覆盖所有创建和展示路径而不进入执行上下文。

### 执行结果

- 新增兼容无 body、`{}`、显式 null 和可选 `project_id` 的 Session 创建请求；目标 Project 在保存 Session 前于同一 UOW 内按认证用户校验。
- Session organization PATCH 使用字段是否出现来区分省略与显式 null，可移动到自有 Project、移回未分组，并对不存在或跨用户 Project 返回稳定 404。
- Repository 的 row-locked organization 更新只写 `project_id`，保留业务 `updated_at`、消息、状态、未读、置顶、事件、next-message 和归档信息；running、waiting、queued 与 archived Session 均可移动。
- Session 列表、详情、SSE 与 organization 响应统一返回 nullable `project_id`；归档/恢复不改变归属。
- fork、edit、regenerate 创建的新分支显式继承来源 Session 的 `project_id`，后续仍可独立移动。
- Project 仅作为 Session 导航元数据接入，未进入 Agent、Planner、Prompt 或其他执行上下文。
- 首轮 RED 验证因尚无 `CreateSessionRequest` 在收集阶段失败；实现后专项、联合和 Session 广泛回归均通过。

### 验证证据

```text
RED:
- Task 3 首轮测试在收集阶段因 ImportError: CreateSessionRequest 失败，符合预期。

PASS:
- Task 3 专项：
  uv run pytest tests/app/repositories/test_db_session_organization.py tests/app/repositories/test_db_session_branching.py tests/app/services/test_session_organization.py tests/app/services/test_session_branching.py tests/app/interfaces/endpoints/test_session_organization_route.py tests/app/interfaces/endpoints/test_session_branching_route.py -q --log-cli-level=CRITICAL
  51 passed, 10 warnings in 0.79s
- Project + Task 3 联合回归：
  uv run pytest tests/app/repositories/test_db_project_repository.py tests/app/services/test_project_service.py tests/app/interfaces/endpoints/test_project_routes.py tests/app/repositories/test_db_session_organization.py tests/app/repositories/test_db_session_branching.py tests/app/services/test_session_organization.py tests/app/services/test_session_branching.py tests/app/interfaces/endpoints/test_session_organization_route.py tests/app/interfaces/endpoints/test_session_branching_route.py -q --log-cli-level=CRITICAL
  72 collected, 72 passed，退出 0
- Session organization/next-message/branch family/branching/interactions/recovery 广泛回归：
  88 passed，退出 0
- Ruff（Task 3 源码与相关测试）：
  All checks passed!
- py_compile（Task 3 后端源码）：
  退出 0
- Alembic：
  uv run alembic heads
  20260726_0001 (head)
- Task 3 限定路径 git diff --check：
  退出 0

备注：
- 全工作区 git diff --check 仍会命中用户已有的 readme.md:3 行尾空格；该文件不属于 Task 3，本任务未修改或清理这项既有改动。
```

## Task 4：建立前端 Project API、Stores 与可访问 Dialog

状态：completed

### 目标

建立前端 Project 状态和创建/重命名/移动交互基础，使后续侧栏集成只组合已验证的 API、Store 与 Dialog。

### 涉及文件

- `agentic/web/src/lib/api/types.ts`
- `agentic/web/src/lib/api/project.ts`（新建）
- `agentic/web/src/lib/api/session.ts`
- `agentic/web/src/stores/projects.ts`（新建）
- `agentic/web/src/stores/projects.spec.ts`（新建）
- `agentic/web/src/stores/sessions.ts`
- `agentic/web/src/stores/sessions.spec.ts`
- `agentic/web/src/components/ProjectDialog.vue`（新建）
- `agentic/web/src/components/ProjectDialog.spec.ts`（新建）
- `agentic/web/src/components/MoveSessionProjectDialog.vue`（新建）
- `agentic/web/src/components/MoveSessionProjectDialog.spec.ts`（新建）
- `agentic/web/src/components/project-directory.css`（新建）
- `agentic/web/src/main.ts`

### 依赖与接口

- 前置任务：Task 2–3。
- 输入：Project CRUD API、Session project_id、Session organization API。
- 输出：
  - `Project` 类型和 `projectApi`;
  - `useProjectsStore`;
  - `useSessionsStore.unassignProject`;
  - 创建/重命名 Dialog；
  - 移动 Session Dialog。

### 实施步骤

1. 先增加 Store/Dialog 失败测试，覆盖 loading/error/retry、成功、同名错误、确认/取消、搜索和焦点。
2. 增加 Project 和 Session project_id 类型；`CreateSessionParams` 与 organization params 支持 nullable project_id。
3. 新建 `projectApi`，只暴露 list/create/rename/delete。
4. 新建 `useProjectsStore`，实现稳定排序、加载、CRUD、本地原子替换和用户切换清理所需 `clear`。
5. 扩展 Sessions Store：Project 删除成功后同时清空 active/archived Session 的匹配 project_id，不改变其他字段。
6. 实现 `ProjectDialog`，复用创建/重命名，支持 trim、maxlength、Enter、Escape、防重复、错误保留和回焦。
7. 实现 `MoveSessionProjectDialog`，提供未分组、Project 搜索、当前选中、loading/error/retry、确认/取消和回焦。
8. 移动确认前不改 Store；失败时保持原归属。
9. 增加暗色、长名称、224px/390px 和滚动样式，不修改全局无关规则。
10. 确保生成组件声明不进入 diff。

### 验证方式

- 运行：`pnpm test:run -- src/stores/projects.spec.ts src/stores/sessions.spec.ts src/components/ProjectDialog.spec.ts src/components/MoveSessionProjectDialog.spec.ts`
- 运行：`pnpm type-check`
- 运行：`git diff --check`
- 预期：退出 0；API/Store 一致性、删除本地 unassign、Dialog 状态、搜索、键盘和类型检查通过。

### 完成条件

- 前端具备独立、可测试的 Project 状态和移动交互，不依赖侧栏组件内部复制业务逻辑。

### 执行结果

- 前端正式增加 `Project`、`ProjectsData`、nullable `Session.project_id`、创建 Session 与 organization 的 Project 参数类型。
- 新增 `projectApi`，仅暴露 list/create/rename/delete 四个单层 Project 接口；未引入层级、上下文或额外依赖。
- 新增 `useProjectsStore`，完成稳定的创建时间倒序、loading/error/retry、CRUD 原子替换和用户切换所需的 `clear`。
- Project 删除只有在 API 成功后才移除本地 Project，并通过 `useSessionsStore.unassignProject` 同时清空 active/archived Session 的匹配归属；其他 Session 字段保持不变。
- 新增复用创建/重命名的 `ProjectDialog`：支持 trim、maxlength、Enter、Escape、防重复提交、409 同名提示、失败保留输入和关闭回焦。
- 新增 `MoveSessionProjectDialog`：支持未分组、搜索、当前选中、loading/error/retry、确认/取消、失败保持原归属和关闭回焦；运行状态不参与禁用判断。
- 增加独立 Project Dialog 样式，覆盖暗色变量、长名称省略、滚动、390px 与极窄宽度，不修改全局无关规则。
- 首轮 RED 因 Project API/Store/Dialog 尚不存在及 Sessions Store 缺少 `unassignProject` 失败；实现后所有 Task 4 测试通过。

### 验证证据

```text
RED:
- 首次运行 Task 4 四文件测试：3 个 suite 因缺少 projectApi、Projects Store 和两个 Dialog 无法解析；Sessions Store 用例因 unassignProject 不存在失败，退出 1。

PASS:
- Task 4 精确定向：
  pnpm test:run -- src/stores/projects.spec.ts src/stores/sessions.spec.ts src/components/ProjectDialog.spec.ts src/components/MoveSessionProjectDialog.spec.ts
  4 files passed，18 tests passed，退出 0
- Project + 既有 Session 组件扩大回归：
  pnpm test:run -- src/stores/projects.spec.ts src/stores/sessions.spec.ts src/components/ProjectDialog.spec.ts src/components/MoveSessionProjectDialog.spec.ts src/components/ArchivedSessionsDialog.spec.ts src/components/SessionList.spec.ts src/components/SessionListItem.spec.ts
  7 files passed，27 tests passed，退出 0
- 类型检查：
  pnpm type-check
  vue-tsc -b，退出 0
- Task 4 已跟踪文件 git diff --check：退出 0。
- Task 4 新文件尾随空格检查：无匹配。
- 生成声明边界：
  git diff --exit-code -- src/components.d.ts src/auto-imports.d.ts
  退出 0；类型检查自动扫描产生的声明差异已从本批恢复。
- 依赖边界：
  git diff --exit-code -- package.json pnpm-lock.yaml
  退出 0。
- 范围检查：Task 4 新文件无 parent_id、instructions、memory、knowledge 或 agent 字段。

备注：
- 全工作区 git diff --check 仍仅命中用户已有的 readme.md:3 行尾空格；该文件不属于 Task 4，本任务未修改或清理这项既有改动。
```

## Task 5：实现侧栏 Project 目录、项目内新建与归档显示

状态：completed

### 目标

在现有侧栏中交付可折叠的单层 Project → Session 目录，并打通项目内首次创建、Session 移动和归档恢复体验。

### 涉及文件

- `agentic/web/src/components/navigation/ProjectSections.vue`（新建）
- `agentic/web/src/components/navigation/ProjectSections.spec.ts`（新建）
- `agentic/web/src/components/navigation/SessionSections.vue`
- `agentic/web/src/components/navigation/SidebarPanel.vue`
- `agentic/web/src/components/SessionList.vue`
- `agentic/web/src/components/SessionList.spec.ts`
- `agentic/web/src/components/SessionListItem.vue`
- `agentic/web/src/components/SessionListItem.spec.ts`
- `agentic/web/src/components/ArchivedSessionsDialog.vue`
- `agentic/web/src/components/ArchivedSessionsDialog.spec.ts`
- `agentic/web/src/components/LeftPanel.vue`
- `agentic/web/src/views/HomeView.vue`
- `agentic/web/src/views/HomeView.spec.ts`
- `agentic/web/src/App.vue`（仅 Project Store 生命周期确有需要时调整）
- `agentic/web/src/components/project-directory.css`

### 依赖与接口

- 前置任务：Task 4。
- 输入：Projects Store、Sessions Store、Project/Move Dialog、route query `project`。
- 输出：
  - 一级 Project 目录和固定“未分组”；
  - 项目内新建任务；
  - Session 移动；
  - Project CRUD 入口；
  - 归档项目标签与正确恢复。

### 实施步骤

1. 先增加组件/页面失败测试，固定两层 DOM、无 parent 入口、排序、空项目和未分组行为。
2. 实现 `ProjectSections`：Project 创建时间倒序，Project 内 Session 按置顶/最近消息排序，单一 Session 只渲染一次。
3. 增加可折叠 Project row、数量、空状态、新建任务、重命名和删除菜单；展开状态写入 localStorage。
4. 固定“未分组”目录，展示所有 null project_id Session；不增加第三层日期标题。
5. Session item 菜单增加“移动到项目”，打开 Task 4 Dialog；running/waiting/queued 不禁用。
6. 删除 Project 前强确认“任务将移到未分组且不会删除”，成功后更新 Project 与 active/archived Session Stores。
7. Project 列表加载失败时仍展示全部 Session 的安全列表并提供重试；未知 Project ID 不得导致 Session 消失。
8. 从 Project 新建时导航到 `/?project=<id>`；首页显示可清除的目标 Project 提示。
9. HomeView 发送首条消息时携带 project_id，仍在发送时才创建 Session；失效 Project 失败时保留输入并允许取消后重试。
10. 已归档 Dialog 显示可解析的 Project 名称；恢复后 Session 返回原目录，Project 删除后归入未分组。
11. 验证 Session 归档、重命名、置顶、删除和打开路由行为保持；Pin 只影响目录内排序。
12. 完成桌面 224/272/384px 侧栏、移动端 390px、暗色、长名称、Tab/Enter/Escape、菜单/Dialog 回焦和无横向溢出。

### 验证方式

- 运行：`pnpm test:run -- src/components/navigation/ProjectSections.spec.ts src/components/SessionList.spec.ts src/components/SessionListItem.spec.ts src/components/ArchivedSessionsDialog.spec.ts src/views/HomeView.spec.ts src/stores/projects.spec.ts src/stores/sessions.spec.ts`
- 运行：`pnpm type-check`
- 运行：`git diff --check`
- 预期：退出 0；两层目录、CRUD、移动、项目内创建、归档恢复、错误降级、响应式和现有 Session 操作回归通过。

### 完成条件

- 用户能在侧栏完成 Project 和 Session 目录管理，且首次创建、归档、运行状态与移动行为符合设计。

### 执行结果

- 新增 `ProjectSections`，在侧栏交付 Project → Session 两层目录和固定“未分组”；Project 按创建时间倒序，目录内 Session 复用 Store 的置顶/最近消息排序，同一 Session 只进入一个目录。
- Project row 支持折叠、数量、空状态、项目内新建、重命名和删除；展开状态只写入 `agentic.projects.expanded`，加载后会忽略不存在的 Project key，新创建 Project 自动展开。
- Project 删除使用强确认，明确“任务将移到未分组且不会删除”；成功后复用 Task 4 Store 同步 active/archived Session，失败不提前修改本地目录。
- `SessionList` 增加可复用的扁平 items 模式；Project 目录不出现“今天/昨天”等第三层日期分组，并继续复用现有重命名、置顶、归档、删除和打开逻辑。
- Session item 菜单增加“移动到项目”；running、waiting 和存在 next-message 的 Session 不禁用移动，移动 Dialog 成功后由 Store 原子换位。
- Projects loading/error 时侧栏切到包含全部 active Session 的安全列表并提供重试，不修改未知 `project_id`；加载完成后未知 Project ID Session 仍可见于“未分组”。
- 首页读取 `?project=<id>`，显示可清除的目标项目提示；只有发送首条消息时才创建 Session 并携带 `project_id`，失效 Project 失败后恢复输入可用状态且 query 保留供清除重试。
- 已归档任务显示可解析的 Project 名称；Project 缺失时显示“未分组”，恢复继续使用服务端保留的归属。
- App 在认证用户建立或切换时加载 Projects Store，退出时清理，避免跨用户残留；移动 Dialog 仅在尚未加载时请求 Project，避免侧栏闪回 loading。
- `project-directory.css` 增加长名称省略、暗色变量、目录滚动、390px 移动端和 224px 侧栏容器查询；未修改依赖或全局无关规则。
- 首轮 RED 因 `ProjectSections`、扁平 SessionList、move、首页 Project query 和归档标签尚不存在而失败；实现后定向、扩大和全量回归全部通过。

### 验证证据

```text
RED:
- 首次运行 Task 5 定向测试：ProjectSections 无法解析；SessionList flat、Session item move、Home Project target 和 archived Project label 用例失败，退出 1。

PASS:
- Task 5 计划定向：
  pnpm test:run -- src/components/navigation/ProjectSections.spec.ts src/components/SessionList.spec.ts src/components/SessionListItem.spec.ts src/components/ArchivedSessionsDialog.spec.ts src/views/HomeView.spec.ts src/stores/projects.spec.ts src/stores/sessions.spec.ts
  7 files passed，28 tests passed，退出 0
- Project/Dialog 扩大回归：
  pnpm test:run -- src/components/navigation/ProjectSections.spec.ts src/components/SessionList.spec.ts src/components/SessionListItem.spec.ts src/components/ArchivedSessionsDialog.spec.ts src/views/HomeView.spec.ts src/stores/projects.spec.ts src/stores/sessions.spec.ts src/components/MoveSessionProjectDialog.spec.ts src/components/ProjectDialog.spec.ts
  9 files passed，37 tests passed，退出 0
- 前端全量：
  pnpm test:run
  43 files passed，172 tests passed，退出 0
- 最新类型检查：
  pnpm type-check
  vue-tsc -b，退出 0
- 生产构建：
  pnpm build-only
  vite build，3678 modules transformed，退出 0
- Task 5 已跟踪文件 git diff --check：退出 0。
- Task 5 全部文件尾随空格检查：无匹配。
- 生成声明与依赖边界：
  git diff --exit-code -- agentic/web/src/components.d.ts agentic/web/src/auto-imports.d.ts agentic/web/package.json agentic/web/pnpm-lock.yaml
  退出 0；测试/构建扫描产生的声明差异已恢复。
- 范围检查：Task 5 文件无 parent_id、Project instructions/memory/knowledge 或其他上下文注入字段。

备注：
- 全工作区 git diff --check 仍仅命中用户已有的 readme.md:3 行尾空格；该文件不属于 Task 5，本任务未修改或清理这项既有改动。
- 真实浏览器的 CRUD、移动、归档恢复、响应式、键盘和焦点页面验收按计划留在 Task 6 最终门禁执行。
```

## Task 6：完成迁移、全量回归、页面验收和代码审查

状态：blocked

### 目标

用最新数据库、后端、前端、页面和审查证据确认 Project 目录满足设计，且不影响 Session 执行、归档、分支、搜索和安全边界。

### 涉及文件

- 本计划涉及的全部代码与测试
- `agentic/docs/designs/session-project-directory.zh-CN.md`
- `agentic/docs/librechat-ui-redesign.zh-CN.md`
- `agentic/docs/reviews/session-project-directory-review.md`（新建）
- `agentic/docs/plans/session-project-directory-plan.md`

### 依赖与接口

- 前置任务：Task 1–5。
- 输入：相对实施基线 `c8ab3c4` 的完整变更集、设计验收标准和迁移 head。
- 输出：最新验证证据、用户页面验收清单、分级代码审查和 `READY_TO_MERGE / BLOCKED / FAILED`。

### 实施步骤

1. 运行 Project Repository/Service/Route、Session organization/branching 和前端 Project/Session 定向测试。
2. 运行后端全量测试与 Ruff。
3. 在可恢复测试数据库执行 migration upgrade、downgrade 到前一 revision、再次 upgrade，并核对 projects、project_id、FK、索引和历史 Session。
4. 运行 `alembic heads/current`，确认唯一 head 且数据库位于最新 revision。
5. 运行前端全量测试、类型检查和生产构建。
6. 检查相对基线无依赖、lockfile、Project Prompt/Memory/Knowledge/Agent/文件自动注入和层级字段。
7. 页面验收 Project 创建、同名、重命名、删除、空项目、折叠和浏览器刷新后的折叠状态。
8. 验收 Session 移入/移出/项目间移动、running/waiting/queued 移动、置顶目录内排序和单实例渲染。
9. 验收项目内首次创建无空 Session、失效 Project 保留输入、普通新任务仍未分组。
10. 验收归档保留项目、恢复、Project 删除后的 active/archived Session 未分组，以及 fork/edit/regenerate 继承后可独立移动。
11. 验收跨用户 404、Project 列表失败安全降级、SSE/REST 最终一致和 Project 删除竞态。
12. 验收桌面、224/272/384px、390px、暗色、长名称、键盘、焦点和无横向溢出。
13. 按 blocking/major/minor/suggestion 完成代码审查；修复后重跑受影响门禁。
14. 将实际范围、迁移证据、页面验收、限制和最终状态写回计划、审查与路线文档。

### 验证方式

- 后端定向：`uv run pytest tests/app/repositories/test_db_project_repository.py tests/app/services/test_project_service.py tests/app/interfaces/endpoints/test_project_routes.py tests/app/repositories/test_db_session_organization.py tests/app/repositories/test_db_session_branching.py tests/app/services/test_session_organization.py tests/app/services/test_session_branching.py tests/app/interfaces/endpoints/test_session_organization_route.py tests/app/interfaces/endpoints/test_session_branching_route.py -q`
- 后端全量：`uv run pytest -q`
- 后端静态：`uv run ruff check app tests`
- 迁移：`uv run alembic heads`、`uv run alembic current`、真实测试数据库 upgrade/downgrade/upgrade。
- 前端定向：`pnpm test:run -- src/stores/projects.spec.ts src/stores/sessions.spec.ts src/components/ProjectDialog.spec.ts src/components/MoveSessionProjectDialog.spec.ts src/components/navigation/ProjectSections.spec.ts src/components/SessionList.spec.ts src/components/SessionListItem.spec.ts src/components/ArchivedSessionsDialog.spec.ts src/views/HomeView.spec.ts`
- 前端全量：`pnpm test:run`
- 类型：`pnpm type-check`
- 构建：`pnpm build`
- 静态：`git diff --check`
- 变更边界：`git diff c8ab3c4 --stat`
- 依赖边界：`git diff --exit-code c8ab3c4 -- agentic/api/pyproject.toml agentic/api/uv.lock agentic/web/package.json agentic/web/pnpm-lock.yaml`
- 生成声明：`git diff --exit-code c8ab3c4 -- agentic/web/src/components.d.ts agentic/web/src/auto-imports.d.ts`
- 手工：真实浏览器 Project/Session/归档/分支/运行状态/响应式/键盘检查。

### 完成条件

- 迁移升降级、后端/前端全量、类型、构建、静态、范围、安全、页面和审查全部通过；无未处理 blocking/major；所有设计验收项有证据。

### 执行结果

- 后端/前端定向、全量、类型和生产构建通过。
- 在隔离 PostgreSQL 数据库完成 `20260724_0002 → 20260726_0001 → 20260724_0002 → 20260726_0001`，核对表、列、`SET NULL`、索引、无 `parent_id` 和历史 Session 无损；临时数据库已删除。
- 本地开发数据库已向前升级到唯一 head `20260726_0001`。
- 真实运行 API 使用一次性账号完成 Project 名称 trim、大小写同名 409、Session 项目内创建、移出/移回、归档/恢复和删除 Project 后归零；测试 Session、Project 和账号均已清理。
- 代码审查发现一个 Project 删除与 Session 归属写入竞态；已增加 `FOR SHARE` 并补充 SQL 回归断言，审查结论为 `APPROVED`。
- 当前浏览器运行时没有可用实例，无法完成真实页面视觉、键盘、焦点和响应式门禁。
- 全仓 Ruff 仍有两个本批未修改的既有未使用导入；全仓 `git diff --check` 仍只报用户既有 `readme.md:3` 尾空格。本批 Ruff 和 Project 范围静态检查通过。

### 验证证据

```text
后端定向：72 passed, 10 warnings
后端全量：303 passed, 10 warnings
本批 Ruff：All checks passed
全仓 Ruff：2 个既有 F401（非本批文件）
前端定向：9 files / 37 tests passed
前端全量：43 files / 172 tests passed
类型：pnpm type-check passed
构建：pnpm build passed；3678 modules transformed
Alembic：heads/current 均为 20260726_0001 (head)
迁移：隔离 PostgreSQL upgrade/downgrade/upgrade passed
依赖/lockfile：无差异
生成声明：无差异
真实 API：7/7 检查为 true，重复名称返回 409
代码审查：APPROVED；唯一 major 已修复
浏览器：browser list = []，页面验收未执行
全仓 diff check：仅 readme.md:3 trailing whitespace（既有、本批外）
```

## 计划变更

| 日期 | 变更内容 | 原因 | 影响任务 | 是否影响设计 |
| --- | --- | --- | --- | --- |
| 2026-07-26 | 初始计划 | 将数据模型、Project CRUD、Session 归属、前端基础、侧栏集成和最终门禁拆为六项 | Task 1–6 | 否 |

## 最终验证

### 执行命令

```powershell
# agentic/api
uv run pytest -q
uv run ruff check app tests
uv run alembic heads
uv run alembic current

# agentic/web
pnpm test:run
pnpm type-check
pnpm build

# D:\AI\Think-Agentic
git diff --check
git status --short
git diff c8ab3c4 --stat
git diff --exit-code c8ab3c4 -- agentic/api/pyproject.toml agentic/api/uv.lock agentic/web/package.json agentic/web/pnpm-lock.yaml
git diff --exit-code c8ab3c4 -- agentic/web/src/components.d.ts agentic/web/src/auto-imports.d.ts
```

### 执行结果

- 单元测试：后端定向 72、前端定向 37，通过。
- 集成测试：后端全量 303、前端全量 172，通过；真实 API 7/7，通过。
- 静态检查：本批 Ruff 和 Project 范围 diff check 通过；全仓门禁被三个本批外/环境项阻塞。
- 类型检查：通过。
- 构建：通过，3678 modules transformed。
- 数据库迁移：唯一 head/current、隔离库升降级和历史数据核对通过。
- 手工验证：真实 API 已执行；真实浏览器页面未执行。
- 代码审查：`APPROVED`，审查中唯一 major 已修复并复验。

### 验收标准检查

- [x] Project 创建、重命名、删除和大小写不敏感唯一性正确。
- [x] 前后端均无 parent_id、递归目录或子 Project 入口。
- [x] 历史 Session 迁移后全部未分组，消息、文件、Trace、Memory 和运行状态不变。
- [x] Session 可移入自有 Project、项目间移动和移回未分组。
- [x] 跨用户 Project/Session 统一 404，无法探测或建立错误归属。
- [x] Project 删除保留 active/archived Session 并清空归属。
- [x] running、waiting、next-message Session 可移动且执行不受影响。
- [x] 移动不改变 Session 时间、状态、未读、置顶、事件或队列字段。
- [x] 归档保留 Project，恢复返回原目录；已删除 Project 时回到未分组。
- [x] fork/edit/regenerate 继承来源 Project，之后可独立移动。
- [x] 侧栏只有 Project → Session 两层，空 Project 可见，未分组固定存在。
- [x] Project 内置顶/最近消息排序正确，同一 Session 不重复显示。
- [x] 项目内首次发送才创建 Session，普通新任务仍默认未分组。
- [x] 失效 Project 创建失败时用户输入保留并可取消归属重试。
- [x] Project loading/error/retry 不隐藏 Session，REST/SSE 最终一致。
- [x] 移动 Dialog 支持搜索、当前选中、确认/取消、键盘和回焦。
- [x] 归档 Dialog 显示 Project 归属并正确恢复。
- [ ] 桌面、可调侧栏、390px、暗色、长名称和键盘通过。
- [x] 没有 Project Prompt、Memory、Knowledge、文件自动注入、Agent 配置、协作、嵌套或拖拽排序。
- [ ] 后端全量、Ruff、迁移升降级、前端全量、类型、构建和代码审查通过。

### 未通过项目

- 当前会话浏览器列表为空，无法完成真实页面的桌面、224/272/384/390px、暗色、长名称、键盘和焦点验收。
- `uv run ruff check app tests` 被两个本批未修改文件的既有 F401 阻挡；本批 Ruff 已通过。
- `git diff --check` 被用户既有 `readme.md:3` 尾空格阻挡；Project 范围检查已通过。

### 最终状态

`BLOCKED`

代码、自动化、迁移、真实 API 和审查均已完成；需要可用浏览器实例完成页面验收，并由用户决定是否允许顺手清理两个既有 Ruff 导入和 `readme.md:3` 尾空格，之后才能复验并标记 `READY_TO_MERGE`。
