# Session 单层项目目录管理

## 文档状态

- 状态：`DESIGN_READY`
- 负责人：Codex
- 创建日期：2026-07-26
- 最近更新：2026-07-26
- 关联路线：第三组大型能力中的 Project 首期

## 背景

Agentic 已支持 Session 重命名、置顶、归档、恢复、删除、全局搜索和分支版本，但所有未归档 Session 仍处于同一个时间分组列表。随着长期使用，同一业务、代码库或目标下的多个 Session 无法形成稳定目录，用户只能依靠标题和搜索回忆关联关系。

本批将 Project 明确定位为“Session 的单层目录”：

- Project 是用户拥有的一级目录；
- Session 最多属于一个 Project，也可以未分组；
- Project 不包含子 Project，不形成递归目录；
- Project 不向模型隐式注入记忆、Prompt、文件或其他对话；
- Project 不改变 Agent、Planner、运行时、Trace 或消息上下文。

这是组织能力，不是上下文或知识能力。未来若 Planner 需要读取项目历史，应通过独立、可观察的项目检索能力设计，不复用本批目录字段实现隐藏 Prompt 注入。

## 目标

- 用户可以创建、重命名和删除单层 Project。
- 用户可以把现有 Session 移入 Project、在 Project 之间移动或移回“未分组”。
- 侧栏按 Project 折叠展示未归档 Session，并保留一个“未分组”目录。
- 用户可以从某个 Project 中发起新任务，新 Session 在真正创建时直接归属该 Project。
- Project 删除只解除 Session 归属，不删除、归档或停止任何 Session。
- Session 归档时保留 Project，恢复后回到原 Project。
- 新建对话分支默认继承来源 Session 的 Project；后续仍可单独移动。
- Project 和 Session 归属严格按当前用户隔离。
- 不改变现有 Session 消息、运行、审批、队列、文件、Trace、Memory 和分支协议。

## 功能范围

### Project 管理

- 创建 Project。
- 重命名 Project。
- 删除 Project。
- Project 名称去除首尾空白，长度 1–100，当前用户内不区分大小写唯一。
- Project 按创建时间倒序稳定展示。
- Project 无归档、层级、排序权重或拖拽排序。

### Session 归属

- Session 新增可空的 `project_id`。
- 通过现有 Session organization 更新接口移动或取消归属。
- 首页支持可选 Project 创建上下文；只有用户发送第一条消息、真正创建 Session 时才写入归属。
- 运行中、等待交互或存在下一条消息的 Session 也可以移动 Project，因为它只改变导航元数据。
- 归档、恢复、置顶、重命名和项目移动相互独立。
- 分支创建时复制来源 Session 当时的 `project_id`。

### 侧栏交互

- “任务历史”区域增加“项目”标题和创建入口。
- 每个 Project 显示文件夹图标、名称、未归档 Session 数量、展开/折叠按钮和操作菜单。
- Project 操作菜单包含：
  - 在此项目中新建任务；
  - 重命名；
  - 删除。
- Project 内直接显示 Session item，不再增加“今天/昨天”等第三层时间标题。
- Project 内 Session 保持现有排序：置顶优先，其次最近消息时间。
- “未分组”作为固定一级目录，展示 `project_id = null` 的 Session。
- Project 展开状态只保存在当前浏览器本地，不进入后端业务数据。
- Session 操作菜单新增“移动到项目”，通过可搜索/可键盘操作的 Dialog 选择目标 Project 或“未分组”。
- 空 Project 仍可见，并显示空状态与“新建任务”入口。

### 归档与分支

- 归档 Session 保留 `project_id`。
- 已归档任务 Dialog 可显示 Project 名称；恢复后自动回到原 Project。
- Project 被删除后，其中未归档和已归档 Session 均变为未分组。
- 新建 fork/edit/regenerate 分支继承来源 Project，但每个分支仍是可独立移动的 Session。

## 非功能范围

- 不实现子 Project、嵌套目录或无限层级。
- 不实现项目详情页、独立 `/projects/:id` 工作台或项目 Dashboard。
- 不实现 Project instructions、项目 Prompt 或 System Prompt 覆盖。
- 不实现跨 Session 记忆、自动历史总结或隐式上下文注入。
- 不实现项目 Knowledge、向量索引、RAG 或引用。
- 不把 Project 文件自动加入 Session；文件中心和附件行为保持不变。
- 不实现成员、分享、协作、角色或项目权限。
- 不实现项目级 Agent、模型、Skills、Tools、MCP 或审批配置。
- 不实现项目标签、收藏、颜色、图标自定义、拖拽移动或手工排序。
- 不实现 Project 归档、回收站或删除恢复。
- 不改变全局搜索范围和结果协议；搜索仍以 Session、消息、Tool、Trace 和文件为主体。
- 不改变 Session URL；继续使用 `/sessions/:id`。

## 业务流程

### 创建 Project

1. 用户点击侧栏“项目”标题旁的新增按钮。
2. Dialog 输入名称并提交。
3. 服务端校验名称和当前用户内唯一性。
4. 创建成功后 Project 出现在列表顶部并自动展开。
5. 创建失败时 Dialog 保持输入并显示可重试错误。

### 从 Project 新建任务

1. 用户在 Project 菜单或空状态中选择“新建任务”。
2. 前端进入首页，并通过 URL query 保存目标 `project_id`，不立即创建空 Session。
3. 首页显示“将创建在「Project 名称」”的可移除提示。
4. 用户发送第一条消息时，`POST /sessions` 携带 `project_id`。
5. 服务端确认 Project 属于当前用户后创建 Session。
6. 创建成功后进入现有 `/sessions/:id?init=...` 流程；消息和运行逻辑不变。
7. Project 已被删除或无权访问时创建失败，首页保留输入并允许取消 Project 后重试。

### 移动现有 Session

1. 用户在 Session 菜单选择“移动到项目”。
2. Dialog 显示当前用户 Project 和“未分组”，当前目标标记为已选。
3. 用户选择目标并确认。
4. `PATCH /sessions/{session_id}` 提交 `project_id: string | null`。
5. 服务端在同一事务中校验 Session 与 Project 都属于当前用户并更新归属。
6. Store 原子替换 Session；侧栏立即将它移动到目标目录。
7. 失败时 Session 保持原位置，并显示稳定错误。

### 删除 Project

1. 用户从 Project 菜单选择删除。
2. 确认框明确说明“不会删除任务，项目内任务将移到未分组”。
3. 服务端只允许所有者删除 Project。
4. 数据库通过外键 `ON DELETE SET NULL` 清空关联 Session 的 `project_id`。
5. 前端移除 Project，并立即把本地关联 Session 归入“未分组”。
6. running、waiting、queued、archived Session 的运行和内容均不改变。

### 归档与恢复

1. 用户归档某个 Project 内 Session。
2. Session 从活动侧栏移除，但 `project_id` 保留。
3. 已归档 Dialog 可显示其 Project 名称。
4. 恢复后 Session 重新出现在原 Project；若 Project 已删除，则出现在“未分组”。

## 核心规则

1. Project 只有一级；Project 不得拥有 `parent_id`，API 不接受层级字段。
2. 一个 Session 最多属于一个 Project；`project_id = null` 表示未分组。
3. Project 和 Session 必须属于同一用户；跨用户 Project ID 统一返回 404，不能泄漏存在性。
4. Project 名称 trim 后长度为 1–100；同一用户内按小写比较唯一。
5. 删除 Project 永远不删除、归档、停止或重启 Session，只清空归属。
6. Project 移动是导航元数据更新，不修改 Session `updated_at`、`latest_message_at`、运行状态或未读数。
7. running、waiting 和存在 next-message 的 Session 允许移动 Project。
8. 归档保留归属；恢复不重新推断 Project。
9. 新分支继承创建时来源 Session 的 Project；移动某个分支不联动整个 branch family。
10. 置顶只在所属 Project 或“未分组”目录内影响排序，不把 Session 跨目录提到全局顶部。
11. Project 展开状态属于浏览器 UI 偏好，不是跨设备业务数据。
12. 首页 Project query 只能作为创建请求提示，最终权限必须由服务端重新校验。
13. Project 不参与 Agent Memory、Planner Prompt、Skill 选择、文件附件或 Tool 注册。
14. Session SSE 必须携带最新 `project_id`，项目移动或删除后最终与 REST 一致。
15. Project CRUD 和 Session 移动不得创建 shell、沙箱或工具审批。

## 现有实现分析

### 相关代码与文档

- `agentic/api/app/core/entities/session.py`
  - Session 领域模型已有标题、置顶、归档、next-message、分支和运行状态；
  - 当前无目录归属。
- `agentic/api/app/models/session.py`
  - Session ORM 已有用户隔离和导航排序索引；
  - 可新增 nullable `project_id`，不触碰 JSONB 事件、文件和 Memory。
- `agentic/api/app/repositories/db_session_repository.py`
  - `update_organization` 已使用行锁原子更新导航元数据并避免改写 `updated_at`；
  - `create_branch` 已集中构造分支 Session，适合复制 `project_id`。
- `agentic/api/app/services/session_service.py`
  - 已稳定映射 organization 的 404/409；
  - `create_session` 可扩展可选 Project 校验。
- `agentic/api/app/controllers/session.py`
  - REST 和 SSE 共用轻量 Session 列表项；
  - PATCH organization 可扩展显式 nullable `project_id`。
- `agentic/web/src/stores/sessions.ts`
  - 已处理 REST/SSE、active/archived 双列表和原子 organization 替换。
- `agentic/web/src/components/SessionList.vue`
  - 已集中处理重命名、置顶、归档和删除；
  - 当前按置顶与时间分组。
- `agentic/web/src/components/SessionListItem.vue`
  - 已有键盘可用操作菜单，适合新增移动入口。
- `agentic/web/src/components/navigation/SidebarPanel.vue`
  - 已有任务历史区、全局新建任务和搜索入口。
- `agentic/web/src/views/HomeView.vue`
  - 当前只在首次发送时创建 Session，不产生空任务；
  - 可通过可选 query 传递 Project 创建上下文。
- `agentic/docs/designs/chat-session-organization.zh-CN.md`
  - 定义了归档、置顶、运行状态和 Session 用户隔离边界，本批必须兼容。

### 可复用能力

- Session organization 的 row lock、权限和稳定错误映射。
- active/archived 双列表与 SSE 最终一致性。
- Session item 操作菜单、确认框、Toast 和焦点模式。
- 首页“首次发送才创建 Session”的无空记录行为。
- 归档恢复和分支测试基础。
- 现有 Alembic 单 head 迁移链。
- Pinia Store 和 390px/暗色侧栏样式体系。

### 当前约束

- `POST /sessions` 当前没有请求 schema，前端默认发送 `{}`。
- `UpdateSessionOrganizationRequest` 当前禁止显式 null；取消 Project 需要只对 `project_id` 允许 null。
- Project 是新的用户拥有实体，需要 Repository、UOW、Service、Controller 和前端 Store。
- Session SSE 只推 active Session；Project 列表需独立 REST 加载。
- 现有 pinned 分组是全局的；改为 Project 后必须明确其目录内语义。
- 当前分支创建未复制目录元数据，需要显式补齐。
- 现有历史数据全部没有 Project，迁移后必须自然落入“未分组”。

## 可选方案

### 方案 A：直接在 Session 存储 `project_name`

- 实现方式：
  - Session 增加可空文本 `project_name`；
  - 前端按字符串分组；
  - 重命名 Project 时批量更新所有 Session。
- 优点：
  - 数据表和 API 改动少；
  - 不需要 Project Repository。
- 缺点：
  - 空 Project 无法存在；
  - 重命名需要批量更新，容易与 SSE/并发移动冲突；
  - 无法可靠表达 Project 身份、唯一性和删除；
  - 后续任何项目元数据都会再次迁移。
- 风险：
  - 同名、大小写、部分更新和历史脏数据导致目录分裂。

### 方案 B：独立 Project 表 + Session 可空外键

- 实现方式：
  - 新建用户拥有的 `projects` 表；
  - `sessions.project_id` nullable FK，删除 Project 时 `SET NULL`；
  - Project 独立 CRUD，Session organization 原子移动。
- 优点：
  - Project 身份稳定；
  - 支持空 Project、可靠重命名和删除；
  - 历史 Session 无需回填；
  - 所有权、唯一性和回滚边界清晰；
  - 不引入层级或通用目录抽象。
- 缺点：
  - 需要数据库迁移、后端完整分层和前端 Store；
  - 需处理跨用户 Project 校验与多个列表一致性。
- 风险：
  - 若只依赖外键而遗漏业务所有权校验，可能产生跨用户归属。

### 方案 C：用户配置 JSON 保存 Project 与 Session ID

- 实现方式：
  - 在用户配置中保存 Project 数组及其 Session ID；
  - Session 表不新增字段。
- 优点：
  - 不修改 Session 表；
  - UI 原型实现快。
- 缺点：
  - Session 删除、归档、分支和 SSE 都需同步 JSON；
  - 并发更新容易覆盖；
  - 无法使用数据库外键保证一致性；
  - 权限、查询和迁移复杂度会迅速上升。
- 风险：
  - 目录与真实 Session 状态长期漂移。

## 方案对比

| 维度 | 方案 A：Session 文本 | 方案 B：Project 表 + FK | 方案 C：配置 JSON |
| --- | --- | --- | --- |
| 实现复杂度 | 低～中 | 中～高 | 中 |
| 维护成本 | 高，重命名和扩展困难 | 中，实体边界清晰 | 高，需手工同步 |
| 空 Project | 不支持 | 支持 | 支持 |
| 数据一致性 | 弱 | 强 | 弱 |
| 用户隔离 | 依赖字符串约定 | Repository/Service 明确校验 | 容易遗漏 |
| SSE 兼容 | 字段直出但重命名批量变化 | Session 只传稳定 ID | JSON 与 Session 流分离 |
| 测试难度 | 中 | 中～高 | 高 |
| 回滚 | 简单但数据语义弱 | 明确、无历史回填 | 配置清理复杂 |
| 主要风险 | 目录分裂和批量更新 | 跨用户归属校验 | 并发覆盖和状态漂移 |

## 推荐方案

选择方案 B：独立 Project 表 + Session 可空外键。

这是满足“单层项目目录”所需的最小可靠模型。它支持空目录、稳定重命名、删除后安全回到未分组，并能复用现有 Session organization 原子更新。它不会因为使用独立表就扩张成项目平台：表中只保存 ID、用户、名称和时间，不包含 instructions、memory、files、agent 或层级字段。

不选择方案 A，因为 Project 一旦需要空目录和重命名就必须拥有稳定身份；不选择方案 C，因为它会绕过现有数据库一致性与 SSE 边界。

## 数据结构

### `Project`

| 字段 | 类型 | 必填 | 说明 | 约束/默认值 |
| --- | --- | --- | --- | --- |
| `id` | `varchar(255)` | 是 | Project ID | UUID，主键 |
| `user_id` | `varchar(255)` | 是 | 所有者 | 与认证用户一致 |
| `name` | `varchar(100)` | 是 | 目录名称 | trim 后 1–100 |
| `created_at` | `datetime` | 是 | 创建时间 | 服务端生成 |
| `updated_at` | `datetime` | 是 | 最近重命名时间 | 服务端生成/更新 |

索引与约束：

- 主键：`pk_projects_id`
- 当前用户内大小写不敏感唯一：`ux_projects_user_lower_name`
- 列表索引：`ix_projects_user_created_at`
- 不包含 `parent_id`、`sort_order`、instructions 或其他扩展字段。

### `Session.project_id`

| 字段 | 类型 | 必填 | 说明 | 约束/默认值 |
| --- | --- | --- | --- | --- |
| `project_id` | `varchar(255)` | 否 | 所属 Project | 默认 null；FK `projects.id ON DELETE SET NULL` |

索引：

- `ix_sessions_user_project_id`：支持用户内归属与测试查询。

领域、列表和详情响应均增加 `project_id: Optional[str]`。

## 接口设计

### `GET /projects`

- 输入：无。
- 输出：当前用户全部 Project，按 `created_at DESC`。
- 权限：只返回当前用户 Project。
- 兼容性：新接口，不影响现有客户端。

### `POST /projects`

- 输入：`{ "name": string }`。
- 输出：创建后的 Project。
- 权限：绑定当前用户，不接受 `user_id`。
- 幂等/并发：同一用户大小写不敏感同名返回 409。
- 兼容性：新接口。

### `PATCH /projects/{project_id}`

- 输入：`{ "name": string }`，禁止额外字段和 null。
- 输出：更新后的 Project。
- 权限：非所有者与不存在统一 404。
- 幂等/并发：重命名为当前名称成功；与其他 Project 冲突返回 409。

### `DELETE /projects/{project_id}`

- 输入：Project ID。
- 输出：成功空响应。
- 权限：非所有者与不存在统一 404。
- 幂等/并发：首次删除成功；再次删除为 404。删除事务内由 FK 清空 Session 归属。
- 兼容性：不删除 Session。

### `POST /sessions`

- 新增可选输入：`{ "project_id": string | null }`。
- 省略或 null：创建未分组 Session。
- 非空：服务端校验当前用户拥有该 Project，否则 404。
- 输出和首次消息流程保持不变。

### `PATCH /sessions/{session_id}`

- `UpdateSessionOrganizationRequest` 新增显式可空 `project_id`。
- `project_id: string`：移动到当前用户 Project。
- `project_id: null`：移动到未分组。
- 省略：不改变 Project。
- 与 title/pinned/archived 可同请求提交，但前端首期每次只发一个导航动作。
- 权限：Session 与目标 Project 都必须属于当前用户。
- 并发：沿用 Session row lock；目标 Project 在事务内验证。
- 兼容性：现有请求不受影响。

### Session REST/SSE

- `ListSessionItem`、`GetSessionResponse` 和前端 `Session` 增加 `project_id: string | null`。
- active/archived scope、排序、SSE 重连和消息协议不变。

## 前端状态与组件设计

### `useProjectsStore`

- 状态：`projects`、`loading`、`error`。
- 动作：`load`、`create`、`rename`、`delete`、`clear`。
- Project 删除成功后由调用方或明确 Store 协作把 Session 本地 `project_id` 清空，等待 SSE 再次校准。
- 登录用户变化时清空，避免跨用户残留。

### `useSessionsStore`

- Session 类型增加 `project_id`。
- `updateOrganization` 继续原子替换 active/archived 列表。
- 增加 Project 删除后的本地批量 `unassignProject(projectId)`，只修改 `project_id`，不改变排序字段。

### `ProjectSections`

- 输入 Project 列表、active Session 和当前路由 Session ID。
- 输出 create/rename/delete/create-task/move-session 等用户动作。
- 只建立一级 Project → Session 视觉层级。
- 展开状态使用独立 localStorage key；不存在的 Project key 在加载时忽略。

### `ProjectDialog`

- 复用创建和重命名。
- 名称 trim、maxlength 100、Enter 提交、Escape 取消、错误后保留输入、提交中防重复。
- 关闭后焦点返回触发按钮。

### `MoveSessionProjectDialog`

- 显示“未分组”和所有 Project。
- 支持名称搜索、当前选中、空状态、loading/error/retry。
- 确认前不修改 Session。
- 运行状态不禁用移动。

### `HomeView`

- 读取可选 `route.query.project`。
- 若 Project Store 中存在，显示创建归属提示并在创建 Session 时提交 ID。
- 用户可清除提示，恢复未分组创建。
- Project 不存在时不伪造名称；刷新列表后仍不存在则显示失效提示并允许取消。

## 错误处理与可观测性

- Project 同名：409，前端提示“已存在同名项目”，Dialog 保持打开。
- Project/Session 不存在或跨用户：统一 404，不透露资源是否属于其他用户。
- 移动时 Project 被删除：404，Session 保持原归属；下一次 REST/SSE 以数据库状态为准。
- 删除 Project 时前端请求成功但本地更新失败：立即刷新 Project 和 Session Store。
- Project 列表失败：侧栏仍展示所有 Session 在临时“未分组/项目加载失败”安全状态，不隐藏任务；提供重试。
- Session SSE 先于 Project 列表到达：未知 `project_id` 的 Session 临时进入“项目加载中”，Projects 加载完成后重新分组；不得误写 null。
- Project 名称不写入 Agent Prompt、Memory、Trace payload 或 Tool 参数。
- 日志记录操作类型、user_id、project_id、session_id 和结果，不记录对话内容。
- 可选指标：Project CRUD 失败数、Session move 404/409 数；首期不建设独立监控面板。

## 迁移与回滚

### 迁移

1. 创建 `projects` 表及唯一/列表索引。
2. 向 `sessions` 增加 nullable `project_id`。
3. 增加 FK `projects.id ON DELETE SET NULL` 和用户/Project 索引。
4. 历史 Session 不回填，全部自然显示在“未分组”。
5. 部署后旧前端忽略新增响应字段，仍可正常使用 Session。

### 回滚

1. 回滚前停止创建/移动 Project。
2. 删除 Session Project 索引与外键。
3. 删除 `sessions.project_id`。
4. 删除 `projects` 表。
5. Session、消息、归档、分支、文件和运行数据不受影响；只丢失目录组织信息。

### 计划分支

- 实施阶段使用普通分支 `feature/session-project-directory`。
- 基线为用户已提交并验收的 A1 完成提交 `c8ab3c4`，以及进入分支前已确认保留的路线/设计文档。

## 风险

| 风险 | 可能性 | 影响 | 缓解措施 | 验证方式 |
| --- | --- | --- | --- | --- |
| 把 Session 移入其他用户 Project | 低 | 高 | 事务内同时校验 Session/Project user_id，跨用户统一 404 | Repository/Service 隔离测试 |
| 删除 Project 误删 Session | 低 | 高 | FK 只 `SET NULL`，Service 不调用 Session delete | 迁移与删除集成测试 |
| 归档/恢复丢失 Project | 中 | 中 | organization 更新不清空 project_id，响应始终返回字段 | 归档恢复回归 |
| 分支没有继承 Project | 中 | 中 | `create_branch` 显式复制 source.project_id | fork/edit/regenerate 测试 |
| 移动导航元数据改变任务排序 | 中 | 中 | 沿用 organization 的 `updated_at` 保持逻辑 | 时间字段精确断言 |
| Project 列表失败导致 Session 消失 | 中 | 高 | 失败时安全展示 Session，不把未知归属当删除 | 前端错误状态测试 |
| SSE 与 Project 删除顺序导致短暂重复/丢失 | 中 | 中 | Project 删除后本地 unassign，SSE 最终校准，按 session_id 单实例渲染 | Store 乱序测试 |
| pinned 语义变化引发困惑 | 中 | 低 | 明确为目录内置顶，保留 Pin 图标 | 分组排序测试与页面验收 |
| 首页 query 指向已删除 Project | 中 | 低 | 服务端重新校验，输入保留并允许取消归属重试 | 首页失效 Project 测试 |
| 长名称导致侧栏操作按钮溢出 | 中 | 中 | 单行省略、固定操作区、tooltip | 224px/272px/384px/390px 验收 |
| 项目能力范围膨胀为上下文平台 | 中 | 高 | 模型和 API 明确不含 instructions/memory/files/agent | 变更边界审查 |

## 重要假设

- 用户当前只需要单层 Project 目录，不需要子目录。
- Project 首期核心价值是组织 Session，而不是增强模型上下文。
- Project 删除应保留所有 Session，并将它们移到“未分组”。
- 归档 Session 仍属于原 Project。
- Project 内新分支默认继承 Project，但分支之后可独立移动。
- 运行中 Session 可以安全移动，因为该字段不参与执行。
- Project 首期没有详情页；所有管理入口集中在侧栏。
- Project 名称足以作为首期唯一可编辑元数据，不需要图标、颜色和描述。
- 项目内 Session 使用现有置顶和最近消息排序，不提供手工排序。
- 当前没有影响核心设计的待决策项。

## 待决策项

无。

## 验收标准

- [ ] 用户可以创建名称合法且当前用户内唯一的 Project。
- [ ] 用户可以重命名 Project；同名冲突有明确提示且不丢输入。
- [ ] 用户删除 Project 时确认文案明确，Project 消失而其 active/archived Session 全部保留并变为未分组。
- [ ] Project 不存在 `parent_id` 或任何嵌套入口，前后端都无法创建子 Project。
- [ ] 历史 Session 迁移后全部出现在“未分组”，消息、文件、Trace、Memory 和运行状态不变。
- [ ] 用户可以把 Session 移入任意自有 Project、在 Project 间移动或移回未分组。
- [ ] 跨用户 Project/Session 访问统一返回 404，无法探测或建立跨用户归属。
- [ ] running、waiting 和存在 next-message 的 Session 可以移动且当前执行、审批和排队消息不受影响。
- [ ] 移动 Session 不改变 `updated_at`、`latest_message_at`、状态、未读数或置顶值。
- [ ] 归档 Session 保留 Project，恢复后回到原目录；Project 已删除时恢复到未分组。
- [ ] fork/edit/regenerate 新分支继承来源 Project，之后可独立移动且不联动 family。
- [ ] 侧栏只呈现 Project → Session 两层；Project 可折叠，空 Project 可见，未分组固定存在。
- [ ] Project 内 Session 按置顶优先、最近消息其次排序，同一 Session 不重复渲染。
- [ ] 用户可从 Project 新建任务；发送首条消息前不产生空 Session，创建后直接归属目标 Project。
- [ ] 首页 Project 失效时保留用户输入，允许清除 Project 后重试。
- [ ] Project 列表 loading/error/retry 不会隐藏或删除已有 Session。
- [ ] Session 菜单移动 Dialog 支持搜索、当前选中、确认/取消、键盘和焦点恢复。
- [ ] 已归档 Dialog 能识别保留的 Project 归属，恢复行为正确。
- [ ] 桌面、224–384px 可调侧栏、390px 页面、暗色、长名称和键盘操作通过验收。
- [ ] 不新增 Project Prompt、记忆、Knowledge、文件自动注入、Agent 配置、协作、嵌套或拖拽排序。
- [ ] 后端测试、前端测试、类型检查、生产构建、Alembic 单 head/current、迁移升降级和代码审查通过后才可标记 `READY_TO_MERGE`。
