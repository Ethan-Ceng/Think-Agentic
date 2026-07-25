# 会话重命名、置顶与归档代码审查

## 审查范围

- 目标分支：`master`
- 变更分支：`feature/chat-session-organization`
- 变更范围：`9fdfeed` 加当前未提交工作区
- 设计文档：`agentic/docs/designs/chat-session-organization.zh-CN.md`
- 计划文档：`agentic/docs/plans/chat-session-organization-plan.md`
- 审查者：同一 Agent 自检
- 审查日期：2026-07-24
- 排除项：根目录 `readme.md` 是用户保存的恢复提示，不属于本功能审查范围，也未被修改。

## 需求符合度

- [x] 符合设计文档和验收标准。
- [x] 没有遗漏重命名、置顶、归档、恢复、永久删除、搜索过滤和直接详情能力。
- [x] 没有引入 Project、标签、批量操作、分享、导入导出等范围外能力。
- [x] 归档详情只读、执行并发门禁和业务更新时间保持等审查整改已记录并验证。

## 正确性

- [x] PATCH 空值、空标题、长度、未知字段和冲突组合有明确校验。
- [x] running、waiting、next-message、归档/置顶冲突和幂等恢复路径有覆盖。
- [x] Run 启动与归档在同一 Session 行锁上串行化，孤儿运行恢复后会重新占用运行态。
- [x] Agent 运行句柄采用目标字段更新，不会用旧 Session 快照覆盖并发重命名、置顶或归档。
- [x] 整理元数据显式保持原 `updated_at`，不会伪造对话内容更新时间。

## 安全性

- [x] 整理、分支、执行、恢复和删除均按 Session 所有权校验。
- [x] 无权访问与不存在统一返回 404，不泄露 Session 是否存在。
- [x] 日志只记录标识和变更字段，不记录消息、文件或事件正文。
- [x] 本功能未增加文件路径、Shell 命令或外部执行入口。

## 可维护性

- [x] 领域、仓储、服务、接口、Store 和组件职责保持分层。
- [x] active/archived scope 和 PATCH 契约向后兼容。
- [x] 迁移具备唯一 head、历史默认值和可逆 downgrade。
- [x] 未引入额外状态库、分页框架或双重客户端真相来源。

## 测试质量

- [x] 后端覆盖用户隔离、排序、标题锁定、归档冲突、执行串行化、搜索过滤和接口错误码。
- [x] 前端覆盖原位重命名、置顶、归档、归档弹窗、失败保留、焦点恢复和归档详情只读。
- [x] 审查发现的顺序、并发和 `updated_at` 问题均先加入失败回归，再实施修复。
- [x] 真实 PostgreSQL 验证迁移往返，并以回滚事务验证整理元数据不改变 `updated_at`。

## 问题列表

未发现未处理问题。

已整改问题：

### [major][已整改] 归档详情仍可启动新执行

位置：`agentic/web/src/components/SessionDetailView.vue:93`、`agentic/api/app/controllers/session.py:339`

问题：直接打开归档 Session 时，页面此前没有归档提示，Composer 和恢复入口仍可触发 Agent Run。

处置：增加归档只读提示和管理入口，禁用 Composer、恢复和分支；服务端在建立 SSE 前返回稳定 409。

### [major][已整改] Run 启动与归档存在检查—执行竞态

位置：`agentic/api/app/repositories/db_session_repository.py:475`、`agentic/api/app/services/agent_service.py:112`

问题：只在 Controller 前置读取归档状态，归档可能在真正创建 Run 前成功，形成隐藏运行任务；旧 Session 快照保存还可能覆盖并发导航元数据。

处置：使用行锁原子确认未归档并占用运行态；孤儿恢复后重新占用；sandbox/task 句柄改为目标字段更新；归档来源分支和 next-message 路径增加仓储门禁。

### [minor][已整改] 相同业务时间的客户端顺序与服务端不一致

位置：`agentic/web/src/stores/sessions.ts:45`

问题：客户端用 Session ID 重排同时间项，可能破坏服务端按 `created_at` 给出的稳定顺序。

处置：相同置顶和消息时间时返回 0，依赖稳定排序保留服务端顺序。

### [minor][已整改] 整理元数据触发业务更新时间

位置：`agentic/api/app/repositories/db_session_repository.py:457`

问题：ORM 的 `updated_at` onupdate 会把置顶等导航操作误算为对话业务更新。

处置：行锁内使用显式 UPDATE 并携带原 `updated_at`；SQL 级测试和真实 PostgreSQL 回滚事务均验证保持不变。

## 无法验证项

- 未使用独立 Reviewer；结论来自同一 Agent 的完整 diff 自检，独立复审仍能进一步降低遗漏风险。
- 未做高并发压力测试；并发正确性依据 PostgreSQL `SELECT ... FOR UPDATE`、状态转换回归和真实数据库语义验证。
- 用户后续验收发现侧栏长文本会把操作区裁出可见范围；CSS 收缩约束和回归测试已补齐，用户在页面复验提示后确认继续。

## 合并门禁

| 门禁 | 结果 | 证据 |
| --- | --- | --- |
| 无 blocking | 通过 | 完整 diff 自检未发现 blocking |
| 无未处理 major | 通过 | 两项 major 均已整改并完成全量回归 |
| 验收标准满足 | 通过 | 原十项验收已通过；用户后续发现的侧栏长文本布局已整改并完成页面复验 |
| 相关测试通过 | 通过 | 后端 172 passed；前端 24 files / 72 tests passed |
| 构建通过 | 通过 | `pnpm type-check` 和 `pnpm build` 通过，3655 modules transformed |
| 数据迁移已验证 | 通过 | 唯一 head/current `20260724_0002`，真实 PostgreSQL downgrade/upgrade 成功 |

## 审查结论

- 结论：`APPROVED`
- 理由：本次侧栏宽度修复范围最小，布局契约、前端全量测试、类型检查和生产构建通过，无未处理 blocking 或 major。
- 剩余风险：同一 Agent 自检和未执行压力测试；不影响当前门禁。
- 下一步：Task 5 已收口；修复已由用户提交至 `master` 的 `24c09e0`。
