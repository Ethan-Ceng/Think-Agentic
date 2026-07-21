# 对话“下一条消息”持久化队列代码审查

## 审查范围

- 目标基线：当前分支 HEAD
- 变更分支：`feature/chat-human-in-the-loop`
- 变更范围：当前未提交工作区中与 next-message 队列及其运行可靠性前置修改相关的差异
- 设计文档：`agentic/docs/designs/chat-next-message-queue.zh-CN.md`
- 计划文档：`agentic/docs/plans/chat-next-message-queue-plan.md`
- 审查者：同一 Agent 自检
- 审查日期：2026-07-21

## 需求符合度

- [x] 每个 Session 只有一个持久化 next-message 槽位，支持创建、替换和取消。
- [x] 运行中 Enter/发送执行排队，停止操作保持为独立按钮。
- [x] 当前 flow 正常结束后才认领并接续 queued 消息，整个连续运行只发送一个最终 DoneEvent。
- [x] Wait、Error 和显式 Stop 不自动执行 queued 消息，恢复时由用户显式点击“发送”。
- [x] 刷新和进程重启后可从 Session 快照恢复 queued 状态；孤儿 processing 会回退为 queued。

## 正确性

- [x] queue、replace、cancel、claim、consume、reset 全部以 Session 行锁为并发边界。
- [x] 认领同时校验 Session 的 running 状态与活动 task_id，旧任务不能消费新任务的队列。
- [x] processing 槽位只允许其 owner task 消费；异常和取消会释放为 queued。
- [x] 排队消息消费时用户事件、Session 历史和槽位清理在同一事务中提交。
- [x] 前端消息流以 epoch 隔离，迟到事件或快照不能覆盖新运行。
- [x] 恢复流即使只收到 DoneEvent，也会清除本地 next-message 快照。

## 安全性

- [x] queue/cancel/run API 全部基于当前用户执行 Session 所有权校验。
- [x] 输入长度、附件数量和技能数量均有 Pydantic 约束，空白消息会被拒绝。
- [x] 本功能未放宽工具审批、沙箱、命令执行或文件系统权限。
- [x] 附件仍通过用户隔离的文件仓储解析，不接受客户端直接文件路径。

## 可维护性

- [x] 领域对象、仓储原子操作、服务错误映射、SSE 接口和 UI 状态职责分离。
- [x] 数据库变更通过单一 Alembic revision 管理，当前 revision 链只有一个 head。
- [x] 复用现有 Session、Task、Redis Stream 和事件映射机制，没有引入第二套运行通道。
- [x] 设计明确限定为单槽位，不把本次需求扩展为通用消息队列。

## 测试质量

- [x] 仓储测试覆盖状态冲突、所有权、旧 task、认领、消费与孤儿重置。
- [x] Runner 测试覆盖自然接续、单一 Done、旧 Redis 输入、Wait、Error 和 Cancel。
- [x] 服务/API 测试覆盖恢复启动、409/404 映射、路由和 schema trim。
- [x] 前端测试覆盖运行中 Enter、独立停止、草稿保留、queue/cancel、恢复流和流竞态。
- [x] 完整前端测试、类型检查、生产构建与后端相关回归均通过。

## 审查整改记录

### [major][已整改] 终止状态后自动执行 queued 消息

位置：`agentic/web/src/components/SessionDetailView.vue`

问题：completed + queued 的通用自动 watcher 无法区分自然完成与 Error/Stop，可能违背“终止后保留、不自动继续”的设计。

整改：移除通用自动执行，改为 completed + queued 卡片上的显式“发送”按钮，并在旧 queued 消息处理前禁用普通输入。

### [major][已整改] 旧任务可以认领当前 Session 的 queued 消息

位置：`agentic/api/app/repositories/db_session_repository.py`

问题：原子 finish-or-claim 只检查 next-message owner，没有先验证传入 task_id 仍是 Session 的活动任务。

整改：在行锁内同时验证 Session 为 running 且 `record.task_id == task_id`；增加 stale task 冲突回归测试。

### [minor][已整改] 恢复流漏收用户事件时本地卡片残留

位置：`agentic/web/src/composables/useSessionDetail.ts`

问题：如果恢复 SSE 只收到最终 DoneEvent，本地 next-message 可能仍显示为 queued，用户再次点击后才通过 409 刷新收敛。

整改：恢复流收到 DoneEvent 时主动清除本地快照，并增加仅有 DoneEvent 的组合式测试。

## 当前问题列表

未发现未处理的 blocking、major 或 minor 代码问题。

## 无法验证项

- 应用内浏览器运行时返回 `No browser is available`，无法执行真实页面上的运行中排队、替换、取消、停止保留、刷新恢复和多标签页冲突检查。
- 未启动完整 API/Web 应用，因此没有执行贯穿浏览器、SSE、Redis Stream 和 PostgreSQL 的端到端业务流。
- 本次为同一 Agent 自检；独立 Reviewer 能进一步降低并发状态机审查盲区。

## 合并门禁

| 门禁 | 结果 | 证据 |
| --- | --- | --- |
| 无 blocking | 通过 | 完整差异自检未发现 blocking |
| 无未处理 major | 通过 | 两项 major 已整改并新增回归测试 |
| 后端自动化 | 通过 | 100/100 passed，10 条既有 Pydantic 弃用警告 |
| 前端自动化 | 通过 | 17 files，53/53 passed |
| 类型检查与构建 | 通过 | `pnpm type-check` 与 `pnpm build` 退出码 0；3651 modules transformed |
| 数据迁移 | 通过 | 单一 head；真实 PostgreSQL upgrade/downgrade/upgrade 成功，最终为 `20260721_0001 (head)` |
| Redis 可用性 | 通过 | `docker exec manus-redis redis-cli ping` 返回 `PONG` |
| 补丁检查 | 通过 | `git diff --check` 退出码 0，仅行尾转换提示 |
| 浏览器端到端验收 | 阻塞 | 当前应用内浏览器不可用 |

## 审查结论

- 结论：`APPROVED`（代码、自动化、真实迁移与依赖可用性范围）
- 理由：审查发现的 major/minor 均已整改；最新后端、前端、类型、构建、迁移和补丁检查通过。
- 剩余风险：真实浏览器/SSE 业务链路及多标签页交互尚未手工验收；同一 Agent 自检存在独立性限制。
- 下一步：提供可用应用内浏览器并启动 API/Web 后完成页面端到端验收；在此之前整体计划门禁保持 `BLOCKED`。
