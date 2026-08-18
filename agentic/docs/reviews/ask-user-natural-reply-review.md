# Ask User 普通回复自动继续代码审查

## 审查结论

- 结论：`APPROVED`
- 合并门禁：`READY_TO_MERGE`
- 审查基线：`develop@6cabc3d`
- 审查范围：`feature/remove-tool-approval` 上 Ask User 自然回复增量，以及其依赖的通用 Tool Approval 移除实现；用户已有的 `agentic/api/.env` 修改不在范围内
- 审查方式：当前会话同一 Agent 自审；受本次协作约束限制，未使用独立子 Agent，正式合并时仍建议保留常规同伴审查

## 需求与设计符合性

- [x] `WAITING` 只表示等待 `ask_user` 业务输入，不是关闭会话或要求用户执行恢复操作。
- [x] `allow_text=true` 时可直接在 Composer 回复，也可使用问题卡；两者形成相同的 server-owned `InteractionResolution`。
- [x] `allow_text=false` 时 Composer 继续阻塞，只接受服务端校验后的结构化选项。
- [x] Action 解决、Session 领取和 `WAITING → RUNNING` 在同一 Session 行锁事务内完成。
- [x] React、Plan 与 Legacy Flow 均从原 Tool Call 精确继续，不重新经过 Lead Planner 猜测用户意图。
- [x] 重复/并发回答不会重复解决 Action 或启动第二个 continuation Run。
- [x] 用户可见 MessageEvent 不持久化内部 `interaction_response`；历史与 Trace 仍保留稳定 Action 身份。

## 正确性与可靠性审查

- 普通输入只路由当前最新 pending `ask_user`；领域校验统一处理空回答、自由文本权限、单/多选和未知选项。
- Repository 使用既有 `SELECT ... FOR UPDATE` 串行化回答和执行领取；最近一次已解决 Ask 在 `RUNNING` 时拒绝重复回答，即使其后已写入用户 MessageEvent 也不会失效。
- 结构化问题卡解决同样原子写入 `RUNNING`；AgentService 识别该预领取状态并创建新的 continuation Task，不复用等待前已经结束的 Task，也不把它误报为服务重启后的孤儿运行。
- Controller 在返回 SSE Response 前推进 continuation 到首个持久化点；浏览器在收到首事件后断线不会造成“回答已接收但 Task 未启动”。外层 SSE 结束时显式关闭流生成器，已启动 Task 保持独立运行。
- 任务构造失败会把已解决 Interaction 的 Session 收敛为 `COMPLETED`，并追加 ErrorEvent，不会重建一个没有 pending Action 的 `WAITING`。
- 普通消息与结构化回答统一采用 10,000 字符上限，避免 Composer 路径绕过回答约束。

## 审查发现与整改

### 已整改：重复回答检查依赖最后一个事件

- 严重级别：`major`
- 原因：首轮实现只在 Session 最后一个事件恰好是 resolved Ask 时拒绝重复提交；首个用户 MessageEvent 写入后，同一回答可能被当成运行中普通消息。
- 整改：改为倒序查找最近一次 Interaction，并在其为 resolved `ask_user` 且 Session 为 `RUNNING` 时拒绝新的普通回答。
- 回归：覆盖 resolved 事件为尾事件、其后已有用户 MessageEvent 两个并发窗口。
- 状态：`resolved`

### 已整改：结构化回答解决与执行领取分成两个状态窗口

- 严重级别：`major`
- 原因：问题卡先把 Action 解决为 `COMPLETED`，后续 SSE 再领取执行；普通输入可能在两者之间抢先启动新 Run，且续跑可能复用等待前旧 Task。
- 整改：显式解决事务直接原子写入 `RUNNING`；Service 通过 action_id/tool_call_id 识别预领取 continuation，强制创建新 Task，并在构造失败时回收状态。
- 回归：Repository 原子状态测试、预领取 Task 成功/失败测试、Lead/Legacy RUNNING 恢复测试均通过。
- 状态：`resolved`

### 已整改：回答被 SSE 暴露后续跑尚未启动

- 严重级别：`major`
- 原因：首轮实现会先 yield resolved/用户事件，再持久化并调用 Task；客户端在首事件后断线可能留下“回答已解决但未继续”。
- 整改：普通回复先持久化输入并调用 Task，再产生首个 SSE 事件；结构化入口在返回 EventSourceResponse 前预取 continuation 首事件，确保 Task 已启动。
- 回归：分别覆盖普通回复和问题卡在首个 SSE 事件之前的持久化/启动顺序。
- 状态：`resolved`

### 已整改：普通聊天回答缺少长度上限

- 严重级别：`major`
- 原因：结构化回答限制为 10,000 字符，但 `ChatRequest.message` 无上限，Composer 可绕过同一回答契约。
- 整改：ChatRequest 使用与 Queue/Resolve 一致的 10,000 字符上限。
- 回归：10,001 字符请求稳定触发 Pydantic ValidationError。
- 状态：`resolved`

## 未发现的开放问题

- Blocking：无。
- Major：无。
- Minor：无阻塞合并的已知缺陷。

## 验证门禁

| 门禁 | 结果 | 证据 |
| --- | --- | --- |
| 后端全量测试 | 通过 | 隔离 PostgreSQL/Redis 下 `uv run pytest -q`：469 项全部通过 |
| 后端静态检查 | 通过 | `uv run ruff check app tests`：All checks passed |
| 前端全量测试 | 通过 | `pnpm test:run`：44 个文件、186 项全部通过 |
| 前端类型检查 | 通过 | `pnpm type-check` |
| 前端生产构建 | 通过 | `pnpm build` |
| 数据库迁移 | 通过 | 隔离 PostgreSQL 上 `uv run alembic upgrade head`；本批无 Schema 变更 |
| Diff 健康检查 | 通过 | `git diff --check` 无空白错误，仅 Git 行尾转换提示 |

## 未覆盖与后续事项

- `ask_user` 当前契约只把文本或选项作为 Tool Result；Composer 中同时选择的附件和新 Skill 不改变暂停前 Tool Call 的恢复上下文。若以后需要文件/多字段输入，应实现独立 `form_input`/文件字段并在 UI 明确输入模式。
- 本批未在真实模型服务和浏览器中做多轮人工冒烟，也未重建/重启本机 8088 服务；部署后应验证“自由文本 Ask → Composer 回复”和“选项 Ask → 卡片回复”各一次。
- MCP/A2A 惰性连接、Provider 错误隔离、稳定 Failure 类型和完整 Durable Run 恢复仍属于后续架构批次。

## 最终判断

实现满足“只有 Ask User 进入 WAITING、用户自然回复即可继续、内部仍按 Action/Tool Call 精确且只继续一次”的目标。所有审查发现已整改，最新自动化门禁通过，代码状态为 `READY_TO_MERGE`；未经用户授权不提交、推送或合并。
