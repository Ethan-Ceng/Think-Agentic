# Agent Runtime Sandbox 懒启动与 Tool Token 优化实施计划

## 关联设计

- 设计文档：`agentic/docs/designs/knowledge-document-processing.zh-CN.md`
- 开发分支：`feature/agent-runtime-lazy-sandbox`
- 后续计划：`agentic/docs/plans/document-processing-foundation-plan.md`
- 实施基线：进入功能分支时的 `master`；保留用户现有未提交文件，不混入本批

## 当前进度

- 整体状态：`IN_PROGRESS`
- 当前阶段：implementation
- 当前任务：无
- 已完成：1 / 6
- 阻塞问题：无
- 最近更新时间：2026-07-27（Asia/Shanghai）

## 全局约束

- 纯对话、Knowledge、Context Search 和文档查看不得创建、恢复或等待完整 Agent Sandbox。
- Sandbox 只能在首次调用 `requires_sandbox` 或 `requires_browser` 的 Tool 时创建，并且同一 Session 并发调用最多创建一个实例。
- 普通附件不得在 Run 开始时自动复制到 Sandbox；只同步当前 Sandbox Tool 实际需要的文件。
- Planner 的 `_tool_choice = none` 保持不变，Planner 模型调用不得再携带完整 Tool JSON Schema。
- Planner 通过紧凑 Capability Catalog 为每个 Step 输出 capability group；ReAct 只收到当前 Step 所需的完整 Tool Schema。
- Runtime Scope 只能缩小现有 ToolConfig 能力，不能重新启用已禁用或被策略拒绝的工具。
- `message_ask_user`、审批恢复、Skill runtime、MCP/A2A/API Tool、下一条消息队列、Trace 和分支行为保持兼容。
- 旧 Plan/Step 没有 capability 字段时必须安全兼容，不得导致历史 waiting Run 无法恢复。
- Sandbox 创建后继续写入 `sessions.sandbox_id`；未创建时保持 null，现有 VNC/文件/Shell API 返回当前稳定的“无沙箱环境”语义。
- 不修改 Sandbox 镜像内容，不把 Document Worker 放进本分支。
- 不新增数据库迁移；Plan/Step 仍存储于现有 Session event JSON。
- 不自动提交、推送、创建 PR 或合并。
- 一次只推进一个 Task；状态、偏差和验证证据必须立即写回本计划。

## 状态变更记录

| 日期时间 | 整体状态 | 当前任务 | 变更原因 |
| --- | --- | --- | --- |
| 2026-07-27 | `PLAN_READY` | 无 | 设计确认后拆出独立的 Sandbox 懒启动与 Tool Token 优化批次 |
| 2026-07-27 | `IN_PROGRESS` | Task 1 | 已建立 `feature/agent-runtime-lazy-sandbox` 分支，开始固定资源与 Tool Schema 基线 |
| 2026-07-27 | `IN_PROGRESS` | 无 | Task 1 基线与 Trace 观测字段验证完成，等待推进 Task 2 |

## Task 1：固定 Sandbox 资源成本与 Tool Schema Token 代理基线

状态：completed

### 目标

用自动化测试和 Trace 摘要分别度量两类成本：Sandbox 的创建/恢复、Browser 初始化、附件同步和启动时延属于运行资源成本；Tool Schema 的数量、序列化字节和模型实际输入 Token（Provider 可返回时）属于模型成本。两者不得混写为“Sandbox Token”。

同时统计当前 Tool Registry 中 `requires_sandbox`、`requires_browser` 与无需 Sandbox 的能力分布，并记录真正触发 Sandbox 的首个 Tool/Capability，以区分“生命周期无条件创建”与“用户任务确实需要 Sandbox”。

### 涉及文件

- `agentic/api/tests/app/services/test_agent_service_lazy_sandbox.py`（新建）
- `agentic/api/tests/app/core/agent/test_agent_task_runner_lazy_sandbox.py`（新建）
- `agentic/api/tests/app/core/agent/test_runtime_tool_scope.py`（新建）
- `agentic/api/app/services/agent_service.py`
- `agentic/api/app/core/agent/agent_task_runner.py`
- `agentic/api/app/services/trace_service.py`
- `agentic/api/tests/app/services/test_trace_service.py`（存在则修改，否则新建定向测试）

### 依赖与接口

- 前置任务：无。
- 输入：无附件普通消息、带附件消息、Shell/Browser Step、当前 Tool Registry。
- 输出：
  - Sandbox `create/get/ensure/get_browser/upload_file` 调用计数；
  - Sandbox 创建/恢复原因、首次请求 capability、启动时延和附件同步字节数；
  - Tool Registry 按 `requires_sandbox/requires_browser/no_sandbox` 的能力与 Schema 数量分布；
  - Planner/ReAct 每次模型调用的 `tool_schema_count`、序列化字节数，以及 Provider 已提供时的实际 input token；
  - 修改前预期失败、修改后持续通过的行为测试。

### 实施步骤

1. 构造 Fake Sandbox Class/Instance，分别记录创建、恢复、ensure、browser 和上传调用。
2. 固定普通无附件 Run 当前会创建 Sandbox 的失败测试，并断言这是 Task 初始化造成的，不是某个 Tool 已被选择。
3. 固定 Planner `_tool_choice=none` 但仍接收工具 Schema 的失败测试。
4. 固定 ReAct 当前接收全部已启用工具的失败测试。
5. 统计 Registry 中 Sandbox、Browser 与无 Sandbox Tool 的 group/function 数量，作为能力结构基线，而不是用单一总数推断原因。
6. 为 Trace Model Call 摘要增加 `tool_schema_count` 与 `tool_schema_bytes`，只记录数量和大小，不记录凭据或完整动态 Schema；Provider 已返回 usage 时复用实际 input token，不自行用字节数伪造 Token。
7. 为 Sandbox 激活增加 `activation_reason`、`first_capability`、启动耗时和附件同步大小摘要；无条件旧路径记为 `task_initialization`。
8. 覆盖空工具列表、动态 API/MCP 工具、中文 Schema 和无 Sandbox Tool Run 的稳定计数。

### 验证方式

- 运行：`uv run pytest tests/app/services/test_agent_service_lazy_sandbox.py tests/app/core/agent/test_agent_task_runner_lazy_sandbox.py tests/app/core/agent/test_runtime_tool_scope.py tests/app/services/test_trace_service.py -q`
- 运行：`uv run ruff check app/services/trace_service.py tests/app/services/test_agent_service_lazy_sandbox.py tests/app/core/agent/test_agent_task_runner_lazy_sandbox.py tests/app/core/agent/test_runtime_tool_scope.py tests/app/services/test_trace_service.py`
- 预期：测试在修改前准确暴露无条件 Sandbox/全量 Schema，Task 完成后基线指标字段通过且不泄露 Schema 内容。

### 完成条件

- 后续任务可以分别证明：
  - 无需 Sandbox 的 Run 不再承担容器和附件同步成本；
  - 确实需要 Shell/Browser/File 的 Run 仍能按需创建 Sandbox；
  - Planner/ReAct 的 Schema 输入显著缩小；
  - 若仍频繁启动 Sandbox，可从 `first_capability` 判断是能力结构问题还是路由/Planner 问题。

### 执行结果

- 已固定当前 Sandbox 生命周期基线：
  - 新 Session 在任何 Tool 被选择前，由 `AgentService._create_task()` 执行 `create=1`、`get_browser=1`；
  - 有 `sandbox_id` 时执行 `get=1`、`get_browser=1`；
  - `AgentTaskRunner.invoke()` 每个 Task 启动执行 `ensure=1`；
  - 普通消息附件在 Flow/Planner 前逐文件执行 `upload_file`，同步字节数按文件大小累计。
- 已固定默认 Tool Registry 基线：6 个 group、27 个 function；其中 Browser 12、Sandbox 10、无 Sandbox 5；完整 Schema UTF-8 代理大小为 12,933 字节。
- 已证明 Planner 虽然 `_tool_choice=none`，仍与 ReAct 一样接收 27 个完整 Schema/12,933 字节；这只是字节代理，不伪造 Token。
- Trace 的 `run.started` 现在记录 Registry 分类摘要；`model.started` 和 Model Call `request_preview` 记录 `tool_schema_count/tool_schema_bytes`，不持久化完整动态 Schema。
- Provider 返回 usage 时继续使用实际 `prompt_tokens/completion_tokens/total_tokens`，没有用 Schema 字节换算 Token。
- 当前 eager Sandbox 创建、ensure、Browser 初始化和附件同步会汇总为一次 `sandbox.activated` 事件，包含 `activation_reason=task_initialization`、operation counts、启动毫秒和附件字节；不记录附件内容或完整 Schema。
- 本 Task 只增加基线测试和观测，不改变 Sandbox 创建时机或工具可见范围；懒启动从 Task 2 开始实施。

### 验证证据

```text
命令：uv run pytest tests/app/services/test_agent_service_lazy_sandbox.py tests/app/core/agent/test_agent_task_runner_lazy_sandbox.py tests/app/core/agent/test_runtime_tool_scope.py tests/app/services/test_trace_service.py tests/app/core/agent/test_agent_task_runner_completion.py tests/app/services/test_agent_service_recovery.py tests/app/services/test_skill_trace.py -q
退出状态：0
关键结果：32 passed；10 个既有 Pydantic deprecation warnings
执行时间：2026-07-27 15:23（Asia/Shanghai）

命令：uv run ruff check app/services/agent_service.py app/core/agent/agent_task_runner.py app/services/trace_service.py tests/app/services/test_agent_service_lazy_sandbox.py tests/app/core/agent/test_agent_task_runner_lazy_sandbox.py tests/app/core/agent/test_runtime_tool_scope.py tests/app/services/test_trace_service.py
退出状态：0
关键结果：All checks passed
执行时间：2026-07-27 15:23（Asia/Shanghai）

命令：uv run python -m py_compile app/services/agent_service.py app/core/agent/agent_task_runner.py app/services/trace_service.py
退出状态：0
关键结果：无语法错误
执行时间：2026-07-27 15:23（Asia/Shanghai）
```

## Task 2：建立并发安全的 Lazy Sandbox Runtime

状态：pending

### 目标

建立一个 Session 级懒 Sandbox Provider 和代理对象，使 Tool 可以在构造时获得稳定依赖，但只有首次实际调用时才创建/恢复 Sandbox 与 Browser。

### 涉及文件

- `agentic/api/app/core/sandbox/runtime.py`（新建）
- `agentic/api/app/core/sandbox/base.py`
- `agentic/api/app/core/browser/lazy.py`（新建，若 Browser Proxy 独立）
- `agentic/api/app/services/agent_service.py`
- `agentic/api/app/repositories/session_repository.py`
- `agentic/api/app/repositories/db_session_repository.py`
- `agentic/api/tests/app/core/sandbox/test_lazy_sandbox_runtime.py`（新建）
- `agentic/api/tests/app/repositories/test_db_session_runtime_handles.py`（存在则扩展，否则新建）

### 依赖与接口

- 前置任务：Task 1。
- 输入：session_id、已有 nullable sandbox_id、Sandbox class、UOW factory。
- 输出：
  - `LazySandboxRuntime.get_sandbox()`；
  - `LazySandboxRuntime.get_browser()`；
  - 实现现有 Sandbox/Browser Protocol 的代理；
  - 首次成功创建后原子持久化 sandbox_id。

### 实施步骤

1. 先写并发失败测试：两个协程同时请求 Sandbox 只能调用一次 `create()`。
2. 定义 Lazy Runtime，内部使用 async lock 和 double-check，优先恢复已有 sandbox_id，恢复失败才创建。
3. 创建成功后通过独立 UOW 更新 Session runtime handle；Session 已删除时销毁新实例并失败。
4. 创建/恢复失败不得写入 sandbox_id；后续调用允许重试。
5. Browser Proxy 在首次 Browser 方法调用时取得真实 Browser，并缓存于同一 Runtime。
6. Sandbox Proxy 将所有 Sandbox 方法委托给真实实例；读取 `id/vnc_url/cdp_url` 前若尚未创建，不得隐式创建，改由明确 async 获取入口使用。
7. 处理 Session 停止、Run 取消和服务关闭：未创建实例不执行 destroy；共享/固定 `SANDBOX_ADDRESS` 保持当前销毁语义。
8. 记录 `sandbox_lazy_create`、`sandbox_lazy_reuse`、`sandbox_lazy_failed`，不记录用户文件内容。

### 验证方式

- 运行：`uv run pytest tests/app/core/sandbox/test_lazy_sandbox_runtime.py tests/app/repositories/test_db_session_runtime_handles.py -q`
- 运行：`uv run python -m py_compile app/core/sandbox/runtime.py app/core/browser/lazy.py app/services/agent_service.py`
- 运行：`uv run ruff check app/core/sandbox/runtime.py app/core/browser/lazy.py app/services/agent_service.py tests/app/core/sandbox/test_lazy_sandbox_runtime.py`
- 预期：退出 0；未调用时零 Sandbox，并发首次调用只创建一次，失败可重试，handle 一致。

### 完成条件

- Agent Runtime 可以持有 Sandbox/Browser 能力而不在构造 Task 时启动真实环境。

### 执行结果

待执行。

### 验证证据

```text
命令：待执行
退出状态：待执行
关键结果：待执行
执行时间：待执行
```

## Task 3：让 Agent Task 与附件同步真正按需触发

状态：pending

### 目标

移除 Run 启动时的 `ensure_sandbox()` 和全附件同步，在 Sandbox Tool 首次使用时只同步当前 Run 所需附件，同时保持已有文件、Shell、Browser 和输出文件行为。

### 涉及文件

- `agentic/api/app/services/agent_service.py`
- `agentic/api/app/core/agent/agent_task_runner.py`
- `agentic/api/app/core/entities/message.py`
- `agentic/api/app/core/entities/event.py`（仅在需要安全附件引用时修改）
- `agentic/api/app/core/sandbox/runtime.py`
- `agentic/api/app/core/tools/shell.py`
- `agentic/api/app/core/tools/file.py`
- `agentic/api/app/core/tools/browser.py`
- `agentic/api/tests/app/services/test_agent_service_lazy_sandbox.py`
- `agentic/api/tests/app/core/agent/test_agent_task_runner_lazy_sandbox.py`
- `agentic/api/tests/app/core/agent/test_lazy_attachment_materialization.py`（新建）

### 依赖与接口

- 前置任务：Task 2。
- 输入：消息附件的 Managed File ID/安全摘要、当前 Session。
- 输出：
  - Planner 可读的文件名/类型 Manifest；
  - Sandbox 首次使用时的确定性路径映射；
  - 每个 File ID 在同一 Sandbox 最多同步一次。

### 实施步骤

1. `AgentService._create_task()` 不再创建 Sandbox 或 Browser，改为创建 Lazy Runtime 和代理。
2. `AgentTaskRunner.invoke()` 移除无条件 `ensure_sandbox()`。
3. 消息进入 Flow 前保留安全附件引用与文件名，不把未创建的 Sandbox 路径伪装成已存在。
4. Lazy Runtime 持有当前 Run 的附件 Manifest；Sandbox Shell/File/Browser 能力首次激活时调用统一 materializer。
5. Materializer 从当前用户 FileStorage 下载文件，使用安全去重文件名写入 `/home/ubuntu/upload`，缓存 `file_id -> sandbox_path`。
6. 非 Sandbox Context Tool 不触发 materialize。
7. Agent 生成文件上传、ToolEvent 预览、Shell Console 和 Browser Screenshot 继续走真实 Sandbox；尚未创建时不访问代理属性。
8. Session/Run 切换和 next-message 更新附件 Manifest，不泄漏上一个用户或 Run 的路径。

### 验证方式

- 运行：`uv run pytest tests/app/services/test_agent_service_lazy_sandbox.py tests/app/core/agent/test_agent_task_runner_lazy_sandbox.py tests/app/core/agent/test_lazy_attachment_materialization.py tests/app/core/agent/test_agent_task_runner_completion.py -q`
- 运行：`uv run ruff check app/services/agent_service.py app/core/agent/agent_task_runner.py app/core/sandbox/runtime.py app/core/tools/shell.py app/core/tools/file.py app/core/tools/browser.py tests/app/core/agent/test_lazy_attachment_materialization.py`
- 预期：普通/Context Run 为零 Sandbox；Sandbox Tool 首次调用创建一次并按需同步；现有完成、等待和队列测试通过。

### 完成条件

- Sandbox 的资源生命周期由实际执行能力驱动，而不是由 Session 或附件存在驱动。

### 执行结果

待执行。

### 验证证据

```text
命令：待执行
退出状态：待执行
关键结果：待执行
执行时间：待执行
```

## Task 4：裁剪 Planner 与 ReAct 的 Tool Schema

状态：pending

### 目标

让 Planner 使用紧凑 Capability Catalog 且不接收完整 Tool Schema，并让每个 ReAct Step 只接收其声明 capability 对应的工具。

### 涉及文件

- `agentic/api/app/core/entities/plan.py`
- `agentic/api/app/core/prompts/planner.py`
- `agentic/api/app/core/agent/base.py`
- `agentic/api/app/core/agent/planner.py`
- `agentic/api/app/core/agent/react.py`
- `agentic/api/app/core/flows/planner_react.py`
- `agentic/api/app/core/tools/factory.py`
- `agentic/api/app/core/tools/scope.py`（新建）
- `agentic/api/app/core/tools/registry.py`
- `agentic/api/app/services/trace_service.py`
- `agentic/api/tests/app/core/agent/test_runtime_tool_scope.py`
- `agentic/api/tests/app/core/agent/test_plan_capabilities.py`（新建）
- `agentic/api/tests/app/core/agent/test_skill_runtime_context.py`
- `agentic/api/tests/app/core/agent/test_branch_context_seed.py`

### 依赖与接口

- 前置任务：Task 1；可与 Task 2–3 独立实现，合并验证依赖 Task 3。
- 输入：Tool Registry descriptor 的 group/requirements、Planner Step。
- 输出：
  - `Step.capabilities: list[str]`，默认空以兼容历史事件；
  - 紧凑 Capability Catalog；
  - `RuntimeToolScope`；
  - Planner tools 始终 `[]`；
  - ReAct 当前 Step 的过滤后 Schema。

### 实施步骤

1. 为 Step 增加 capability group 列表和稳定校验，只接受 Registry 提供的 group；旧 JSON 缺失时可解析。
2. 从 Tool Registry 生成紧凑 Catalog：group、简短描述、是否需要 sandbox/browser；不包含参数 JSON Schema。
3. 更新 Planner Prompt 输出每个 Step 的 capabilities；Planner `_tool_choice=none` 时 `_get_available_tools()` 明确返回空。
4. 在执行 Step 前设置 Runtime Tool Scope；ToolFactory/FilteredTool 先按 Scope 缩小，再应用现有 ToolConfig。
5. 永久保留完成结构化交互所需的系统 message 能力；Skill runtime context 只可在 Scope 内增加本 Run 明确启用的 contextual tool。
6. 未知 capability、空 capability 和旧 Plan 使用安全回退：
   - 纯文本步骤默认无外部执行工具；
   - 恢复已有待审批 Tool Call 时按持久化 function_name 精确恢复；
   - 不使用“空列表等于全部工具”。
7. Trace 记录 capability groups、实际 Schema count/bytes 和被 Scope 排除数量。
8. 固定 Planner 为 0 Schema、纯 Context Step 仅 Context Tool、Shell Step 包含 Shell/File 但不包含 Browser 的测试。

### 验证方式

- 运行：`uv run pytest tests/app/core/agent/test_runtime_tool_scope.py tests/app/core/agent/test_plan_capabilities.py tests/app/core/agent/test_skill_runtime_context.py tests/app/core/agent/test_branch_context_seed.py -q`
- 运行：`uv run python -m py_compile app/core/entities/plan.py app/core/tools/scope.py app/core/tools/factory.py app/core/agent/base.py app/core/flows/planner_react.py`
- 运行：`uv run ruff check app/core/entities/plan.py app/core/prompts/planner.py app/core/tools/scope.py app/core/tools/factory.py app/core/tools/registry.py app/core/agent/base.py app/core/agent/planner.py app/core/agent/react.py app/core/flows/planner_react.py tests/app/core/agent/test_runtime_tool_scope.py tests/app/core/agent/test_plan_capabilities.py`
- 预期：退出 0；Planner 0 Schema，ReAct Schema 与 Step capability 精确匹配，现有 ToolConfig/Skill/恢复行为不被绕过。

### 完成条件

- Tool Token 成本从“每轮全量工具”变为“Planner 紧凑目录 + 当前 Step 必要 Schema”。

### 执行结果

待执行。

### 验证证据

```text
命令：待执行
退出状态：待执行
关键结果：待执行
执行时间：待执行
```

## Task 5：保持 VNC、审批恢复、队列与生命周期兼容

状态：pending

### 目标

在懒 Sandbox 和 Tool Scope 下收口跨 Run 生命周期与兼容性，确保只有资源创建时机改变，用户已有交互不回归。

### 涉及文件

- `agentic/api/app/services/session_service.py`
- `agentic/api/app/controllers/session.py`（仅在错误映射需要时修改）
- `agentic/api/app/core/agent/agent_task_runner.py`
- `agentic/api/app/core/sandbox/runtime.py`
- `agentic/api/tests/app/services/test_agent_interactions.py`
- `agentic/api/tests/app/services/test_agent_next_message.py`
- `agentic/api/tests/app/services/test_agent_service_recovery.py`
- `agentic/api/tests/app/interfaces/endpoints/test_session_interactions.py`
- `agentic/api/tests/app/interfaces/endpoints/test_session_next_message_route.py`
- `agentic/api/tests/app/interfaces/endpoints/test_session_recovery_route.py`
- `agentic/web/src/components/SessionDetailView.spec.ts`（只有前端状态需调整时修改）

### 依赖与接口

- 前置任务：Task 2–4。
- 输入：waiting approval、resume、next message、VNC 请求、Run 取消、服务关闭。
- 输出：原有协议和稳定错误；Sandbox 未创建时明确不可用，创建后行为不变。

### 实施步骤

1. 覆盖普通 running Session 尚未创建 Sandbox 时 VNC 返回当前稳定错误，不因此反向创建 Sandbox。
2. 覆盖 Browser Tool 创建 Sandbox 后 VNC 可连接的 Service 行为。
3. 覆盖 Tool Approval 在 Sandbox 创建前暂停、批准后首次创建并只执行一次。
4. 覆盖 waiting 恢复时 Capability Scope 可由持久化待调用函数恢复，不依赖重新规划。
5. 覆盖 next-message：第一条纯文本不创建，后续 Shell 消息创建；反向顺序复用同一实例。
6. 覆盖 Run cancel/error、Sandbox 创建中取消、实例创建后 Task destroy 和固定 Sandbox Address。
7. 确认未创建 Sandbox 的 Session 删除/归档/分支行为不变。
8. 如 UI 把 `running` 等同于 VNC 可用，改为仅 ToolEvent/明确能力后显示入口；否则不修改前端。

### 验证方式

- 运行：`uv run pytest tests/app/services/test_agent_interactions.py tests/app/services/test_agent_next_message.py tests/app/services/test_agent_service_recovery.py tests/app/interfaces/endpoints/test_session_interactions.py tests/app/interfaces/endpoints/test_session_next_message_route.py tests/app/interfaces/endpoints/test_session_recovery_route.py -q`
- 如前端修改，运行：`pnpm test:run -- src/components/SessionDetailView.spec.ts`
- 预期：退出 0；暂停/恢复/队列/VNC/取消路径无重复执行和资源泄漏。

### 完成条件

- Sandbox 懒启动不改变可观察业务协议，只改变无需要 Run 的资源与 Tool Schema 成本。

### 执行结果

待执行。

### 验证证据

```text
命令：待执行
退出状态：待执行
关键结果：待执行
执行时间：待执行
```

## Task 6：全量验证、资源对比和代码审查

状态：pending

### 目标

用自动化、真实 Docker 行为和 Trace 数据证明普通 Run 零 Sandbox、工具 Schema 明显缩小，同时完成回归和合并门禁。

### 涉及文件

- `agentic/docs/plans/agent-runtime-lazy-sandbox-plan.md`
- `agentic/docs/reviews/agent-runtime-lazy-sandbox-review.md`（新建）
- 本计划实际修改的代码与测试

### 依赖与接口

- 前置任务：Task 1–5。
- 输出：最新测试、静态检查、资源/Token 对比、手工验证和分级代码审查。

### 实施步骤

1. 运行所有定向测试、后端全量测试、Ruff、py_compile 和 diff 检查。
2. 在 Docker 可用环境执行三条真实路径：
   - 普通文本问答；
   - 未来 Context Tool/Fake Context Tool 问答；
   - Shell 或 Browser Tool 问答。
3. 检查前两条在首个模型调用和结束后均无新 Sandbox container/session sandbox_id。
4. 检查第三条只创建一个 Sandbox，VNC/附件/输出文件保持可用。
5. 从 Trace 比较修改前后 Planner/ReAct 的 `tool_schema_count/bytes`；Planner 必须为 0，纯 Context Step 不含 Sandbox 工具。
6. 检查并发首次调用、取消、失败重试和服务关闭无孤儿容器。
7. 执行代码审查，处理 blocking/major 后重新验证。
8. 将实际命令、结果、资源数据和最终状态写回计划。

### 验证方式

- 运行：`uv run pytest -q`
- 运行：`uv run ruff check app tests`
- 运行：`uv run python -m py_compile app/core/sandbox/runtime.py app/core/tools/scope.py app/core/agent/base.py app/core/agent/agent_task_runner.py app/core/flows/planner_react.py app/services/agent_service.py`
- 运行：`git diff --check`
- 如前端修改，运行：`pnpm test:run`、`pnpm type-check`、`pnpm build`
- 手工：Docker container 数、Session sandbox_id、VNC、Trace Schema bytes 对比。
- 预期：全部退出 0；无未处理 blocking/major；资源与 Token 目标有可重复证据。

### 完成条件

- 自动化与真实环境都证明按需创建、按需同步和按 Step Schema 裁剪，无业务回归。

### 执行结果

待执行。

### 验证证据

```text
命令：待执行
退出状态：待执行
关键结果：待执行
执行时间：待执行
```

## 计划变更

| 日期 | 变更内容 | 原因 | 影响任务 | 是否影响设计 |
| --- | --- | --- | --- | --- |
| 2026-07-27 | 初始计划 | 将急迫的 Sandbox/Token 优化与文档格式能力拆分，先建立无 Sandbox Run 基础 | Task 1–6 | 否 |
| 2026-07-27 | 固定 eager Sandbox 与全量 Tool Schema 基线，并把摘要接入 Trace | 将容器资源成本、Schema 字节代理和 Provider 实际 Token 分开观测后才能证明后续优化幅度 | Task 1–Task 6 | 否 |

## 最终验证

### 执行命令

```bash
cd agentic/api
uv run pytest -q
uv run ruff check app tests
uv run python -m py_compile app/core/sandbox/runtime.py app/core/tools/scope.py app/core/agent/base.py app/core/agent/agent_task_runner.py app/core/flows/planner_react.py app/services/agent_service.py
git diff --check
```

如前端发生实际修改：

```bash
cd agentic/web
pnpm test:run
pnpm type-check
pnpm build
```

### 执行结果

- 单元测试：未执行
- 集成测试：未执行
- 静态检查：未执行
- 类型检查：未执行
- 构建：未执行
- 数据库迁移：不适用，本批不修改数据库 Schema
- 手工验证：未执行
- 代码审查：未执行

### 验收标准检查

- [ ] 普通文本、Knowledge 和 Context Run 不创建/恢复 Sandbox。
- [ ] Planner 模型调用的完整 Tool Schema 数为 0。
- [ ] ReAct 只接收当前 Step capability 对应的 Schema。
- [ ] 首次 Shell/Browser/File Workspace Tool 调用只创建一个 Sandbox。
- [ ] 附件只在 Sandbox Tool 实际需要时同步，且同一 File 不重复同步。
- [ ] ToolConfig、审批、waiting 恢复、下一条消息、Skill、MCP/A2A/API 和 Trace 无回归。
- [ ] VNC 在 Sandbox 未创建时不诱发创建，创建后可用。
- [ ] Trace 能展示 Schema 数量/大小与 Sandbox lazy 指标。
- [ ] 全量测试、静态检查、真实 Docker 验证和代码审查通过。

### 未通过项目

无；实施后填写。

### 最终状态

`READY_TO_MERGE / BLOCKED / FAILED`
