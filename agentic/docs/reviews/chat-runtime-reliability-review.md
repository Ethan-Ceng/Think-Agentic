# 对话运行状态与草稿恢复代码审查

## 审查范围

- 目标基线：当前分支 HEAD
- 变更分支：`feature/chat-human-in-the-loop`
- 变更范围：当前未提交工作区中与本功能相关的差异
- 设计文档：`agentic/docs/designs/chat-runtime-reliability.zh-CN.md`
- 计划文档：`agentic/docs/plans/chat-runtime-reliability-plan.md`
- 审查者：同一 Agent 自检
- 审查日期：2026-07-21

## 需求符合度

- [x] 符合设计文档和验收标准。
- [x] 服务端终止事件、断流校准、刷新恢复、显式停止和文本草稿均已实现。
- [x] 未实现自动下一条消息队列、附件草稿或数据库迁移，没有扩大范围。
- [x] 审查中发现的实现偏差和整改均已写回计划。

## 正确性

- [x] 正常、等待、异常和取消状态有独立测试。
- [x] 输出流临时超时不会重置 Redis 事件游标。
- [x] Task 已结束时仍能排空尾部终止事件。
- [x] chat、resume、resolve 和空监听流均受流代次保护，旧事件/旧刷新不能覆盖新运行。
- [x] PlannerReActFlow 已产生的 DoneEvent 会延迟到 Session completed 提交后发送，且不会重复补发。
- [x] 延迟完成的旧会话发送不会清空新会话草稿。

## 安全性

- [x] 未改变会话权限、审批、工具调用或文件执行边界。
- [x] localStorage key 只包含 Session ID，内容只保存用户未发送纯文本，不保存附件、技能或凭据结构。
- [x] 存储不可用时捕获异常并退化为内存草稿。
- [x] 未新增公共输入解析、命令执行或文件路径处理。

## 可维护性

- [x] 复用现有 refresh、事件去重和空监听机制。
- [x] 流代次和权威快照逻辑集中在 `useSessionDetail`。
- [x] 后端仅增强现有事件契约，无数据库或公共接口迁移。
- [x] 自动下一条消息队列保持独立设计边界。

## 测试质量

- [x] 核心状态机和历史 Bug 有回归覆盖。
- [x] 测试包含临时超时、迟到事件、迟到刷新、跨会话异步发送和存储失败。
- [x] 组件测试验证键盘默认行为、显式停止和草稿实际存储结果。
- [x] 完整前端测试、类型检查和生产构建通过。

## 审查整改记录

### [major][已整改] 临时读取超时重置输出游标

位置：`agentic/api/app/services/agent_service.py`

问题：有限阻塞读取返回空结果时先把 `latest_event_id` 写成 `None`，下一轮会从输出流开头重放。

整改：只有读到有效事件后才推进游标，并增加“超时后两次读取使用同一游标”的测试。

### [major][已整改] 旧消息流和旧空监听流污染新运行

位置：`agentic/web/src/composables/useSessionDetail.ts`

问题：被替换流迟到的 DoneEvent 或快照刷新可能清理新连接、覆盖新运行状态。

整改：chat、resume、resolve、空监听事件及其快照加载均绑定创建时的 `runStreamEpoch`；增加迟到事件与迟到刷新测试。

### [major][已整改] 延迟发送完成清除错误会话草稿

位置：`agentic/web/src/components/chat/ChatInput.vue`

问题：会话 A 的发送 Promise 在切到会话 B 后完成，会按当前 props 清空 B 草稿。

整改：发送开始时捕获 Session ID，只清除原会话存储；仅当组件仍位于原会话时清空可见输入。

### [major][已整改] 正常流重复 DoneEvent 且早于权威状态

位置：`agentic/api/app/core/agent/agent_task_runner.py`

问题：PlannerReActFlow 已产生 DoneEvent，Runner 再补一个会造成重复；原 Done 也早于 completed 状态提交。

整改：缓存 Flow 的 DoneEvent，先提交 Session completed，再发送一次；仅无终止事件的异常正常返回才补兜底 Done。

## 当前问题列表

未发现未处理的 blocking、major 或 minor 问题。

## 无法验证项

- 应用内浏览器发现结果为 `[]`，无法执行真实页面的运行中刷新、断网恢复、显式停止和草稿交互检查。
- PostgreSQL 与 Redis 服务不可用，无法执行真实 SSE/Redis Stream/数据库集成验收。
- 本次为同一 Agent 自检；独立 Reviewer 能进一步降低状态机审查盲区。

## 合并门禁

| 门禁 | 结果 | 证据 |
| --- | --- | --- |
| 无 blocking | 通过 | 完整差异自检未发现 blocking |
| 无未处理 major | 通过 | 四类 major 均已整改并新增回归测试 |
| 自动化验收标准 | 通过 | 后端 13/13、前端 50/50 |
| 类型检查 | 通过 | `pnpm type-check` 退出码 0 |
| 构建 | 通过 | `pnpm build` 退出码 0 |
| 数据迁移 | 不适用 | 无数据结构变更 |
| 真实集成与手工验收 | 阻塞 | 无 PostgreSQL/Redis/可用浏览器 |

## 审查结论

- 结论：`APPROVED`（代码与自动化范围）
- 理由：审查发现的 major 均已整改，最新测试、类型检查、构建与补丁检查通过。
- 剩余风险：真实依赖和浏览器路径未验收；同一 Agent 自检存在独立性限制。
- 下一步：环境恢复后完成真实 SSE 和页面手工验收；在此之前整体合并门禁保持 `BLOCKED`。
