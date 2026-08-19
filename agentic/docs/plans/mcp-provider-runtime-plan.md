# MCP Provider Runtime、Schema Snapshot 与取消隔离实施计划

## 关联设计

- 设计文档：`agentic/docs/designs/agent-runtime-hitl-provider-reliability.zh-CN.md`
- 实施范围：设计中的“阶段 2：MCP Provider Actor 和 Schema Snapshot”，以及该阶段交付所必需的最小 FailureInfo、取消来源和前端错误投影
- 开发分支：`refactor/unified-tool-plane`
- 基线阶段：Stage 1A/1B `READY_TO_MERGE` 工作区

## 当前进度

- 整体状态：`COMPLETE`
- 当前阶段：completed
- 当前任务：Task 6：完成 Stage 2 回归、设计回写与代码审查
- 已完成：6 / 6
- 阻塞问题：无
- 最近更新时间：2026-08-19（Asia/Shanghai）

## 全局约束

- 保留 Stage 1B 的离线 Provider Catalog、不可扩大的 RuntimeToolScope、统一 Schema Resolver、Executor Router 和 Trace 合同；Stage 2 不新增平行工具注入链路。
- 每个 MCP Provider 的传输创建、Schema 发现、调用和关闭必须由同一个 Actor Task 所有，Agent Run 不得接触 `ClientSession`、`AsyncExitStack` 或 AnyIO cancel scope。
- Pool 的隔离键至少包含 `user_id + provider_id + config_fingerprint + protocol_version`；不同用户即使 Provider ID 相同也不得共享连接或快照。
- Schema Snapshot 只保存安全 Tool Schema、发现时间和失效信息，不保存 URL、Header、Env、Credential、用户参数或 Tool Result。
- 有新鲜 Snapshot 时 Schema 解析不得连接 Provider；实际 Tool 调用仍可按需激活 Actor。
- Provider 内部 `CancelledError` 必须在 Actor 边界转换为类型化 Provider 失败，不能取消父 Agent Task；明确用户停止和应用关闭继续作为真正的 Run 取消。
- `ErrorEvent.error` 和 `ToolResult.message` 保留兼容；新增 `failure` 为可选字段，原始异常、端点、Header、Env 和凭据不得进入 SSE、ToolResult 或低权限 Trace。
- Provider Actor 使用有界指数退避、连接去重、独立健康状态和 idle TTL；一个 Provider 的失败或关闭不得影响其他 Provider。
- 本批不实现跨进程 Pool、持久化 Snapshot、A2A Card TTL/共享 HTTP Client、完整 Capability Grant、Durable Run Finalizer、`form_input` 或数据库迁移。
- 本批不重启服务，不自动提交、推送、创建 PR 或合并。

## 状态变更记录

| 日期时间 | 整体状态 | 当前任务 | 变更原因 |
| --- | --- | --- | --- |
| 2026-08-19（Asia/Shanghai） | `PLAN_READY` | 无 | Stage 2 边界、依赖顺序和六个可恢复任务已确认 |
| 2026-08-19（Asia/Shanghai） | `IN_PROGRESS` | Task 1 | 计划覆盖度与分支门禁通过，开始 FailureInfo 合同测试 |
| 2026-08-19（Asia/Shanghai） | `IN_PROGRESS` | Task 2 | FailureInfo 的 4 项合同测试与 Ruff 通过，开始租户隔离 Schema Snapshot |
| 2026-08-19（Asia/Shanghai） | `IN_PROGRESS` | Task 3 | Snapshot 隔离、TTL、深拷贝和失效通过 8 项相关测试与 Ruff，开始 Actor/Pool 生命周期实现 |
| 2026-08-19（Asia/Shanghai） | `IN_PROGRESS` | Task 4 | Actor/Pool 的并发、单 Task 所有权、Cancel 隔离、退避、TTL 和配置更新通过 10 项测试与 Ruff，开始应用集成 |
| 2026-08-19（Asia/Shanghai） | `IN_PROGRESS` | Task 5 | 共享 Pool、跨 Run Snapshot/Actor 复用、用户隔离和应用关闭通过 25 项相关测试与 Ruff，开始取消/错误投影 |
| 2026-08-19（Asia/Shanghai） | `VERIFYING` | Task 6 | 取消来源、Failure Trace 与前端错误投影通过 39 项后端、9 项前端组件测试、Ruff 和类型检查，进入最终验证 |
| 2026-08-19（Asia/Shanghai） | `REVIEWING` | Task 6 | Stage 2 定向 210、后端全量 523、Web 全量 187 及静态/编译/类型/构建/差异门禁通过，进入代码审查 |
| 2026-08-19（Asia/Shanghai） | `IN_PROGRESS` | Task 6 | 自检累计发现 7 项 major，修复配置代际失效、连续退避、Pool 所有权、缓存容量、关停顺序/容错和 Provider 操作超时 |
| 2026-08-19（Asia/Shanghai） | `COMPLETE` | Task 6 | 7 项 major 全部修复；定向 218、后端全量 531、Web 全量 187 及全部静态/编译/类型/构建/差异门禁通过，复审批准 |

## Task 1：建立兼容的 FailureInfo 与 Provider 错误合同

状态：completed

### 目标

为 Provider/Tool/Run 失败建立安全、稳定、可序列化的领域模型，并保持旧事件和旧 ToolResult 的读取兼容。

### 涉及文件

- `agentic/api/app/core/entities/failure.py`
- `agentic/api/app/core/entities/tool_result.py`
- `agentic/api/app/core/entities/event.py`
- `agentic/api/app/core/tools/provider_runtime.py`
- `agentic/api/tests/app/core/test_failure_contract.py`

### 依赖与接口

- 前置任务：无。
- 输入：现有字符串 `ErrorEvent.error`、`ToolResult.message` 与设计错误码基线。
- 输出：`FailureInfo`、稳定枚举、`ProviderRuntimeError` 和安全工厂函数。

### 实施步骤

1. 定义 FailureCategory、FailureScope、RecoveryAction 和 FailureInfo，强制稳定 code、低基数 source、安全 message、retryable、可选 provider/tool call 和 debug ID。
2. 给 ErrorEvent 与 ToolResult 增加可选 failure；自动保持 `error == failure.message` 或 `message == failure.message`，旧 JSON 无 failure 时继续反序列化。
3. 定义 ProviderRuntimeError，只携带 FailureInfo；实现连接、超时、协议和 Schema 发现失败的安全映射，原始异常仅作为服务端 cause/log。
4. 增加序列化、旧事件兼容、敏感错误不外泄和稳定恢复动作测试。

### 验证方式

- 运行：`uv run pytest tests/app/core/test_failure_contract.py -q`
- 运行：`uv run ruff check app/core/entities/failure.py app/core/entities/tool_result.py app/core/entities/event.py app/core/tools/provider_runtime.py tests/app/core/test_failure_contract.py`
- 预期：退出码均为 0；旧 JSON 兼容，失败投影中不含端点、Header、Credential 或原始异常。

### 完成条件

- ErrorEvent/ToolResult V2 兼容旧调用方。
- Provider 错误具有稳定 code/scope/retryable/recovery_actions/debug_id。
- 原始异常不会直接进入用户可见字段。

### 执行结果

新增 FailureInfo、FailureCategory、FailureScope 和 RecoveryAction 稳定合同；ErrorEvent 与 ToolResult 增加可选 failure 并自动投影兼容字段。新增 ProviderFailureCode、provider_failure 和 ProviderRuntimeError，用户投影只包含安全消息、稳定错误码、恢复动作和 debug_id，原始异常仅保留为服务端 cause。

### 验证证据

```text
命令：uv run pytest tests/app/core/test_failure_contract.py -q
退出状态：0
关键结果：4 passed；旧 JSON 兼容、failure 消息投影、安全 Provider 错误和唯一 debug_id 均通过。

命令：uv run ruff check app/core/entities/failure.py app/core/entities/tool_result.py app/core/entities/event.py app/core/tools/provider_runtime.py tests/app/core/test_failure_contract.py
退出状态：0
关键结果：All checks passed!
执行日期：2026-08-19（Asia/Shanghai）
```

## Task 2：实现租户隔离的 MCP Schema Snapshot

状态：completed

### 目标

实现进程内、配置指纹感知、TTL 控制且不含敏感配置的 MCP Schema Snapshot，使多轮 Run 可无连接复用有效 Schema。

### 涉及文件

- `agentic/api/app/core/tools/provider_runtime.py`
- `agentic/api/app/core/config.py`
- `agentic/api/tests/app/core/tools/test_mcp_schema_snapshot.py`

### 依赖与接口

- 前置任务：Task 1。
- 输入：user_id、稳定 provider_id、单 Server MCPConfig、protocol_version 和安全 Tool Schema。
- 输出：ProviderRuntimeKey、配置指纹、MCPSchemaSnapshot、TTL Cache 与显式失效接口。

### 实施步骤

1. 定义包含 user_id/provider_id/config_fingerprint/protocol_version 的不可变 Runtime Key；配置指纹覆盖完整连接配置但只以摘要形式存在。
2. 定义 Snapshot 的深拷贝读写、发现/过期时间和 fresh/stale 判定；不缓存用户参数、调用结果或连接对象。
3. 增加可配置 Snapshot TTL、Actor idle TTL、连接退避基数/上限，设置保守且可测试的默认值。
4. 配置指纹变化时立即拒绝旧 Snapshot，并为 Pool 后续关闭旧 Actor 提供按 user/provider 失效能力。

### 验证方式

- 运行：`uv run pytest tests/app/core/tools/test_mcp_schema_snapshot.py -q`
- 运行：`uv run ruff check app/core/tools/provider_runtime.py app/core/config.py tests/app/core/tools/test_mcp_schema_snapshot.py`
- 预期：退出码均为 0；同用户同配置命中，不同用户/配置不命中，快照修改不污染缓存，过期后失效。

### 完成条件

- Snapshot Key 不允许跨用户或跨配置复用。
- Snapshot 内容不含 MCP 连接配置和调用数据。
- TTL、深拷贝和显式失效行为确定且有测试。

### 执行结果

新增 ProviderRuntimeKey、MCP 配置指纹、MCPSchemaSnapshot 与进程内 Cache。Runtime Key 包含用户命名空间、稳定 Provider ID、完整配置摘要和协议版本；Cache 在读写边界深拷贝 Schema，支持 TTL 过期和按用户/Provider 失效。新增四个可配置 Runtime 默认值及相互约束。

### 验证证据

```text
命令：uv run pytest tests/app/core/tools/test_mcp_schema_snapshot.py tests/app/core/test_failure_contract.py -q
退出状态：0
关键结果：8 passed；跨用户/配置隔离、无敏感配置投影、深拷贝、TTL、失效和配置默认值全部通过。

命令：uv run ruff check app/core/tools/provider_runtime.py app/core/config.py tests/app/core/tools/test_mcp_schema_snapshot.py
退出状态：0
关键结果：All checks passed!
执行日期：2026-08-19（Asia/Shanghai）
```

## Task 3：实现单所有者 MCP Provider Actor 与 Pool

状态：completed

### 目标

让每个 MCP Provider 由独立 Actor Task 串行拥有连接生命周期，并保证并发连接去重、取消隔离、退避、idle TTL 和应用级关闭。

### 涉及文件

- `agentic/api/app/core/tools/provider_runtime.py`
- `agentic/api/tests/app/core/tools/test_mcp_provider_actor.py`

### 依赖与接口

- 前置任务：Task 1-2。
- 输入：Runtime Key、单 Provider 配置、低层 MCP manager factory 和 discover/invoke/close 请求。
- 输出：MCPProviderActor、MCPProviderPool、Schema Snapshot 命中路径和类型化 ToolResult/ProviderRuntimeError。

### 实施步骤

1. 用请求队列和 Future 实现 Actor；manager 初始化、Schema 发现、调用和 cleanup 全部只在 Actor Task 执行。
2. Pool 用锁保证同 Key 首次并发请求只创建一个 Actor/连接；Provider 间 Actor、状态、请求和失败完全隔离。
3. Actor 捕获 Provider 操作的 BaseException：内部 cancel scope 异常转换为 PROVIDER_PROTOCOL_ERROR 并完成请求 Future；仅显式 Actor/Pool 关闭执行有序终止。
4. 实现有界指数退避、DEGRADED 状态、idle TTL 自动关闭、配置指纹变化关闭旧 Actor，以及幂等 Pool.close。
5. 通过 Actor done 收尾所有在途 Future，确保任何路径都不向 Agent Run 泄漏裸 CancelledError。

### 验证方式

- 运行：`uv run pytest tests/app/core/tools/test_mcp_provider_actor.py tests/app/core/tools/test_mcp_schema_snapshot.py -q`
- 运行：`uv run ruff check app/core/tools/provider_runtime.py tests/app/core/tools/test_mcp_provider_actor.py`
- 预期：退出码均为 0；并发首次连接为 1、生命周期同 Task、Provider Cancel 转类型化失败、其他 Provider 继续、TTL/配置更新/关闭无泄漏。

### 完成条件

- Agent Run 只能通过 Pool/Proxy 调用 Provider，不接触 manager/session。
- 一个 Provider 的失败不取消调用者或其他 Actor。
- 首次并发连接、退避、idle timeout、配置更新和 Pool.close 行为全部可验证。

### 执行结果

新增应用级 MCPProviderPool 和单 Provider MCPProviderActor。Actor 通过请求队列/Future 独占 manager 的初始化、Schema 发现、调用和清理；Pool 负责租户/配置隔离、首次并发去重、Snapshot 命中、配置更新淘汰、独立 Actor、幂等关闭。Provider 内部 Cancel 与其他 BaseException 在 Actor 边界转换为 ProviderRuntimeError/失败 ToolResult；连接失败进入有界指数退避，idle TTL 自动有序清理。

### 验证证据

```text
命令：uv run pytest tests/app/core/tools/test_mcp_provider_actor.py tests/app/core/tools/test_mcp_schema_snapshot.py -q
退出状态：0
关键结果：10 passed；并发首次连接 1 次，完整 manager 生命周期属于同一 Actor Task，Provider Cancel 不泄漏，健康 Provider 继续运行，退避/TTL/配置更新/幂等关闭均通过。

命令：uv run ruff check app/core/tools/provider_runtime.py tests/app/core/tools/test_mcp_provider_actor.py tests/app/core/tools/test_mcp_schema_snapshot.py
退出状态：0
关键结果：All checks passed!
执行日期：2026-08-19（Asia/Shanghai）
```

## Task 4：将 MCPTool 与应用生命周期迁移到共享 Provider Pool

状态：completed

### 目标

让真实 Agent Run 复用应用级 Provider Pool 和 Schema Snapshot，删除 MCPTool 的 Run 内 manager 所有权，同时保持 Stage 1B 的 Scope 与 Schema Budget 行为。

### 涉及文件

- `agentic/api/app/core/tools/mcp.py`
- `agentic/api/app/core/agent/agent_task_runner.py`
- `agentic/api/app/services/agent_service.py`
- `agentic/api/app/dependencies/infrastructure.py`
- `agentic/api/app/dependencies/services.py`
- `agentic/api/app/main.py`
- `agentic/api/tests/app/core/tools/test_mcp_lazy_provider.py`
- `agentic/api/tests/app/core/tools/test_mcp_provider_reuse.py`
- `agentic/api/tests/app/core/agent/test_agent_task_runner_lazy_sandbox.py`

### 依赖与接口

- 前置任务：Task 3。
- 输入：user_id、MCPConfig 和应用级 MCPProviderPool。
- 输出：Pool-backed MCPTool；Snapshot hit 零连接；应用关闭有序关闭 Pool。

### 实施步骤

1. MCPTool 按 user/provider/config 构建 Runtime Key，通过 Pool discover/invoke，不再保存或清理 MCPClientManager。
2. 保留本地当前 Scope、Schema Budget、search_tools 和动态 Registry 更新；MCPTool.cleanup 只释放 Run 局部状态，不关闭共享 Actor。
3. AgentService 为每个 Runner 注入 user_id 与同一应用级 Pool；测试/兼容构造允许注入隔离 Pool，但不恢复跨 Task manager 清理。
4. 应用 lifespan 在取消 Run 后调用 Pool.close，再关闭数据库/Redis；普通 Runner destroy 不关闭共享 Pool。
5. 增加多轮 Runner 复用 Snapshot、实际调用复用连接、未选 Provider 零连接和关闭顺序测试。

### 验证方式

- 运行：`uv run pytest tests/app/core/tools/test_mcp_lazy_provider.py tests/app/core/tools/test_mcp_provider_reuse.py tests/app/core/agent/test_agent_task_runner_lazy_sandbox.py tests/app/core/task/test_redis_stream_task_lifecycle.py -q`
- 运行：`uv run ruff check app/core/tools/mcp.py app/core/agent/agent_task_runner.py app/services/agent_service.py app/dependencies app/main.py tests/app/core/tools/test_mcp_provider_reuse.py`
- 预期：退出码均为 0；第二个 Run Schema 命中不连接，真实调用复用 Actor，Runner cleanup 不关闭 Pool，应用关闭统一回收。

### 完成条件

- 多轮对话和 Ask User 自动继续不重复发现有效 MCP Schema。
- MCPTool 不再拥有跨 Task 敏感的 AsyncExitStack/ClientSession。
- 应用关闭可幂等、有序关闭全部 Actor。

### 执行结果

MCPTool 已迁移为 Pool-backed Adapter：只保存 Run 局部 Scope/Schema/Search 状态，通过共享 Pool 发现和调用，不再拥有 MCPClientManager。AgentService/Runner 注入按用户隔离的应用级 Pool；lifespan 在取消活动 Run 后统一关闭 Pool，再关闭数据库/Redis。低层 Manager 在单 Provider 全部连接失败或 Schema 发现失败时向 Actor 抛出，并允许初始化失败后的同 Task cleanup。共享 MCPTool.cleanup 不关闭 Actor，隔离构造仍可自行关闭本地 Pool。

### 验证证据

```text
命令：uv run pytest tests/app/core/tools/test_mcp_lazy_provider.py tests/app/core/tools/test_mcp_provider_reuse.py tests/app/core/tools/test_mcp_provider_actor.py tests/app/core/tools/test_provider_catalog.py tests/app/core/agent/test_agent_task_runner_lazy_sandbox.py tests/app/core/task/test_redis_stream_task_lifecycle.py -q
退出状态：0
关键结果：25 passed；跨 Run Snapshot/Actor 复用、Runner cleanup 不关闭 Pool、跨用户隔离、Stage 1B 惰性连接和应用 Task 清理均通过。

命令：uv run ruff check app/core/tools/mcp.py app/core/tools/provider_runtime.py app/core/agent/agent_task_runner.py app/services/agent_service.py app/dependencies/infrastructure.py app/dependencies/services.py app/main.py tests/app/core/tools/test_mcp_lazy_provider.py tests/app/core/tools/test_mcp_provider_reuse.py
退出状态：0
关键结果：All checks passed!
执行日期：2026-08-19（Asia/Shanghai）
```

## Task 5：贯通 Run 取消来源、Provider 错误 Trace 与前端安全提示

状态：completed

### 目标

区分用户停止、应用关闭和意外取消，并让 Provider 错误以真实、安全的 FailureInfo 呈现，不再统一显示为模型配置或余额错误。

### 涉及文件

- `agentic/api/app/core/task/base.py`
- `agentic/api/app/core/task/redis_stream_task.py`
- `agentic/api/app/core/agent/agent_task_runner.py`
- `agentic/api/app/services/agent_service.py`
- `agentic/api/app/services/trace_service.py`
- `agentic/web/src/lib/api/types.ts`
- `agentic/web/src/lib/session-events.ts`
- `agentic/web/src/components/chat/ChatMessage.vue`
- `agentic/api/tests/app/core/agent/test_agent_task_runner_completion.py`
- `agentic/api/tests/app/core/task/test_redis_stream_task_lifecycle.py`
- `agentic/api/tests/app/services/test_trace_service.py`
- `agentic/web/src/components/chat/ChatMessage.spec.ts`

### 依赖与接口

- 前置任务：Task 1、Task 4。
- 输入：RunCancellationContext、ErrorEvent/ToolResult.failure 和 Provider Runtime 失败。
- 输出：明确取消原因、低基数 error_code Trace 和 failure-aware 前端错误卡。

### 实施步骤

1. 为 Task 增加取消上下文；AgentService.stop_session 写入 USER，应用 destroy 写入 SHUTDOWN 后再调用底层 cancel。
2. Runner 只把存在明确上下文的 CancelledError 当成正常 Run 取消；无上下文的意外 Cancel 转为安全 RUN_INTERNAL_ERROR，不再伪装成用户停止或模型故障。
3. Trace 对 ErrorEvent/失败 ToolResult 记录 failure.code/category/source/provider_id，不记录原始 Provider 异常或敏感配置。
4. 前端类型和 Timeline 保留 FailureInfo；错误卡按 failure.category/code/message 展示 Provider、Model、Cancel、Context Lost 或 Internal 的真实标题和安全提示，旧事件仍使用 error 文本。
5. 覆盖用户停止、shutdown、Provider cancel、不带上下文的意外 cancel、旧错误事件和 Provider 错误展示。

### 验证方式

- 运行：`uv run pytest tests/app/core/agent/test_agent_task_runner_completion.py tests/app/core/task/test_redis_stream_task_lifecycle.py tests/app/services/test_agent_service_recovery.py tests/app/services/test_trace_service.py -q`
- 运行：`pnpm test:run -- src/components/chat/ChatMessage.spec.ts`
- 运行：`pnpm type-check`
- 预期：退出码均为 0；四类取消/错误可区分，Provider Failure 不显示模型配置/余额提示，旧 ErrorEvent 正常展示。

### 完成条件

- 只有明确用户停止/应用关闭会进入对应 Run Cancel 语义。
- Provider 失败留在 Tool/Provider 边界并具有可聚合错误码。
- 前端不再把 Provider/Internal 错误统一渲染为模型不可用。

### 执行结果

新增 RunCancellationContext 与明确的 USER/SHUTDOWN/TIMEOUT/CLIENT_DISCONNECT 原因；RedisStreamTask 在用户停止和应用销毁前写入来源。Runner 只把有上下文的 CancelledError 视为真实取消，无上下文 Cancel 与通用异常投影为安全 RUN_INTERNAL_ERROR；ProviderRuntimeError 单独投影为 Provider Failure。Trace 记录 run.cancellation_requested 以及失败 Tool 的 error_code/category。Web Timeline 和错误卡读取 FailureInfo，按 Model/Provider/Tool/Runtime/Interaction/Config 显示真实类别；旧无 failure 事件继续使用兼容提示且不展示原始错误。

### 验证证据

```text
命令：uv run pytest tests/app/core/agent/test_agent_task_runner_completion.py tests/app/core/task/test_redis_stream_task_lifecycle.py tests/app/services/test_agent_service_recovery.py tests/app/services/test_trace_service.py tests/app/core/test_failure_contract.py -q
退出状态：0
关键结果：39 passed；显式用户/停机取消、无来源 Cancel、Context Lost、Failure Trace 和旧合同均通过。

命令：uv run ruff check app/core/entities/failure.py app/core/task/base.py app/core/task/redis_stream_task.py app/core/agent/agent_task_runner.py app/services/agent_service.py app/services/trace_service.py tests/app/core/agent/test_agent_task_runner_completion.py tests/app/core/task/test_redis_stream_task_lifecycle.py tests/app/services/test_trace_service.py
退出状态：0
关键结果：All checks passed!

命令：pnpm test:run -- src/components/chat/ChatMessage.spec.ts
退出状态：0
关键结果：1 file、9 tests passed；Provider Failure 不再显示模型配置/余额提示。

命令：pnpm type-check
退出状态：0
关键结果：vue-tsc -b 通过。
执行日期：2026-08-19（Asia/Shanghai）
```

## Task 6：完成 Stage 2 回归、设计回写与代码审查

状态：completed

### 目标

完成 Stage 2 自动化、静态、编译、前端和代码审查门禁，并准确保留 Stage 3 与后续范围。

### 涉及文件

- `agentic/api/tests/app/core/agent/`
- `agentic/api/tests/app/core/tools/`
- `agentic/api/tests/app/core/task/`
- `agentic/api/tests/app/services/`
- `agentic/web/src/`
- `agentic/docs/designs/agent-runtime-hitl-provider-reliability.zh-CN.md`
- `agentic/docs/plans/mcp-provider-runtime-plan.md`
- `agentic/docs/reviews/mcp-provider-runtime-review.md`

### 依赖与接口

- 前置任务：Task 1-5。
- 输入：Stage 2 全部实现与局部验证证据。
- 输出：最终验证、审查结论和 `READY_TO_MERGE / BLOCKED / FAILED` 状态。

### 实施步骤

1. 运行 Provider Runtime、Agent/Tool/Task/Trace 定向回归和后端全量测试。
2. 运行 Ruff、Python compileall、前端单测/类型检查/构建和 `git diff --check`。
3. 对照设计验收 Snapshot 零连接命中、连接复用、租户隔离、Provider Cancel 隔离、配置更新、idle TTL 和应用关闭。
4. 执行代码审查并修复 blocking/major；修复后重新运行受影响测试和最终门禁。
5. 回写设计进度，明确 A2A Card TTL、Capability Grant、Durable Finalizer 和完整错误 UX 后续范围。

### 验证方式

- 运行：`uv run pytest tests/app/core/agent tests/app/core/tools tests/app/core/task tests/app/services/test_trace_service.py tests/app/services/test_agent_service_recovery.py -q`
- 运行：`uv run pytest -q`
- 运行：`uv run ruff check app tests`
- 运行：`uv run python -m compileall -q app tests`
- 运行：`pnpm test:run`
- 运行：`pnpm type-check`
- 运行：`pnpm build`
- 运行：`git diff --check`
- 预期：全部退出码 0；无未解决 blocking/major；只对 Stage 2 给出完成结论。

### 完成条件

- 自动化、静态、编译、前端和差异检查通过。
- 代码审查为 `APPROVED`。
- 计划、设计和代码的已实施/待实施边界一致。

### 执行结果

完成 Stage 2 的首轮验证、代码自检、7 项 major 修复与复审。新增配置代际协调、连续协议失败指数退避、共享 Pool 所有权保持、Provider 操作超时、有界 Snapshot、Run 退出后再销毁 Runner，以及应用级清理异常隔离。设计文档已把 Stage 2 标记为已实施，并保留 Stage 3 A2A、Capability Grant、Durable Finalizer 与真实远端 Provider 场景边界。

### 验证证据

```text
定向回归：218 passed，11 个既有 Pydantic deprecation warnings。
后端全量：隔离 PostgreSQL 16 + Redis 7，Alembic upgrade head 成功，531 passed，退出码 0。
前端全量：44 files / 187 tests passed；vue-tsc 与 Vite production build 通过。
静态/编译：Ruff 与 compileall 退出码 0。
代码审查：首轮 CHANGES_REQUIRED（7 major）；修复后 APPROVED。
```

## 计划变更

| 日期 | 变更内容 | 原因 | 影响任务 | 是否影响设计 |
| --- | --- | --- | --- | --- |
| 2026-08-19 | 无 | 初始计划 | 无 | 否 |
| 2026-08-19 | 复审增加配置代际失效、完整成功后清零退避、操作超时、有界 Snapshot 和关停容错 | 首轮实现虽通过测试，但生产生命周期边界仍不完整 | Task 2-6 | 否，属于既定 Stage 2 可靠性目标的补全 |

## 最终验证

### 执行命令

```bash
uv run pytest tests/app/core/agent tests/app/core/tools tests/app/core/task tests/app/services/test_trace_service.py tests/app/services/test_agent_service_recovery.py tests/app/test_main_shutdown.py -q
uv run pytest -q
uv run ruff check app tests
uv run python -m compileall -q app tests
pnpm test:run
pnpm type-check
pnpm build
git diff --check
```

### 执行结果

- 单元/定向测试：通过，218 passed。
- 集成/后端全量：通过，隔离 PostgreSQL/Redis 下 531 passed。
- 静态检查：通过，Ruff 与 compileall 退出码 0。
- 类型检查：通过，`vue-tsc -b` 退出码 0。
- 构建：通过，Vite production build 共转换 3678 modules。
- 数据库迁移：本批无新迁移；隔离数据库执行现有 Alembic 链到 head 成功。
- 手工验证：未连接真实第三方 MCP；以 Fake Manager 覆盖并发、取消、超时、配置切换、退避和生命周期。
- 代码审查：`APPROVED`；同一 Agent 自检，7 项 major 已修复。

### 验收标准检查

- [x] 有效 Schema Snapshot 命中时不连接 MCP；多轮 Run 可复用 Snapshot。
- [x] 同一 Provider 的并发首次请求只建立一次连接，调用与清理由同一 Actor Task 执行。
- [x] Pool Key 包含用户命名空间和配置指纹，不跨用户/配置复用连接或快照。
- [x] 一个 MCP Provider 的连接失败或内部 Cancel 不向父 Agent Task 传播裸 CancelledError，其他 Provider 可继续。
- [x] 连接退避、idle timeout、配置更新和应用关闭均能无泄漏清理 Actor。
- [x] ErrorEvent.error 与 ToolResult.message 保持旧客户端兼容，FailureInfo 不泄露敏感信息。
- [x] 用户停止、应用关闭、Provider cancel 和无上下文意外 cancel 产生可区分结果。
- [x] Provider 失败不会在 Web 端显示为模型余额、模型配置或模型网络错误。
- [x] Stage 3 A2A Card TTL、完整 Capability Grant 和 Durable Finalizer 未被错误宣称完成。
- [x] Stage 2 后端/前端测试、静态检查、编译/构建和代码审查通过。

### 未通过项目

无。真实第三方 MCP smoke 作为部署前验证建议保留，不是本地 Stage 2 合并阻塞项。

### 最终状态

`READY_TO_MERGE`
