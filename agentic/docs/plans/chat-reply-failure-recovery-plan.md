# 对话回复失败恢复交互实施计划

## 关联设计

- 设计文档：`agentic/docs/designs/chat-reply-failure-recovery.zh-CN.md`
- 开发分支：`feature/chat-reply-failure-recovery`

## 当前进度

- 整体状态：`READY_TO_MERGE`
- 当前阶段：completed
- 当前任务：无
- 已完成：4 / 4
- 阻塞问题：无
- 最近更新时间：2026-07-17 16:26（Asia/Shanghai）

## 全局约束

- 不修改后端恢复接口、事件协议、数据库或 Agent 记忆。
- “重新生成回复”必须复用 `recoverTask("continue")`，不能发送重复用户消息。
- 默认不在对话正文展示内部错误原文；原始错误仍保留在事件和追踪中。
- 只有现有 `showRecoveryActions` 判定为真的最后一个错误显示恢复按钮。
- 不触碰工作区中已有的 `agentic/web/src/components.d.ts` 用户修改。

## 状态变更记录

| 日期时间 | 整体状态 | 当前任务 | 变更原因 |
| --- | --- | --- | --- |
| 2026-07-17 15:25 | `IN_PROGRESS` | Task 1 | 设计完成并创建独立开发分支 |
| 2026-07-17 15:22 | `IN_PROGRESS` | Task 2 | 回归测试已稳定复现旧交互问题 |
| 2026-07-17 15:23 | `VERIFYING` | Task 3 | 轻量失败恢复卡片实现完成，定向测试通过 |
| 2026-07-17 15:49 | `REVIEWING` | Task 3 | 完整测试、类型检查和补丁检查通过，进入代码审查 |
| 2026-07-17 15:52 | `IN_PROGRESS` | Task 3 | 审查发现内部恢复指令会显示为用户消息，需整改 major 问题 |
| 2026-07-17 16:25 | `VERIFYING` | Task 4 | 内部恢复指令可见性整改完成，前后端定向测试通过 |
| 2026-07-17 16:26 | `READY_TO_MERGE` | 无 | 全量验证与复审通过 |

## Task 1：建立失败卡片回归测试

状态：completed

### 目标

用组件测试固定新的用户可见文案、内部错误隐藏规则和两个恢复事件映射，并证明旧实现不满足要求。

### 涉及文件

- `agentic/web/src/components/chat/ChatMessage.spec.ts`
- `agentic/web/src/components/chat/ChatMessage.vue`

### 依赖与接口

- 前置任务：无
- 输入：`TimelineItem` 的 `kind: "error"` 分支、`showRecoveryActions` 属性。
- 输出：可重复执行的组件回归测试。

### 实施步骤

1. 构造包含内部异常文本的错误时间线项目。
2. 验证可恢复卡片显示“本次回复未完成”和通用说明，且不显示内部异常原文。
3. 验证主、次按钮分别发出 `recoverTask("continue")` 与 `recoverTask("restart")`。
4. 验证非可恢复历史错误不显示恢复按钮。
5. 在修改组件前运行定向测试并记录预期失败。

### 验证方式

- 运行：`pnpm test:run -- src/components/chat/ChatMessage.spec.ts`
- 预期：组件修改前至少一个新断言失败，且失败原因与旧文案或原始异常展示一致。

### 完成条件

- 测试能够稳定复现旧交互问题，并覆盖设计中的核心显示与事件规则。

### 执行结果

新增 `ChatMessage.spec.ts`，隔离无关子组件后覆盖错误文案、内部错误隐藏、恢复模式映射、历史错误操作隐藏和忙碌禁用状态。修改前定向测试 3 项中 2 项按预期失败，失败均来自旧交互文案。

### 验证证据

```text
命令：pnpm test:run -- src/components/chat/ChatMessage.spec.ts
退出状态：1（预期失败）
关键结果：3 tests；1 passed，2 failed。失败断言分别为缺少“本次回复未完成”和按钮仍显示“从未完成处继续”。
执行时间：2026-07-17 15:22 Asia/Shanghai
```

## Task 2：实现轻量失败恢复卡片

状态：completed

### 目标

在不改变恢复 API 的前提下，把错误消息优化为用户可理解且可重试的回复失败状态卡。

### 涉及文件

- `agentic/web/src/components/chat/ChatMessage.vue`
- `agentic/web/src/components/chat/chat.css`（仅在现有样式不足时修改）
- `agentic/web/src/components/chat/ChatMessage.spec.ts`

### 依赖与接口

- 前置任务：Task 1
- 输入：现有 `showRecoveryActions`、`recoveryBusy`、`recoverTask`。
- 输出：保持原事件接口不变的新卡片文案和布局。

### 实施步骤

1. 将错误标题统一改为“本次回复未完成”。
2. 用固定、可行动的用户说明替代原始异常 Markdown。
3. 将 `continue` 操作改标“重新生成回复”，将 `restart` 操作改标“重新执行任务”。
4. 移除错误原文的消息操作入口，避免复制内部错误。
5. 如现有样式无法容纳说明，做最小 CSS 调整。
6. 运行 Task 1 的定向测试直至通过。

### 验证方式

- 运行：`pnpm test:run -- src/components/chat/ChatMessage.spec.ts`
- 预期：新增组件测试全部通过。

### 完成条件

- 新文案、内部错误隐藏、恢复事件映射、历史错误和忙碌禁用规则均通过自动测试。

### 执行结果

更新 `ChatMessage.vue`：错误标题统一为“本次回复未完成”，以固定的可行动说明替代内部异常，恢复按钮改为“重新生成回复”和“重新执行任务”，并移除复制内部错误的消息操作入口。恢复事件与接口未改变，未新增 CSS。

### 验证证据

```text
命令：pnpm test:run -- src/components/chat/ChatMessage.spec.ts
退出状态：0
关键结果：1 test file passed；3 tests passed。
执行时间：2026-07-17 15:22 Asia/Shanghai
```

## Task 3：隐藏内部恢复指令

状态：completed

### 目标

让恢复指令继续驱动 Agent，但不显示为用户气泡，也不覆盖会话最新消息。

### 涉及文件

- `agentic/api/app/core/entities/event.py`
- `agentic/api/app/schemas/event.py`
- `agentic/api/app/services/agent_service.py`
- `agentic/api/tests/app/services/test_agent_service_recovery.py`
- `agentic/web/src/lib/api/types.ts`
- `agentic/web/src/lib/session-events.ts`
- `agentic/web/src/lib/session-events.spec.ts`

### 依赖与接口

- 前置任务：Task 2
- 输入：现有 `MessageEvent`、SSE 消息数据和恢复调用链。
- 输出：缺省可见、恢复时内部的向后兼容消息可见性字段。

### 实施步骤

1. 为领域消息事件和 SSE 消息数据增加缺省为真的 `visible` 字段。
2. 让 `resume()` 调用 `chat()` 时传递 `visible=False`。
3. `chat()` 对内部消息跳过会话最新消息更新，但仍写入任务输入流、事件历史和 SSE。
4. 前端消息类型接受可选 `visible`；时间线仅过滤显式为假的消息。
5. 补后端恢复参数/SSE 映射和前端时间线过滤回归测试。

### 验证方式

- 运行：`uv run pytest tests/app/services/test_agent_service_recovery.py`
- 运行：`pnpm test:run -- src/lib/session-events.spec.ts src/components/chat/ChatMessage.spec.ts`
- 预期：恢复模式传递内部标记，SSE 保留标记，前端不渲染内部消息；普通旧消息仍显示。

### 完成条件

- 内部恢复消息不会进入可见时间线或覆盖会话摘要，相关前后端定向测试通过。

### 执行结果

为消息事件、SSE 数据和前端消息类型增加缺省为真的 `visible` 字段。恢复运行使用 `visible=False`：指令仍进入任务输入流、事件历史和 SSE，但不更新会话最新消息；前端时间线忽略显式不可见的消息。旧事件缺少字段时仍正常展示。

### 验证证据

```text
命令：uv run pytest tests/app/services/test_agent_service_recovery.py
退出状态：0
关键结果：5 passed；验证恢复参数、Agent 输入保留、摘要不更新和 SSE 可见性标记。
执行时间：2026-07-17 16:24 Asia/Shanghai

命令：pnpm test:run -- src/lib/session-events.spec.ts src/components/chat/ChatMessage.spec.ts
退出状态：0
关键结果：2 test files passed；4 tests passed。
执行时间：2026-07-17 16:24 Asia/Shanghai
```

## Task 4：完成全量验证与复审

状态：completed

### 目标

确认整改后的交互没有破坏现有聊天功能，并完成合并前质量门禁。

### 涉及文件

- 本计划中 Task 1-3 的全部代码与测试文件
- `agentic/docs/reviews/chat-reply-failure-recovery-review.md`
- `agentic/docs/plans/chat-reply-failure-recovery-plan.md`

### 依赖与接口

- 前置任务：Task 3
- 输入：完成的实现、整改和定向测试。
- 输出：最新前后端测试、类型检查、静态检查和复审证据。

### 实施步骤

1. 运行相关后端恢复测试和完整前端测试集。
2. 运行 TypeScript 类型检查、Python 编译检查与 `git diff --check`。
3. 对照更新后的设计验收标准检查补丁。
4. 复审 major 问题是否关闭，并检查是否产生新问题。
5. 将所有证据写回计划并给出最终状态。

### 验证方式

- 运行：`uv run pytest tests/app/services/test_agent_service_recovery.py`
- 运行：`pnpm test:run`
- 运行：`pnpm type-check`
- 运行：`uv run python -m py_compile app/core/entities/event.py app/schemas/event.py app/services/agent_service.py`
- 运行：`git diff --check`
- 预期：所有命令退出码为 0，复审无 blocking/major 问题。

### 完成条件

- 自动验证全部通过，更新后验收标准有证据，复审允许合并。

### 执行结果

完成后端完整测试、前端完整测试、类型检查、Python 编译检查和补丁检查。复审确认原 major 问题已关闭，未发现新的 blocking、major 或 minor 问题，结论为 `APPROVED`。

### 验证证据

```text
命令：uv run pytest
退出状态：0
关键结果：156 items collected；全部通过。
执行时间：2026-07-17 16:25 Asia/Shanghai

命令：pnpm test:run
退出状态：0
关键结果：12 test files passed；30 tests passed。
执行时间：2026-07-17 16:25 Asia/Shanghai

命令：pnpm type-check
退出状态：0
关键结果：vue-tsc -b 通过。
执行时间：2026-07-17 16:25 Asia/Shanghai

命令：uv run python -m py_compile app/core/entities/event.py app/schemas/event.py app/services/agent_service.py
退出状态：0
关键结果：Python 编译检查通过。
执行时间：2026-07-17 16:26 Asia/Shanghai

命令：git diff --check
退出状态：0
关键结果：无空白错误。
执行时间：2026-07-17 16:26 Asia/Shanghai
```

## 计划变更

| 日期 | 变更内容 | 原因 | 影响任务 | 是否影响设计 |
| --- | --- | --- | --- | --- |
| 2026-07-17 | 创建计划 | 设计已确认 | Task 1-3 | 否 |
| 2026-07-17 | 增加内部恢复消息可见性整改 | 审查发现恢复指令会显示为用户消息并覆盖会话摘要 | Task 3-4 | 是，设计已同步更新 |

## 最终验证

### 执行命令

```bash
pnpm test:run -- src/components/chat/ChatMessage.spec.ts
uv run pytest tests/app/services/test_agent_service_recovery.py
pnpm test:run
pnpm type-check
uv run python -m py_compile app/core/entities/event.py app/schemas/event.py app/services/agent_service.py
git diff --check
```

### 执行结果

- 单元测试：通过；后端 Pytest 156 项、前端 Vitest 30 项全部通过
- 集成测试：不适用；无接口或后端行为变化
- 静态检查：通过；`git diff --check` 退出码 0
- 类型检查：通过；`vue-tsc -b` 退出码 0
- 构建：不适用；类型检查覆盖本次 Vue 模板和 TypeScript 改动
- 数据库迁移：不适用；无数据库变化
- 手工验证：通过代码与组件断言检查；可恢复错误有两个操作，历史错误无操作，忙碌时按钮禁用
- 代码审查：`APPROVED`；原 major 已整改，无未处理 blocking/major/minor

### 验收标准检查

- [x] 可恢复错误标题显示“本次回复未完成”，不再显示“回复异常”。
- [x] 默认不展示内部异常原文，而显示通用可行动说明。
- [x] “重新生成回复”触发 `continue`。
- [x] “重新执行任务”触发 `restart`。
- [x] 历史错误没有恢复按钮。
- [x] 恢复期间按钮禁用。
- [x] 内部恢复指令不显示为用户气泡，也不覆盖会话最新消息。
- [x] 相关测试、类型检查和完整测试集通过。

### 未通过项目

无。

### 最终状态

`READY_TO_MERGE`
