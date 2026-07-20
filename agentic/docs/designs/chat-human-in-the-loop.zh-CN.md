# Chat Human-in-the-loop 交互闭环

## 文档状态

- 状态：`DESIGN_READY`
- 负责人：Codex
- 创建日期：2026-07-20
- 最近更新：2026-07-20

## 背景

Agentic 已能通过 `message_ask_user` 让运行进入 `waiting`，但问题被降级为普通 Assistant 文本，用户只能在通用 Composer 中自由输入；选项、多选、回答失败恢复和历史回答状态均没有结构化表达。工具治理已经具备 `risk_level`，但高风险工具仍会直接执行，缺少执行前批准、拒绝和可审计的决定记录。

LibreChat 的可借鉴点不是 React 组件本身，而是把 Agent 暂停统一表达为可持久化、可恢复、可审计的交互动作。Agentic 需要保留 Plan、Step、Tool Call、Run/Trace 语义，并在现有事件流和会话恢复机制之上建立自己的 Human-in-the-loop 闭环。

## 目标

- `message_ask_user` 支持结构化单选、多选和自由文本回答，回答后从原 Tool Call 继续当前步骤。
- 风险策略要求确认时，在工具实际执行前展示工具名称、风险、参数和“批准/拒绝”操作。
- 暂停请求与解决结果持久化到 Session 事件；刷新页面后仍能看到待处理动作和历史决定。
- 交互解决接口按当前用户校验 Session 所有权，并保证同一动作只能成功解决一次。
- 服务进程重启后，只要 Session、Plan 和 Agent Memory 仍完整，用户仍可解决待处理动作并恢复运行。

## 功能范围

- 新增统一 `interaction` 领域/SSE 事件，覆盖 `ask_user` 和 `tool_approval`。
- 扩展 `message_ask_user` Tool Schema：选项、多选、自由文本开关和输入提示。
- 扩展 ToolBinding 与 RuntimeToolPolicy：`auto/allow/ask/deny` 审批策略，以及高风险工具默认确认开关。
- 在工具调用前应用审批策略；`deny` 直接返回拒绝结果，`ask` 创建待处理动作且不执行工具。
- 新增交互解决 SSE 接口；回答、批准或拒绝后恢复原 Tool Call。
- 前端增加结构化问题卡、工具审批卡及待处理状态；解决中禁止重复操作。
- 为交互事件、权限、幂等、恢复和前端操作增加测试。

## 非功能范围

- 本批次不实现用户消息编辑、普通回复重新生成、消息树/Fork。
- 本批次不实现 Markdown 数学公式、Mermaid、代码运行或 Citation。
- 本批次不实现多人审批、审批委托、长期审批工单或组织级审批策略。
- 本批次不允许用户直接编辑工具参数；先交付批准和拒绝，参数编辑留到独立增量。
- 本批次不新增数据库表；交互状态沿用 Session JSONB 事件和现有 Run/Trace 投影。
- 不复制 LibreChat React、Recoil、Jotai 或 Provider 实现。

## 业务流程

### 结构化询问

1. Agent 调用 `message_ask_user`，BaseAgent 在实际调用前创建 `interaction(status=pending, interaction_type=ask_user)`。
2. ReAct Step 输出该事件和 `wait`，Session 进入 `waiting`，当前 Tool Call 保留在 React Memory 尾部。
3. 前端根据问题配置展示选项、多选或自由文本输入。
4. 用户提交回答，前端调用交互解决 SSE 接口。
5. 服务端校验所有权、Session 状态、动作状态和回答格式，写入 `interaction(status=resolved)`。
6. 新 Run 从 React Memory 中的原 Tool Call 恢复，把回答作为对应 Tool Result 写入 Memory，然后继续 LLM、Step 和 Plan。

### 工具审批

1. BaseAgent 准备调用工具时，从 FilteredTool 获取有效审批策略。
2. `allow` 直接执行；`deny` 不执行并向 LLM 返回拒绝 Tool Result；`ask` 创建 `tool_approval` 待处理动作。
3. 前端展示工具名称、风险等级和参数，用户批准或拒绝。
4. 批准后服务端从 Memory 校验 Tool Call ID、函数名和参数，执行原调用；拒绝后生成失败 Tool Result，但不执行工具。
5. Tool Result 写回 Memory，运行继续；交互决定、工具结果和后续事件进入 Session/Trace。

## 核心规则

1. 未批准的 `ask` 工具绝不能执行；拒绝路径不得产生工具副作用。
2. 恢复时必须以 `action_id + tool_call_id + function_name + canonical arguments` 校验原调用，任一不匹配即失败。
3. 每个 `action_id` 只能从 `pending` 转为一次 `resolved`；重复提交返回冲突，不创建第二个 Run。
4. 同一 Session 同一时刻只允许一个 pending 交互；当前运行一次只允许一个 Tool Call，沿用现有限制。
5. `message_ask_user` 的回答写为 Tool Result，不伪装成新的普通用户任务，不触发重新规划。
6. 待处理动作必须可从持久化事件恢复；不能只保存在浏览器状态或进程内 Future。
7. `auto` 策略：当全局 `require_approval_for_high_risk=true` 且有效风险为 `high` 时等价于 `ask`，其余等价于 `allow`。
8. Sandbox 内 `read_file` 为低风险，`write_file`/`replace_in_file` 为中风险，因此默认 `auto` 不打断执行；Shell、浏览器脚本和外部副作用仍按高风险确认。显式 `ask/deny` 始终优先。
9. 系统消息工具 `message_notify_user` 与 `message_ask_user` 不走高风险审批；后者使用自己的结构化询问流程。
10. 解决接口只接受与 interaction 类型相符的决定：询问接受 `answer`，审批接受 `approve/reject`。
11. 前端不得把未经脱敏的 Trace 内部数据当作审批说明；审批卡仅展示事件中明确允许展示的函数名、风险和参数。

## 现有实现分析

### 相关代码与文档

- `api/app/core/tools/message.py`：已有 `message_ask_user`，目前只有文本、附件和浏览器接管提示。
- `api/app/core/agent/base.py`：Tool Call 在这里实际执行；Memory 尾部保留 Assistant Tool Call，可作为精确恢复点。
- `api/app/core/agent/react.py`：当前把询问转换为普通 Assistant 消息后输出 `wait`。
- `api/app/core/flows/planner_react.py`：等待后再次输入会回滚 Memory 并继续执行，但没有“恢复原 Tool Call”分支。
- `api/app/services/agent_service.py`：已有 Session 所有权校验、SSE、waiting 状态和恢复 Run 基础。
- `api/app/core/entities/tool_config.py`、`api/app/core/tools/filter.py`：已有 enabled/risk_level 和运行时过滤，适合扩展审批策略。
- `web/src/composables/useSessionDetail.ts`：已有按 event_id 去重、等待态识别和重连。
- `web/src/lib/session-events.ts`、`web/src/components/chat/ChatMessage.vue`：当前时间线无交互动作类型。

### 可复用能力

- Session JSONB 事件可兼容新增事件，无需数据库迁移。
- Agent Memory 已持久化完整 Assistant Tool Call，可用于服务重启后的精确恢复。
- `SessionStatus.WAITING`、`WaitEvent` 和 Task 重建机制可继续使用。
- `FilteredTool + ToolRegistry` 能解析最终 binding 和风险等级。
- 现有 SSE `event_id`、Session 所有权查询、Run/Trace 投影和前端 pending 状态可复用。

### 当前约束

- 当前 LLM 一次只保留一个 Tool Call，因此第一版无需批量审批。
- Plan 的最新持久化快照与 Step 事件分离；恢复必须选择当前未完成 Step，不能依赖进程内 Flow 对象。
- 系统内置工具不在 API Tools 设置页逐项展示，因此第一版以全局高风险默认确认和配置字段为主，不新增庞大设置界面。
- Session 事件为追加式 JSONB；resolved 状态使用同 action_id 的新事件表示，不能原地修改历史事件。

## 可选方案

### 方案 A：仅做前端确认，批准后让模型重新选择工具

- 实现方式：UI 展示确认；批准后向对话追加“已批准，请继续”，模型重新生成 Tool Call。
- 优点：改动小，可快速展示交互。
- 缺点：不能保证函数和参数与用户批准的一致；模型可能不再调用或改写参数。
- 风险：形成“批准 A、执行 B”的安全漏洞，不满足审批语义。

### 方案 B：进程内 Future 暂停原协程

- 实现方式：Tool Call 创建 asyncio Future，解决接口唤醒原 BaseAgent 协程后执行。
- 优点：恢复原调用直接，代码路径直观。
- 缺点：等待期间占用 Task、Sandbox 和连接资源；服务重启后 Future 丢失。
- 风险：长时间等待导致资源泄漏，无法提供持久恢复。

### 方案 C：持久化交互事件 + Memory Tool Call 精确恢复

- 实现方式：待处理/已解决动作写入事件；等待时结束当前 Task；解决后重建 Task，从持久化 Memory 恢复并执行或拒绝原 Tool Call。
- 优点：安全边界明确，可刷新、可审计、可在进程重启后恢复，不长期占用运行资源。
- 缺点：需要扩展事件协议、Flow 恢复分支和测试面。
- 风险：Plan/Memory/Interaction 对不上时恢复失败，需要严格一致性校验和可行动错误。

## 方案对比

| 维度 | 方案 A | 方案 B | 方案 C |
| --- | --- | --- | --- |
| 实现复杂度 | 低 | 中 | 高 |
| 维护成本 | 低 | 中高 | 中 |
| 安全性 | 低 | 高 | 高 |
| 服务重启兼容 | 依赖模型 | 不支持 | 支持 |
| 测试难度 | 低 | 中 | 高 |
| 主要风险 | 批准与执行不一致 | 资源占用/Future 丢失 | 恢复状态一致性 |

## 推荐方案

采用方案 C。审批的核心不是“出现两个按钮”，而是保证用户看到并批准的调用与最终执行完全一致。方案 A 无法提供该保证；方案 B 虽能执行原调用，但与 Agentic 自部署、长任务和可恢复运行目标冲突。现有持久化 Memory、Session 事件和 Task 重建能力已经为方案 C 提供了基础，新增复杂度是可控且值得的。

## 数据结构

### InteractionEvent

| 字段 | 类型 | 必填 | 说明 | 约束/默认值 |
| --- | --- | --- | --- | --- |
| `action_id` | `string` | 是 | 交互动作稳定 ID | UUID |
| `interaction_type` | `ask_user \| tool_approval` | 是 | 动作类型 | 不可变 |
| `status` | `pending \| resolved` | 是 | 动作状态 | 追加式事件 |
| `tool_call_id` | `string` | 是 | 对应 Memory Tool Call | 必须精确匹配 |
| `function_name` | `string` | 是 | 工具函数 | 必须精确匹配 |
| `function_args` | `object` | 是 | 待调用参数 | JSON 对象 |
| `prompt` | `string` | 是 | 用户可见问题/说明 | 非空 |
| `options` | `InteractionOption[]` | 否 | 可选答案 | 默认空数组 |
| `allow_multiple` | `boolean` | 否 | 是否多选 | 默认 false |
| `allow_text` | `boolean` | 否 | 是否允许自由输入 | 默认 true（ask_user） |
| `placeholder` | `string` | 否 | 输入提示 | 可空 |
| `risk_level` | `low \| medium \| high` | 否 | 工具有效风险 | tool_approval 必填 |
| `decision` | `answer \| approve \| reject` | resolved 时是 | 解决决定 | 与类型匹配 |
| `answer` | `string` | 否 | 自由文本或多选值的稳定序列化 | 最大长度受限 |
| `selected_values` | `string[]` | 否 | 选择值 | 必须来自 options |

### ToolBinding / RuntimeToolPolicy

| 字段 | 类型 | 必填 | 说明 | 约束/默认值 |
| --- | --- | --- | --- | --- |
| `ToolBinding.approval` | `auto \| allow \| ask \| deny` | 否 | 单工具覆盖策略 | 默认 `auto` |
| `RuntimeToolPolicy.require_approval_for_high_risk` | `boolean` | 否 | auto 对 high 的行为 | 默认 `true` |

现有配置缺少字段时由 Pydantic 默认值兼容，无数据库迁移。

## 接口设计

### `POST /api/sessions/{session_id}/interactions/{action_id}/resolve`

- 输入：`decision`，以及按类型需要的 `answer`、`selected_values`。
- 输出：SSE；先返回 resolved interaction，随后返回恢复后的 Tool、Step、Message、Plan、Done/Error/Wait 事件。
- 权限：只允许 Session 当前所有者。
- 幂等/并发：仅第一个对 pending action 的有效请求成功；重复、过期、非 waiting 或非当前 pending action返回 409。
- 兼容性：新增接口，不修改现有 `/chat` 和 `/resume` 请求语义。

### Tool 配置接口

- `POST /api/tools/bindings` 沿用现有路径，接受新增 `approval` 与全局高风险确认字段。
- 旧客户端不传字段时由服务端默认值补齐。

## 错误处理与可观测性

- 400：决定与 interaction 类型不匹配、选项非法、回答为空或超限。
- 404：Session/action 不存在或不属于当前用户；不泄露其他用户动作是否存在。
- 409：动作已解决、Session 不在 waiting、不是当前 pending 动作、Memory/Tool Call 校验失败。
- 恢复失败时保留 pending/resolved 历史，并输出用户可行动的错误；原始异常进入 Trace。
- Run/Trace 记录 interaction pending/resolved、action_id、decision、tool_call_id、risk_level；不记录敏感自由文本以外的额外内部数据。

## 迁移与回滚

- 迁移：无需数据库迁移；旧 Session 无 interaction 事件时按原逻辑显示。
- 配置：旧 ToolConfig 自动补 `approval=auto` 和 `require_approval_for_high_risk=true`。
- 回滚：关闭全局高风险确认可使 `auto` 恢复为 allow；前端未知事件可由现有 normalize 层安全忽略。已经产生的 interaction 历史保留为审计记录。

## 风险

| 风险 | 可能性 | 影响 | 缓解措施 | 验证方式 |
| --- | --- | --- | --- | --- |
| 批准调用与实际执行不一致 | 中 | 高 | 四元组精确校验，服务端从 Memory 取原参数 | 篡改参数/ID 测试 |
| 重复点击创建多个恢复 Run | 中 | 高 | pending→resolved 原子校验与 Session waiting 门禁 | 并发接口测试 |
| Plan 快照与当前 Step 不一致 | 中 | 中 | 以未完成 Step + Tool Call Memory 双重校验 | 等待后重启恢复测试 |
| 旧配置上线后高风险工具开始询问 | 高 | 中 | 明确全局策略、可关闭、卡片解释风险 | 配置兼容测试和文档 |
| 参数包含密钥 | 低到中 | 高 | 复用/增加参数脱敏，只展示允许字段 | 敏感字段组件测试 |
| pending 动作跨用户访问 | 低 | 高 | 所有查询先按 session_id + user_id | 权限测试 |

## 重要假设

- Agent Memory 会在 Assistant Tool Call 写入后持久化；这是恢复原调用的事实来源。
- 当前一次仅处理一个 Tool Call，因此单 pending 动作约束不会降低现有并发能力。
- 用户同意第一批先交付结构化询问和批准/拒绝；参数编辑、多审批人属于后续增量。
- 高风险工具默认需要确认符合本次产品目标；用户可通过 RuntimeToolPolicy 关闭全局默认。

## 待决策项

- 无。按“优先落地 Human-in-the-loop，再做编辑/富消息”的既定顺序实施。

## 验收标准

- [ ] Agent 发出带选项的问题时，前端显示结构化卡片，支持键盘和触屏提交。
- [ ] 单选、多选、自由文本均经过服务端校验，并在历史中显示已回答状态。
- [ ] 高风险 `auto/ask` 工具在批准前没有执行记录或副作用。
- [ ] 批准后执行的 Tool Call ID、函数和参数与卡片完全一致；拒绝后工具不执行且 Agent 可继续选择替代方案。
- [ ] 刷新页面后 pending 卡片仍可操作；服务进程重启后可从持久化 Memory 恢复。
- [ ] 重复解决、跨用户解决和篡改参数均被拒绝，不创建重复 Run。
- [ ] 旧 Session、旧 ToolConfig、现有 chat/resume/SSE 和失败恢复测试保持通过。
- [ ] 前端单元测试、类型检查、生产构建、后端单元/接口/集成测试和 diff 检查通过。
