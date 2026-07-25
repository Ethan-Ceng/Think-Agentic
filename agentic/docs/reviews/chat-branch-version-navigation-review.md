# 分支版本导航与气泡内编辑代码审查

## 审查范围

- 目标分支：`master`
- 变更分支：`feature/chat-branch-version-navigation`
- 变更范围：`24c09e0..ae7e48a` 加当前未提交 Task 5 文档
- 设计文档：`agentic/docs/designs/chat-branch-version-navigation.zh-CN.md`
- 计划文档：`agentic/docs/plans/chat-branch-version-navigation-plan.md`
- 审查者：同一 Agent 自检
- 审查日期：2026-07-25

## 需求符合度

- [x] 采用 Session 级直接分支族，没有改造成同 Session 消息树。
- [x] 来源、同锚点直接子分支、嵌套分支和来源不可用降级均有实现。
- [x] 版本切换不携带 `runQueued`，创建分支仍保留一次性 queued-run 意图。
- [x] 用户消息编辑迁移到原气泡位置，没有提供原地保存或 Assistant 人工编辑。
- [x] 没有数据库结构变化或超出范围的分支合并、分享、导出能力。

## 正确性

- [x] 当前 Session、来源 Session 和子分支查询均按当前用户过滤。
- [x] 锚点只接受可见 user/assistant MessageEvent，并区分来源模式与子分支模式。
- [x] 子分支按 `created_at ASC, id ASC` 稳定排序，当前项必须存在于结果中。
- [x] 404/409/422 错误路径、来源删除降级和归档版本均有覆盖。
- [x] 内联编辑失败保留编辑态，相同请求重试复用 request ID。

## 安全性

- [x] 不返回不可访问来源的 ID、标题或存在性。
- [x] `branchEvent` 仅作为查询锚点，服务端重新校验归属和可见性。
- [x] API 只返回轻量导航元数据，不返回事件、Memory、Trace、文件或消息正文。
- [x] 结构化日志不记录标题或消息正文。

## 可维护性

- [x] 仓储解析、Service 投影、API 契约和 UI 状态职责清晰。
- [x] 复用现有分支创建、queued-run 和 Session 路由机制。
- [x] 旧 `ChatEditBranchDialog` 已删除，避免双入口。
- [x] 本批无迁移，兼容现有 Session 和第一阶段分支数据。

## 测试质量

- [x] 仓储覆盖用户隔离、锚点、稳定排序、来源删除、二级分支和归档项。
- [x] Service/route 覆盖轻量响应、安全日志与 404/409/422 契约。
- [x] 前端覆盖 50 版本、导航边界、错误恢复、branchEvent 和无 runQueued。
- [x] 内联编辑覆盖聚焦、快捷键、空白、长度、附件/Skills、失败重试和单编辑态。
- [x] 全量后端 196 项、前端 86 项、类型检查和生产构建通过。

## 问题列表

未发现 `blocking`、`major`、`minor` 或需要立即整改的代码问题。

## 无法验证项

- 当前环境没有可连接的浏览器实例。虽然本地 Vite 页面 `http://127.0.0.1:9532` 正常响应，但无法完成桌面、390px、暗色、键盘焦点、刷新和真实点击链路的页面验收。
- 同一 Agent 完成实现与自审；独立 Reviewer 可进一步降低遗漏风险。

## 合并门禁

| 门禁 | 结果 | 证据 |
| --- | --- | --- |
| 无 blocking | 通过 | 完整生产代码和测试 diff 自检未发现 blocking |
| 无未处理 major | 通过 | 未发现 major |
| 验收标准满足 | 未通过 | 自动化契约通过，但浏览器页面验收无法执行 |
| 相关测试通过 | 通过 | 后端 196 passed；前端 25 files / 86 tests passed |
| 构建通过 | 通过 | `pnpm type-check`、`pnpm build` 通过，3657 modules transformed |
| 数据迁移已验证 | 通过 | 无新增迁移；唯一 head/current 均为 `20260724_0002` |

## 审查结论

- 结论：`CHANGES_REQUIRED`
- 理由：代码自审没有发现需整改缺陷，但计划把桌面、移动端、暗色和键盘页面验收列为强制门禁；当前缺少浏览器证据，不能批准合并。
- 剩余风险：响应式布局、暗色对比度、真实焦点迁移和 branchEvent 刷新后的可视交互尚未页面复验。
- 下一步：连接可用浏览器或由用户按验收清单完成页面复验；若通过，只需更新证据并重跑静态检查，无代码变更时无需重复全量测试。
