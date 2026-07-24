# 会话重命名、置顶与归档设计

## 文档状态

- 状态：`DESIGN_READY`
- 负责人：Codex
- 创建日期：2026-07-24
- 最近更新：2026-07-24

## 背景

当前侧栏会话列表已经支持按时间分组、标题/最近消息过滤和永久删除，但“更多操作”只有删除。随着会话分支、下一条消息、Human-in-the-loop 和长期运行任务增多，用户缺少低风险的整理手段，只能保留所有会话或永久删除。

LibreChat 的会话列表提供重命名、置顶、归档和归档恢复，并为重命名提供原位键盘交互，为归档提供独立管理视图。这些模式适合 Agentic，但必须保留 Agentic 的运行状态、queued next-message、分支 lineage 和自动标题语义。

本批次选择“会话整理”，优先于对话导出和 Knowledge 引用：

- 会话整理直接改善每天都使用的侧栏，且现有 Session、列表 SSE、删除确认和设置外壳均可复用。
- 对话导出是低频操作，不能解决会话越来越多后的导航问题。
- Knowledge 引用需要知识库、文档解析、索引、权限和引用数据模型，应作为独立产品阶段设计。

参考：

- `D:/AI/LibreChat/client/src/components/Conversations/ConvoOptions/ConvoOptions.tsx`
- `D:/AI/LibreChat/client/src/components/Conversations/RenameForm.tsx`
- `D:/AI/LibreChat/client/src/components/Nav/SettingsTabs/General/ArchivedChatsModal.tsx`
- `D:/AI/LibreChat/client/src/components/Nav/SettingsTabs/General/ArchivedChatsTable.tsx`

## 目标

- 用户可在侧栏原位重命名自己的 Session，刷新和后续 Agent 运行后标题仍保持。
- 用户可置顶/取消置顶 Session，置顶会话稳定显示在普通时间分组之前。
- 用户可归档已停止的 Session，使其从默认侧栏和默认搜索中隐藏，并可从归档管理弹窗恢复。
- 所有操作保持用户隔离、失败可恢复、键盘可访问，并与现有列表 SSE 一致。

## 功能范围

- Session 新增手工标题标记、置顶状态和归档时间。
- 提供用户隔离的 Session 元数据 PATCH 接口。
- 默认 REST/SSE 列表只返回未归档 Session；REST 可显式查询归档 Session。
- 默认全局搜索排除归档 Session。
- 侧栏会话菜单新增重命名、置顶/取消置顶、归档；保留现有删除。
- 重命名使用原位表单，支持自动聚焦、全选、Enter 保存和 Escape 取消。
- 置顶会话独立成组，普通会话继续按日期分组。
- 新增归档管理弹窗，支持搜索、打开、恢复和永久删除。
- 当前 Session 被归档或删除后返回首页；恢复后立即回到默认侧栏。

## 非功能范围

- 不实现 Project、标签、文件夹、批量操作或拖拽排序。
- 不实现分享、导出、导入或跨用户协作。
- 不实现软删除、回收站或删除恢复。
- 不改变 Session 事件、Memory、Trace、文件和 lineage 内容。
- 不复制 LibreChat React、Recoil、TanStack Query 或组件代码。
- 不增加“恢复自动标题”开关；手工重命名后标题持续由用户控制。
- 不为归档列表单独引入分页框架；第一版沿用当前全量 Session 列表规模。

## 业务流程

### 重命名

1. 用户在会话菜单选择“重命名”。
2. 列表项进入原位编辑，输入框聚焦并选中现有标题。
3. 用户提交非空标题；前端调用元数据 PATCH。
4. 服务端按 Session 所有权更新标题并将 `title_is_manual` 设为 `true`。
5. 前端更新本地列表；后续列表 SSE 返回相同标题。
6. 后续 Agent 产生 TitleEvent 时，自动标题更新因手工标题锁定而跳过。

### 置顶

1. 用户选择“置顶”或“取消置顶”。
2. 前端调用元数据 PATCH，并在成功后更新本地列表。
3. 置顶 Session 进入“已置顶”分组；取消后回到对应日期分组。
4. 置顶只改变导航排序，不改变 `updated_at`、消息顺序或运行状态。

### 归档与恢复

1. 用户对非运行中的 Session 选择“归档”。
2. 服务端锁定所属 Session，确认不处于 `running/waiting` 且没有 next-message。
3. 服务端写入 `archived_at` 并清除置顶；默认列表和默认搜索不再返回该 Session。
4. 若归档的是当前 Session，前端返回首页。
5. 用户打开“已归档任务”弹窗，可搜索、在新标签打开、恢复或永久删除。
6. 恢复清空 `archived_at`；Session 重新出现在默认侧栏，但不会自动恢复置顶。

## 核心规则

1. 所有读写都必须先按 `session_id + user_id` 校验；无权访问与不存在统一返回 404。
2. 手工标题 trim 后长度为 1–100；保存成功后 `title_is_manual=true`。
3. Agent 自动标题只可更新 `title_is_manual=false` 的 Session，不能覆盖用户标题。
4. 已归档 Session 可以直接按 ID 打开详情、查看 lineage、恢复或删除，但不出现在默认侧栏和默认搜索。
5. 已归档 Session 不能置顶；归档动作自动清除置顶。
6. `running`、`waiting` 或存在 next-message 的 Session 不能归档，返回 409；重命名和置顶仍允许。
7. 恢复是幂等操作：已恢复 Session 再次提交 `archived=false` 返回当前状态。
8. 置顶写入不更新时间线业务时间，排序使用 `is_pinned DESC, latest_message_at DESC NULLS LAST, created_at DESC`。
9. PATCH 至少包含一个允许字段；未知字段、空标题和冲突组合返回 422。
10. 当前永久删除行为保持不变，归档不是删除确认的替代品。

## 现有实现分析

### 相关代码与文档

- `agentic/api/app/core/entities/session.py`：Session 领域模型，已有状态、next-message 和 lineage。
- `agentic/api/app/models/session.py`：Session ORM 与领域转换，适合新增标量元数据。
- `agentic/api/app/repositories/db_session_repository.py`：已有 `update_title`、用户列表排序和用户隔离查询。
- `agentic/api/app/services/session_service.py`：已有创建、列表、详情和永久删除服务。
- `agentic/api/app/controllers/session.py`：已有 REST/SSE 列表、详情、分支和删除端点。
- `agentic/api/app/repositories/db_search_repository.py`：默认跨 Session 搜索需增加未归档过滤。
- `agentic/web/src/components/SessionListItem.vue`：已有可访问列表项和更多操作菜单。
- `agentic/web/src/components/SessionList.vue`：已有日期分组、过滤、删除确认和当前项导航。
- `agentic/web/src/stores/sessions.ts`：已有 REST 初始加载、列表 SSE 和本地删除。
- `agentic/web/src/lib/api/session.ts`：已有 Session CRUD 客户端。
- `agentic/docs/librechat-ui-redesign.zh-CN.md`：要求选择性学习会话管理，保留 Agent 运行状态。

### 可复用能力

- Session 所有权查询和现有 404 契约。
- 每 5 秒推送完整列表的 SSE，可作为最终一致性来源。
- Element Plus Dropdown、Dialog、MessageBox 和现有 Toast。
- Sidebar 的搜索、时间分组、移动端关闭和焦点样式。
- 删除确认、当前 Session 删除后返回首页的行为。
- Alembic 可逆迁移和真实 PostgreSQL 测试基础。

### 当前约束

- Agent 每次 Planner run 都可能产生 TitleEvent，直接暴露现有 `update_title` 会覆盖手工标题。
- 当前列表和搜索都没有归档范围概念。
- 当前 Session 表使用标量字段与 JSONB 混合存储；整理元数据应保持为可索引标量。
- 当前列表未分页，归档第一版沿用相同规模，避免本批次引入游标协议。
- 会话分支实现已由用户提交为 `17231e3`；其最终验收计划和审查状态仍在工作区，进入实施前需先单独提交这两份收口文档。

## 可选方案

### 方案 A：仅前端本地偏好

- 实现方式：标题、置顶和隐藏状态保存在 `localStorage`，服务端不变。
- 优点：开发快，不需要迁移。
- 缺点：换设备或清理浏览器后丢失；服务端搜索、SSE 和 lineage 不理解状态；手工标题会被自动标题覆盖。
- 风险：产生多个互相冲突的真相来源，不满足持久化与多端一致性。

### 方案 B：Session 一等元数据与统一 PATCH 接口

- 实现方式：在 `sessions` 增加 `title_is_manual`、`is_pinned`、`archived_at`，服务端统一校验和排序；前端通过 PATCH 操作并由 SSE 校准。
- 优点：领域语义直接、查询高效、用户隔离清晰、可复用现有 Session 事务与列表链路。
- 缺点：需要数据库迁移，并需调整自动标题和搜索过滤。
- 风险：列表、搜索和归档详情若过滤规则不一致会造成“消失”或误暴露。

### 方案 C：独立 Session 偏好表

- 实现方式：新增 `user_session_preferences(session_id, user_id, title, pinned, archived_at)`，查询时关联 Session。
- 优点：偏好与运行记录解耦，未来共享 Session 时可支持每用户不同偏好。
- 缺点：当前 Session 是单用户所有，额外表、关联、清理和一致性逻辑没有即时价值。
- 风险：删除级联、孤儿记录、列表 JOIN 和共享语义会显著提高测试成本。

## 方案对比

| 维度 | 方案 A：本地偏好 | 方案 B：Session 元数据 | 方案 C：偏好表 |
| --- | --- | --- | --- |
| 实现复杂度 | 低 | 中 | 高 |
| 维护成本 | 高，双重真相 | 低，单一真相 | 中高，跨表一致性 |
| 多端兼容 | 差 | 好 | 好 |
| 搜索/列表一致性 | 差 | 好 | 中 |
| 测试难度 | 中 | 中 | 高 |
| 交付成本 | 低 | 中 | 高 |
| 主要风险 | 数据丢失和覆盖 | 过滤边界遗漏 | 过度设计和孤儿数据 |

## 推荐方案

选择方案 B。

Session 当前由单一用户拥有，重命名、置顶和归档都是 Session 的导航元数据。把它们作为 Session 一等字段能保持一个服务端真相来源，并直接复用当前用户隔离、事务、REST/SSE 列表和搜索查询。

不选择方案 A，因为它无法满足刷新、换设备和服务端搜索一致性；不选择方案 C，因为当前没有共享 Session 或每用户不同偏好的需求，引入关联表属于提前设计。

## 数据结构

### Session

| 字段 | 类型 | 必填 | 说明 | 约束/默认值 |
| --- | --- | --- | --- | --- |
| `title_is_manual` | `boolean` | 是 | 标题是否由用户明确设置 | 默认 `false` |
| `is_pinned` | `boolean` | 是 | 是否在默认侧栏置顶 | 默认 `false` |
| `archived_at` | `datetime nullable` | 否 | 归档时间；空表示未归档 | 默认 `null` |

迁移新增默认值以兼容历史 Session；历史标题继续视为自动标题。增加面向用户列表的组合索引，至少覆盖 `user_id`、`archived_at`、`is_pinned` 和最近消息时间。

## 接口设计

### `GET /sessions?scope=active|archived`

- 输入：`scope` 默认 `active`；仅允许 `active` 或 `archived`。
- 输出：沿用现有 `ListSessionResponse`，列表项新增 `is_pinned` 和 `archived_at`。
- 权限：只返回当前用户 Session。
- 排序：active 先置顶后按最近消息；archived 按 `archived_at DESC`。
- 兼容性：不传 scope 的现有客户端继续得到未归档列表。

### `POST /sessions/stream`

- 输入：无变化。
- 输出：只推送 active Session，列表项增加 `is_pinned` 和 `archived_at`。
- 兼容性：新增响应字段向后兼容；归档操作后最多一个轮询周期完成服务端校准。

### `PATCH /sessions/{session_id}`

- 输入：
  - `title?: string`，trim 后 1–100。
  - `pinned?: boolean`。
  - `archived?: boolean`。
  - 至少出现一个字段，不接受未知字段。
- 输出：更新后的 Session 列表项。
- 权限：只允许当前 Session 所有者；无权或不存在统一 404。
- 幂等/并发：仓储按所属 Session 行锁执行；同值重复请求返回当前状态。
- 冲突：
  - 对归档 Session 设置 `pinned=true` 返回 409。
  - 对 running/waiting 或存在 next-message 的 Session 设置 `archived=true` 返回 409。
  - 同一请求同时 `archived=true` 与 `pinned=true` 返回 422。
- 兼容性：新增端点，不改变现有创建、聊天、分支和删除请求。

### 自动标题更新

- Agent 路径改用 `update_generated_title(session_id, title)`。
- 该操作仅在 `title_is_manual=false` 时更新，更新行数为 0 代表手工标题已锁定，不视为运行失败。
- 用户 PATCH title 使用 `update_manual_title`，同时写入 `title_is_manual=true`。

## 错误处理与可观测性

- 404：Session 不存在或不属于当前用户，响应不区分原因。
- 409：Session 正在运行、等待交互、存在 next-message，或归档状态与置顶冲突。
- 422：空标题、超长标题、未知 scope、空 PATCH 或互斥字段组合。
- 500：未预期数据库错误，记录 session_id、user_id、操作字段名和异常，不记录消息、文件内容或事件 JSON。
- 前端失败时保留原状态并显示可行动 Toast；重命名输入不因失败丢失。
- 归档、恢复、置顶和重命名记录结构化 INFO 日志，不新增 Trace 事件，避免把导航偏好混入 Agent 执行审计。

## 迁移与回滚

- 迁移：
  1. 添加三个字段及服务端默认值。
  2. 历史记录自动为 `title_is_manual=false`、`is_pinned=false`、`archived_at=null`。
  3. 创建列表组合索引。
  4. 更新领域/ORM 映射、列表查询、搜索过滤和 API schema。
- 回滚：
  - 前端入口可先移除，旧客户端仍可使用默认 active 列表。
  - Alembic downgrade 删除索引和三个字段；归档/置顶/手工标题标记会丢失，但 Session 内容不受影响。
  - 回滚前应先将所有归档 Session 恢复可见，避免旧版本列表因部署切换出现短时不一致。

## 风险

| 风险 | 可能性 | 影响 | 缓解措施 | 验证方式 |
| --- | --- | --- | --- | --- |
| 自动标题覆盖用户标题 | 中 | 中 | 区分 manual/generated 更新路径 | 连续两次 Agent run 回归测试 |
| 归档运行中 Session 后任务“消失” | 中 | 高 | running/waiting/next-message 409 门禁 | 服务与接口状态测试 |
| 默认搜索仍返回归档内容 | 中 | 中 | 仓储统一 active 条件并加搜索测试 | 搜索集成测试 |
| SSE 延迟使归档项短暂回出现 | 低 | 中 | 成功后先本地更新，SSE 使用服务端同一过滤 | Store/SSE 测试 |
| 并发置顶/归档状态错乱 | 低 | 中 | 用户行锁、原子规则和幂等同值写入 | 并发仓储测试 |
| 归档来源 Session 导航中断 | 低 | 中 | 详情按 ID 仍可读，只有列表/搜索默认过滤 | lineage 详情回归 |
| 大量归档 Session 导致弹窗慢 | 低 | 中 | 沿用当前列表规模并记录后续分页阈值 | 大数据量查询检查 |

## 重要假设

- Session 仍是单用户所有，不需要每用户不同的标题、置顶和归档偏好。
- “归档”表示从默认导航和默认搜索隐藏，不限制直接 URL 访问和 lineage 导航。
- 用户确认的页面表面验收已使上一批会话分支达到 `READY_TO_MERGE`；实现提交为 `17231e3`，本批实施前只需收口并隔离上一批的验收文档。
- 第一版归档管理无需分页，容量边界与当前全量会话列表一致。
- 手工重命名后不自动恢复 Agent 标题，避免不可预测覆盖。

## 待决策项

无。

## 验收标准

- [ ] 用户可从侧栏进入原位重命名；Enter 保存、Escape 取消、空标题不可提交，失败后输入仍保留。
- [ ] 手工标题刷新后仍存在，后续 Agent TitleEvent 不会覆盖。
- [ ] 置顶 Session 显示在“已置顶”组；取消置顶后回到正确日期组，刷新后保持。
- [ ] completed/pending 且无 next-message 的 Session 可归档；running、waiting 或存在 next-message 时返回 409 并保持可见。
- [ ] 归档 Session 从默认 REST/SSE 列表和默认全局搜索消失，但直接详情和 lineage 导航仍可访问。
- [ ] 归档弹窗支持过滤、打开、恢复和永久删除；恢复后默认不置顶并重新进入侧栏。
- [ ] 当前 Session 归档后安全返回首页，其他标签页通过 SSE 最终收敛。
- [ ] 跨用户重命名、置顶、归档、恢复和删除统一 404，不泄露 Session 是否存在。
- [ ] migration upgrade/downgrade/upgrade 成功，历史 Session 默认仍可见且排序稳定。
- [ ] 后端相关回归、前端全量测试、类型检查、生产构建和 `git diff --check` 通过。
