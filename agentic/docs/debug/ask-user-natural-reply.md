# Ask User 普通消息无法可靠继续

## 文档状态

- 状态：`FIXED`
- 修复分支：`feature/remove-tool-approval`
- 创建日期：2026-08-18
- 最近更新：2026-08-18

## 问题描述

Session 因 `message_ask_user` 进入 `WAITING` 后，前端强制禁用 Composer，只允许 InteractionCard 调用结构化解决接口。若客户端直接向 `/chat` 发送普通回复，执行领取会把 Session 改为 `RUNNING`，但 pending `ask_user` 没有被解决，也没有形成精确的 `InteractionResolution`，从而可能遗留 pending 事件或把回复错误地当作新任务。用户期望与 `mooc-manus` 一样直接回复即可，但内部仍保持 Agentic 的 action/tool-call 精确恢复、并发和幂等保证。

## 预期行为

1. `WAITING + pending ask_user + 普通文本消息` 在 Session 行锁内原子解决最新 Action，并且只成功一次。
2. 普通回复形成与结构化表单相同的服务端 `InteractionResolution`，从持久化 Tool Call 继续原 React/Plan 步骤，不重新规划成新任务。
3. `allow_text=false` 的问题继续要求结构化选项提交，普通文本不得绕过校验。
4. 前端仅在 pending ask 允许自由文本时开放 Composer；结构化卡片仍可使用。
5. 用户看不到“恢复对话”动作；底层创建新 Task 只是实现细节。

## 实际行为

- `DBSessionRepository.claim_execution()` 对 `WAITING` 只特殊处理历史 `tool_approval`，不会解决 `ask_user`，随后直接写 `RUNNING`。
- `AgentService.chat()` 的普通消息没有生成 `interaction_response`，所以 Lead 无法进入精确恢复分支。
- `SessionDetailView` 在任何 pending `ask_user` 下都禁用 Composer，前端规避了后端缺口，但牺牲自然对话体验。
- 结构化解决先追加 resolved 事件，再由 `continue_interaction()` 另一次领取执行；领取写入 `RUNNING` 后，Lead/Legacy Flow 的恢复前置检查仍只接受 `WAITING`。

## 复现步骤

1. 构造 `Session(status=WAITING)`，追加一个允许自由文本的 pending `ask_user`。
2. 调用普通聊天入口并传入文本回答，不传 `interaction_response`。
3. 观察 Session 被领取为 `RUNNING`，但事件中仍只有 pending Action，Task 输入也没有 InteractionResolution。

- 复现频率：每次。
- 最小复现：`api/tests/app/repositories/test_db_session_organization.py` 与 `api/tests/app/services/test_agent_service_recovery.py` 新增回归测试。

## 日志和证据

### 证据 1：执行领取不路由 Ask User

```text
DBSessionRepository.claim_execution():
  if previous_status == WAITING:
      retire_pending_tool_approval()
  record.status = RUNNING
```

- 获取命令：`rg -n "claim_execution|retire_pending_tool_approval" api/app/repositories/db_session_repository.py`
- 说明：证明普通输入不会解决 pending `ask_user`；不能单独证明前端行为。

### 证据 2：Composer 统一阻塞 pending Ask

```text
disabled = isArchived || Boolean(pendingInteraction) || ...
```

- 获取命令：`rg -n "Boolean\(pendingInteraction\)" web/src/components/SessionDetailView.vue`
- 说明：证明当前产品只能通过卡片回答，后端缺口被 UI 掩盖。

### 证据 3：恢复状态契约不一致

```text
claim_execution(): record.status = RUNNING
LeadAgent._prepare_resume(): requires status == WAITING
PlannerReActFlow.invoke(): resume_pending requires status == WAITING
```

- 获取命令：`rg -n "record.status = SessionStatus.RUNNING|_prepare_resume|resume_pending" api/app`
- 说明：证明领取事务与恢复 Flow 对 Session 状态的期望相互矛盾。

## 调用链

```text
POST /chat
  → AgentService._claim_execution
  → DBSessionRepository.claim_execution（最早偏差：未解决 ask_user）
  → MessageEvent(interaction_response=None)
  → Lead 作为普通新输入执行
```

- 正常结构化路径：InteractionCard → resolve_interaction → server-owned resolution → continue original Tool Call。
- 故障路径：Composer/API 普通回复 → 只领取 Session → pending Action 与回复失去关联。
- 关键差异：是否在领取事务内生成并传递服务端校验的 `InteractionResolution`。

## 根因假设

### 假设 1

- 假设：普通聊天入口缺少 Interaction Router，导致 WAITING 状态被当作一般可领取 Session，而不是等待用户输入的领域状态。
- 依据：Repository 只收敛历史审批；Service 只有显式 resolve 接口能构造 `InteractionResolution`；前端统一阻塞 Composer。
- 最小验证：新增 Repository 测试，要求普通输入领取时追加 resolved ask 事件并返回该事件；在未修复代码上应因方法/结果缺失而失败。
- 预期结果：测试 RED；加入原子路由后 GREEN。

## 假设验证

| 假设 | 命令或实验 | 实际结果 | 结论 |
| --- | --- | --- | --- |
| 假设 1 | `uv run pytest tests/app/repositories/test_db_session_organization.py -q` | 新增 2 项均因缺少 `claim_execution_for_user_input` 失败；实现原子命令后相关 25 项通过 | 成立 |

## 最终根因

普通聊天和结构化回答使用了两条不同的状态转换路径：只有结构化接口解决 Interaction，普通聊天只领取 Session。领域层缺少“按当前 pending Interaction 路由新用户输入”的原子命令，前端只能通过禁用 Composer 避免触发。这同时造成自然回复缺失、pending 事件可能遗留，以及领取状态与 Flow 恢复前置条件不一致。

## 修复方案

- 修复位置：`api/app/core/entities/session.py`、`api/app/repositories/db_session_repository.py`、`api/app/services/agent_service.py`、Lead/Legacy Flow、`web/src/components/SessionDetailView.vue`。
- 最小修改：新增普通用户输入领取命令，在同一行锁事务内识别并解决最新 `ask_user`；Service 将 resolved 事件转换为现有 `InteractionResolution` 并随 Task 输入传递；恢复 Flow 接受已由领取事务写成 `RUNNING` 的合法状态；前端仅对 `allow_text=false` 保持 Composer 阻塞。
- 不采用的方案：不复制 `mooc-manus` 的“读取第一个 Tool Call + roll_back 猜测回复”实现，因为缺少 action_id、幂等和并发校验。
- 相同模式检查：结构化卡片、React/Plan/Legacy 三条恢复路径，以及历史 `tool_approval` 收敛路径一起检查。

## 回归测试

- 测试文件：Repository、AgentService、Lead/Legacy Flow、SessionDetailView 现有测试文件。
- 覆盖行为：原子解决、重复领取、非法自由文本、server-owned resolution、普通回复 UI、选项-only UI。
- RED 命令：`uv run pytest tests/app/repositories/test_db_session_organization.py -q`。
- RED 结果：2 failed、18 passed；普通输入领取方法不存在。
- GREEN 命令：`uv run pytest tests/app/repositories/test_db_session_organization.py tests/app/services/test_agent_service_recovery.py tests/app/controllers/test_session_streaming.py -q`。
- GREEN 结果：原子领取、普通回复、结构化回答、SSE 断线边界和任务创建失败回收均通过；后端全量 469 项通过。

## 验证结果

- 回归测试：通过。Repository、AgentService、Lead React/Plan、Legacy Flow、Controller 和前端 Composer/InteractionCard 均有覆盖。
- 相关测试：后端全量 `469 passed`；前端全量 `44 files / 186 tests passed`。
- 构建或静态检查：Ruff、Vue TypeScript 类型检查和 Vite 生产构建通过。
- 手工复现：未连接真实模型做浏览器端多轮冒烟；当前 8088 服务也未在本批重建/重启。
- 未验证项：真实部署下的模型调用与浏览器断线重连；不影响自动化门禁结论，但应在部署后冒烟。

## 审查与最终状态

- 审查文档：`docs/reviews/ask-user-natural-reply-review.md`
- 审查结论：通过；首轮发现的并发重复回答、结构化回答非原子领取、SSE 首事件前未启动续跑和消息长度不一致均已整改并回归。
- 最终状态：`FIXED`
