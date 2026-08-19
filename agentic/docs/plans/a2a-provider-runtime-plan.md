# Stage 3 A2A Provider Runtime 实施计划

## 关联设计

- 独立设计：`agentic/docs/designs/a2a-provider-runtime.zh-CN.md`
- 上位设计：`agentic/docs/designs/agent-runtime-hitl-provider-reliability.zh-CN.md`
- 实施范围：阶段 3 的 A2A Card 惰性刷新、共享 HTTP Runtime、委派目录与应用集成
- 开发分支：`refactor/unified-tool-plane`
- 基线提交：`e1c5543`

## 当前进度

- 整体状态：`COMPLETE`
- 当前阶段：completed
- 当前任务：Task 5：完成 Stage 3 回归、回写、审查与单提交（completed）
- 已完成：5 / 5
- 阻塞问题：无
- 最近更新时间：2026-08-19（Asia/Shanghai）

## 全局约束

- 保留固定的 A2A Tool Schema 和离线聚合 Provider `a2a.remote`；动态 Card 不进入 Lead 静态 Catalog。
- A2A Client/Card 只能在真实执行 `get_remote_agent_cards` 或 `call_remote_agent` 后激活。
- Runtime 按 user/target/config/policy 隔离，Cache 有界、深拷贝、支持条件刷新和配置代际失效。
- A2A 调用者取消继续作为父 Run 控制流；Provider 失败不得转换为 Run cancel。
- 用户可见数据不得包含 URL、Header、Credential、query、原始异常或未筛选 Card 字段。
- 本批不实现 A2A streaming、认证、JWS 验签、跨进程缓存、本地 Sub Agent 编排、Capability Grant 或 Durable Finalizer。
- 每个 Task 完成后立即更新本计划的状态和验证证据。
- 用户已明确授权提交：完整 Stage 3 在全部验证和代码审查通过后只创建一个 Git commit；不分 Task 提交、不推送、不创建 PR、不合并。

## 状态变更记录

| 日期时间 | 整体状态 | 当前任务 | 变更原因 |
| --- | --- | --- | --- |
| 2026-08-19（Asia/Shanghai） | `IN_PROGRESS` | Task 1 | 独立设计完成，分支与基线干净，开始 Stage 3 实施 |
| 2026-08-19（Asia/Shanghai） | `IN_PROGRESS` | Task 2 | 7 项 Snapshot/配置合同测试与 Ruff 通过，开始共享 HTTP Runtime |
| 2026-08-19（Asia/Shanghai） | `IN_PROGRESS` | Task 3 | 14 项 A2A HTTP Runtime 测试与 Ruff 通过，开始 Tool Adapter 与安全目录改造 |
| 2026-08-19（Asia/Shanghai） | `IN_PROGRESS` | Task 4 | A2ATool/Provider Catalog 10 项测试与 Ruff 通过，开始应用级注入与关闭 |
| 2026-08-19（Asia/Shanghai） | `VERIFYING` | Task 5 | 应用注入/生命周期 10 项测试与 Ruff 通过，开始最终回归和代码审查 |
| 2026-08-19（Asia/Shanghai） | `REVIEWING` | Task 5 | Stage 3 定向、API 全量、Ruff 和编译通过；进入设计/安全/并发/兼容性审查 |
| 2026-08-19（Asia/Shanghai） | `COMPLETE` | Task 5 | 审查问题全部修复，最终 563 项 API 测试及静态/编译/差异门禁通过，Stage 3 准备单提交 |

## Task 1：建立 A2A Runtime 合同与 Card Snapshot

状态：completed

### 目标

定义类型化失败、隔离 Runtime Key、接口选择结果、Card Snapshot、目标描述与有界缓存，为后续网络行为建立可测试合同。

### 涉及文件

- `agentic/api/app/core/tools/a2a_runtime.py`
- `agentic/api/app/core/config.py`
- `agentic/api/app/core/entities/app_config.py`
- `agentic/api/tests/app/core/tools/test_a2a_card_snapshot.py`

### 实施步骤

1. 先写隔离、TTL、深拷贝、容量、配置指纹和类型化失败测试。
2. 定义 Runtime Key、Snapshot、Selected Interface、Delegation Descriptor 和 A2A failure code。
3. 实现有界 LRU Snapshot Cache 及配置代际失效。
4. 增加 A2A timeout/TTL/容量/响应体设置和 A2A 配置基础校验。

### 验证方式

- `uv run pytest tests/app/core/tools/test_a2a_card_snapshot.py -q`
- `uv run ruff check app/core/tools/a2a_runtime.py app/core/config.py app/core/entities/app_config.py tests/app/core/tools/test_a2a_card_snapshot.py`

### 完成条件

- 隔离键、Cache 和失败合同测试通过。
- 配置默认值有效，非法值被拒绝。

### 执行结果

新增 A2A Runtime Key、配置指纹、Selected Interface、Card Snapshot、有界 LRU Cache、委派描述和稳定 FailureInfo。A2A 配置开始校验 HTTP(S)、禁止 URL userinfo/query/fragment 及重复 Target ID；Settings 增加 Card TTL/stale/容量、发现/调用超时和响应大小限制。

### 验证证据

```text
命令：uv run pytest tests/app/core/tools/test_a2a_card_snapshot.py -q
退出状态：0
关键结果：7 passed；租户/配置隔离、深拷贝、fresh/stale、LRU、类型化失败、配置校验全部通过。

命令：uv run ruff check app/core/tools/a2a_runtime.py app/core/config.py app/core/entities/app_config.py tests/app/core/tools/test_a2a_card_snapshot.py
退出状态：0
关键结果：All checks passed!
执行日期：2026-08-19（Asia/Shanghai）
```

## Task 2：实现目标级发现、条件刷新与协议调用

状态：completed

### 目标

实现共享 Client、每目标 single-flight、条件刷新、stale fallback，以及现代/legacy A2A 同步调用。

### 涉及文件

- `agentic/api/app/core/tools/a2a_runtime.py`
- `agentic/api/tests/app/core/tools/test_a2a_provider_runtime.py`

### 实施步骤

1. 先写 lazy Client、目标隔离、并发刷新、ETag/304、过期和 stale 测试。
2. 实现请求级 timeout、响应大小限制、Card JSON 校验与同源接口校验。
3. 实现现代 `JSONRPC/SendMessage`、`HTTP+JSON /message:send` 和 legacy `message/send`。
4. 验证远端错误只生成安全 FailureInfo，并让调用者 CancelledError 继续传播。

### 验证方式

- `uv run pytest tests/app/core/tools/test_a2a_provider_runtime.py -q`
- `uv run ruff check app/core/tools/a2a_runtime.py tests/app/core/tools/test_a2a_provider_runtime.py`

### 完成条件

- 同目标刷新去重且不同目标互不阻塞。
- 三种协议路径和全部错误边界有测试。

### 执行结果

实现应用可共享的 A2A HTTP Runtime、惰性 Client、每 Target single-flight、配置代际协调、ETag/Last-Modified 条件请求、Cache-Control TTL、stale-if-error、响应体上限和同源接口约束。现代 Card 按顺序选择 JSONRPC/HTTP+JSON，发送 A2A-Version 与 tenant；旧顶层 URL 保持原 `message/send` payload。所有失败只投影安全 FailureInfo，调用者 CancelledError 不被捕获。

### 验证证据

```text
命令：uv run pytest tests/app/core/tools/test_a2a_provider_runtime.py -q
退出状态：0
关键结果：14 passed；惰性激活、并发去重、304、stale、隔离、三类协议、安全失败和取消传播全部通过。

命令：uv run ruff check app/core/tools/a2a_runtime.py tests/app/core/tools/test_a2a_provider_runtime.py
退出状态：0
关键结果：All checks passed!
执行日期：2026-08-19（Asia/Shanghai）
```

## Task 3：改造 A2ATool 与安全委派目录

状态：completed

### 目标

让固定 Tool Schema 使用共享 Runtime，只返回安全目标摘要，并保持未调用时零网络 I/O。

### 涉及文件

- `agentic/api/app/core/tools/a2a.py`
- `agentic/api/tests/app/core/tools/test_a2a_lazy_provider.py`

### 实施步骤

1. 先更新 lazy、单目标调用、部分目录失败、共享所有权和安全投影测试。
2. A2ATool 接收 user_id 与可选共享 Runtime；本地 Runtime 仅用于兼容和独立测试。
3. `get_remote_agent_cards` 并行按 Target 发现并返回 targets/unavailable IDs。
4. `call_remote_agent` 只解析指定 enabled Target；不存在/禁用返回类型化失败。

### 验证方式

- `uv run pytest tests/app/core/tools/test_a2a_lazy_provider.py tests/app/core/tools/test_provider_catalog.py -q`
- `uv run ruff check app/core/tools/a2a.py tests/app/core/tools/test_a2a_lazy_provider.py`

### 完成条件

- Schema 构建、Catalog、Scope 和 Tool 构造不触发网络。
- 目录不泄露 Card URL 或任意外部字段。

### 执行结果

移除 Run 私有 A2AClientManager，A2ATool 改为固定 Schema 的共享 Runtime Adapter。目录并行发现 enabled Target，返回有界 DelegationTargetDescriptor 与不可用 ID；部分失败不阻断健康目标，全部失败投影类型化 FailureInfo。调用仅解析指定目标；共享 Runtime 由应用拥有，本地 Runtime 保持独立关闭能力。工具描述补齐中英双语且所有外部 Card 元数据明确标记为不可信。

### 验证证据

```text
命令：uv run pytest tests/app/core/tools/test_a2a_lazy_provider.py tests/app/core/tools/test_provider_catalog.py -q
退出状态：0
关键结果：10 passed；静态 Schema、零网络构造、目标级调用、部分失败、安全投影与所有权全部通过。

命令：uv run ruff check app/core/tools/a2a.py tests/app/core/tools/test_a2a_lazy_provider.py tests/app/core/tools/test_provider_catalog.py
退出状态：0
关键结果：All checks passed!
执行日期：2026-08-19（Asia/Shanghai）
```

## Task 4：接入 Agent Runtime 与应用生命周期

状态：completed

### 目标

把 A2A Runtime 提升到应用作用域，按用户注入每个 Runner，并在所有 Agent Task 结束后统一关闭。

### 涉及文件

- `agentic/api/app/dependencies/infrastructure.py`
- `agentic/api/app/dependencies/services.py`
- `agentic/api/app/services/agent_service.py`
- `agentic/api/app/core/agent/agent_task_runner.py`
- `agentic/api/app/main.py`
- `agentic/api/tests/app/services/test_agent_service_lazy_sandbox.py`
- `agentic/api/tests/app/test_main_shutdown.py`

### 实施步骤

1. 增加缓存依赖 `get_a2a_provider_runtime`，构造时仍不创建 Client。
2. AgentService → AgentTaskRunner → A2ATool 传递共享 Runtime 与 user_id。
3. Runner destroy 只清理 Tool 局部状态，不关闭共享 Runtime。
4. lifespan 在 Agent Task 后、数据库前关闭 A2A 和 MCP 运行时，并保持某一步失败后继续清理。

### 验证方式

- `uv run pytest tests/app/services/test_agent_service_lazy_sandbox.py tests/app/test_main_shutdown.py tests/app/core/tools/test_a2a_lazy_provider.py -q`
- `uv run ruff check app/dependencies/infrastructure.py app/dependencies/services.py app/services/agent_service.py app/core/agent/agent_task_runner.py app/main.py`

### 完成条件

- 跨 Runner 复用且跨用户 Card 不共享。
- 应用关闭顺序和 shared/local 所有权测试通过。

### 执行结果

新增应用级 `get_a2a_provider_runtime`，通过 AgentService 和 AgentTaskRunner 将共享 Runtime 与 user_id 注入 A2ATool。Runner cleanup 不关闭共享 Runtime；FastAPI lifespan 在 Agent Task 完成后统一关闭 A2A、MCP，再关闭数据库/Redis。构造和注入过程保持零 A2A 网络 I/O。

### 验证证据

```text
命令：uv run pytest tests/app/services/test_agent_service_lazy_sandbox.py tests/app/test_main_shutdown.py tests/app/core/tools/test_a2a_lazy_provider.py -q
退出状态：0
关键结果：10 passed；共享注入、零激活、Tool 所有权和清理容错通过。

命令：uv run ruff check app/dependencies/infrastructure.py app/dependencies/services.py app/services/agent_service.py app/core/agent/agent_task_runner.py app/main.py tests/app/services/test_agent_service_lazy_sandbox.py
退出状态：0
关键结果：All checks passed!
执行日期：2026-08-19（Asia/Shanghai）
```

## Task 5：完成 Stage 3 回归、回写、审查与单提交

状态：completed

### 目标

用最新证据证明 Stage 3 可合并，修复代码审查问题，准确回写上位设计，并生成唯一提交。

### 涉及文件

- `agentic/docs/designs/a2a-provider-runtime.zh-CN.md`
- `agentic/docs/designs/agent-runtime-hitl-provider-reliability.zh-CN.md`
- `agentic/docs/plans/a2a-provider-runtime-plan.md`
- Stage 3 的全部代码和测试文件

### 实施步骤

1. 运行 Stage 3 定向测试、全部 API 测试、Ruff、编译和 Git 差异检查。
2. 按设计、正确性、安全、并发、兼容性和测试质量执行代码审查；修复 blocking/major 后重跑验证。
3. 将独立设计标记为 IMPLEMENTED，上位设计标记 Stage 3 已落地，记录后续边界。
4. 检查 staged diff 只包含 Stage 3，创建一次且仅一次 Git commit；不 push。

### 验证方式

- `uv run pytest tests/app/core/tools/test_a2a_card_snapshot.py tests/app/core/tools/test_a2a_provider_runtime.py tests/app/core/tools/test_a2a_lazy_provider.py tests/app/core/tools/test_provider_catalog.py tests/app/services/test_agent_service_lazy_sandbox.py tests/app/test_main_shutdown.py -q`
- `uv run pytest -q`
- `uv run ruff check app tests`
- `uv run python -m compileall -q app tests`
- `git diff --check`
- `git status --short --branch`

### 完成条件

- 所有验证退出码为 0，代码审查结论为批准。
- 文档未错误宣称后续 A2A streaming/认证/JWS/本地 Sub Agent 已完成。
- Git 历史相对 `e1c5543` 只新增一个 Stage 3 提交，工作区干净。

### 执行结果

完成 Stage 3 全量回归与两轮代码自检。首轮审查发现并修复：运行时代际/刷新锁注册表无界、公共/领域 A2A 配置校验漂移、异常端口与非 HTTP 异常越过 Provider 边界、无 result 的 JSON-RPC 被误判成功、HTTP no-store/no-cache 与 304 缓存头继承不完整、应用关闭顺序缺少直接测试，以及双语 Tool 描述引起的 Schema 字节基线变化。复审未发现 blocking/major 遗留，结论为 `APPROVED`。

全量测试使用临时隔离 PostgreSQL/Redis，并在验证后删除容器；没有连接或修改正在运行的服务数据。独立设计标记 IMPLEMENTED，上位设计只将 Stage 3 标记已落地，明确保留 streaming、远程 Task 续订、认证/JWS、本地 Sub Agent、跨进程 Cache、Capability Grant 和 Durable Finalizer 的后续边界。

### 验证证据

```text
命令：uv run pytest -o addopts="" -q --tb=short --basetemp=.pytest_tmp
退出状态：0
关键结果：563 passed，11 个既有 Pydantic 弃用 warning。

命令：uv run ruff check app tests
退出状态：0
关键结果：All checks passed!

命令：uv run python -m compileall -q app tests
退出状态：0
关键结果：无输出，退出码 0。

命令：git diff --check
退出状态：0
关键结果：无空白错误；仅 Git 行尾转换提示。
执行日期：2026-08-19（Asia/Shanghai）
```

## 恢复点

当前从 Task 1 开始。若中断，先读取本计划的当前进度、状态变更与最近一个 Task 验证证据，再检查 `git status --short --branch`；不得提前创建中间提交。
