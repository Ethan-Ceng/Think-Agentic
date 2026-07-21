# 对话运行状态与草稿恢复实施计划

## 关联设计

- 设计文档：`agentic/docs/designs/chat-runtime-reliability.zh-CN.md`
- 开发分支：`feature/chat-human-in-the-loop`

## 当前进度

- 整体状态：`BLOCKED`
- 当前阶段：completed with external verification blocker
- 当前任务：无
- 已完成：5 / 5
- 阻塞问题：真实浏览器、PostgreSQL 与 Redis 暂不可用；不阻塞自动化实现，阻塞最终手工门禁
- 最近更新时间：2026-07-21 09:39（Asia/Shanghai）

## 全局约束

- Session 服务端状态是断流后的权威状态，前端不得仅凭 SSE 结束乐观标记完成。
- `waiting` 不能被通用清理逻辑覆盖。
- 不实现运行中新消息自动排队，不改变现有聊天请求结构或数据库模型。
- 草稿只持久化纯文本，按 Session ID 隔离；localStorage 失败必须静默降级。
- 不覆盖工作区内与本计划无关的用户修改，不提交、不推送。

## 状态变更记录

| 日期时间 | 整体状态 | 当前任务 | 变更原因 |
| --- | --- | --- | --- |
| 2026-07-20 | `IN_PROGRESS` | Task 1 | 设计完成，开始建立后端终止契约回归测试 |
| 2026-07-20 19:14 | `IN_PROGRESS` | Task 2 | 两个回归测试按预期失败，开始实现可靠终止契约 |
| 2026-07-20 19:25 | `IN_PROGRESS` | Task 3 | 服务端终止契约实现完成，11 项定向测试通过 |
| 2026-07-20 19:28 | `IN_PROGRESS` | Task 4 | 三类权威状态和三条流路径测试通过，开始 Composer 与草稿实现 |
| 2026-07-20 19:31 | `VERIFYING` | Task 5 | 运行中安全输入和按会话文本草稿完成，开始完整验证 |
| 2026-07-20 19:34 | `IN_PROGRESS` | Task 5 | 审查发现输出游标重置和旧流迟到事件两项 major，返回实施整改 |
| 2026-07-21 09:39 | `BLOCKED` | 无 | 审查整改与完整自动化通过；真实浏览器、PostgreSQL、Redis 环境仍不可用 |

## Task 1：建立后端终止事件与尾部排空回归测试

状态：completed

### 目标

用自动化测试证明正常完成必须输出 `done`，并固定任务先结束时 AgentService 仍能读取尾部终止事件的行为。

### 涉及文件

- `agentic/api/tests/app/core/agent/test_agent_task_runner_completion.py`（新建）
- `agentic/api/tests/app/services/test_agent_service_recovery.py`
- `agentic/api/app/core/agent/agent_task_runner.py`（仅作为被测对象）
- `agentic/api/app/services/agent_service.py`（仅作为被测对象）

### 依赖与接口

- 前置任务：无
- 输入：现有 `DoneEvent`、`SessionStatus`、Task 输入/输出流协议。
- 输出：修改实现前稳定失败、修改实现后可回归的测试。

### 实施步骤

1. 用最小 fake UoW、Trace 和 Task 隔离 AgentTaskRunner 正常完成路径。
2. 断言完成状态写入后输出一个 `DoneEvent`。
3. 为 AgentService 构造 `done=True` 但输出流仍有终止事件的 Task。
4. 断言服务能够排空并返回尾部事件，且不会永久等待。
5. 在修改实现前运行定向测试并记录预期失败。

### 验证方式

- 运行：`uv run pytest tests/app/core/agent/test_agent_task_runner_completion.py tests/app/services/test_agent_service_recovery.py -q`
- 工作目录：`agentic/api`
- 预期：实现前新增断言稳定失败，失败原因分别指向缺少正常 `done` 或未读取尾事件。

### 完成条件

- 两类竞态都有独立回归断言，并记录修复前失败证据。

### 执行结果

新增 AgentTaskRunner 正常完成测试和 AgentService 已结束任务尾事件排空测试。首次运行发现仓库未安装 pytest-asyncio，按仓库惯例改用 `asyncio.run` 后，两项产品断言均稳定失败。

### 验证证据

```text
命令：uv run pytest tests/app/core/agent/test_agent_task_runner_completion.py tests/app/services/test_agent_service_recovery.py -q
退出状态：1（预期失败）
关键结果：8 tests；6 passed，2 failed。失败分别为正常完成输出事件数量 0、已结束任务尾事件返回数量 0。
执行时间：2026-07-20 19:14 Asia/Shanghai
```

## Task 2：实现服务端可靠终止契约

状态：completed

### 目标

让正常完成、取消和异常运行具有明确终止事件，并保证 SSE 消费端不会因 `task.done` 提前漏读尾事件。

### 涉及文件

- `agentic/api/app/core/agent/agent_task_runner.py`
- `agentic/api/app/services/agent_service.py`
- Task 1 的测试文件

### 依赖与接口

- 前置任务：Task 1
- 输入：Task 1 的失败测试。
- 输出：正常完成 `done`、等待 `wait`、异常 `error` 的稳定流终止契约。

### 实施步骤

1. 正常完成时先更新 Session 为 `completed`，再持久化并输出 `DoneEvent`。
2. 保持 `WaitEvent` 提前返回，不额外产生 `done`。
3. 调整取消路径，使状态与 `done` 顺序可被断流刷新正确观察。
4. 修改 AgentService 输出读取：使用有限阻塞读取；收到终止事件即退出；任务已结束且队列确认无尾事件时退出并告警。
5. 运行 Task 1 定向测试直至通过。

### 验证方式

- 运行：`uv run pytest tests/app/core/agent/test_agent_task_runner_completion.py tests/app/services/test_agent_service_recovery.py -q`
- 工作目录：`agentic/api`
- 预期：全部通过，无挂起。

### 完成条件

- 终止事件契约和尾部排空测试全部通过，等待态行为不变。

### 执行结果

AgentTaskRunner 现在在正常完成时先写入 completed 状态再输出 DoneEvent；取消和异常路径也先收敛权威状态。AgentService 改为有限阻塞读取，在 Task 已结束时仍执行一次尾部排空，并在确认没有终止事件时告警退出。补充了 normal、waiting、error、cancelled 四条 Runner 状态测试。

### 验证证据

```text
命令：uv run pytest tests/app/core/agent/test_agent_task_runner_completion.py tests/app/services/test_agent_service_recovery.py -q
退出状态：0
关键结果：11 passed；覆盖正常 done、等待 wait、异常 error、取消 done 和已结束任务尾事件排空。
执行时间：2026-07-20 19:25 Asia/Shanghai
```

## Task 3：统一前端断流后的权威状态校准

状态：completed

### 目标

chat、resume、resolve 流结束后都刷新服务端 Session；若仍运行则恢复监听，且保留 waiting。

### 涉及文件

- `agentic/web/src/composables/useSessionDetail.ts`
- `agentic/web/src/composables/useSessionDetail.spec.ts`

### 依赖与接口

- 前置任务：Task 2
- 输入：稳定的服务端终止事件与现有 `refresh/startEmptyStream`。
- 输出：统一的流结束协调函数及竞态回归测试。

### 实施步骤

1. 扩展测试，覆盖断流刷新为 completed、waiting、running 三种结果。
2. 覆盖 chat、resume、resolve 的 SSE_STREAM_END 路径。
3. 移除 `finishRunStream()` 对 completed 的无条件乐观写入。
4. 新增统一异步校准：清理流状态、刷新 Session、running 时启动空监听。
5. 保持 Abort 只做连接清理，不触发旧连接状态覆盖。

### 验证方式

- 运行：`pnpm test:run -- src/composables/useSessionDetail.spec.ts`
- 工作目录：`agentic/web`
- 预期：新增与既有测试全部通过。

### 完成条件

- 三条流路径共享同一校准规则，completed/waiting/running 均有测试证据。

### 执行结果

新增 completed、waiting、running 三种断流校准测试，以及 resume、interaction resolve 路径测试。实现流代次保护和统一异步校准，旧流返回不能覆盖新运行；服务端仍为 running 时恢复空监听。

### 验证证据

```text
命令：pnpm test:run -- src/composables/useSessionDetail.spec.ts
退出状态：1（修改前，预期失败）；0（修改后）
关键结果：修改前 5 failed；修改后 5 passed。
执行时间：2026-07-20 19:28 Asia/Shanghai
```

## Task 4：实现运行中安全输入与按会话文本草稿

状态：completed

### 目标

运行中 Enter 不再停止任务，并让未发送纯文本在刷新和会话切换后恢复。

### 涉及文件

- `agentic/web/src/components/chat/ChatComposer.vue`
- `agentic/web/src/components/chat/ChatComposer.runtime.spec.ts`（新建）
- `agentic/web/src/components/chat/ChatInput.vue`
- `agentic/web/src/components/chat/ChatInput.spec.ts`（新建）

### 依赖与接口

- 前置任务：Task 3
- 输入：`sessionId`、`isRunning`、现有 send/stop 事件。
- 输出：显式停止行为与按 Session ID 隔离的纯文本草稿。

### 实施步骤

1. 新增键盘测试：运行中 Enter 不发出 stop/send，并保留文本编辑行为；停止按钮仍发出 stop。
2. 根据运行状态调整 Composer 提示，避免显示“Enter 发送”。
3. 为 ChatInput 增加安全 localStorage 读写，key 使用 Session ID。
4. 新增草稿恢复、会话隔离、空值删除、发送成功清除和存储异常降级测试。
5. 明确不序列化附件和技能选择。

### 验证方式

- 运行：`pnpm test:run -- src/components/chat/ChatComposer.skills.spec.ts src/components/chat/ChatInput.spec.ts`
- 工作目录：`agentic/web`
- 预期：相关组件测试全部通过。

### 完成条件

- 运行中无法通过 Enter 误停止；文本草稿按会话可靠保存、恢复和清除。

### 执行结果

运行中无修饰 Enter 现在保留为文本编辑，不再触发 stop；停止仍只能通过显式按钮。ChatInput 使用 `agentic:chat-draft:<sessionId>` 保存纯文本，支持刷新恢复、会话切换隔离、成功发送后清除，并在 localStorage 写入失败时退化为内存草稿。

### 验证证据

```text
命令：pnpm test:run -- src/components/chat/ChatComposer.runtime.spec.ts src/components/chat/ChatInput.spec.ts
退出状态：1（修改前，预期失败）
关键结果：7 tests；4 passed，3 failed。失败对应 Enter 触发 stop、草稿未保存、会话切换未恢复。

命令：pnpm test:run -- src/components/chat/ChatComposer.runtime.spec.ts src/components/chat/ChatInput.spec.ts src/components/chat/ChatComposer.skills.spec.ts
退出状态：0
关键结果：3 files，9 passed。
执行时间：2026-07-20 19:31 Asia/Shanghai
```

## Task 5：完整验证、审查与门禁结论

状态：completed

### 目标

运行与声明匹配的完整自动化检查，审查状态机、竞态和回归风险，并给出最终门禁状态。

### 涉及文件

- 本计划涉及的全部代码和测试
- `agentic/docs/reviews/chat-runtime-reliability-review.md`（新建）
- `agentic/docs/plans/chat-runtime-reliability-plan.md`

### 依赖与接口

- 前置任务：Task 1–4
- 输入：完整实现和定向测试证据。
- 输出：验证记录、分级审查结论与 READY_TO_MERGE/BLOCKED/FAILED。

### 实施步骤

1. 运行后端相关测试与可行的完整测试集。
2. 运行前端完整测试、类型检查和生产构建。
3. 运行 `git diff --check` 并检查实际差异范围。
4. 按 blocking/major/minor/suggestion 审查状态竞态、资源清理、兼容性和测试质量。
5. 尝试真实浏览器手工检查；环境不可用则准确记录阻塞，不伪造结果。
6. 把所有证据和最终状态写回计划。

### 验证方式

- 后端：`uv run pytest tests/app/core/agent/test_agent_task_runner_completion.py tests/app/services/test_agent_service_recovery.py -q`
- 前端：`pnpm test:run`
- 类型：`pnpm type-check`
- 构建：`pnpm build`
- 补丁：`git diff --check`
- 手工：运行中刷新、无终止事件断流、waiting、停止、草稿刷新与会话隔离。

### 完成条件

- 自动化验证通过，审查无 blocking/major；若只有环境门禁未完成，最终状态为 BLOCKED 并列出解除条件。

### 执行结果

完成两轮差异审查和审查整改。最终实现覆盖输出游标保持、终止事件尾部排空、DoneEvent 去重与权威状态顺序、三条消息流及空监听流代次隔离、跨会话延迟发送和文本草稿恢复。自动化、类型与构建全部通过；真实依赖和浏览器手工验收记录为外部阻塞。

### 验证证据

```text
后端：uv run pytest tests/app/core/agent/test_agent_task_runner_completion.py tests/app/services/test_agent_service_recovery.py -q
退出状态：0；13 passed，10 warnings（Pydantic 既有弃用警告）

前端：pnpm test:run
退出状态：0；17 files，50 passed

类型：pnpm type-check
退出状态：0

构建：pnpm build
退出状态：0；3651 modules transformed，built in 1.29s

补丁：git diff --check
退出状态：0；仅有 Git 行尾转换警告

浏览器：agent.browsers.list()
结果：[]，无法执行真实页面手工验收

代码审查：agentic/docs/reviews/chat-runtime-reliability-review.md
结论：APPROVED（代码与自动化范围），整体门禁因外部环境 BLOCKED
执行时间：2026-07-21 09:39 Asia/Shanghai
```

## 计划变更

| 日期 | 变更内容 | 原因 | 影响任务 | 是否影响设计 |
| --- | --- | --- | --- | --- |
| 2026-07-20 | 自动下一条消息队列拆分为后续设计 | 现有运行中输入语义会打断当前 flow，可靠队列需要幂等和持久化 | 无 | 否 |
| 2026-07-20 | Task 5 增加两项审查整改 | 有限阻塞读取不能重置游标，旧流事件必须受流代次保护 | Task 5 | 否 |

## 最终验证

### 执行命令

```powershell
# agentic/api
uv run pytest tests/app/core/agent/test_agent_task_runner_completion.py tests/app/services/test_agent_service_recovery.py -q

# agentic/web
pnpm test:run
pnpm type-check
pnpm build

# D:\AI\Think-Agentic
git diff --check
```

### 执行结果

- 单元测试：通过；后端 13/13，前端 50/50
- 集成测试：受 PostgreSQL/Redis 环境阻塞
- 静态检查：通过；`git diff --check` 退出码 0
- 类型检查：通过；`pnpm type-check` 退出码 0
- 构建：通过；`pnpm build` 退出码 0
- 数据库迁移：不适用
- 手工验证：阻塞；`agent.browsers.list()` 返回 `[]`
- 代码审查：APPROVED（代码与自动化范围）；详见 `agentic/docs/reviews/chat-runtime-reliability-review.md`

### 验收标准检查

- [x] Agent 正常完成、取消和异常分别产生预期终止事件，Session 最终为 completed。
- [x] 任务先结束时客户端仍能收到尾部终止事件。
- [x] chat、resume、resolve 无终止事件断流后按服务端状态校准。
- [x] 服务端仍为 running 时恢复监听，waiting 不被覆盖。
- [x] 运行中 Enter 不停止任务，停止按钮仍可用。
- [x] 文本草稿刷新恢复、会话隔离、成功发送后清除。
- [ ] 自动化检查通过；真实依赖和浏览器环境恢复后仍需完成手工验收。

### 未通过项目

- PostgreSQL、Redis 未运行，无法验证真实任务、Redis Stream 和数据库状态顺序。
- 应用内浏览器不可用，无法执行页面级刷新、断网、停止和草稿手工验收。

### 最终状态

`BLOCKED`
