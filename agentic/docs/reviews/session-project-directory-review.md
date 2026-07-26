# Session 单层项目目录管理代码审查

## 审查范围

- 目标分支：实施基线 `c8ab3c4`
- 变更分支：`feature/session-project-directory`
- 变更范围：`c8ab3c4` 到当前工作区，包含尚未跟踪的 Project 新文件
- 设计文档：`agentic/docs/designs/session-project-directory.zh-CN.md`
- 计划文档：`agentic/docs/plans/session-project-directory-plan.md`
- 审查者：同一 Agent 自检
- 审查日期：2026-07-27

## 需求符合度

- [x] 数据库、API、Store 和侧栏只实现 Project → Session 单层目录。
- [x] Project 不进入 Agent、Planner、Prompt、Memory、Knowledge、文件或 Tool 上下文。
- [x] Project CRUD、Session 创建/移动、归档、分支继承及 REST/SSE 字段符合设计。
- [x] 未发现 Project 详情页、协作、拖拽、图标配置或其他范围扩张。
- [x] 计划内代码范围无新增依赖或 lockfile 修改。

## 正确性

- [x] 名称 trim、长度、大小写不敏感唯一性和显式 null/省略语义已覆盖。
- [x] Project 删除只通过 `ON DELETE SET NULL` 解除 active/archived Session 归属。
- [x] Session 移动保留时间、状态、未读、置顶、事件、文件、Memory 和 next-message。
- [x] 归档/恢复保留归属，fork/edit/regenerate 复制来源 Project。
- [x] 审查中发现的 Project 删除竞态已修复并回归。

## 安全性

- [x] Project 列表、读取、重命名、删除和 Session 目标校验均绑定认证用户。
- [x] 不存在与跨用户 Project/Session 使用相同 404。
- [x] 请求禁止额外字段，不接受 `user_id`、`parent_id` 或层级数据。
- [x] 日志只包含操作和 ID，不记录项目内对话内容。
- [x] 本功能不增加 shell、沙箱或工具审批路径。

## 可维护性

- [x] Project 保持最小实体和完整 Repository/UOW/Service/Controller 分层。
- [x] 前端 Project Store、Dialog 和目录组件职责清晰。
- [x] 删除 Project 后 active/archived Session 的本地归属由单一 Store 动作校准。
- [x] 迁移升降级顺序明确，旧客户端可忽略新增 nullable 字段。

## 测试质量

- [x] Repository、Service、Route、Store、Dialog、侧栏、归档和首页均有定向测试。
- [x] 覆盖空值、同名、跨用户、运行/等待/排队、归档、分支和失败安全降级。
- [x] 使用真实 PostgreSQL 完成迁移升→降→升与历史 Session 无损核对。
- [x] 使用真实本地 API 进程完成 Project/Session 端到端冒烟。
- [ ] 当前会话没有可用浏览器实例，视觉、焦点和响应式页面门禁无法自动执行。

## 问题列表

### [major] Project 校验与 Session 写入之间存在删除竞态

位置：`agentic/api/app/repositories/db_project_repository.py:42`

问题：

Session 创建或移动先读取 Project，再写入 `sessions.project_id`。原实现读取时未持有 Project 行锁，另一事务可在两步之间删除 Project，使外键写入抛出未映射的数据库异常。

影响：

极窄竞态下，预期的稳定 404 或 `SET NULL` 最终一致可能变成 500。

处理：

已在用户范围 Project 读取上增加 PostgreSQL `FOR SHARE`，使删除与归属写入按 Project → Session 的一致锁顺序串行；测试明确断言生成 `FOR SHARE`。

状态：已修复。相关后端定向 72 项和本批 Ruff 通过。

## 无法验证项

- 浏览器运行时返回空实例列表，无法执行真实页面 Project CRUD、键盘/焦点、暗色和 224/272/384/390px 视觉验收。
- 仓库全量 Ruff 被本批未修改的两个既有未使用导入阻挡：
  - `tests/app/core/agent/test_interaction_resume.py:2`
  - `tests/app/services/test_agent_interactions.py:1`
- 仓库级 `git diff --check` 被用户既有 `readme.md:3` 尾空格阻挡；Project 范围检查通过。

## 合并门禁

| 门禁 | 结果 | 证据 |
| --- | --- | --- |
| 无 blocking | 通过 | 未发现 blocking |
| 无未处理 major | 通过 | 唯一 major 已修复，定向 72 项通过 |
| 验收标准满足 | 暂未完成 | 缺少真实浏览器页面门禁 |
| 相关测试通过 | 通过 | 后端定向 72、后端全量 303、前端定向 37、前端全量 172 |
| 构建通过 | 通过 | `pnpm type-check` 与 `pnpm build` 通过，3678 modules |
| 数据迁移已验证 | 通过 | 隔离 PostgreSQL 升→降→升、唯一 head/current 和结构/历史数据核对通过 |

## 审查结论

- 结论：`APPROVED`
- 理由：代码层未留下 blocking/major，发现的删除竞态已修复并回归；自动化、迁移和真实 API 路径均通过。
- 剩余风险：同一 Agent 自检不如独立 Reviewer；浏览器视觉门禁尚未执行。
- 下一步：连接可用浏览器完成页面验收，并处理或明确豁免仓库既有 Ruff/尾空格门禁后再标记 `READY_TO_MERGE`。
