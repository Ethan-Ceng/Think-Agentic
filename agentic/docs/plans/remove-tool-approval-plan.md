# 移除通用 Tool Approval 实施计划

## 关联设计

- 主设计：`agentic/docs/designs/agent-runtime-hitl-provider-reliability.zh-CN.md`
- 被替代设计：`agentic/docs/designs/configurable-tool-approval.zh-CN.md`
- 关联设计：`agentic/docs/designs/chat-human-in-the-loop.zh-CN.md`
- 开发分支：`feature/remove-tool-approval`
- 实施基线：`develop@6cabc3d`

## 当前进度

- 整体状态：`READY_TO_MERGE`
- 当前阶段：complete
- 当前任务：无
- 已完成：6 / 6
- 阻塞问题：无
- 最近更新时间：2026-08-18 16:37（Asia/Shanghai）

## 目标

从目标架构和产品交互中移除通用 `tool_approval`。终端用户不再承担 Shell、File、Browser 或外部 Provider 调用的平台安全判断；平台通过 Sandbox 隔离、能力授权、网络策略、禁止策略和审计承担安全责任。

本批次交付以下可验证结果：

1. 新 Agent Run 不再创建 `tool_approval` Interaction，高风险标签不再触发等待。
2. `message_ask_user` 继续创建 `ask_user` Interaction，并保持持久化等待语义。
3. 显式平台 `deny` 仍然拒绝工具，且不会退化为自动执行或用户审批。
4. 设置 API、领域配置和前端设置页不再暴露通用审批配置。
5. 历史 `tool_approval` 事件仍可读取，但永远不能再批准执行；待审批历史会在用户发送下一条普通消息时自动安全收敛为“未执行”，不会继续阻塞输入。
6. MCP/A2A Provider Runtime 的能力筛选、连接生命周期和外部写授权不在本批次实现；本批次只保留清晰的服务端策略边界，避免把两次架构升级混在一起。

## 全局约束

- 不把“移除审批”实现为“全部工具无条件放行”。`deny`、Tool 启用状态、Provider 能力授权和现有安全校验必须继续生效。
- `risk_level` 可继续作为遥测、审计和策略输入，但不能触发面向终端用户的逐次确认。
- `WAITING` 只表示等待业务输入；本批次允许 `ask_user`，不允许新建 `tool_approval`。
- 为兼容数据库中的历史 JSON，后端和前端可保留 `tool_approval`、`approve/reject` 的只读解析能力，但不得从新运行写入审批，也不得执行历史批准。
- 历史待审批工具调用在下一条普通用户消息开始前必须原子收敛：追加拒绝/取消 resolution、为悬空 tool call 补充“未执行”的 ToolResult，并允许新 Run 正常领取。任何失败都不得执行旧工具。
- 前端不得因历史 `tool_approval` 禁用输入框；历史卡片仅说明该机制已停用和调用未执行，不显示“批准执行”按钮。
- 不新增数据库 Schema 迁移；兼容和收敛基于现有 Session events/memories JSON 完成。
- 保留用户现有 `agentic/api/.env` 修改，不读取、不输出、不纳入本批次。
- 不自动提交、推送、创建 PR 或合并。
- 一次只推进一个 Task；状态、偏差和验证证据完成后立即写回本计划。

## 状态变更记录

| 日期时间 | 整体状态 | 当前任务 | 变更原因 |
| --- | --- | --- | --- |
| 2026-08-18 15:33 | `PLAN_READY` | 无 | 设计已确认，拆分为零审批运行时、历史收敛、配置契约和前端交互六个任务 |
| 2026-08-18 15:36 | `IN_PROGRESS` | Task 1 | 已创建 `feature/remove-tool-approval` 分支，开始固定零审批 Tool Loop 契约 |
| 2026-08-18 15:42 | `IN_PROGRESS` | Task 2 | Task 1 零审批 Tool Loop 契约验证通过，开始处理历史待审批会话 |
| 2026-08-18 15:47 | `IN_PROGRESS` | Task 3 | Task 2 历史审批原子收敛与 Memory 修复验证通过，开始清理配置/API 契约 |
| 2026-08-18 15:53 | `IN_PROGRESS` | Task 4 | Task 3 ToolConfig v2 与业务 Interaction API 契约验证通过，开始清理前端审批体验 |
| 2026-08-18 16:02 | `IN_PROGRESS` | Task 5 | Task 4 设置页、历史只读卡片与 WAITING 输入语义验证通过，开始全链路残留检查 |
| 2026-08-18 16:21 | `VERIFYING` | Task 6 | Task 5 全链路检索、文档收口、后端 456 项和前端 185 项全量回归通过；进入独立审查与最终门禁 |
| 2026-08-18 16:22 | `REVIEWING` | Task 6 | 首轮最终验证通过：后端全量、Ruff、前端测试/类型/构建、迁移和 diff 门禁均有最新证据；开始分级代码审查 |
| 2026-08-18 16:27 | `IN_PROGRESS` | Task 6 | 自检发现 major：内部 `execution_policy` 被公共 `/tools/bindings` 写模型暴露，旧 `approval=ask` 可能静默迁移为 allow；要求整改 |
| 2026-08-18 16:29 | `VERIFYING` | Task 6 | 新增终端用户专用 ToolBindingUpdate，拒绝 `approval/execution_policy`，保留内部历史迁移；17 项工具测试、Ruff 和前端类型检查通过，开始最终全量门禁 |
| 2026-08-18 16:37 | `READY_TO_MERGE` | 无 | major 已整改并复审关闭；后端 460 项、前端 185 项、静态检查、类型检查、构建、迁移及 diff 门禁全部通过 |

## Task 1：固定零审批 Tool Loop 契约

状态：completed

### 目标

先用失败测试证明当前 Tool Loop 会因高风险工具进入审批，再将运行时改为：只有 `message_ask_user` 会暂停；允许的工具直接执行；显式 `deny` 立即返回失败 ToolResult。

### 涉及文件

- `agentic/api/tests/app/core/agent/test_interaction_resume.py`
- `agentic/api/tests/app/core/agent/test_tool_loop.py`（若现有覆盖不足则新建）
- `agentic/api/app/core/agent/base.py`
- `agentic/api/app/core/tools/base.py`
- `agentic/api/app/core/tools/filter.py`
- `agentic/api/app/core/prompts/en/react.py`
- `agentic/api/app/core/prompts/react.py`

### 实施步骤

1. 增加高风险 Shell 工具在策略为 `auto/ask` 时仍直接执行且不产生 InteractionEvent 的测试。
2. 保留 `message_ask_user` 进入 `ASK_USER/PENDING` 并暂停工具循环的测试。
3. 增加显式 `deny` 不调用工具、返回失败 ToolResult、不中断为等待的测试。
4. 删除 BaseAgent 对通用 approval policy 的暂停分支，`_build_interaction_event()` 只允许构造 `ASK_USER`。
5. 将 FilteredTool 的运行时判断收敛为启用/允许/拒绝，不再把 high-risk 或 `ask` 转换为用户审批。
6. 删除中英文 ReAct Prompt 中“需要审批的工具会由运行时暂停”的旧说明；Prompt 只保留业务输入使用 `message_ask_user`，不把审批消除依赖于提示词约束。

### 验证方式

- `cd agentic/api && uv run pytest tests/app/core/agent/test_interaction_resume.py tests/app/core/tools/test_tool_management.py -q`
- `cd agentic/api && uv run ruff check app/core/agent/base.py app/core/tools/base.py app/core/tools/filter.py tests/app/core/agent/test_interaction_resume.py`

### 完成条件

- 新 Tool Loop 只有 `ask_user` 能创建 Interaction。
- 高风险标签不导致等待，显式 `deny` 仍强制失败。

### 执行结果

- 先将测试改为目标契约，修改前得到 4 个预期失败：高风险工具和 Shell 仍产生审批，FilteredTool 仍把 high-risk/旧 `ask` 解析为 `ask`。
- BaseAgent 的 Interaction 构造器现在只接受 `message_ask_user`；Tool Loop 只因业务输入暂停。
- FilteredTool 将历史 `ask` 与 high-risk 默认值解释为 `allow`，只保留显式 `deny` 的强制阻断。
- 中英文 ReAct Prompt 已删除旧审批说明，只保留业务输入使用 `message_ask_user`；零审批契约完全由运行时代码保证。
- Shell 自动执行回归确认 Lazy Sandbox 只创建一次，且没有 InteractionEvent。

### 验证证据

```text
命令：uv run pytest tests/app/core/agent/test_interaction_resume.py tests/app/core/tools/test_tool_management.py -q
退出状态：0
关键结果：22 passed，11 个既有 Pydantic deprecation warnings
执行时间：2026-08-18 15:41（Asia/Shanghai）

命令：uv run ruff check app/core/agent/base.py app/core/tools/base.py app/core/tools/filter.py app/core/prompts/react.py app/core/prompts/en/react.py tests/app/core/agent/test_interaction_resume.py tests/app/core/tools/test_tool_management.py
退出状态：0
关键结果：All checks passed
执行时间：2026-08-18 15:41（Asia/Shanghai）
```

## Task 2：安全收敛历史待审批会话

状态：completed

### 目标

让用户打开旧会话后可直接输入下一条消息。领取新 Run 时，后端在同一并发控制边界内把旧待审批调用标记为未执行，并补齐模型所需的 tool result，避免悬空 tool call 导致 Chat Completions 请求失败。

### 涉及文件

- `agentic/api/app/core/entities/session.py`
- `agentic/api/app/core/entities/memory.py`
- `agentic/api/app/core/entities/event.py`
- `agentic/api/app/repositories/session_repository.py`
- `agentic/api/app/repositories/db_session_repository.py`
- `agentic/api/app/services/agent_service.py`
- `agentic/api/tests/app/repositories/test_db_session_organization.py`
- `agentic/api/tests/app/services/test_agent_service_recovery.py`
- `agentic/api/tests/app/core/test_interaction_events.py`

### 实施步骤

1. 构造状态为 `WAITING`、最新 Interaction 为历史 `TOOL_APPROVAL/PENDING`、ReAct memory 以 assistant tool call 结尾的回归夹具。
2. 在 Session/Memory 领域方法中识别并关闭所有悬空 tool call，为每个 call 追加合规的 ToolResult，内容只说明机制已停用且工具未执行，不复制敏感参数。
3. 在 `claim_execution` 的行锁/原子领取路径中，仅当开始普通新 Run 时收敛历史待审批：追加 `REJECT/RESOLVED` 事件、修复 memory、再把 Session 置为 `RUNNING`。
4. 证明旧 tool call 从未调用，重复领取不会重复追加 resolution/tool result，并发领取仍只有一个执行者。
5. 禁止旧 `APPROVE` resolution 执行工具；兼容入口收到批准时返回明确的已停用错误，拒绝/历史读取保持安全兼容。
6. 覆盖 memory 缺失、事件已解决、`ASK_USER/PENDING` 和普通 `COMPLETED` Session，确保只处理目标历史状态。

### 验证方式

- `cd agentic/api && uv run pytest tests/app/repositories/test_db_session_execution_claim.py tests/app/services/test_agent_service_recovery.py tests/app/core/test_interaction_events.py -q`
- `cd agentic/api && uv run ruff check app/core/entities/session.py app/core/entities/memory.py app/repositories/db_session_repository.py app/services/agent_service.py`

### 完成条件

- 旧审批永远不执行；直接发新消息可以启动新 Run。
- 发送给模型的消息序列不存在未闭合的 assistant tool call。
- `ask_user` 的等待与回答路径不受影响。

### 执行结果

- 新增 `Memory.close_pending_tool_calls()`，只在 Memory 尾部包含目标历史 Tool Call 时生效，并为同一 assistant 消息中的每个 Tool Call 追加不含参数的失败 ToolResult。
- 新增 `Session.retire_pending_tool_approval()`：仅处理当前最新的历史 `TOOL_APPROVAL/PENDING`，以 `REJECT/RESOLVED` 追加收敛事件；重复调用幂等。
- `DBSessionRepository.claim_execution()` 在行锁内完成历史事件与 Memory 修复，再领取新 Run；若后续 Task 创建失败，恢复为 `COMPLETED` 而不是无待处理动作的 `WAITING`。
- Session resolution 与 BaseAgent continuation 均拒绝历史 `APPROVE`，即使绕过前端也不能执行旧工具；历史 reject 只产生“未执行”结果。
- 普通 `ASK_USER/PENDING` 不会被该兼容逻辑误处理。

### 验证证据

```text
命令：uv run pytest tests/app/core/test_interaction_events.py tests/app/repositories/test_db_session_organization.py tests/app/core/agent/test_interaction_resume.py tests/app/services/test_agent_service_recovery.py -q
退出状态：0
关键结果：48 passed，11 个既有 Pydantic deprecation warnings
执行时间：2026-08-18 15:46（Asia/Shanghai）

命令：uv run ruff check app/core/entities/memory.py app/core/entities/session.py app/repositories/db_session_repository.py app/core/agent/base.py tests/app/core/test_interaction_events.py tests/app/repositories/test_db_session_organization.py tests/app/core/agent/test_interaction_resume.py
退出状态：0
关键结果：All checks passed
执行时间：2026-08-18 15:46（Asia/Shanghai）
```

## Task 3：移除审批配置与 API 写模型

状态：completed

### 目标

让 ToolConfig 只管理工具启用、平台允许/禁止和后续 Provider 策略，不再向新客户端返回或接受“高风险需确认”和逐工具审批设置。

### 涉及文件

- `agentic/api/app/core/entities/tool_config.py`
- `agentic/api/app/schemas/tool_config.py`
- `agentic/api/app/services/tool_config_service.py`
- `agentic/api/app/controllers/tools.py`
- `agentic/api/tests/app/core/tools/test_tool_management.py`
- `agentic/api/tests/app/interfaces/endpoints/test_tools.py`（按实际路径调整）
- `agentic/api/tests/app/services/test_agent_interactions.py`
- `agentic/api/app/schemas/session.py`

### 实施步骤

1. 先固定 Tool List/Update 新契约：响应无 `approval_tools`，绑定无 approval，runtime policy 无 `require_approval_for_high_risk`。
2. 从 Pydantic schema、service merge 和内置 approval settings 中移除审批字段与生成逻辑。
3. 对数据库中历史 binding/runtime JSON 做读取兼容：旧字段允许被忽略，不影响启用状态和显式 `deny`；新写入不再生成旧字段。
4. 清理 Session API 文档和测试中把业务 Interaction 描述为工具审批的内容。
5. 将只为了测试 continuation 的 approval fixture 改为 `ASK_USER/ANSWER`，避免新测试继续制造审批。

### 验证方式

- `cd agentic/api && uv run pytest tests/app/core/tools/test_tool_management.py tests/app/interfaces/endpoints/test_session_interactions.py tests/app/services/test_agent_interactions.py -q`
- `cd agentic/api && uv run ruff check app/core/entities/tool_config.py app/schemas/tool_config.py app/services/tool_config_service.py tests/app/core/tools/test_tool_management.py`

### 完成条件

- 新 ToolConfig API 不再包含通用审批字段。
- 旧配置可读取，新写配置不再保存 approval。

### 执行结果

- ToolConfig 升级为 `tool_config_v2`：`ToolBinding.approval` 被确定性的 `execution_policy: allow|deny` 取代，RuntimeToolPolicy 删除高风险审批开关。
- 历史 `approval=deny` 在反序列化时迁移为平台 `execution_policy=deny`；`ask/allow/auto` 迁移为 `allow`。历史字段被忽略且不会再次写回。
- BaseTool/FilteredTool 的内部方法从 `get_approval_policy()` 更名为 `get_execution_policy()`，消除运行时审批语义。
- Tool List 响应删除 `approval_tools`；设置写模型不再接受或保存审批字段，且不允许终端用户写内部 `execution_policy`，但保留旧 JSON 读取迁移。
- 公共 Interaction resolve 请求现在只接受 `answer`，`approve/reject` 在 API Schema 层即被拒绝；历史事件枚举只用于反序列化。
- 测试中用于验证 Skill continuation 的审批夹具已改为 `ASK_USER/ANSWER`。

### 验证证据

```text
命令：uv run pytest tests/app/core/tools/test_tool_management.py tests/app/core/agent/test_interaction_resume.py tests/app/services/test_agent_interactions.py tests/app/interfaces/endpoints/test_session_interactions.py tests/app/core/test_interaction_events.py tests/app/repositories/test_db_session_organization.py -q
退出状态：0
关键结果：60 passed，11 个既有 Pydantic deprecation warnings
执行时间：2026-08-18 15:52（Asia/Shanghai）

命令：uv run ruff check app/core/entities/tool_config.py app/schemas/tool_config.py app/services/tool_config_service.py app/core/tools/base.py app/core/tools/filter.py app/core/agent/base.py app/schemas/session.py tests/app/core/tools/test_tool_management.py tests/app/core/agent/test_interaction_resume.py tests/app/services/test_agent_interactions.py tests/app/interfaces/endpoints/test_session_interactions.py
退出状态：0
关键结果：All checks passed
执行时间：2026-08-18 15:52（Asia/Shanghai）
```

## Task 4：移除前端审批设置与终端用户安全判断

状态：completed

### 目标

从设置页、Interaction 卡片和输入阻塞逻辑中移除通用审批体验，同时保留 `ask_user` 表单和历史事件只读展示。

### 涉及文件

- `agentic/web/src/lib/api/types.ts`
- `agentic/web/src/components/settings/SettingsGeneralPanel.vue`
- `agentic/web/src/components/settings/SettingsGeneralPanel.spec.ts`
- `agentic/web/src/components/settings/SettingsApiToolsPanel.vue`
- `agentic/web/src/components/chat/InteractionCard.vue`
- `agentic/web/src/components/chat/InteractionCard.spec.ts`
- `agentic/web/src/views/SessionDetailView.vue`
- `agentic/web/src/views/SessionDetailView.spec.ts`（或实际测试文件）
- `agentic/web/src/composables/useSessionDetail.ts`
- `agentic/web/src/lib/session-events.ts`

### 实施步骤

1. 删除设置页“高风险工具确认”总开关和逐工具 approval 控件；保存 payload 不再包含审批字段。
2. TypeScript 新写契约移除 approval 配置类型；历史 Interaction union 保留 `tool_approval` 解析分支并标注 deprecated。
3. `pendingInteraction` 和 waiting 判定只把 `ask_user` 视为业务等待；历史待审批不得禁用 ChatInput。
4. 历史 approval 卡片只读显示“审批机制已停用、调用不会执行、可直接继续输入”，不显示批准/拒绝按钮，不泄露敏感参数。
5. 保持 `ask_user` 的提交、已回答展示、刷新恢复和错误重试行为。
6. 增加前端测试，证明设置项消失、历史审批不阻塞输入、ask_user 仍阻塞并可回答。

### 验证方式

- `cd agentic/web && pnpm test:run -- SettingsGeneralPanel.spec.ts InteractionCard.spec.ts SessionDetailView.spec.ts`
- `cd agentic/web && pnpm type-check`

### 完成条件

- 终端用户界面没有任何“是否批准平台工具”的决策入口。
- 历史审批不再卡住输入，ask_user 行为保持完整。

### 执行结果

- 通用设置页删除高风险确认总开关、逐工具审批列表、审批提示和对应样式；API Tools 面板同步采用无审批 RuntimeToolPolicy。
- TypeScript 新写契约删除 `approval_tools`、`require_approval_for_high_risk` 和 Tool Approval Policy；resolve 请求只能提交 `answer`。
- 历史 `tool_approval/approve/reject` 仅保留在事件读取 union，并有明确 deprecated 注释。
- 历史审批卡片不显示参数、风险判断或批准/拒绝按钮，只说明旧机制已停用；已解决记录按当时结果只读展示。
- SessionDetail 只把 pending `ask_user` 视为阻塞性业务 Interaction。只有旧审批的 WAITING Session 会显示“可继续输入”，Composer 保持启用。
- `useSessionDetail` 只根据 `ask_user` Interaction 改变 WAITING 状态；工具历史事件不再影响运行态。

### 验证证据

```text
命令：pnpm test:run -- src/components/settings/SettingsGeneralPanel.spec.ts src/components/chat/InteractionCard.spec.ts src/components/SessionDetailView.spec.ts src/composables/useSessionDetail.spec.ts src/lib/session-events.spec.ts
退出状态：0
关键结果：5 个测试文件、38 项测试全部通过
执行时间：2026-08-18 16:00（Asia/Shanghai）

命令：pnpm type-check
退出状态：0
关键结果：vue-tsc -b 通过
执行时间：2026-08-18 16:01（Asia/Shanghai）
```

## Task 5：全链路回归与文档收口

状态：completed

### 目标

清除运行时代码、提示词、API 和 UI 中仍会创建或宣传通用审批的残留，并用中英文、流式事件、多轮会话和错误恢复回归证明改造没有破坏 Lead Agent 主链路。

### 涉及文件

- `agentic/api/app/**`
- `agentic/api/tests/**`
- `agentic/web/src/**`
- `agentic/docs/designs/agent-runtime-hitl-provider-reliability.zh-CN.md`
- `agentic/docs/designs/configurable-tool-approval.zh-CN.md`
- `agentic/docs/designs/chat-human-in-the-loop.zh-CN.md`
- 本计划

### 实施步骤

1. 全局检索 `tool_approval`、`require_approval_for_high_risk`、`approval_tools`、`approval=ask` 和用户可见审批文案，逐项分类为历史兼容或应删除残留。
2. 回归中文和英文用户输入，确认 Prompt 不再诱导 Agent 请求工具审批。
3. 回归 `ask_user`、普通 Sandbox Tool、显式 deny、工具异常、模型异常和连续多轮消息。
4. 更新设计文档的实现状态和实际兼容策略；记录 MCP/A2A Provider Runtime 为后续独立批次。
5. 将定向测试、全量测试和构建证据写回计划。

### 验证方式

- `cd agentic/api && uv run pytest tests/app/core/agent tests/app/core/tools tests/app/services/test_agent_interactions.py tests/app/interfaces/endpoints/test_session_interactions.py -q`
- `cd agentic/api && uv run ruff check app tests`
- `cd agentic/web && pnpm test:run`
- `cd agentic/web && pnpm type-check`
- `cd agentic/web && pnpm build`
- `git diff --check`

### 完成条件

- 代码检索中所有审批残留都有明确的“历史只读兼容”理由，且无新建路径。
- 后端定向/全量测试、前端测试、类型检查和构建通过。

### 执行结果

- 运行时代码全局检索后，`tool_approval` 仅保留在历史事件枚举、旧 pending 会话原子收敛、只读前端卡片及对应兼容测试；没有新建 Interaction、批准执行或输入阻塞旁路。
- 按用户对 `mooc-manus` 的观察，删除了中英文 ReAct Prompt 中审批专用约束；仅删除旧的“需要审批的工具会暂停”表述，保留 `message_ask_user` 的业务输入语义。零审批完全由代码状态机保证。
- 当前状态、工具治理、Roadmap、Lead/Durable 后续计划均已收口为“平台 allow/deny + Execution Class/Capability Grant”；旧审批设计和计划增加显著历史/替代标识。
- 首次后端全量测试因本机测试配置指向未运行的 PostgreSQL/Redis 而失败；使用独立临时容器、执行当前 Alembic migration 后原命令通过，证明失败属于基础设施缺失而非代码回归。

### 验证证据

```text
命令：uv run pytest tests/app/core/agent tests/app/core/tools tests/app/core/test_interaction_events.py tests/app/repositories/test_db_session_organization.py tests/app/services/test_agent_interactions.py tests/app/services/test_agent_service_recovery.py tests/app/services/test_trace_service.py tests/app/interfaces/endpoints/test_session_interactions.py -q
退出状态：0
关键结果：188 passed，11 个既有 Pydantic deprecation warnings
执行时间：2026-08-18 16:05（Asia/Shanghai）

命令：uv run pytest -q（REDIS_PORT=6479，SQLALCHEMY_DATABASE_URI 指向隔离临时 PostgreSQL）
退出状态：0
关键结果：collected 460，全部通过；运行前已对隔离数据库执行 alembic upgrade head
执行时间：2026-08-18 16:35（Asia/Shanghai）

命令：uv run ruff check app tests
退出状态：0
关键结果：All checks passed
执行时间：2026-08-18 16:14（Asia/Shanghai）

命令：pnpm test:run
退出状态：0
关键结果：44 个测试文件、185 项测试全部通过
执行时间：2026-08-18 16:14（Asia/Shanghai）

命令：pnpm type-check
退出状态：0
关键结果：vue-tsc -b 通过
执行时间：2026-08-18 16:15（Asia/Shanghai）

命令：pnpm build
退出状态：0
关键结果：vue-tsc -b && vite build 通过，3678 modules transformed
执行时间：2026-08-18 16:15（Asia/Shanghai）

命令：git diff --check
退出状态：0
关键结果：无空白错误；仅 Git 行尾转换提示
执行时间：2026-08-18 16:15（Asia/Shanghai）
```

## Task 6：独立代码审查、整改与最终验证

状态：completed

### 目标

按设计、公共接口兼容性、状态机、并发安全、隐私和测试质量审查全部改动；修复 blocking/major 问题后重新执行与最终声明匹配的验证。

### 涉及文件

- 本分支全部 diff
- 本计划

### 实施步骤

1. 审查新 Run 是否存在任何创建 `tool_approval` 的旁路。
2. 审查历史收敛的原子性、幂等性、tool call/result 对齐和永不执行保证。
3. 审查旧配置/事件 JSON 的读取兼容以及新 API 契约是否一致。
4. 审查前端是否仍把平台安全判断转嫁给终端用户。
5. 修复 blocking/major，重跑受影响测试，再运行最终验证矩阵。
6. 将结论标记为 `READY_TO_MERGE`、`BLOCKED` 或 `FAILED`；未经用户授权不提交或推送。

### 验证方式

- `cd agentic/api && uv run pytest -q`
- `cd agentic/api && uv run ruff check app tests`
- `cd agentic/web && pnpm test:run`
- `cd agentic/web && pnpm type-check`
- `cd agentic/web && pnpm build`
- `git diff --check`

### 完成条件

- 无 blocking/major 审查问题。
- 最新验证证据完整写回计划，并给出真实的合并就绪判断。

### 执行结果

- 按运行时创建路径、历史状态收敛、公共配置契约、前端等待语义、隐私和测试质量完成全 diff 自审；审查记录见 `agentic/docs/reviews/remove-tool-approval-review.md`。
- 首轮审查发现并修复 1 个 `major`：内部 `execution_policy` 曾被公共工具设置写模型暴露，旧 `approval=ask` 可能被静默接受。整改后，公共 `ToolBindingUpdate`/`RuntimeToolPolicyUpdate` 使用 `extra=forbid` 且不包含平台策略字段；内部历史迁移与终端用户写契约完全分离。
- 复审确认新 Run 没有 `tool_approval` 构造旁路；历史符号只用于只读兼容和安全收敛。Prompt 不承担审批消除逻辑，只保留 `message_ask_user` 的业务输入说明。
- 无开放 blocking、major 或已知 minor；结论为 `APPROVED / READY_TO_MERGE`。因未使用独立审查 Agent，正式合并时仍建议保留常规同伴审查。

### 最终验证证据

```text
命令：uv run pytest tests/app/core/tools/test_tool_management.py -q
退出状态：0
关键结果：19 passed；11 个既有 Pydantic deprecation warnings
执行时间：2026-08-18 16:34（Asia/Shanghai）

命令：uv run pytest -q（REDIS_PORT=6479，SQLALCHEMY_DATABASE_URI 指向隔离临时 PostgreSQL）
退出状态：0
关键结果：collected 460，全部通过
执行时间：2026-08-18 16:35（Asia/Shanghai）

命令：uv run ruff check app tests
退出状态：0
关键结果：All checks passed
执行时间：2026-08-18 16:35（Asia/Shanghai）

命令：pnpm test:run
退出状态：0
关键结果：44 个测试文件、185 项测试全部通过
执行时间：2026-08-18 16:30（Asia/Shanghai）

命令：pnpm type-check
退出状态：0
关键结果：vue-tsc -b 通过
执行时间：2026-08-18 16:31（Asia/Shanghai）

命令：pnpm build
退出状态：0
关键结果：vue-tsc -b && vite build 通过，3678 modules transformed
执行时间：2026-08-18 16:31（Asia/Shanghai）

命令：uv run alembic upgrade head（隔离 PostgreSQL）
退出状态：0
关键结果：当前 migration head 应用成功
执行时间：2026-08-18 16:31（Asia/Shanghai）

命令：git diff --check
退出状态：0
关键结果：无空白错误；仅 Git 行尾转换提示
执行时间：2026-08-18 16:35（Asia/Shanghai）
```

### 最终状态

`READY_TO_MERGE`

## 恢复点

若实施中断，先读取本计划的“当前进度”“状态变更记录”和当前 Task 的“执行结果/验证证据”，再检查 `git status --short --branch`。不要重做已完成 Task，不要覆盖 `agentic/api/.env`。
