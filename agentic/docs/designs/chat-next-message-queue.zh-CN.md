# 对话“下一条消息”持久化队列设计

## 文档状态

- 状态：`DESIGN_READY`
- 负责人：Codex
- 创建日期：2026-07-21
- 最近更新：2026-07-21

## 背景

上一阶段已经修复对话流结束后的输入锁死、运行中 Enter 误停止和文本草稿丢失，但运行中的文本仍只能作为草稿保存。现有后端若在任务运行中再次调用 `chat`，会把消息写入 Redis 输入流；`AgentTaskRunner` 会在下一个 flow 事件处跳出当前执行并转向新消息，这属于“打断当前回答”，不符合“当前回答完成后再发送”的交互语义。

本阶段实现一个明确的一槽式“下一条消息”：任务运行时允许用户提交一条后续消息；消息保存在 PostgreSQL，会话刷新或服务断线后仍可见；当前 flow 自然结束后，同一个任务运行器接续消费，不再依赖浏览器内存或 Redis 输入流模拟排队。

## 目标

- 每个会话最多保存一条待发送消息，包含文本、已上传附件 ID 和手动选择的 Skills。
- 排队写入、替换、取消和运行器认领都通过会话行锁串行化。
- 当前 flow 必须自然结束；排队消息不得触发中断、停止或写入正在运行的 Redis 输入流。
- 当前 flow 正常结束后自动认领并执行下一条消息，SSE 连接持续输出新的用户消息和后续 Agent 事件。
- 刷新、断网和服务重启不会丢失尚未认领的消息；孤儿运行收敛后，用户可继续发送该消息。
- UI 明确区分“停止当前任务”和“加入下一条”，并允许取消尚未开始的排队消息。

## 非目标

- 不实现无限长度或可排序的多消息队列；本阶段只有一个 next-message 槽位。
- 不保证 Agent 工具副作用在进程崩溃后 exactly-once；沿用现有孤儿运行的恢复边界。
- 不持久化尚未上传完成的本地文件；附件仍先走现有文件上传流程。
- 不支持编辑已经被运行器认领的消息，也不改变等待人工交互时的输入规则。
- 不引入独立队列 worker、消息中间件或跨会话调度器。

## 可选方案

### 方案 A：前端 localStorage 队列

- 做法：运行中点击发送后把消息存在浏览器，收到 `done` 后再次调用 `chat`。
- 优点：改动小，无数据库迁移。
- 缺点：多标签页、跨设备、清理浏览器数据和断线竞态都会导致丢失或重复；服务端无法判断消息是否真正排队。
- 结论：不采用。

### 方案 B：独立多条消息队列表

- 做法：新增队列表和完整的 queued/claimed/completed/cancelled 状态机，由后台消费者调度。
- 优点：可扩展到多条、重排和跨进程 worker。
- 缺点：当前产品只需要“下一条”；会引入额外表、调度器、租约和清理策略，明显超出本阶段需求。
- 结论：暂不采用；未来出现多条排队需求时再迁移。

### 方案 C：Session 上的一槽式 JSONB next-message（推荐）

- 做法：在 `sessions` 增加可空 `next_message` JSONB；仓储用 `SELECT ... FOR UPDATE` 完成写入、取消和认领；运行器在当前 flow 正常结束后原子认领并继续执行。
- 优点：持久、简单，与“最多一条”需求一致；删除会话时自然清理；无需额外 worker。
- 缺点：不能自然扩展到多条；进程在认领后崩溃仍需沿用孤儿运行恢复语义。
- 结论：采用。

## 数据模型

新增领域对象 `NextMessage`：

- `id`：UUID，作为替换、取消和幂等比较标识。
- `message`：非空文本，去除首尾空白后最大 10000 字符。
- `attachment_ids`：已上传文件 ID，最多 20 个。
- `skills`：现有 `SkillRef` 列表，最多 5 个。
- `state`：`queued | processing`。
- `task_id`：认领它的 Task ID；queued 时为空。
- `created_at`、`claimed_at`：排队与认领时间。

`Session` 与 `SessionModel` 增加可空字段 `next_message`，数据库列类型为 JSONB。对外响应只返回用户需要的内容和状态，不返回内部认领细节之外的敏感信息。

## 核心状态机

```text
无消息 --queue--> queued --replace--> queued
queued --cancel--> 无消息
queued --runner claim--> processing --用户事件持久化--> 无消息
processing --服务重启/孤儿收敛--> queued
```

核心规则：

1. 只有会话所有者可以读写 next-message。
2. 仅 `running` 会话接受排队；状态已完成时客户端回退为普通发送。
3. queued 可以被新内容整体替换；processing 不允许替换或取消，返回 409。
4. 认领必须同时校验会话仍为 running，并写入当前 task_id。
5. 运行器把排队消息转换为可见 `MessageEvent` 并成功持久化后清空槽位；随后按普通用户消息运行 flow。
6. 当前 flow 的 DoneEvent 在确认没有 next-message 前不对外发送；若认领到消息，则丢弃该轮 DoneEvent，最终一轮结束时只发一个权威 DoneEvent。
7. Wait/Error/显式 Stop 不自动启动新的 queued 消息；queued 保留，避免用户停止后立即又启动任务。
8. 孤儿运行收敛时把仍处于 processing 的槽位重置为 queued，避免认领后进程退出造成永久卡死。

## 接口设计

- `PUT /sessions/{session_id}/next-message`
  - 请求：`message`、`attachments`、`skills`。
  - 行为：创建或整体替换 queued 槽位。
  - 响应：当前 next-message。
- `DELETE /sessions/{session_id}/next-message`
  - 行为：取消 queued 槽位；processing 返回 409。
- `POST /sessions/{session_id}/next-message/run`（SSE）
  - 用途：刷新或服务重启后，会话已经 completed 但仍有 queued 消息时，由前端恢复执行。
  - 行为：原子把会话切回 running、创建 Task，并让运行器从数据库认领消息；重复请求由行锁和状态校验收敛。
- `GET /sessions/{session_id}`
  - `data.next_message` 返回当前槽位或 null，供刷新恢复 UI。

## 前端交互

- 运行中且没有 queued 消息：Enter 或发送按钮执行“加入下一条”；停止按钮保持独立。
- queued 消息显示在 Composer 上方，包含摘要、附件数量和“取消”；输入框继续可编辑，重新提交会替换 queued 内容。
- processing 时显示“正在发送”，禁用替换和取消，等待对应用户 MessageEvent 到达后卡片消失。
- 正常完成由后端同一运行器自动接续，不需要前端二次调度；若刷新或服务重启后快照为 completed + queued，则卡片提供显式“发送”恢复入口。这样 Error 和用户 Stop 后不会意外自动重启；409 视为其他标签页已接管，刷新快照即可。
- 排队 API 成功后才清空本地草稿和附件，失败时保留原输入。
- waiting 状态继续由 Interaction UI 接管，不开放排队发送。

## 并发、失败与恢复

- 所有 next-message 状态变更锁定 Session 行，避免两个标签页同时替换、取消或认领。
- 当前轮结束与认领 next-message 在同一事务中完成：有 queued 则保持 running 并认领；没有则写 completed。这样不会出现“刚排队却被随后 completed 覆盖”的窗口。
- 若排队写入与任务完成竞争：先获得锁的一方决定结果；API 收到 409 后刷新，并在 completed 状态按普通消息发送。
- queued 在数据库中可跨刷新和服务重启恢复。
- processing 的崩溃恢复是 at-least-once 边界；孤儿收敛重置为 queued。外部工具副作用仍遵循现有恢复提示，不在本阶段承诺 exactly-once。

## 测试与验收

- 仓储：所有权、仅 running、replace、cancel、processing 冲突、原子认领/完成竞争。
- 运行器：当前 flow 不被打断；自动消费 next-message；只输出最终一个 DoneEvent；Wait/Error/Stop 保留 queued。
- 服务/API：详情返回、排队、取消、恢复执行、409 状态映射、孤儿 processing 重置。
- 前端：运行中 Enter 排队而非停止；停止按钮独立；成功后清草稿；失败保留；刷新恢复卡片；最终 done 自动恢复 queued。
- 静态与构建：后端定向测试、前端定向与全量测试、类型检查、生产构建、迁移检查、`git diff --check`。

## 风险与后续演进

- 一槽模型若未来需要多条消息，应迁移到独立表，不在 JSONB 内堆叠数组。
- 多 API 进程仍依赖数据库行锁决定唯一认领者，但当前 Task 注册表是进程内的；真实多进程调度需要后续独立 worker。
- 真实 PostgreSQL、Redis 和浏览器不可用时，只能先完成单元/组件验证，并把端到端门禁明确记录为阻塞项。
