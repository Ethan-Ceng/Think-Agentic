# MCP Provider Runtime Stage 2 代码审查

## 审查范围

- 目标分支：`develop`
- 变更分支：`refactor/unified-tool-plane`
- 变更范围：Stage 2 MCP Provider Actor、Schema Snapshot、取消语义与类型化失败
- 设计文档：`docs/designs/agent-runtime-hitl-provider-reliability.zh-CN.md`
- 计划文档：`docs/plans/mcp-provider-runtime-plan.md`
- 审查方式：同一 Agent 自检
- 审查日期：2026-08-19

## 首轮问题列表

### [major] Provider 配置切换无法使仅存于缓存中的旧配置快照失效

位置：`api/app/core/tools/provider_runtime.py`

问题：Pool 只在创建 Actor 时关闭同 Provider 的旧 Actor；`discover()` 在进入 Actor 注册表前直接命中快照。配置 A 切换到 B 后再切回 A 时，仍可能返回 A 的旧快照，也可能让 B Actor 保持存活。

影响：凭据、Endpoint 或传输参数变化后，模型可继续看到旧工具定义，配置失效边界不可靠。

建议：为 `(user_id, provider_id)` 维护当前 Runtime Key，在任何缓存读取或调用前原子协调配置版本；版本变化时使该 Provider 全部快照失效并关闭旧 Actor。

状态：已修复；Pool 在任何缓存读取/调用前协调当前配置代际，切换时使全部旧快照失效并关闭旧 Actor，切回旧配置也会重新发现。

### [major] 连续 Schema/协议失败无法形成指数退避

位置：`api/app/core/tools/provider_runtime.py`

问题：连接初始化一成功就清零失败计数；若初始化成功但 `list_tools` 或 `invoke` 持续失败，每次重连都会把计数重置，实际永远只使用基础退避时长。

影响：异常 Provider 会产生稳定的重连风暴，违背 Stage 2 的退避目标。

建议：只在一次完整 discover/invoke 成功后清零失败状态；底层 Manager 的传输异常必须抛给 Actor 统一降级，不能转成无类型 `ToolResult`。

状态：已修复；失败计数只在完整 discover/invoke 成功后清零，底层 Manager 传输异常上抛 Actor，并新增连续 Schema 失败的 5/10/20 秒退避回归。

### [major] 共享 Provider Pool 在 MCPTool 重新配置后退化为 Run 私有 Pool

位置：`api/app/core/tools/mcp.py`

问题：`MCPTool.initialize(new_config)` 通过重新调用构造函数更新状态，但没有把原共享 `provider_pool` 传回构造函数。

影响：同一应用内连接与快照复用失效，且 Run cleanup 会意外关闭新建 Pool。

建议：重建 Tool 状态时保留共享 Pool；只有原本拥有 Pool 时才创建新的本地 Pool。

状态：已修复；`MCPTool.initialize(new_config)` 保留应用级共享 Pool，Runner cleanup 不会关闭它。

### [major] 应用关停在执行任务退出前销毁 Runner 资源

位置：`api/app/core/task/redis_stream_task.py`

问题：`destroy()` 发出 `Task.cancel()` 后立即调用 `runner.destroy()`，没有等待 `_execution_task` 完成其取消处理和 `finally` 清理。

影响：Sandbox/Tool cleanup 与正在退出的 Run 并发，可能复现跨 Task 资源释放错误或造成关停竞态。

建议：先取消全部任务，再汇总等待执行任务结束，最后逐一销毁 Runner。

状态：已修复；关停先取消所有 Run、等待 execution task 的 finally 完成，再销毁 Runner。

### [major] Provider 操作没有超时边界，Actor 与服务关停可能无限等待

位置：`api/app/core/tools/provider_runtime.py`、`api/app/core/config.py`

问题：initialize、schema discovery、invoke 和 cleanup 都可以无限挂起；Pool close 只能排队等待 Actor，无法保证有界关停。

影响：单个异常 Provider 能长期占用 Actor，并阻塞进程生命周期退出。

建议：增加可配置的 Provider 操作超时，并在 Actor 所有外部 await 边界执行；超时统一映射为 `PROVIDER_TIMEOUT`。

状态：已修复；initialize/discover/invoke/cleanup 均受可配置正数超时约束，超时映射为 `PROVIDER_TIMEOUT`。

### [major] 一个 Runner 的清理异常会跳过其余应用资源关闭

位置：`api/app/core/task/redis_stream_task.py`、`api/app/core/agent/agent_task_runner.py`、`api/app/main.py`

问题：Runner 按顺序销毁且异常直接上抛；应用 lifespan 也按顺序执行关闭步骤，没有隔离单步失败。Sandbox 销毁失败还会跳过该 Runner 的 Tool cleanup。

影响：一个局部清理失败即可阻止其他 Runner、共享 Provider Pool、数据库和 Redis 释放。

建议：Run 内用 `finally` 保证 Tool cleanup；Runner 销毁并行汇总且记录局部异常；应用级每个关闭步骤独立捕获并继续。

状态：已修复；Run 内 Tool cleanup 使用 finally，Runner 销毁汇总局部异常，应用关闭步骤逐项隔离失败并继续。

### [major] TTL Snapshot 与当前配置索引没有容量上限

位置：`api/app/core/tools/provider_runtime.py`、`api/app/core/config.py`

问题：Snapshot 只在相同 Key 再次读取时删除过期值；只访问一次的大量用户/Provider 会永久保留过期字典项，`_current_keys` 也不会随 idle Actor 释放。

影响：应用级共享 Pool 在长期多租户流量下存在无界内存增长。

建议：增加正数最大条目配置；写入时清理过期项并按最早到期顺序淘汰，协调新请求时同步清除已无 Actor/快照的配置索引。

状态：已修复；Snapshot 增加可配置容量上限，写入时清除过期项并淘汰最早到期项，配置索引同步清除无 Actor/快照的代际。

## 首轮门禁

| 门禁 | 结果 | 证据 |
| --- | --- | --- |
| 无 blocking | 通过 | 未发现 blocking |
| 无未处理 major | 失败 | 7 项 major 待修复 |
| 修复前定向回归 | 通过 | 210 passed |
| 修复前后端全量 | 通过 | 523 passed |
| 修复前 Web 全量 | 通过 | 187 passed |

## 首轮审查结论

- 结论：`CHANGES_REQUIRED`
- 理由：存在 7 项配置一致性、退避、所有权、容量和生命周期 major，修复前不可进入完成状态。
- 审查限制：本轮为同一 Agent 自检；修复后需要最新定向及全量验证，并再次更新本报告。

## 修复后复审

- 需求符合度：Stage 2 的租户/配置隔离 Actor、跨 Run 有界 Snapshot、惰性连接、取消隔离、类型化错误、安全前端投影和有序关停均已落地。
- 正确性：7 项 major 均已修复，并覆盖配置 A→B→A、连续 Schema 失败指数退避、共享 Pool 重配置、Provider 超时、关停顺序/容错和缓存容量。
- 安全性：Snapshot 不保存 URL/Header/Env/Credential/Tool Result；原始 Provider 异常不进入 SSE、ToolResult 或低权限 Trace；不同用户不共享连接或快照。
- 可维护性：Provider 生命周期集中在单 Actor Task；应用级 Pool 通过依赖注入复用；FailureInfo 维持旧字段兼容；Stage 3 与 Durable Runtime 边界未混入本批。
- 测试质量：Fake Manager 对并发、同 Task 所有权、Cancel、超时、配置更新、租户隔离、退避、idle TTL 和 shutdown 做确定性覆盖；全量数据库测试使用一次性隔离容器。
- 复审结果：未发现新的 blocking 或未处理 major。

## 无法验证项与剩余边界

- 未连接真实第三方 MCP Server，未覆盖真实网络代理、远端认证和第三方协议实现差异；这不影响本地合同通过，但部署前仍应做至少一个 stdio 与一个 streamable-http smoke。
- 调用者取消已经开始的外部 Tool Call 时，Actor 为保护共享传输所有权会让该调用在操作超时内结束；未来有副作用外部工具仍需 Capability Grant、幂等键和 Durable Effect 对账。
- A2A Card TTL/共享 HTTP Client、完整 Capability Grant、Durable Finalizer、跨进程 Pool 和完整 Provider 管理 UX 明确保留后续阶段。
- 本次为同一 Agent 自检；独立 Reviewer 可进一步降低审查偏差。

## 最终合并门禁

| 门禁 | 结果 | 证据 |
| --- | --- | --- |
| 无 blocking | 通过 | 复审未发现 blocking |
| 无未处理 major | 通过 | 7 项 major 全部修复并回归 |
| Stage 2 定向回归 | 通过 | 218 passed，11 个既有 Pydantic deprecation warnings |
| 后端全量 | 通过 | 隔离 PostgreSQL 16/Redis 7、Alembic head，531 passed |
| Web 全量 | 通过 | 44 files / 187 tests passed |
| 静态/编译/类型/构建 | 通过 | Ruff、compileall、vue-tsc、Vite build 均退出 0 |
| 差异检查 | 通过 | `git diff --check` 退出 0，仅 Git LF/CRLF 工作区提示 |
| 产品数据库迁移 | 不适用 | 本批未新增或修改迁移 |

## 最终审查结论

- 结论：`APPROVED`
- 合并判断：`READY_TO_MERGE`
- 理由：Stage 2 范围内无未处理 blocking/major，最新定向、后端全量、Web 全量及所有静态门禁通过。
- 下一步：等待用户决定是否提交/推送；后续进入 Stage 3 A2A Card TTL/共享 Client，不把其计入本次完成声明。
