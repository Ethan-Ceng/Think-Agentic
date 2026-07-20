# 对话完成后 Composer 无法继续发送

## 问题描述

一次对话运行已经结束，但会话页仍保留运行态，Composer 无法继续正常发送下一条消息。

## 预期行为

- 普通聊天、任务恢复或审批续跑的 SSE 正常结束后，本地 Session 状态变为 `completed`，Composer 恢复发送能力。
- 如果流结束是因为结构化询问或工具审批，Session 保持 `waiting`，Composer 继续禁用，用户必须处理 InteractionCard。

## 实际行为

后端正常完成任务时会把数据库 Session 更新为 `completed`，但正常路径不保证发送 `DoneEvent`。前端收到 `SSE_STREAM_END` 后只清理 `streaming/isSendMessage`，本地 Session 仍为 `running`。

## 最小复现

1. 初始 Session 状态为 `completed`。
2. 调用 `sendMessage`，前端先把本地状态设为 `running`。
3. 模拟聊天 SSE 未发送 `done` 而正常关闭，回调错误为 `SSE_STREAM_END`。
4. 修复前结果：`streaming=false`，但 `session.status=running`。

## 证据与调用链

- `api/app/core/agent/agent_task_runner.py` 正常路径在运行结束时更新数据库状态，但只有取消路径显式写入 `DoneEvent`。
- `web/src/lib/api/session.ts` 在读取器正常结束后回调 `SSE_STREAM_END`。
- `web/src/composables/useSessionDetail.ts` 修复前在 chat/resume/resolve 的 `SSE_STREAM_END` 分支没有完成本地 Session 状态。
- 新增回归测试修复前稳定失败：期望 `completed`，实际为 `running`；等待路径测试保持通过。

## 根因假设与验证

主要假设：Composer 卡住不是输入组件自身禁用，而是 SSE 正常关闭后本地运行状态未收敛。

验证结果：ChatComposer 文本域只受 `sending || disabled` 控制，发送按钮/Enter 行为受 `isRunning` 控制；回归测试精确复现 `running` 残留，因此假设成立。

## 最终根因

前后端对“正常完成信号”的契约不一致：后端以任务结束和数据库状态为事实，前端只在显式 `done/error` 事件时更新本地 Session，未把干净的 SSE 流结束视为当前运行结束。

## 修复方案

- 新增统一 `finishRunStream()`：清理流状态，并在当前不是 `waiting` 时把 Session 设为 `completed`。
- chat、resume、resolve 三条流结束路径复用该逻辑。
- 空监听流正常结束时刷新 Session，从服务端读取权威状态，再决定是否重连。
- 明确保留 `waiting`，避免绕过待处理的结构化问题或工具审批。

## 回归测试

文件：`web/src/composables/useSessionDetail.spec.ts`

- 正常 SSE 结束且无 `done`：Session 恢复 `completed`。
- pending interaction 导致流结束：Session 保持 `waiting`。

## 验证结果

- 修复前：1 failed、1 passed，失败值为 `running`。
- 修复后聚焦测试：2/2 passed。
- 完整前端测试：15 个测试文件、37/37 passed。
- `pnpm build`（包含 vue-tsc）退出码 0。
- `git diff --check` 退出码 0。

## 代码审查

- 结论：`APPROVED`。
- 未发现 blocking/major；`waiting` 保留测试覆盖了不能绕过 InteractionCard 的安全边界。
- 空监听流使用服务端刷新获取权威状态，避免仅凭断流把仍在运行的后台任务标记为完成。
- 限制：同一 Agent 自审；当前没有可用浏览器实例，尚未进行真实页面手工复现与修复后验证。

## 最终状态

`BLOCKED`：代码与自动化验证通过，等待真实浏览器环境补验。
