# 统一工具平面与内置工具迁移实施计划

## 关联设计

- 设计文档：`agentic/docs/designs/agent-runtime-hitl-provider-reliability.zh-CN.md`
- 实施范围：设计中的 `阶段 1A：统一 Tool Plane 与内置工具迁移`
- 开发分支：`refactor/unified-tool-plane`
- 基线分支：`develop`

## 当前进度

- 整体状态：`READY_TO_MERGE`
- 当前阶段：completed
- 当前任务：无
- 已完成：5 / 5
- 阻塞问题：无
- 最近更新时间：2026-08-18（Asia/Shanghai）

## 全局约束

- 内置、API、MCP、A2A 最终共用 Descriptor、Scope、Schema Injection、执行前校验、ToolResult 和 Trace 合同；本批只迁移并完整验证 Message/Search/File/Shell/Browser，外部 Provider 生命周期留在 Stage 1B/2。
- Tool 的 `source_type` 与 `execution_backend` 必须分离；保留既有 `executor_type` 作为 ToolConfig/API 兼容字段，但不能再用它表达 Sandbox 资源位置。
- Lead/Planner 只读取无参数 Schema 的紧凑目录；目录生成、Scope 解析、Schema 解析、模型上下文注入和 Tool 构造不得创建、恢复或 ensure Sandbox/Browser。
- 只有已通过当前 Scope Snapshot、ToolConfig 与平台确定性策略的真实 Tool Call 才能进入 Sandbox-backed Tool 实现；拒绝路径不得触发 Sandbox。
- `message_ask_user` 继续作为系统能力可见并进入持久化 WAITING；不恢复通用 Tool Approval。
- 旧 `capabilities`、缺少新字段的历史 Plan/Interaction、现有 ToolConfig v2 和公共工具管理 API 必须继续可读。
- `shell_execute`、`browser_console_exec` 标记为 `general_fallback` 只影响路由提示和观测，不触发用户审批，也不阻止显式代码执行/项目操作/交互浏览任务直接选择。
- 中英文 Lead/Planner Prompt 必须同步更新并由回归测试覆盖。
- 不新增数据库迁移，不修改 Sandbox 容器镜像，不实现 MCP Actor、Schema Snapshot 或 A2A Card TTL。
- 一次只推进一个 Task；每个 Task 完成后立即记录实际结果和最新验证证据。
- 不自动提交、推送、创建 PR 或合并。

## 状态变更记录

| 日期时间 | 整体状态 | 当前任务 | 变更原因 |
| --- | --- | --- | --- |
| 2026-08-18（Asia/Shanghai） | `PLAN_READY` | 无 | 设计已确认，Stage 1A 拆分为五个可独立验证任务 |
| 2026-08-18（Asia/Shanghai） | `IN_PROGRESS` | Task 1 | 独立分支与计划就绪，开始以 Descriptor/Catalog 契约测试驱动实施 |
| 2026-08-18 19:35（Asia/Shanghai） | `IN_PROGRESS` | Task 2 | Task 1 的统一元数据、紧凑目录和兼容迁移通过 33 项定向测试与 Ruff，开始细粒度 Scope |
| 2026-08-18 19:38（Asia/Shanghai） | `IN_PROGRESS` | Task 3 | Task 2 的不可变 Scope Snapshot、Provider/Tool 裁剪和历史恢复兼容通过 16 项测试与 Ruff，开始统一注入和执行门禁 |
| 2026-08-18 19:45（Asia/Shanghai） | `IN_PROGRESS` | Task 4 | Task 3 的 Schema Resolver、执行前 Router、确定性拒绝和 Scope Trace 通过工具/Trace 回归与 Ruff，开始 Lead/Plan 全链路传播 |
| 2026-08-18 20:00（Asia/Shanghai） | `IN_PROGRESS` | Task 5 | Task 4 的精确 Scope 持久化、双语路由与恢复链路通过 79 项主链路、33 项 Scope/Registry 测试与 Ruff，开始固定 Lazy Sandbox 零激活契约 |
| 2026-08-18 20:10（Asia/Shanghai） | `REVIEWING` | Task 5 | Lazy Sandbox 契约、169 项核心回归、484 项后端全量测试、Ruff、编译与 diff 门禁通过，进入最终代码审查 |
| 2026-08-18 20:17（Asia/Shanghai） | `READY_TO_MERGE` | 无 | 审查发现已修复，171 项核心回归、486 项后端全量测试及全部最终门禁通过，Stage 1A 完成 |

## Task 1：建立统一 ToolDescriptor 与无副作用目录

状态：completed

### 目标

为现有工具增加来源、执行后端、资源需求、执行分类、通用程度和成本分类等正交元数据，并让 Registry 生成无参数 Schema、无运行时资源副作用的统一 Lead Tool Catalog。

### 涉及文件

- `agentic/api/app/schemas/tool_config.py`
- `agentic/api/app/core/tools/builtin/catalog.py`
- `agentic/api/app/core/tools/registry.py`
- `agentic/api/app/services/trace_service.py`
- `agentic/api/tests/app/core/agent/test_runtime_tool_scope.py`
- `agentic/api/tests/app/core/agent/test_plan_capabilities.py`
- `agentic/api/tests/app/core/tools/test_tool_management.py`

### 依赖与接口

- 前置任务：无。
- 输入：现有 `ToolDescriptor`、`BuiltinToolGroup`、动态/API Descriptor 与 ToolConfig v2。
- 输出：兼容旧字段的统一 Descriptor；按 Capability/Provider/Tool 汇总的紧凑 Catalog；Trace 可读取新元数据。

### 实施步骤

1. 先写失败测试，固定 `builtin.shell`、`builtin.file`、`builtin.browser`、`builtin.search`、`builtin.message` 的 `source_type/execution_backend/resource_requirements/execution_class/generality/cost_class` 映射。
2. 扩展 Pydantic ToolDescriptor，保留 `executor_type/requires_*` 兼容投影，并确保旧 JSON 可以反序列化。
3. 扩展 BuiltinToolGroup 和函数级分类，区分结构化 File/Browser Tool 与通用 Shell/Browser Script。
4. 统一 Registry 的 builtin/runtime/API Descriptor 创建路径，新增 Provider/Tool ID 查询与关系校验能力。
5. 将紧凑目录升级为 Capability + Provider + Tool 摘要；明确排除 `schema/parameters/properties` 和敏感配置。
6. Trace 元数据优先读取新 Descriptor 字段，同时保留旧消费者字段。

### 验证方式

- 运行：`uv run pytest tests/app/core/agent/test_runtime_tool_scope.py tests/app/core/agent/test_plan_capabilities.py tests/app/core/tools/test_tool_management.py -q`
- 运行：`uv run ruff check app/schemas/tool_config.py app/core/tools/builtin/catalog.py app/core/tools/registry.py app/services/trace_service.py tests/app/core/agent/test_runtime_tool_scope.py tests/app/core/agent/test_plan_capabilities.py tests/app/core/tools/test_tool_management.py`
- 预期：退出码 0；目录不含参数 Schema；旧 ToolConfig/API 测试保持通过。

### 完成条件

- Descriptor 能明确表达 `builtin.shell -> source_type=builtin + execution_backend=sandbox`。
- `shell_execute/browser_console_exec` 为 `general_fallback`，File/普通 Browser 操作为 `specialized`。
- Catalog 读取不调用任何 Runtime Tool 方法以外的静态 `get_tools()`，且不依赖 Sandbox/Browser 激活。
- 旧工具配置和管理接口没有破坏性字段变化。

### 执行结果

已扩展 ToolDescriptor 与 BuiltinToolGroup，新增 source/backend/resource/execution class/generality/cost 元数据；Registry 的 builtin/runtime/API 创建路径均生成统一元数据，并提供 Provider/Tool ID 集合。Capability Catalog 现在包含排序稳定的 Tool 摘要但不含参数 Schema；Trace 优先读取新字段。旧 Descriptor JSON、ToolConfig v2、executor_type 和 requires_* 保持兼容。

### 验证证据

```text
RED：uv run pytest tests/app/core/tools/test_tool_management.py tests/app/core/agent/test_plan_capabilities.py -q
退出状态：1
关键结果：4 项新增契约按预期失败，缺少 source_type/execution_backend/tools 摘要。

GREEN：uv run pytest tests/app/core/agent/test_runtime_tool_scope.py tests/app/core/agent/test_plan_capabilities.py tests/app/core/tools/test_tool_management.py -q
退出状态：0
关键结果：33 passed，11 个既有 Pydantic deprecation warnings。

静态检查：uv run ruff check app/schemas/tool_config.py app/core/tools/builtin/catalog.py app/core/tools/builtin/__init__.py app/core/tools/registry.py app/services/trace_service.py tests/app/core/agent/test_runtime_tool_scope.py tests/app/core/agent/test_plan_capabilities.py tests/app/core/tools/test_tool_management.py
退出状态：0
关键结果：All checks passed!
执行时间：2026-08-18 19:35（Asia/Shanghai）
```

## Task 2：建立不可扩大的 Tool Scope Snapshot

状态：completed

### 目标

把运行时边界从 Capability 扩展为 Capability + Provider + Tool ID + Exact Function，并保证模型可见范围和执行允许范围共享同一个 Scope Snapshot。

### 涉及文件

- `agentic/api/app/core/tools/scope.py`
- `agentic/api/app/core/tools/filter.py`
- `agentic/api/app/core/tools/registry.py`
- `agentic/api/app/core/agent/base.py`
- `agentic/api/tests/app/core/agent/test_runtime_tool_scope.py`
- `agentic/api/tests/app/core/agent/test_interaction_resume.py`

### 依赖与接口

- 前置任务：Task 1。
- 输入：稳定 ToolDescriptor、Provider/Tool ID 关系。
- 输出：`ToolScopeSnapshot`、细粒度 activate/resolve/allows 行为、未知选择诊断。

### 实施步骤

1. 先写失败测试，覆盖同 Capability 内按 Provider/Tool ID 裁剪、未知 ID 不授权、空 Scope 不等于全部、Exact Function 历史恢复和系统 Message 能力。
2. 新增不可变 Scope Snapshot，保存规范化后的 capabilities/provider_ids/tool_ids/exact_functions 与未知值。
3. `RuntimeToolScope.activate()` 接收新字段；过滤顺序固定为 Capability -> Provider -> Tool ID -> Exact Function 恢复例外。
4. Registry 提供确定性 Scope 解析，Tool/Provider 必须属于所选 Capability，非法关系只缩小权限。
5. BaseAgent 和 FilteredTool 使用同一个 Snapshot；Trace 可取得选中数量与安全 ID，不记录 Schema/参数。

### 验证方式

- 运行：`uv run pytest tests/app/core/agent/test_runtime_tool_scope.py tests/app/core/agent/test_interaction_resume.py -q`
- 运行：`uv run ruff check app/core/tools/scope.py app/core/tools/filter.py app/core/tools/registry.py app/core/agent/base.py tests/app/core/agent/test_runtime_tool_scope.py tests/app/core/agent/test_interaction_resume.py`
- 预期：退出码 0；既有 capability-only 调用保持兼容，新 provider/tool 选择只能缩小范围。

### 完成条件

- Scope Snapshot 可稳定序列化/观测，激活新 Scope 时原子替换旧边界。
- 未知或错配 Provider/Tool 不会扩大可见/可执行工具。
- 历史 Ask User 恢复仍只精确恢复原函数。

### 执行结果

新增不可变 ToolScopeSnapshot，并将 RuntimeToolScope 扩展为 Capability + Provider + Tool ID + Exact Function 四层边界；未知值单独记录且永不授权。FilteredTool 继续通过同一个 RuntimeToolScope 执行可见性与调用前检查，BaseAgent 已支持传入 provider_ids/tool_ids；Registry 新增稳定 Tool ID 查询和有效 Provider/Tool 集合。

### 验证证据

```text
RED：uv run pytest tests/app/core/agent/test_runtime_tool_scope.py -q
退出状态：1
关键结果：2 项新增契约按预期失败，activate 尚不接受 provider_ids/tool_ids。

GREEN：uv run pytest tests/app/core/agent/test_runtime_tool_scope.py tests/app/core/agent/test_interaction_resume.py -q
退出状态：0
关键结果：16 passed，既有 Interaction 恢复行为保持通过。

静态检查：uv run ruff check app/core/tools/scope.py app/core/tools/filter.py app/core/tools/registry.py app/core/agent/base.py tests/app/core/agent/test_runtime_tool_scope.py tests/app/core/agent/test_interaction_resume.py
退出状态：0
关键结果：All checks passed!
执行时间：2026-08-18 19:38（Asia/Shanghai）
```

## Task 3：统一 Schema 注入与执行前路由门禁

状态：completed

### 目标

建立统一 ToolSchemaResolver/Context Injector 与 ToolExecutorRouter，使模型注入和真实执行都受同一 Scope/ToolConfig 约束，拒绝路径在进入内置实现前完成。

### 涉及文件

- `agentic/api/app/core/tools/schema_resolver.py`（新增）
- `agentic/api/app/core/tools/execution.py`（新增）
- `agentic/api/app/core/tools/filter.py`
- `agentic/api/app/core/tools/factory.py`
- `agentic/api/app/core/agent/base.py`
- `agentic/api/tests/app/core/tools/test_tool_execution_router.py`（新增）
- `agentic/api/tests/app/core/agent/test_runtime_tool_scope.py`

### 依赖与接口

- 前置任务：Task 2。
- 输入：统一 Descriptor、Scope Snapshot、ToolConfig、现有 BaseTool bundle。
- 输出：无副作用 Schema Resolver；统一执行前门禁；兼容现有 BaseTool 实现的 Router。

### 实施步骤

1. 先写失败测试，证明未选/禁用/未知 Tool 返回确定性失败且不会调用 inner Tool，选中 Tool 只调用一次。
2. 新增 ToolSchemaResolver，集中收集 ToolConfig 后和当前 Scope 后的 Schema；不获取 Sandbox/Provider Handle。
3. 新增 ToolExecutorRouter，按 Descriptor 重新校验 Scope、ToolConfig 与 execution backend 后委托现有 inner Tool；首版不重写具体 Tool 协议。
4. FilteredTool 改为统一适配器：`get_tools()` 走 Resolver 规则，`invoke()` 走 Router，不保留平行授权判断。
5. BaseAgent 的模型调用统一使用 Resolver，并在 Trace 中记录 Scope Snapshot 和注入数量。

### 验证方式

- 运行：`uv run pytest tests/app/core/tools/test_tool_execution_router.py tests/app/core/agent/test_runtime_tool_scope.py -q`
- 运行：`uv run ruff check app/core/tools/schema_resolver.py app/core/tools/execution.py app/core/tools/filter.py app/core/tools/factory.py app/core/agent/base.py tests/app/core/tools/test_tool_execution_router.py tests/app/core/agent/test_runtime_tool_scope.py`
- 预期：退出码 0；模型可见和真实执行门禁一致；无资源副作用。

### 完成条件

- 一个 Tool Call 不能通过调用 `FilteredTool.invoke()` 绕过当前 Scope。
- Resolver 与 Router 都按稳定 `tool_id` 工作，函数名只作为协议兼容输入。
- 所有拒绝发生在 inner Tool/Sandbox 代理调用之前。

### 执行结果

新增无资源副作用 ToolSchemaResolver 和统一 ToolExecutorRouter。FilteredTool 现在作为统一适配器使用 Resolver 生成模型 Schema、使用 Router 执行调用，不再在 invoke 中维护平行门禁；ToolFactory 为所有内部/上下文 Tool 共享同一个 Resolver/Router。BaseAgent 集中收集 Schema，并将 provider_ids/tool_ids 写入模型调用 Trace。Router 对未知、禁用、平台 deny、越出 Scope 的调用均在 inner Tool 前返回失败。

### 验证证据

```text
RED：uv run pytest tests/app/core/tools/test_tool_execution_router.py -q
退出状态：1
关键结果：测试收集按预期失败，尚无 ToolExecutorRouter 模块。

GREEN：uv run pytest tests/app/core/tools/test_tool_management.py tests/app/core/tools/test_tool_execution_router.py tests/app/core/agent/test_runtime_tool_scope.py tests/app/core/agent/test_plan_capabilities.py -q
退出状态：0
关键结果：39 passed，统一注入和路由未破坏现有工具配置行为。

Trace GREEN：uv run pytest tests/app/services/test_trace_service.py tests/app/core/tools/test_tool_execution_router.py tests/app/core/agent/test_runtime_tool_scope.py -q
退出状态：0
关键结果：18 passed，模型调用摘要记录 capability/provider/tool Scope 且不持久化 Schema。

静态检查：uv run ruff check app/core/tools/schema_resolver.py app/core/tools/execution.py app/core/tools/filter.py app/core/tools/factory.py app/core/agent/base.py app/services/trace_service.py tests/app/core/tools/test_tool_execution_router.py tests/app/core/agent/test_runtime_tool_scope.py tests/app/services/test_trace_service.py
退出状态：0
关键结果：All checks passed!
执行时间：2026-08-18 19:45（Asia/Shanghai）
```

## Task 4：让 Lead/Plan 持久化并传播内部 Provider/Tool Scope

状态：completed

### 目标

让 Lead、Planner、Plan Step、React 和 Ask User 恢复链路携带 provider_ids/tool_ids，并同步中英文 Prompt；缺少新字段的历史数据继续按 capability-only 运行。

### 涉及文件

- `agentic/api/app/core/entities/lead.py`
- `agentic/api/app/core/entities/plan.py`
- `agentic/api/app/core/entities/event.py`
- `agentic/api/app/core/agent/lead_decision.py`
- `agentic/api/app/core/agent/lead.py`
- `agentic/api/app/core/agent/planner.py`
- `agentic/api/app/core/agent/react.py`
- `agentic/api/app/services/agent_service.py`
- `agentic/api/app/core/prompts/lead.py`
- `agentic/api/app/core/prompts/planner.py`
- `agentic/api/app/core/prompts/en/planner.py`
- `agentic/api/tests/app/core/agent/test_lead_decision.py`
- `agentic/api/tests/app/core/agent/test_lead_agent_react.py`
- `agentic/api/tests/app/core/agent/test_lead_agent_plan.py`
- `agentic/api/tests/app/core/agent/test_plan_capabilities.py`
- `agentic/api/tests/app/core/agent/test_interaction_resume.py`
- `agentic/api/tests/app/core/agent/test_prompt_locale_routing.py`

### 依赖与接口

- 前置任务：Task 3。
- 输入：统一紧凑 Catalog、Scope 激活接口。
- 输出：Lead/Plan/Interaction 的内部 Tool Scope 持久化与传播；双语决策契约。

### 实施步骤

1. 先写失败测试，覆盖 Lead 过滤未知/错配 Provider/Tool、Plan Step 规范化、React 精确注入、Ask User 自动继续保留 Scope、旧事件缺字段兼容。
2. 为 ReactDecision/Step/InteractionEvent/InteractionResolution 增加默认空数组的 provider_ids/tool_ids。
3. LeadDecisionPolicy 和 Planner 使用 Registry 的确定性 Scope 解析，而不是分别只过滤 capability。
4. Lead -> React/Plan -> Interaction -> Resume 全链路传播新字段；所有调用继续接受旧 capability-only 数据。
5. 同步修改 Lead 双语 Prompt、中文 Planner Prompt、英文 Planner Prompt，要求从 Catalog 选择最小 Tool 集，显式任务可以直接选 Sandbox-backed Tool，简单问题不得为使用 Shell 而规划。
6. 更新路由评测，覆盖“今天几号/概念解释不选 Sandbox”“运行 Python/处理文件可直接选择 Sandbox-backed Tool”的结构化决策。

### 验证方式

- 运行：`uv run pytest tests/app/core/agent/test_lead_decision.py tests/app/core/agent/test_lead_agent_react.py tests/app/core/agent/test_lead_agent_plan.py tests/app/core/agent/test_plan_capabilities.py tests/app/core/agent/test_interaction_resume.py tests/app/core/agent/test_prompt_locale_routing.py tests/app/core/agent/test_lead_agent_routing_eval.py -q`
- 运行：`uv run ruff check app/core/entities/lead.py app/core/entities/plan.py app/core/entities/event.py app/core/agent/lead_decision.py app/core/agent/lead.py app/core/agent/planner.py app/core/agent/react.py app/core/prompts/lead.py app/core/prompts/planner.py app/core/prompts/en/planner.py tests/app/core/agent/test_lead_decision.py tests/app/core/agent/test_lead_agent_react.py tests/app/core/agent/test_lead_agent_plan.py tests/app/core/agent/test_plan_capabilities.py tests/app/core/agent/test_interaction_resume.py tests/app/core/agent/test_prompt_locale_routing.py tests/app/core/agent/test_lead_agent_routing_eval.py`
- 预期：退出码 0；中英文 Prompt 镜像一致；历史 JSON fixture 继续通过。

### 完成条件

- Lead/Plan 可按 `capability + provider + tool_id` 裁剪内部工具 Schema。
- Ask User 恢复不会扩大暂停前 Scope。
- capability-only 历史数据不报错，行为与改造前一致。
- 路由 Prompt 明确“Sandbox 永远晚激活，但不是所有匹配任务都最后选择”。

### 执行结果

ReactDecision、Plan Step、InteractionEvent 与 InteractionResolution 已兼容地增加 `provider_ids/tool_ids`；LeadDecisionPolicy 与 Planner 通过 Registry 统一解析 capability/provider/tool 关系，Lead -> React/Plan -> WAITING -> Resume 全链路保持精确 Scope。中文与英文 Lead/Planner Prompt 已同步要求选择最小工具集，并区分“Sandbox 晚激活”与“显式执行任务可直接选择 Sandbox-backed Tool”。路由评测已覆盖简单日期问题不选择 Sandbox、明确代码执行可精确选择 Shell。额外修复了未知精确 ID 被过滤为空后退化为 capability 宽授权的问题。

### 验证证据

```text
RED：uv run pytest Task 4 定向测试 -q
退出状态：1
关键结果：10 failed, 42 passed；新字段、传播与双语 Prompt 契约按预期先失败。

GREEN：uv run pytest tests/app/core/agent/test_lead_decision.py tests/app/core/agent/test_lead_agent_react.py tests/app/core/agent/test_lead_agent_plan.py tests/app/core/agent/test_plan_capabilities.py tests/app/core/agent/test_interaction_resume.py tests/app/core/agent/test_prompt_locale_routing.py tests/app/core/agent/test_lead_agent_routing_eval.py tests/app/services/test_agent_service_recovery.py -q
退出状态：0
关键结果：79 passed；Lead/Plan/React/Interaction/Recovery 与中英文 Prompt 回归通过。

Scope 收紧 GREEN：uv run pytest tests/app/core/agent/test_runtime_tool_scope.py tests/app/core/tools/test_tool_management.py -q
退出状态：0
关键结果：33 passed；未知 provider/tool 精确约束不会退化成 capability 宽授权。

静态检查：Task 4 实现、提示词与测试文件的 uv run ruff check
退出状态：0
关键结果：All checks passed!
执行时间：2026-08-18 20:00（Asia/Shanghai）
```

## Task 5：固定 Lazy Sandbox 零激活契约并完成阶段验证

状态：completed

### 目标

用真实 ToolFactory/Lazy Sandbox Fake 证明 Catalog、Lead、Scope、Schema 注入和拒绝路径零激活，只有允许的 File/Shell/Browser 调用才激活，并完成 Stage 1A 全量回归和审查门禁。

### 涉及文件

- `agentic/api/tests/app/core/agent/test_agent_task_runner_lazy_sandbox.py`
- `agentic/api/tests/app/core/agent/test_lazy_attachment_materialization.py`
- `agentic/api/tests/app/core/sandbox/test_lazy_sandbox_runtime.py`
- `agentic/api/tests/app/core/tools/test_tool_execution_router.py`
- `agentic/api/tests/app/core/agent/test_runtime_tool_scope.py`
- `agentic/docs/designs/agent-runtime-hitl-provider-reliability.zh-CN.md`
- `agentic/docs/plans/unified-tool-plane-plan.md`

### 依赖与接口

- 前置任务：Task 4。
- 输入：完成迁移的内部工具平面、现有 LazySandboxRuntime。
- 输出：零激活与真实激活的回归证据；最终验证和代码审查结论。

### 实施步骤

1. 增加 Fake Runtime 计数测试，分别覆盖 Catalog、Direct、Lead Decide、Schema Resolve、out-of-scope invoke、允许的 File/Shell/Browser invoke。
2. 验证 Tool 构造只持有 Lazy Proxy，不会触发 create/get/ensure/get_browser；首次真实调用只激活一次。
3. 运行 Agent/Tool/Sandbox 定向回归、后端全量测试、Ruff、Python 编译和 diff 门禁。
4. 对照设计验收标准检查 Stage 1A 覆盖；Stage 1B/2 项明确保留未完成，不错误宣称外部 Provider 已优化。
5. 进入代码审查；修复 blocking/major 后重新执行受影响验证与最终门禁。

### 验证方式

- 运行：`uv run pytest tests/app/core/agent tests/app/core/tools tests/app/core/sandbox -q`
- 运行：`uv run pytest -q`
- 运行：`uv run ruff check app tests`
- 运行：`uv run python -m compileall -q app tests`
- 运行：`git diff --check`
- 预期：全部命令退出码 0；无未处理 blocking/major；只对 Stage 1A 给出完成结论。

### 完成条件

- Direct/Catalog/Lead/Schema/拒绝路径 Sandbox 激活计数为 0。
- 允许的首次 Sandbox-backed Tool 调用激活一次，并保持现有并发认领、附件物化和清理测试通过。
- 全量后端验证通过，或如实记录与本批无关的外部阻塞。
- 代码审查为 `APPROVED`，计划最终状态才可写为 `READY_TO_MERGE`。

### 执行结果

已增加真实 ToolFactory + LazySandboxRuntime 计数契约：Tool 构造、Catalog、Lead Direct 决策、Scope/Schema 解析及 out-of-scope invoke 均保持零激活；允许的 File/Browser 调用在执行 Router 放行后才创建 Sandbox，且复用同一实例，既有 Shell 测试继续证明首次允许调用只激活一次。全量测试所需宿主机 PostgreSQL/Redis 最初未启动，随后使用与 8088 部署隔离的临时测试容器完成迁移和验证，验证后已删除临时容器。

### 验证证据

```text
Lazy 契约：uv run pytest tests/app/core/agent/test_lazy_attachment_materialization.py tests/app/core/agent/test_interaction_resume.py tests/app/core/sandbox/test_lazy_sandbox_runtime.py tests/app/core/tools/test_tool_execution_router.py -q
退出状态：0
关键结果：34 passed；Catalog/Lead/Schema/拒绝路径零激活，允许的 File/Shell/Browser 调用按需激活。

核心定向（最终复验）：uv run pytest tests/app/core/agent tests/app/core/tools tests/app/core/sandbox -q
退出状态：0
关键结果：171 passed，11 个既有 Pydantic 弃用警告。

后端全量（最终复验）：uv run pytest -q
退出状态：0
关键结果：collected 486 items，全部通过。

静态与编译：uv run ruff check app tests；uv run python -m compileall -q app tests；git diff --check
退出状态：0
关键结果：All checks passed；编译与 diff 无错误，仅 Git 报告工作区 LF/CRLF 转换提示。

环境说明：首次全量因宿主机 127.0.0.1:5432/6479 未提供依赖失败；按项目本地开发约定启动隔离的 agentic-test-postgres/redis、执行 Alembic 后全量通过，随后删除两个临时容器；现有 manus-* 部署容器未变更。
执行时间：2026-08-18 20:17（Asia/Shanghai）
```

## 计划变更

| 日期 | 变更内容 | 原因 | 影响任务 | 是否影响设计 |
| --- | --- | --- | --- | --- |
| 2026-08-18 | 无 | 初始计划 | 无 | 否 |

## 最终验证

### 执行命令

```bash
uv run pytest tests/app/core/agent tests/app/core/tools tests/app/core/sandbox -q
uv run pytest -q
uv run ruff check app tests
uv run python -m compileall -q app tests
git diff --check
```

### 执行结果

- 单元测试：通过；Agent/Tool/Sandbox 核心回归 171 passed。
- 集成测试：通过；后端全量 486 passed。
- 静态检查：通过；Ruff 输出 `All checks passed!`。
- 类型检查：不适用（项目未配置独立 Python 类型检查门禁）
- 构建：通过 Python `compileall` 编译检查；本批无独立前端或制品构建。
- 数据库迁移：产品迁移不适用（本批不修改数据库）；仅为隔离测试数据库执行既有 Alembic 迁移。
- 手工验证：Lazy Sandbox 零激活/按需激活契约 34 passed；隔离测试容器验证后已删除，现有部署未变更。
- 代码审查：`APPROVED`；无阻塞项、无未解决 major。

### 验收标准检查

- [x] Descriptor 明确区分 Tool 来源与执行后端。
- [x] Lead/Planner 目录无参数 Schema、无敏感配置、无 Sandbox/Provider 激活。
- [x] Scope 支持 Capability + Provider + Tool ID + Exact Function，未知选择不扩大权限。
- [x] 模型 Schema 注入和真实 Tool 执行共享同一 Scope Snapshot。
- [x] Direct、Catalog、Lead、Schema 与拒绝路径 Sandbox 激活为 0。
- [x] 允许的 File/Shell/Browser 调用在真实调用时才激活 Lazy Sandbox。
- [x] 通用 Shell/Browser Script 可作为后备，但显式匹配任务可以直接选择。
- [x] 中英文 Lead/Planner Prompt 同步，旧 Plan/Interaction/ToolConfig 兼容。
- [x] Stage 1A 自动化、静态检查、编译检查和代码审查通过。

### 未通过项目

无。存在 11 个既有 Pydantic 弃用警告及 Git 的 LF/CRLF 转换提示，不影响本阶段结论。

### 最终状态

`READY_TO_MERGE`
