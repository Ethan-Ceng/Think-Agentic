# 对话编辑、重新生成与会话分支设计

## 文档状态

- 状态：`DESIGN_READY`
- 负责人：Codex
- 创建日期：2026-07-24
- 最近更新：2026-07-24

## 背景

当前消息操作仅提供复制；失败回复支持“重新生成回复”，但正常历史消息不能编辑、重新提交或从指定位置探索另一条路径。用户如果想修改早先问题，只能新建空会话并手工复制上下文。

LibreChat 的 Fork 会从指定消息创建新对话并保留原对话，Edit/Resubmit/Continue 则让用户沿历史节点探索不同结果。当前系统使用 Session JSONB 追加式事件、独立 Agent Memory、Run/Trace 和工具副作用记录，直接修改历史事件会破坏审计与恢复语义。因此本批次以“新 Session 分支”实现历史编辑与重新生成。

参考：

- LibreChat Fork：`https://www.librechat.ai/docs/features/fork`
- LibreChat 功能总览：`https://www.librechat.ai/docs/features`

## 目标

- 用户可从任意可见消息创建独立对话分支，原会话不变化。
- 用户可编辑历史用户消息并在新分支中立即重新提交。
- 用户可对正常 Assistant 回复执行“重新生成”，在新分支中重新运行对应用户回合。
- 新分支保留选定节点之前的可见上下文、附件引用和来源关系。
- 双击、网络重试和多标签页重复请求不会创建多个分支。

## 功能范围

- 消息操作增加“从这里分支”。
- 用户消息增加“编辑并重新提交”。
- Assistant 消息增加“重新生成回复”。
- 创建新 Session 并记录源 Session、目标事件、分支操作和幂等请求 ID。
- 分支只复制到目标边界的安全可见消息投影，不复制旧 Task、运行状态、Plan、Tool、Interaction、Error、Done 或隐藏事件。
- 为新 Session 保存可见对话上下文种子，使 Planner/ReAct 的新 Memory 在首次运行时获得分支上下文。
- 编辑与重新生成复用 durable next-message 槽位保存待运行输入；创建成功后由一次性导航意图启动，启动失败时仍可在新 Session 手工“发送”。
- Session 页面显示来源提示并允许返回源会话。

## 非功能范围

- 不在同一个 Session 内建立消息树或左右箭头切换 sibling branch。
- 不允许原地修改、删除或重排历史事件。
- 不复制旧工具调用结果作为模型隐藏上下文，也不重放工具副作用。
- 不编辑历史附件或 Skills；编辑操作沿用原用户消息的附件和 Skills。
- 不在运行中、waiting、processing next-message 或存在 queued next-message 时创建分支。
- 不实现公开分享、导入导出、Preset、Agent Builder 或 Projects。

## 业务流程

### 从这里分支

1. 用户打开任意可见用户/Assistant 消息操作菜单并选择“从这里分支”。
2. 前端提交源 Session、目标事件 ID、`operation=fork` 和客户端 UUID 请求 ID。
3. 服务端在事务内校验所有权、源 Session 可分支状态和目标事件。
4. 服务端创建 completed 新 Session，复制从开头到目标消息的安全可见投影，并保存 lineage/context seed。
5. 前端导航到新 Session；不自动运行，用户可继续输入。

### 编辑并重新提交

1. 用户在历史用户消息上选择“编辑并重新提交”。
2. 对话框预填原文本；附件和 Skills 只读沿用。
3. 服务端复制目标用户消息之前的可见历史，创建新 Session，并把编辑后的输入保存为 queued next-message。
4. 前端导航到新 Session，携带一次性 `runQueued` 导航意图。
5. 新页面调用现有 next-message run SSE；若启动或连接失败，queued 输入仍保留并显示“发送”按钮。

### 重新生成回复

1. 用户在正常 Assistant 消息上选择“重新生成回复”。
2. 服务端定位该 Assistant 消息所属回合最近的前置可见用户消息。
3. 服务端复制该用户消息之前的可见历史，并将原用户消息文本、附件和 Skills 保存为 queued next-message。
4. 前端按编辑流程导航并启动新分支；原回复及其工具副作用不变。

## 核心规则

1. 源 Session 永不被分支操作修改。
2. 可分支源必须属于当前用户，状态为 completed，且没有 next-message。
3. 目标必须是源 Session 中 `visible=true` 的 MessageEvent；编辑目标必须是 user，重新生成目标必须是 assistant。
4. `fork` 包含目标消息；`edit` 和 `regenerate` 的上下文边界都在待重新执行用户消息之前。
5. 新分支不继承 `sandbox_id`、`task_id`、旧 Agent memories、未读数、pending interaction 或运行状态。
6. 上下文种子只包含可见 user/assistant 文本与附件文件名；不包含工具参数、工具结果、内部错误、审批记录或隐藏恢复指令。
7. 附件只复用当前用户仍有权限访问的 File ID；缺失附件使创建请求返回 409，不静默删减。
8. `branch_request_id` 全局唯一；相同用户、源 Session 和请求 ID 重试时返回同一目标 Session。
9. 编辑和重新生成创建的是 durable queued 输入；只有带一次性导航意图的新页面会立即启动，普通刷新不会自动执行。
10. 新分支后续产生全新的 Run/Trace，不复用源 Session 的运行记录。

## 现有实现分析

### 相关代码与文档

- `agentic/api/app/core/entities/session.py`：Session 领域对象、状态、追加式 Interaction 和 next-message。
- `agentic/api/app/core/entities/event.py`：MessageEvent 有稳定 ID、role、visible、attachments 和 Skills。
- `agentic/api/app/models/session.py`：Session 的 events、files、memories、next_message 均存储为 JSONB。
- `agentic/api/app/repositories/db_session_repository.py`：提供用户隔离查询、JSONB 原子追加和 Session 行锁。
- `agentic/api/app/core/agent/base.py`：各 Agent 首次调用时从 Session 加载独立 Memory，并在空 Memory 时加入 system prompt。
- `agentic/api/app/services/agent_service.py`：普通 chat、next-message run、Task/Redis/SSE 生命周期。
- `agentic/web/src/lib/session-events.ts`：把追加式事件投影为可见时间线并保留 `sourceEventId`。
- `agentic/web/src/components/chat/MessageActions.vue`：当前只有复制操作。
- `agentic/web/src/composables/useSessionDetail.ts`：Session 快照、SSE epoch、next-message 恢复。
- `agentic/web/src/lib/session-init.ts`：已有一次性跨路由初始输入传递模式，可复用其消费思想。

### 可复用能力

- MessageEvent 的事件 ID 可作为稳定分支边界。
- next-message 提供可靠的“创建后待运行输入”与失败恢复。
- Session 所有权查询和行锁可承载幂等分支创建。
- 现有文件仓储可验证附件仍属于当前用户。
- SSE epoch、草稿保护和导航后恢复机制可继续使用。
- Search/Trace 使用 Session/Event ID，新分支天然生成独立记录。

### 当前约束

- Agent Memory 与可见事件分离，且 Memory 消息没有来源事件 ID，不能安全截断到任意历史节点。
- events 为单个 Session JSONB 数组，不适合直接升级为大规模消息树。
- 工具调用可能有不可逆副作用，分支不得复制或重放旧工具执行状态。
- 当前页面没有通用消息菜单、编辑弹窗或分支 lineage UI。

## 可选方案

### 方案 A：原地截断和修改源 Session

- 实现方式：删除目标之后的 events/memories，替换用户消息，再从源 Session 运行。
- 优点：页面和 URL 不变化，数据结构修改少。
- 缺点：破坏历史、Trace、搜索定位和用户审计；Memory 无法按事件精确截断。
- 风险：可能重复工具副作用，且并发刷新时容易看到混合历史。

### 方案 B：同 Session 消息树

- 实现方式：为每条消息增加 parent/children，Session 保存 active leaf；事件、Memory、搜索和 Trace 全部感知 branch path。
- 优点：最接近完整的左右分支切换体验，数据复制少。
- 缺点：需要重构事件投影、Memory、SSE 游标、搜索和工具步骤归属。
- 风险：迁移面大，容易破坏现有追加式交互和 next-message 状态机。

### 方案 C：新 Session 快照分支

- 实现方式：根据目标事件生成安全可见历史投影，创建带 lineage/context seed 的新 Session；编辑/重新生成输入通过 next-message 启动。
- 优点：源数据不变、权限清晰、可独立回滚；最大化复用当前 Session、事件和队列。
- 缺点：分支会复制可见消息；第一版不能在单页左右切换 sibling branch。
- 风险：必须明确 Memory context seed 与附件引用语义，并控制批量分支带来的存储增长。

## 方案对比

| 维度 | 方案 A：原地修改 | 方案 B：消息树 | 方案 C：新 Session |
| --- | --- | --- | --- |
| 实现复杂度 | 中 | 高 | 中 |
| 维护成本 | 高，历史语义易损坏 | 高，所有消费者需 branch-aware | 中，沿用 Session 边界 |
| 兼容性 | 差 | 中，需要历史迁移 | 好，旧 Session 无新字段也可加载 |
| 测试难度 | 高，需验证破坏性回滚 | 很高，组合路径多 | 中，源不变与新分支可独立断言 |
| 主要风险 | 数据丢失、副作用重放 | 全链路状态机回归 | 上下文种子和存储增长 |
| 交付成本 | 表面低、长期高 | 很高 | 可控 |

## 推荐方案

选择方案 C：新 Session 快照分支。

当前 Session 已是用户隔离、运行、文件和 Trace 的稳定边界；新 Session 能保证原历史与工具副作用不可变。与方案 A 相比，它不会为“编辑”牺牲审计；与方案 B 相比，它不要求一次重写事件、Memory、SSE 和搜索模型。第一版牺牲同页 sibling 切换，但已覆盖用户最关键的编辑、重新生成和探索替代路径。

## 数据结构

### Session 新字段

| 字段 | 类型 | 必填 | 说明 | 约束/默认值 |
| --- | --- | --- | --- | --- |
| `source_session_id` | `string/null` | 否 | 直接来源 Session | 普通索引、不建外键；源删除后保留不可导航的 lineage ID |
| `forked_from_event_id` | `string/null` | 否 | 分支边界 MessageEvent ID | 只用于 lineage，不作为跨用户查询条件 |
| `branch_operation` | `fork/edit/regenerate/null` | 否 | 创建分支的动作 | 普通 Session 为 null |
| `branch_request_id` | `uuid string/null` | 否 | 客户端幂等 ID | 唯一索引 |
| `context_seed` | `JSONB list` | 是 | 新 Agent Memory 的可见上下文种子 | 默认 `[]`，只允许 user/assistant 文本投影 |

### BranchContextMessage

| 字段 | 类型 | 必填 | 说明 | 约束/默认值 |
| --- | --- | --- | --- | --- |
| `role` | `user/assistant` | 是 | 对话角色 | 不允许 system/tool |
| `content` | `string` | 是 | 可见消息文本 | 最大长度沿用 MessageEvent；服务端生成 |
| `attachment_names` | `list[string]` | 是 | 上下文提示中的附件名 | 默认 `[]`，不含路径和凭据 |

### 分支 Session 初始化

- `status=completed`
- `sandbox_id=null`
- `task_id=null`
- `memories={}`
- `next_message=null`（fork）或新的 queued NextMessage（edit/regenerate）
- `events` 为安全可见 MessageEvent 副本，副本生成新 event ID；Session 级 lineage 记录直接分支来源和边界
- `files` 为被复制可见事件引用且仍可访问的文件集合

## 接口设计

### `POST /sessions/{session_id}/branches`

- 输入：
  - `operation`: `fork | edit | regenerate`
  - `target_event_id`: 非空字符串
  - `request_id`: UUID
  - `message`: edit 必填，trim 后 1–10000；其他操作禁止
- 输出：
  - `session_id`
  - `source_session_id`
  - `forked_from_event_id`
  - `operation`
  - `queued`: edit/regenerate 为 true
- 权限：当前登录用户必须拥有源 Session 和所有沿用附件。
- 幂等/并发：
  - 源 Session 以行锁读取并校验 completed/no-next-message。
  - `branch_request_id` 唯一；重复请求返回已创建分支。
  - 重复 request_id 必须同时匹配当前用户、源 Session、目标事件和 operation；不匹配返回 409。
  - 相同目标的不同 request ID 可创建多个独立分支。
- 兼容性：新增接口和可空字段；旧客户端、旧 Session 不受影响。

### `GET /sessions/{session_id}` 扩展

- 输出新增可空 lineage：
  - `source_session_id`
  - `source_session_title`
  - `forked_from_event_id`
  - `branch_operation`
- 权限：仅当来源 Session 仍属于当前用户时返回可导航来源；否则只显示“来自历史分支”而不暴露 ID/标题。

### Agent Memory context seed

- `SessionRepository.get_context_seed(session_id)` 返回服务端生成的 BranchContextMessage 列表。
- BaseAgent 首次初始化空 Memory 时按顺序加入：
  1. Agent 自身 system prompt；
  2. context seed 的 user/assistant 消息；
  3. 当前调用消息。
- Memory 一旦持久化则不重复注入 seed。

## 错误处理与可观测性

- 404：源 Session、目标事件或来源附件不存在/无权访问，对外不区分越权与不存在。
- 409：源仍在 running/waiting、存在 next-message、目标角色不符合操作、来源附件已不可用。
- 422：operation/message/request_id 格式错误。
- 分支创建记录结构化日志：user、source session、target event、operation、new session、idempotent replay；不记录消息全文。
- Trace 从新分支首次运行开始新建，不把分支创建伪装成模型 Run。
- 建议指标：branch_created_total、branch_idempotent_replay_total、branch_conflict_total，按 operation 聚合。

## 迁移与回滚

- 迁移：为 sessions 增加 5 个可空/默认字段及 source/request 索引；历史 Session 默认无 lineage、`context_seed=[]`。
- 不回填历史数据，不解析既有 memories。
- 回滚：先下线 UI 和 branches API，再删除索引及字段；新分支仍是普通 Session，删除 lineage 不影响其对话历史。
- 如果 context seed 注入发现模型兼容问题，可通过配置暂时禁用自动 seed；新 Session 仍可打开和手工继续。

## 风险

| 风险 | 可能性 | 影响 | 缓解措施 | 验证方式 |
| --- | --- | --- | --- | --- |
| 分支上下文与源 Agent Memory 不完全一致 | 中 | 中 | 明确只继承可见上下文，不复制隐藏工具状态 | LLM 输入快照测试和人工语义检查 |
| 编辑后重复执行外部副作用 | 中 | 高 | 新分支不复制工具状态；UI 明示“将重新执行后续任务”，审批策略照常生效 | 工具 mock 与审批回归 |
| 重复点击创建多个分支 | 中 | 中 | request_id 唯一、服务端幂等返回 | 并发仓储测试 |
| 源 Session 在创建分支时重新启动 | 低 | 高 | 同一 Session 行锁内校验状态和 next-message | 竞争测试 |
| 附件已删除或越权 | 中 | 中 | 创建时逐个验证，缺失即 409 | 权限和删除附件测试 |
| JSONB 复制导致存储增长 | 中 | 中 | 第一版只复制安全可见消息；限制单次事件数和请求频率 | 大会话基准与速率限制测试 |
| 一次性自动启动丢失 | 低 | 低 | 输入先持久 queued；失败后显示手工“发送” | 导航刷新和断网测试 |

## 重要假设

- 本批次“分支”定义为新 Session，而不是同 Session 内消息树。
- 用户更重视原历史不可变和可追溯，而不是第一版的同页左右分支切换。
- 编辑只修改文本；附件和 Skills 沿用原用户消息。
- 分支上下文只包含用户能看到的对话，不包含隐藏 Tool/Memory 内容。
- 用户已确认上一批审批、HITL、运行可靠性和 next-message 交互验收无问题。

## 待决策项

无。上述范围按最小可交付版本确定；同 Session sibling 导航、附件编辑和完整工具上下文复制作为后续独立设计，不阻塞本批次。

## 验收标准

- [ ] 从任意可见用户/Assistant 消息创建分支后打开新 Session，源 Session 的 events、memories、files、status 和 Trace 不变化。
- [ ] 编辑历史用户消息会创建新 Session，显示编辑后的用户消息并开始新 Run；原消息保持不变。
- [ ] 重新生成正常 Assistant 回复会在新 Session 中重放对应用户输入，且不会复制或重放旧工具执行记录。
- [ ] fork 分支包含目标可见消息但不自动运行；edit/regenerate 只复制待重放用户消息之前的历史。
- [ ] 新 Agent 首次模型调用包含按顺序排列的可见 context seed、自身 system prompt 和新输入，不包含工具参数、错误或隐藏消息。
- [ ] 原消息附件和 Skills 被安全沿用；附件删除或越权时返回 409 且不创建半成品 Session。
- [ ] 同一 request_id 的并发或重试只生成一个分支并返回同一 session_id。
- [ ] running、waiting、存在 queued/processing next-message 的源 Session 返回 409。
- [ ] 自动启动失败、刷新或路由中断后，编辑/重新生成输入仍以 queued 状态可恢复。
- [ ] 旧 Session、普通发送、next-message、HITL、搜索、文件和 Trace 回归通过。
- [ ] 桌面、移动端、暗色模式、键盘操作和屏幕阅读器标签通过页面验收。
