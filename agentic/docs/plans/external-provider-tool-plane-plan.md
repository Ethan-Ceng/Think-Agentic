# 外部 Provider 接入统一 Tool Plane 实施计划

## 关联设计

- 设计文档：`agentic/docs/designs/agent-runtime-hitl-provider-reliability.zh-CN.md`
- 实施范围：设计中的 `阶段 1B：外部 Provider 接入统一 Tool Plane`
- 开发分支：`refactor/unified-tool-plane`
- 基线阶段：Stage 1A `READY_TO_MERGE` 工作区

## 当前进度

- 整体状态：`READY_TO_MERGE`
- 当前阶段：completed
- 当前任务：无（Stage 1B 已完成）
- 已完成：5 / 5
- 阻塞问题：无
- 最近更新时间：2026-08-19（Asia/Shanghai）

## 全局约束

- API、MCP、A2A 必须复用 Stage 1A 的 Descriptor、Catalog、Scope Snapshot、Schema Resolver、FilteredTool、Executor Router、ToolResult 和 Trace 合同，不新增平行上下文注入链路。
- Catalog Plane 只能读取配置和安全摘要，不得访问 MCP 网络、启动 stdio 子进程、请求 A2A Agent Card、创建 HTTP Client 或激活 Sandbox。
- MCP 只允许连接当前 Scope 明确选中的 Provider；没有明确 Provider 且存在多个候选时不得全量连接。单一候选可确定性收窄。
- A2A 的函数 Schema 保持本地静态；只有真实调用 A2A 函数时才初始化本批仍按 Run 管理的客户端。按 Target 的 Card TTL 与共享 HTTP Client 留在 Stage 3。
- MCP Schema 数量或字符预算超限时暴露显式的 Provider Tool Search，不允许静默注入全量 Schema 或无提示截断。
- `AgentTaskRunner.invoke()` 不再初始化 MCP/A2A；Direct、内置工具、Ask User、无关 Provider 路径的外部连接计数必须为 0。
- 本批继续使用 Run 内、同 Task 所有权的 MCP Manager；长生命周期 Actor、连接锁、退避、熔断、idle TTL、跨 Run Schema Snapshot 和裸 `CancelledError` 的完整隔离留在 Stage 2。
- 不新增数据库迁移，不修改 Sandbox 镜像，不实现本地 Sub Agent 调度，不修改终端用户审批策略。
- 保留旧构造方式、旧 capability-only Plan/Interaction 和 ToolConfig v2 的读取兼容。
- 不自动提交、推送、创建 PR 或合并。

## 状态变更记录

| 日期时间 | 整体状态 | 当前任务 | 变更原因 |
| --- | --- | --- | --- |
| 2026-08-19（Asia/Shanghai） | `PLAN_READY` | 无 | Stage 1B 设计边界和五个可恢复任务已确认 |
| 2026-08-19（Asia/Shanghai） | `IN_PROGRESS` | Task 1 | 计划与分支满足实施门禁，开始 Provider Catalog 契约测试 |
| 2026-08-19 08:56（Asia/Shanghai） | `IN_PROGRESS` | Task 2 | Provider Catalog 的安全摘要、未连接候选和稳定 ID 通过 27 项定向测试与 Ruff，开始 MCP 惰性发现 |
| 2026-08-19 09:04（Asia/Shanghai） | `IN_PROGRESS` | Task 3 | MCP Provider Scope、惰性发现、预算和二阶段检索通过 62 项相关回归与 Ruff，开始移除 Runner 预连接 |
| 2026-08-19 09:06（Asia/Shanghai） | `IN_PROGRESS` | Task 4 | Runner 零预连接和 A2A 真实调用时初始化通过 17 项定向回归与 Ruff，开始固定选择/恢复/Trace 合同 |
| 2026-08-19 09:11（Asia/Shanghai） | `IN_PROGRESS` | Task 5 | 双语选择、历史 Scope 重分类与动态 Provider Trace 通过 63 项回归与 Ruff，进入阶段验证 |
| 2026-08-19 09:19（Asia/Shanghai） | `REVIEWING` | Task 5 | 核心定向 177 项、后端全量 501 项、Ruff、compileall 与差异检查均通过，进入代码审查 |
| 2026-08-19（Asia/Shanghai） | `READY_TO_MERGE` | Task 5 | 审查发现的 4 个 major 与 3 个 minor 均已修复；修复后核心定向 182 项、隔离依赖下后端全量 506 项及全部静态门禁通过，复审结论为 `APPROVED` |

## Task 1：建立安全、无网络 I/O 的 Provider Catalog

状态：completed

### 目标

从现有 ToolConfig、MCPConfig 和 A2AConfig 生成统一 ProviderDescriptor，并让 Lead/Planner 在 MCP 尚未连接时也能看到安全候选和稳定 Provider ID。

### 涉及文件

- `agentic/api/app/schemas/tool_config.py`
- `agentic/api/app/core/entities/app_config.py`
- `agentic/api/app/core/tools/provider_catalog.py`
- `agentic/api/app/core/tools/registry.py`
- `agentic/api/app/core/tools/factory.py`
- `agentic/api/tests/app/core/tools/test_provider_catalog.py`
- `agentic/api/tests/app/core/tools/test_tool_management.py`

### 依赖与接口

- 前置任务：Stage 1A ToolDescriptor/Registry。
- 输入：ToolConfig registrations、MCP server 配置、A2A target 配置。
- 输出：无 Secret/URL/Header/Env/参数 Schema 的 ProviderDescriptor 与 capability catalog `providers` 摘要。

### 实施步骤

1. 定义稳定 ProviderDescriptor 字段和 MCP Provider ID 规范化函数，限制 label/description/tag 长度并移除控制字符。
2. 从 MCP/A2A 配置及已有 API registration 构建 enabled、credential/snapshot/health 状态，不读取远端。
3. 扩展 ToolRegistry 注册、列举和 Scope 解析，使“尚无在线 Tool Schema 的 MCP Provider”仍是有效候选。
4. Catalog 按 capability/provider/tool 稳定排序；加入测试证明目录不包含 URL、Header、Env、凭据或参数 Schema。

### 验证方式

- 运行：`uv run pytest tests/app/core/tools/test_provider_catalog.py tests/app/core/tools/test_tool_management.py -q`
- 运行：`uv run ruff check app/core/tools/provider_catalog.py app/core/tools/registry.py app/schemas/tool_config.py tests/app/core/tools/test_provider_catalog.py`
- 预期：全部退出码 0；构建 Catalog 的 Fake 网络/初始化计数为 0。

### 完成条件

- 未连接 MCP 时 Lead Catalog 已包含各 enabled MCP Provider 的安全摘要。
- API/MCP/A2A Provider 使用稳定、唯一且不含 Secret 的 ID。
- disabled Provider 不进入有效候选，未知 Provider 不扩大 Scope。

### 执行结果

已新增 ProviderDescriptor 和离线 Provider Catalog Builder；API registration、每个 MCP Server 与 A2A umbrella 均生成安全、稳定摘要。ToolRegistry 现在可以在尚无动态 Tool Schema 时列出并解析 MCP Provider，disabled Provider 不进入有效 Scope；ToolFactory 构造 Catalog 时不初始化任何外部运行时。

### 验证证据

```text
命令：uv run pytest tests/app/core/tools/test_provider_catalog.py tests/app/core/tools/test_tool_management.py -q
退出状态：0
关键结果：27 passed；目录未包含 URL、Header、Env、凭据或参数 Schema，Factory 构造时 MCP/A2A Manager 均为空。

命令：uv run ruff check app/core/tools/provider_catalog.py app/core/tools/registry.py app/core/tools/factory.py app/core/tools/mcp.py app/core/tools/a2a.py app/schemas/tool_config.py tests/app/core/tools/test_provider_catalog.py
退出状态：0
关键结果：All checks passed!
执行时间：2026-08-19 08:56（Asia/Shanghai）
```

## Task 2：实现按 Scope 惰性 MCP Schema 发现与预算

状态：completed

### 目标

在第一次需要模型可见 MCP Schema 时只连接选中的 MCP Provider，并在 Schema 超预算时通过显式本地 Tool Search 二阶段收窄。

### 涉及文件

- `agentic/api/app/core/entities/tool_config.py`
- `agentic/api/app/core/tools/mcp.py`
- `agentic/api/app/core/tools/filter.py`
- `agentic/api/app/core/tools/factory.py`
- `agentic/api/app/core/tools/registry.py`
- `agentic/api/app/core/tools/schema_resolver.py`
- `agentic/api/app/core/agent/base.py`
- `agentic/api/tests/app/core/tools/test_mcp_lazy_provider.py`
- `agentic/api/tests/app/core/agent/test_runtime_tool_scope.py`

### 依赖与接口

- 前置任务：Task 1。
- 输入：不可变 RuntimeToolScope Snapshot、MCP Provider 配置、每 Step Schema 数量/字符预算。
- 输出：provider-scoped MCP Schema、显式 `search_tools` 收窄接口和零全量连接保证。

### 实施步骤

1. 为 FilteredTool/BaseAgent 增加模型调用前的异步 Schema 准备钩子；Lead/Planner 空 Scope 不触发准备。
2. 将 MCPTool 改为按 Provider 持有本 Run Manager，只初始化 Scope 选中的 enabled Server，并保持连接与清理由同一 Runner Task 执行。
3. 将发现的动态函数按真实 Provider ID 注册到统一 Registry，再由同一 Scope Snapshot 控制注入和执行。
4. 增加可配置的外部 Schema 数量/字符预算；超限 Provider 只暴露本地 search-tools Schema，搜索调用后下一轮仅注入 Top-K 匹配函数。
5. 覆盖单一候选确定性收窄、多候选未选择零连接、选中一个只连接一个、未知 Provider 零连接和预算二阶段检索。

### 验证方式

- 运行：`uv run pytest tests/app/core/tools/test_mcp_lazy_provider.py tests/app/core/agent/test_runtime_tool_scope.py tests/app/core/tools/test_tool_execution_router.py -q`
- 运行：`uv run ruff check app/core/tools/mcp.py app/core/tools/filter.py app/core/agent/base.py tests/app/core/tools/test_mcp_lazy_provider.py`
- 预期：全部退出码 0；未选 Provider 连接计数为 0；单 Provider 选择只初始化对应 Server 一次。

### 完成条件

- MCP Schema 发现不再依赖 Run 开头全量初始化。
- 动态 Tool Descriptor 的 provider/tool/function 边界一致，模型不可见的函数无法执行。
- 超预算不会全量注入，也不会静默截断。

### 执行结果

已为 BaseAgent/FilteredTool 增加 Scope-aware 异步 Schema 准备钩子；MCPTool 按真实 `mcp.<server>` 创建本 Run Manager，未选/未知/多候选未收窄路径均不连接。动态 Schema 注册回统一 Registry，并在惰性发现后只重新分类原请求 ID。新增外部 Schema 数量/字符预算，超限时仅注入 Provider 专属 `search_tools`，调用后下一轮注入 Top-K 匹配函数。

### 验证证据

```text
命令：uv run pytest tests/app/core/tools/test_mcp_lazy_provider.py tests/app/core/agent/test_runtime_tool_scope.py tests/app/core/tools/test_tool_execution_router.py tests/app/core/agent/test_plan_capabilities.py tests/app/core/agent/test_lead_decision.py tests/app/core/tools/test_provider_catalog.py tests/app/core/tools/test_tool_management.py -q
退出状态：0
关键结果：62 passed；未选/未知 Provider 零连接，选中 github 只初始化 github，超预算显式检索后只注入 Top-1。

命令：uv run ruff check app/core/entities/tool_config.py app/core/tools/mcp.py app/core/tools/filter.py app/core/tools/factory.py app/core/tools/registry.py app/core/tools/scope.py app/core/agent/base.py app/schemas/tool_config.py tests/app/core/tools/test_mcp_lazy_provider.py
退出状态：0
关键结果：All checks passed!
执行时间：2026-08-19 09:04（Asia/Shanghai）
```

## Task 3：实现 A2A 真实调用时惰性初始化并删除 Runner 预连接

状态：completed

### 目标

让 A2A 静态函数 Schema 可在选中时直接进入统一 Tool Plane，但网络客户端和 Agent Card 获取只在真实 A2A 调用发生时初始化，同时删除 Runner 的 MCP/A2A 全量预连接。

### 涉及文件

- `agentic/api/app/core/tools/a2a.py`
- `agentic/api/app/core/agent/agent_task_runner.py`
- `agentic/api/app/core/agent/lead.py`
- `agentic/api/app/core/flows/planner_react.py`
- `agentic/api/tests/app/core/agent/test_agent_task_runner_lazy_sandbox.py`
- `agentic/api/tests/app/core/tools/test_a2a_lazy_provider.py`
- `agentic/api/tests/app/core/agent/test_agent_task_runner_completion.py`

### 依赖与接口

- 前置任务：Task 1、Task 2 的统一准备/执行边界。
- 输入：A2AConfig 与统一 Executor Router。
- 输出：静态 A2A Schema、真实调用时初始化、Runner 无预连接。

### 实施步骤

1. A2ATool 构造时保存配置但不创建 HTTP Client、不获取 Card；两个公开函数在执行边界幂等 ensure 初始化。
2. AgentTaskRunner 构造配置化 MCP/A2A Adapter，删除 invoke 开头 initialize/refresh 调用。
3. 清理路径只关闭本 Run 实际激活的 Provider，未激活路径保持无副作用。
4. 删除 Lead/Legacy Flow 的手工 `refresh_mcp_tools()` 平行接口，动态刷新只由统一准备钩子完成。
5. 增加 Direct、Shell-only、Ask User、A2A Schema-only 和真实 A2A 调用的初始化计数回归。

### 验证方式

- 运行：`uv run pytest tests/app/core/agent/test_agent_task_runner_lazy_sandbox.py tests/app/core/agent/test_agent_task_runner_completion.py tests/app/core/tools/test_a2a_lazy_provider.py -q`
- 运行：`uv run ruff check app/core/tools/a2a.py app/core/agent/agent_task_runner.py tests/app/core/tools/test_a2a_lazy_provider.py`
- 预期：全部退出码 0；Runner invoke 本身不产生 MCP/A2A 连接；真实 A2A 函数首次调用只初始化一次。

### 完成条件

- 普通对话及内置工具 Run 没有 MCP/A2A 连接尝试。
- A2A Schema 和执行都经过统一 FilteredTool/Scope/Router。
- 未激活 Provider 的 cleanup 不创建资源、不抛异常。

### 执行结果

已删除 AgentTaskRunner.invoke() 开头的 MCP/A2A initialize 与 Lead/Legacy Flow 手工刷新入口。A2ATool 保存静态配置但不创建 HTTP Client；两个公开函数在真实执行时共享一次幂等初始化。Runner cleanup 只关闭已激活 Adapter，未激活 A2A cleanup 为无副作用操作。

### 验证证据

```text
命令：uv run pytest tests/app/core/agent/test_agent_task_runner_lazy_sandbox.py tests/app/core/agent/test_agent_task_runner_completion.py tests/app/core/tools/test_a2a_lazy_provider.py -q
退出状态：0
关键结果：17 passed；Runner 进入 Flow 前 MCP/A2A 初始化计数均为 0，A2A 两次真实调用共享一次初始化。

命令：uv run ruff check app/core/tools/a2a.py app/core/agent/agent_task_runner.py app/core/agent/lead.py app/core/flows/planner_react.py tests/app/core/tools/test_a2a_lazy_provider.py tests/app/core/agent/test_agent_task_runner_lazy_sandbox.py
退出状态：0
关键结果：All checks passed!
执行时间：2026-08-19 09:06（Asia/Shanghai）
```

## Task 4：贯通外部 Provider 选择、恢复和 Trace 合同

状态：completed

### 目标

验证 Lead/Plan/Ask User Continuation 对外部 Provider、Tool ID 和 Exact Function 的选择能稳定持久化、恢复与观测，且 API/MCP/A2A 结果不再走独立注入路径。

### 涉及文件

- `agentic/api/app/core/prompts/lead.py`
- `agentic/api/app/core/prompts/planner.py`
- `agentic/api/app/core/prompts/en/planner.py`
- `agentic/api/app/services/trace_service.py`
- `agentic/api/tests/app/core/agent/test_lead_agent_routing_eval.py`
- `agentic/api/tests/app/core/agent/test_plan_capabilities.py`
- `agentic/api/tests/app/core/agent/test_interaction_resume.py`
- `agentic/api/tests/app/services/test_trace_service.py`

### 依赖与接口

- 前置任务：Task 1-3。
- 输入：Provider-aware Catalog、Scope Snapshot 和动态 Descriptor。
- 输出：中英文选择规则、恢复边界和低基数 Provider/Backend Trace。

### 实施步骤

1. 强化 Lead/Planner 双语规则：点名 Provider 确定性选择、单候选收窄、多候选不得默认全选、MCP 超限先 search-tools。
2. 覆盖 React/Plan/Interaction 恢复对 provider/tool/exact function 的完整传播，历史 capability-only 记录继续可读。
3. 验证外部 Tool 调用 Trace 使用统一 tool_id/provider_id/source/backend 字段，不记录 URL/Header/Env/原始认证错误。
4. 删除剩余平行 MCP 刷新/注入入口及对应过时测试替身。

### 验证方式

- 运行：`uv run pytest tests/app/core/agent/test_lead_agent_routing_eval.py tests/app/core/agent/test_plan_capabilities.py tests/app/core/agent/test_interaction_resume.py tests/app/services/test_trace_service.py -q`
- 运行：`uv run ruff check app/core/prompts app/services/trace_service.py tests/app/core/agent tests/app/services/test_trace_service.py`
- 预期：全部退出码 0；中英文行为一致；Trace 不含敏感配置。

### 完成条件

- 外部 Provider 的模型可见边界、执行边界、恢复边界使用同一个 Scope Snapshot。
- 多 Provider 候选未明确选择时不会全量连接或注入。
- 旧会话和旧 Plan 不因新增字段失效。

### 执行结果

已强化 Lead/Planner 中英文 Provider 选择规则，并覆盖单 MCP 候选确定性收窄、多候选不默认全选和显式选择。惰性发现后 RuntimeToolScope 只重新分类原请求的 Tool ID，不扩大边界。TraceService 与 Lead Runtime 共享实时 Registry，动态 MCP Tool 的 tool_id/provider_id/source/backend 进入低基数 Trace 元数据。

### 验证证据

```text
命令：uv run pytest tests/app/core/tools/test_mcp_lazy_provider.py tests/app/core/agent/test_lead_agent_routing_eval.py tests/app/core/agent/test_prompt_locale_routing.py tests/app/core/agent/test_plan_capabilities.py tests/app/core/agent/test_interaction_resume.py tests/app/services/test_trace_service.py -q
退出状态：0
关键结果：63 passed；单候选/多候选/显式选择、历史 Tool ID 重分类、双语规则和动态 Provider Trace 全部通过。

命令：uv run ruff check app/core/prompts/lead.py app/core/prompts/planner.py app/core/prompts/en/planner.py app/services/trace_service.py app/core/agent/lead.py app/core/agent/agent_task_runner.py tests/app/core/tools/test_mcp_lazy_provider.py tests/app/core/agent/test_lead_agent_routing_eval.py tests/app/core/agent/test_prompt_locale_routing.py tests/app/services/test_trace_service.py
退出状态：0
关键结果：All checks passed!
执行时间：2026-08-19 09:11（Asia/Shanghai）
```

## Task 5：完成 Stage 1B 回归、设计回写与代码审查

状态：completed

### 目标

完成外部 Provider Tool Plane 的自动化、静态、编译、差异和代码审查门禁，并准确保留 Stage 2/3 未实施边界。

### 涉及文件

- `agentic/api/tests/app/core/agent/`
- `agentic/api/tests/app/core/tools/`
- `agentic/api/tests/app/services/`
- `agentic/docs/designs/agent-runtime-hitl-provider-reliability.zh-CN.md`
- `agentic/docs/plans/external-provider-tool-plane-plan.md`
- `agentic/docs/reviews/external-provider-tool-plane-review.md`

### 依赖与接口

- 前置任务：Task 1-4。
- 输入：Stage 1B 全部实现和定向验证证据。
- 输出：最终验证、审查结论和 `READY_TO_MERGE / BLOCKED / FAILED` 状态。

### 实施步骤

1. 运行 Agent/Tool/Trace 定向回归和后端全量测试。
2. 运行 Ruff、Python compileall 和 `git diff --check`。
3. 对照设计验收普通 Run 零外部连接、选中 Provider 单独激活、预算收窄、Scope/Trace/恢复一致性。
4. 执行代码审查并修复 blocking/major；修复后重新运行受影响测试和最终门禁。
5. 回写设计实施进度，明确 MCP Actor/快照与 A2A Card TTL 仍属于 Stage 2/3。

### 验证方式

- 运行：`uv run pytest tests/app/core/agent tests/app/core/tools tests/app/services/test_trace_service.py -q`
- 运行：`uv run pytest -q`
- 运行：`uv run ruff check app tests`
- 运行：`uv run python -m compileall -q app tests`
- 运行：`git diff --check`
- 预期：全部退出码 0；无未解决 blocking/major；只对 Stage 1B 给出完成结论。

### 完成条件

- 自动化、静态、编译和差异检查通过。
- 代码审查为 `APPROVED`。
- 计划和设计中的已实施/待实施边界与代码一致。

### 执行结果

已完成 Stage 1B 最终回归、设计回写和两轮代码审查。首轮审查识别的混合 Provider/Tool 约束、MCP 稳定 ID 与函数名碰撞、跨 Provider Schema 总预算、显式 Tool Search 后 Scope 收窄等 4 个 major，以及运行时 Descriptor 替换、Provider 元数据提示词边界和 MCP 专属刷新回调等 3 个 minor 均已修复并增加回归覆盖。复审未发现新的 blocking 或 major，结论为 `APPROVED`。

Stage 1B 仅完成外部 Provider 接入统一 Tool Plane；MCP 长生命周期 Provider Actor、跨 Run Schema Snapshot、取消隔离与类型化失败信息仍属于 Stage 2，A2A Card TTL 和共享 HTTP Client 仍属于 Stage 3。

### 验证证据

```text
命令：uv run pytest tests/app/core/agent tests/app/core/tools tests/app/services/test_trace_service.py -q
退出状态：0
关键结果：182 passed；11 条既有 Pydantic deprecation warning，无失败。

命令：uv run pytest -q
环境：一次性隔离 PostgreSQL/Redis 容器，数据库迁移升级至 20260818_0001；验证后容器已删除。
退出状态：0
关键结果：506 passed。

命令：uv run ruff check app tests
退出状态：0
关键结果：All checks passed!

命令：uv run python -m compileall -q app tests
退出状态：0
关键结果：编译检查通过。

命令：git diff --check
退出状态：0
关键结果：无空白错误；仅报告工作区既有 LF/CRLF 转换提示。

代码审查：docs/reviews/external-provider-tool-plane-review.md
最终结论：APPROVED；READY_TO_MERGE。
执行日期：2026-08-19（Asia/Shanghai）
```

## 计划变更

| 日期 | 变更内容 | 原因 | 影响任务 | 是否影响设计 |
| --- | --- | --- | --- | --- |
| 2026-08-19 | 无 | 初始计划 | 无 | 否 |

## 最终验证

### 执行命令

```bash
cd agentic/api
uv run pytest tests/app/core/agent tests/app/core/tools tests/app/services/test_trace_service.py -q
uv run pytest -q
uv run ruff check app tests
uv run python -m compileall -q app tests

cd ..
git diff --check
```

### 执行结果

- 单元测试：通过；Agent/Tool/Trace 核心定向 `182 passed`。
- 集成测试：通过；一次性隔离 PostgreSQL/Redis、迁移至最新版本后，后端全量 `506 passed`。
- 静态检查：通过；`ruff check app tests` 退出码 0。
- 类型检查：不适用（项目未配置独立 Python 类型检查门禁）
- 构建：不适用；Python `compileall` 检查通过。
- 数据库迁移：本批无新迁移；在隔离数据库执行既有迁移至 `20260818_0001` 成功。
- 手工验证：通过；确认临时测试容器已删除，未触碰现有 `manus-*` 服务。
- 代码审查：通过；首轮 4 个 major、3 个 minor 已全部修复，复审结论 `APPROVED`。

### 验收标准检查

- [x] Direct、Shell-only、File-only 和 Ask User Run 不连接 MCP/A2A。
- [x] Lead 在远端未连接时可读取安全 Provider 摘要，且目录不含凭据、端点和参数 Schema。
- [x] 只连接 Scope 选中的 MCP Provider；多候选未选择时不全量连接。
- [x] MCP Schema 超预算通过显式 search-tools 二阶段收窄。
- [x] A2A 网络资源只在真实 A2A 调用时初始化。
- [x] API/MCP/A2A 使用统一 Descriptor/Scope/Schema/Result/Trace 合同。
- [x] Provider/Tool/Exact Function 在 Plan 与 Ask User 恢复后保持不扩大。
- [x] Stage 2 MCP Actor/Snapshot 和 Stage 3 A2A Card TTL 未被错误宣称完成。
- [x] Stage 1B 全量测试、静态检查、编译检查与代码审查通过。

### 未通过项目

无。Stage 2/3 为本批明确排除的后续范围，不计为 Stage 1B 未通过项。

### 最终状态

`READY_TO_MERGE`
