# Chat Human-in-the-loop 实施计划

## 关联设计

- 设计文档：`docs/designs/chat-human-in-the-loop.zh-CN.md`
- 开发分支：`feature/chat-human-in-the-loop`

## 当前进度

- 整体状态：`BLOCKED`
- 当前阶段：verification
- 当前任务：无；等待 PostgreSQL/Redis 与浏览器环境补验
- 已完成：6 / 6
- 阻塞问题：PostgreSQL/Redis 未启动；当前无可用浏览器实例
- 最近更新时间：2026-07-20 15:53（Asia/Shanghai）

## 全局约束

- 不修改现有 `/chat`、`/resume` 的公开语义，不新增数据库迁移。
- Interaction 使用追加式 Session JSONB 事件；同 action 的最新事件决定有效状态。
- 工具执行前必须校验原 Memory Tool Call，不能信任前端提交函数名或参数。
- `ask` 工具在批准前不得执行；`reject/deny` 路径不得产生副作用。
- 旧 Session 和缺少新字段的 ToolConfig 必须继续加载。
- 保留 Plan、Step、Tool、Run/Trace、文件预览、VNC 和现有失败恢复行为。
- 不修改用户已有的 `web/src/components.d.ts` 工作区变更。

## 状态变更记录

| 日期时间 | 整体状态 | 当前任务 | 变更原因 |
| --- | --- | --- | --- |
| 2026-07-20 11:00 | `PLAN_READY` | 无 | 设计确认并完成可恢复任务拆分 |
| 2026-07-20 11:05 | `IN_PROGRESS` | Task 1 | 已创建独立开发分支并开始契约测试 |
| 2026-07-20 11:34 | `IN_PROGRESS` | Task 2 | Task 1 的 15 项契约测试通过，开始运行时恢复实现 |
| 2026-07-20 12:32 | `IN_PROGRESS` | Task 4 | 运行时恢复和并发安全解决接口通过 26 项聚焦测试 |
| 2026-07-20 12:54 | `IN_PROGRESS` | Task 6 | 交互卡、策略设置、Trace 脱敏和文档已落地，进入完整验证 |
| 2026-07-20 13:22 | `BLOCKED` | 无 | 实现与可运行验证完成；数据库/Redis 依赖和真实浏览器环境不可用，不能完成最终合并门禁 |

## Task 1：建立 Interaction 事件与审批策略契约

状态：completed

### 目标

新增向后兼容的领域/SSE/前端类型和工具审批策略解析，并用单元测试锁定序列化、默认值与策略行为。

### 涉及文件

- `api/app/core/entities/event.py`
- `api/app/schemas/event.py`
- `api/app/core/entities/tool_config.py`
- `api/app/schemas/tool_config.py`
- `api/app/core/tools/base.py`
- `api/app/core/tools/filter.py`
- `api/app/core/tools/registry.py`
- `api/tests/app/core/test_interaction_events.py`（新建）
- `api/tests/app/core/tools/test_tool_management.py`
- `web/src/lib/api/types.ts`

### 依赖与接口

- 前置任务：无。
- 输入：设计文档中的 `InteractionEvent`、`ToolBinding.approval` 和全局高风险确认规则。
- 输出：Task 2、3、4 可依赖的稳定领域类型、SSE 结构和 `FilteredTool` 有效审批策略接口。

### 实施步骤

1. 定义 interaction 类型、状态、选项、决定与恢复载荷；加入 `Event` 判别联合和 EventMapper。
2. 为 ToolBinding 增加 `approval=auto|allow|ask|deny`，为 RuntimeToolPolicy 增加高风险默认确认字段。
3. 在 FilteredTool 暴露函数级风险和有效审批策略；系统消息工具按设计绕过通用审批。
4. 更新前端 API 类型，并增加旧配置缺字段、interaction SSE 往返和策略矩阵测试。

### 验证方式

- 运行：`py -m pytest agentic/api/tests/app/core/test_interaction_events.py agentic/api/tests/app/core/tools/test_tool_management.py -q`
- 预期：退出码 0；新增事件可序列化/反序列化，旧配置默认值和 allow/ask/deny/auto 策略全部通过。

### 完成条件

- 领域、SSE、配置和前端类型一致；策略解析只有一个事实来源；测试覆盖旧数据兼容。

### 执行结果

新增统一 `interaction` 领域/SSE/前端类型；ToolBinding 支持 `auto/allow/ask/deny`，RuntimeToolPolicy 默认对高风险工具要求确认。FilteredTool 统一解析有效风险和审批策略，消息交互工具绕过通用审批以防递归暂停。未修改数据库或实际执行路径。

### 验证证据

```text
命令：py -m pytest tests/app/core/test_interaction_events.py tests/app/core/tools/test_tool_management.py -q
退出状态：0
关键结果：15 passed；新增事件往返 2 项，旧配置与审批策略矩阵全部通过
执行时间：2026-07-20 11:34 Asia/Shanghai
```

## Task 2：实现暂停原 Tool Call 与精确恢复执行

状态：completed

### 目标

让结构化询问和工具审批在 BaseAgent/ReAct/PlannerReAct 中暂停，并在解决后从持久化 Memory 恢复同一 Tool Call。

### 涉及文件

- `api/app/core/tools/message.py`
- `api/app/core/agent/base.py`
- `api/app/core/agent/react.py`
- `api/app/core/flows/planner_react.py`
- `api/app/core/entities/message.py`
- `api/app/core/agent/agent_task_runner.py`
- `api/tests/app/core/agent/test_interaction_resume.py`（新建）
- `api/tests/app/services/test_agent_service_recovery.py`

### 依赖与接口

- 前置任务：Task 1。
- 输入：InteractionEvent 和 FilteredTool 有效审批策略。
- 输出：可由 Task 3 调用的 interaction response 恢复载荷和运行路径。

### 实施步骤

1. 扩展 `message_ask_user` Schema，规范选项、多选和自由文本字段。
2. BaseAgent 在 ask_user 或审批策略为 ask 时生成 pending interaction 并在调用前退出；deny 直接生成失败 Tool Result。
3. 新增恢复方法：从 React Memory 读取最后一个 Assistant Tool Call，校验 action/tool/function/canonical args；回答写为 Tool Result，批准执行原调用，拒绝只写失败结果。
4. ReActAgent 将 interaction 转换为 waiting；增加恢复当前 Step 的处理，复用 Step 结果解析。
5. PlannerReActFlow 识别 interaction response，跳过普通新消息回滚和重新规划，从当前未完成 Step 恢复；AgentTaskRunner 传递恢复载荷。
6. 覆盖批准前不调用、批准精确执行、拒绝无副作用、ask_user 回答、Memory 不匹配失败和进程重建恢复测试。

### 验证方式

- 运行：`py -m pytest agentic/api/tests/app/core/agent/test_interaction_resume.py agentic/api/tests/app/services/test_agent_service_recovery.py -q`
- 预期：退出码 0；测试 Spy 证明批准前/拒绝后调用次数为 0，批准后仅执行一次且参数完全一致。

### 完成条件

- ask_user 与 tool approval 均可在新 Task 中恢复原 Tool Call；任何校验失败都不执行工具。

### 执行结果

BaseAgent 在工具执行前暂停，ReAct/PlannerReAct 保留当前 Step 并通过新 Task 恢复；恢复严格比对持久化 Memory 中的 Tool Call ID、函数名和参数。ask_user 回答转换为 Tool Result，拒绝转换为失败结果且不调用工具。

### 验证证据

`test_interaction_resume.py` 5 项通过，覆盖批准、拒绝、结构化回答、防篡改和步骤恢复。

## Task 3：交付所有权、幂等和 SSE 解决接口

状态：completed

### 目标

提供按用户隔离、只解决一次并继续输出恢复事件的 interaction resolve API。

### 涉及文件

- `api/app/schemas/session.py`
- `api/app/services/agent_service.py`
- `api/app/controllers/session.py`
- `api/app/repositories/session_repository.py`
- `api/app/repositories/db_session_repository.py`
- `api/tests/app/interfaces/endpoints/test_session_interactions.py`（新建）
- `api/tests/app/services/test_agent_interactions.py`（新建）

### 依赖与接口

- 前置任务：Task 1、Task 2。
- 输入：`POST /sessions/{id}/interactions/{action_id}/resolve` 请求和 Task 2 恢复载荷。
- 输出：Task 4 使用的 SSE API。

### 实施步骤

1. 新增 resolve 请求校验，限制决定类型、回答长度、选项值和字段组合。
2. AgentService 按 session_id + user_id 查找最新 pending interaction，验证 waiting、当前动作和未解决状态。
3. 以并发安全方式追加 resolved interaction 并启动恢复 Task；如仓库无法一次完成比较写入，则使用行锁事务方法。
4. Controller 返回 resolved interaction 及后续恢复 SSE；把 400/404/409 映射为现有异常体系。
5. 增加跨用户、重复提交、并发提交、非法选项、非 waiting、action 不存在及成功恢复接口测试。

### 验证方式

- 运行：`py -m pytest agentic/api/tests/app/interfaces/endpoints/test_session_interactions.py agentic/api/tests/app/services/test_agent_interactions.py -q`
- 预期：退出码 0；跨用户不可见，重复/并发提交最多一个成功，成功响应包含 resolved interaction 和恢复事件。

### 完成条件

- API 权限、幂等、状态门禁和 SSE 行为符合设计，且不信任前端工具参数。

### 执行结果

新增 resolve SSE 接口；Session 领域校验最新 pending、回答形状和会话状态，DB Repository 使用 `SELECT ... FOR UPDATE` 原子追加 resolved 事件。跨用户统一不可见，重复/并发提交返回冲突。

### 验证证据

`test_agent_interactions.py` 与 `test_session_interactions.py` 共 6 项通过；与 Task 1、2 聚焦测试合计 26 项通过。

## Task 4：实现结构化问题卡和工具审批卡

状态：completed

### 目标

在会话时间线展示 pending/resolved interaction，并通过解决接口完成回答、批准和拒绝。

### 涉及文件

- `web/src/lib/api/session.ts`
- `web/src/lib/api/types.ts`
- `web/src/lib/session-events.ts`
- `web/src/composables/useSessionDetail.ts`
- `web/src/components/SessionDetailView.vue`
- `web/src/components/chat/InteractionCard.vue`（新建）
- `web/src/components/chat/ChatMessage.vue`
- `web/src/components/chat/chat.css`
- `web/src/components/chat/InteractionCard.spec.ts`（新建）
- `web/src/lib/session-events.spec.ts`

### 依赖与接口

- 前置任务：Task 1、Task 3。
- 输入：interaction SSE 与 resolve API。
- 输出：用户可访问的完整 Human-in-the-loop 操作面。

### 实施步骤

1. 时间线按 action_id 合并 pending/resolved 事件，旧客户端未知字段保持安全。
2. 问题卡实现单选、多选、自由文本、提交中、失败保留输入、已回答和只读历史状态。
3. 审批卡展示脱敏参数、风险、批准/拒绝、提交中和历史决定；参数 JSON 失败时降级显示。
4. useSessionDetail 接入 resolve SSE，复用 event_id 去重和当前流清理；解决期间 Session 状态切换为 running。
5. SessionDetailView 连接交互事件；pending 动作存在时通用 Composer 保持可见但禁用，避免绕过结构化解决。
6. 增加键盘、重复点击、失败重试、刷新历史合并和触屏可见操作测试。

### 验证方式

- 运行：`pnpm test:run -- src/components/chat/InteractionCard.spec.ts src/lib/session-events.spec.ts`
- 运行：`pnpm type-check`
- 预期：两条命令退出码 0；组件测试覆盖 ask_user、approve、reject、resolved 和 error 状态。

### 完成条件

- 用户能完成所有第一版交互；pending 不可被普通消息绕过；历史决定清晰且可访问。

### 执行结果

新增 InteractionCard，支持问题选项、自由文本、批准/拒绝、参数脱敏、错误重试和 resolved 只读历史；时间线按 action_id 合并状态，pending 时禁用普通 Composer。

### 验证证据

`InteractionCard.spec.ts` 与 `session-events.spec.ts` 共 5 项通过；`pnpm type-check` 退出码 0。

## Task 5：补齐策略配置、Trace 和产品文档

状态：completed

### 目标

让全局高风险默认确认可配置，并确保 interaction 决定进入现有可观测链路和文档。

### 涉及文件

- `web/src/lib/api/types.ts`
- `web/src/components/settings/SettingsApiToolsPanel.vue`
- `api/app/services/trace_service.py`
- `api/tests/app/services/test_trace_service.py`
- `web/src/components/settings/SettingsApiToolsPanel.spec.ts`（如现有挂载成本可控则新建）
- `docs/tool-management.zh-CN.md`
- `docs/librechat-ui-redesign.zh-CN.md`
- `docs/current-state.zh-CN.md`

### 依赖与接口

- 前置任务：Task 1、Task 3、Task 4。
- 输入：RuntimeToolPolicy 与 interaction 事件。
- 输出：用户可理解的默认策略、审计证据和最新状态文档。

### 实施步骤

1. 在工具策略设置中增加“高风险工具执行前确认”，保存到现有 bindings API。
2. Trace 投影 interaction pending/resolved 的 action、decision、tool_call、risk，不额外记录敏感参数。
3. 更新工具治理和 LibreChat UI 改造文档，明确已完成范围、默认行为、回滚开关和非功能范围。
4. 增加策略保存、Trace 脱敏和旧配置默认值测试。

### 验证方式

- 运行：`py -m pytest agentic/api/tests/app/services/test_trace_service.py -q`
- 运行：`pnpm test:run`
- 预期：退出码 0；Trace 不包含原始敏感参数，设置保存后重新加载保持一致。

### 完成条件

- 用户可控制全局默认，Trace 可审计且不泄露参数，文档与代码一致。

### 执行结果

通用设置新增“高风险工具执行前确认”；Trace 新增 interaction.pending/resolved，载荷不包含 function_args；工具治理、当前状态和 LibreChat UI 文档已同步。

### 验证证据

Trace 聚焦测试 2 项通过，其中交互测试证明敏感参数不会进入 interaction Trace；前端类型检查通过。

## Task 6：端到端回归、视觉检查与审查整改

状态：completed

### 目标

证明新闭环不破坏旧 Chat/恢复/工具/Skill 行为，完成代码审查整改并形成合并判断。

### 涉及文件

- `docs/plans/chat-human-in-the-loop-plan.md`
- `docs/reviews/chat-human-in-the-loop-review.md`（新建）
- 前述任务中测试或审查要求修改的文件

### 依赖与接口

- 前置任务：Task 1–5。
- 输入：完整实现和全部验收标准。
- 输出：最新验证证据、代码审查结论和 `READY_TO_MERGE/BLOCKED/FAILED`。

### 实施步骤

1. 运行聚焦测试、后端完整测试、前端完整测试、类型检查、生产构建和静态检查。
2. 使用真实或测试会话手工检查 ask_user、批准、拒绝、刷新后操作、移动端与暗色模式；环境不可用时记录未验证项，不伪造证据。
3. 按 code-review Skill 审查正确性、安全性、并发、兼容性、可维护性和测试质量。
4. 修复 blocking/major 问题，重新运行受影响验证；更新设计偏差、计划结果和最终状态。

### 验证方式

- 运行：`py -m pytest agentic/api/tests -q`
- 运行：`pnpm test:run`
- 运行：`pnpm type-check`
- 运行：`pnpm build`
- 运行：`git diff --check`
- 预期：所有适用命令退出码 0；审查无 blocking/major；手工检查通过或明确列出无法验证项。

### 完成条件

- 所有设计验收标准均有证据；审查结论允许合并；计划最终状态准确。

### 执行结果

完成实现审查和安全整改：内部恢复消息不再进入 Session 历史或 Message SSE，Interaction SSE 的工具参数在服务端递归脱敏。审查未发现 blocking/major 问题；保留一个 minor：interaction resolved 已提交但恢复 Task 尚未启动之间存在极小故障窗口，需要未来用持久化 outbox 或执行租约彻底消除。

### 验证证据

后端 7 个交互相关测试文件共 36 项通过，其中新增策略测试确认 Sandbox 文件读写默认放行且显式 `ask` 仍生效；前端 13 个测试文件共 34 项通过；`py_compile`、`pnpm type-check`、`pnpm build` 与 `git diff --check` 均退出 0。后端全量测试收集 173 项，其中 11 项因本机 PostgreSQL/Redis 拒绝连接失败；排除已知外部 Skill 套件后 150 项通过、1 项状态接口仍因 PostgreSQL 未启动报错。当前无可用浏览器实例，因此真实页面、移动端、暗色模式和可访问性视觉检查未执行。详见 `docs/reviews/chat-human-in-the-loop-review.md`。

## 计划变更

| 日期 | 变更内容 | 原因 | 影响任务 | 是否影响设计 |
| --- | --- | --- | --- | --- |
| 2026-07-20 | 初始计划 | 将已确认设计拆为六个可独立验证任务 | Task 1–6 | 否 |
| 2026-07-20 | Sandbox 文件写入/替换由高风险调整为中风险，`auto` 默认放行 | 避免 Agent 在受控工作区内每次文件修改都要求点击确认；保留显式审批覆盖 | Task 1、Task 6 | 是，细化风险分层 |

## 最终验证

### 执行命令

```powershell
py -m pytest tests/app/core/test_interaction_events.py tests/app/core/tools/test_tool_management.py tests/app/core/agent/test_interaction_resume.py tests/app/services/test_agent_interactions.py tests/app/services/test_agent_service_recovery.py tests/app/services/test_trace_service.py tests/app/interfaces/endpoints/test_session_interactions.py -q
py -m pytest tests -q
py -m pytest tests -q --ignore=tests/app/interfaces/endpoints/test_skill_routes.py --ignore=tests/app/repositories/test_skill_repository.py --ignore=tests/app/services/test_skill_service.py
py -m py_compile app/core/entities/event.py app/core/agent/base.py app/core/agent/react.py app/services/agent_service.py app/schemas/event.py
pnpm test:run
pnpm type-check
pnpm build
git diff --check
```

前端命令工作目录：`agentic/web`。后端命令工作目录：仓库根目录或按命令中的显式路径执行。

### 执行结果

- 单元测试：交互相关后端测试 36/36 通过；前端测试 34/34 通过。
- 集成测试：排除已知外部 Skill 套件后 150 项通过、1 项 PostgreSQL 连接错误；全量 173 项中 11 项因 PostgreSQL/Redis 未启动失败。
- 静态检查：相关 Python 文件 `py_compile` 与 `git diff --check` 通过。
- 类型检查：`pnpm type-check` 通过。
- 构建：`pnpm build` 通过。
- 数据库迁移：不适用；设计明确不新增迁移。
- 手工验证：当前没有可用浏览器实例；真实页面、移动端、暗色模式和可访问性视觉检查未验证，已明确记录。
- 代码审查：`APPROVED`，无 blocking/major；记录 1 个恢复启动故障窗口 minor。

### 验收标准检查

- [x] 结构化问题可回答且可恢复。
- [x] 高风险工具批准前不执行，批准精确执行，拒绝无副作用。
- [x] 刷新和服务重启后可恢复 pending interaction（由持久化 Memory 重建测试覆盖）。
- [x] 权限、幂等、并发和参数篡改测试通过。
- [ ] 旧 Session、旧配置和现有 Chat/Resume/Tool/Skill 回归通过。
- [x] 前端可访问性、移动端和暗色模式检查通过或有明确未验证记录。

### 未通过项目

- PostgreSQL/Redis 未启动，依赖这些服务的 11 项全量后端测试无法通过；真实 PostgreSQL 行锁路径未执行。
- 当前无可用浏览器实例，未进行真实页面、移动端、暗色模式和可访问性视觉检查。

### 最终状态

`BLOCKED`
