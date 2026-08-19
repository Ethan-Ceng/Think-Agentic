# Stage 3：A2A Provider Runtime、Card Snapshot 与委派目录

## 文档状态

- 状态：`IMPLEMENTED`
- 负责人：Codex
- 创建日期：2026-08-19
- 最近更新：2026-08-19
- 上位设计：`agent-runtime-hitl-provider-reliability.zh-CN.md`

## 背景

当前 `A2ATool` 的函数 Schema 已经是本地静态的，但第一次真实调用任一 A2A 函数时，会创建一个 Run 私有 HTTP Client，并顺序获取全部已配置目标的 Agent Card。每个 Run 结束后 Client 与 Card 缓存又被销毁。因此，调用一个远程 Agent 会被无关目标的延迟和故障拖累，多轮对话也无法复用发现结果。

现有实现还直接把原始 Card（包括 URL、安全声明和任意外部字段）返回模型，只支持旧版顶层 `url + message/send` JSON-RPC 形态，并把原始 URL 和异常文本拼入 ToolResult。它既不是稳定的委派目录，也没有可靠的错误边界。

A2A 1.0 规范要求客户端从 `supportedInterfaces` 中按顺序选择首个受支持接口，并建议 Agent Card 使用标准 HTTP 缓存及条件请求。本阶段需要补齐这层运行时能力，同时保留当前旧版 Card 的兼容路径。

## 目标

- 未真实调用 A2A 函数时不创建 HTTP Client、不发现 Card、不连接远程 Agent。
- `call_remote_agent(id, query)` 只发现并调用目标 `id`，不访问其他 A2A Target。
- 同一进程内跨 Run 复用一个连接池和有界 Card Snapshot；缓存按用户、目标和配置代际隔离。
- 同一目标的并发 Card 刷新合并为一次请求；不同目标可并行刷新和调用。
- 支持 Agent Card 的 `ETag`、`Last-Modified`、`Cache-Control: max-age` 与 `304 Not Modified`。
- 支持 A2A 1.0 的 `JSONRPC`、`HTTP+JSON` 接口选择与请求格式，并兼容当前旧版顶层 `url` Card。
- 模型只看到有界、安全、明确标记为外部不可信元数据的委派摘要，不看到 URL、安全声明或原始 Card。
- A2A 发现或调用失败返回类型化 Tool failure，不升级为整个 Run 的取消或“模型服务不可用”。
- 建立本地 Sub Agent 与远程 A2A Target 将来可共用的 `DelegationTargetDescriptor`，但本阶段不实现本地多 Agent 调度器。

## 功能范围

- 应用级 `A2AProviderRuntime` 与共享 `httpx.AsyncClient`。
- 目标级 Agent Card Snapshot、TTL、条件刷新、配置代际失效、有界容量和 stale-if-error。
- A2A 目标描述、接口选择、同步 SendMessage 调用与安全失败投影。
- `A2ATool` 改造及 AgentService/Runner/应用生命周期注入。
- 配置校验、定向测试、全量回归和设计状态回写。

## 非功能范围

- 不实现 A2A streaming、push notification、远程 Task 轮询或跨进程 Card Cache。
- 不实现 Agent Card JWS 验签、认证扩展、Credential Broker 或完整 Capability Grant。
- 不实现本地 Sub Agent 编排、负载均衡、竞速委派或多 Agent DAG。
- 不把动态 A2A Target 变成 Lead 静态 Catalog 中逐目标 Provider；Lead 仍只看到离线的聚合 Provider `a2a.remote`。
- 不支持 gRPC A2A Binding；发现时跳过不支持的接口。
- 不重做 Stage 2 MCP Provider Runtime。

## 核心规则

1. `A2ATool` 的两个函数 Schema 永远来自本地代码；Card 只在函数真实执行后获取。
2. Runtime Key 为 `user_id + target_id + config_fingerprint + negotiation_policy_version`。不同用户、目标、配置代际不得共享 Snapshot。
3. 配置变化立即切换代际；旧代际即使 TTL 未到也不能被新调用读取。
4. 有效 Snapshot 直接返回；过期 Snapshot 使用 ETag/Last-Modified 条件刷新；服务器无缓存头时使用平台默认 TTL。
5. 刷新失败时，只允许在配置指纹未变化且 stale grace 未过期时使用旧 Snapshot；输出明确标记 `snapshot_state=stale`。
6. Card 与调用响应均执行独立超时和最大响应体限制。调用者自身的 `CancelledError` 必须继续向上传播，不能被伪装成 Provider 失败。
7. Card 声明的调用 URL 必须为 HTTP(S)、无 userinfo，且与用户配置的 `base_url` 同源；本阶段不允许 Card 把已信任目标跳转到另一网络源。
8. 对现代 Card，按 `supportedInterfaces` 顺序选择第一个 `JSONRPC` 或 `HTTP+JSON`；对旧 Card，顶层 `url` 进入 legacy JSON-RPC 兼容路径。
9. 模型可见目标摘要只包含 ID、名称、描述、技能摘要、协议、安全信任标签与 Snapshot 状态；字段数量和长度均有上限。
10. A2A 单目标失败只影响该 Tool Call。列目录时，一个目标失败不阻断其他目标；全部失败时返回一个类型化失败及不可用目标 ID 列表。

## 现有实现分析

### 相关代码

- `api/app/core/tools/a2a.py`：Run 私有 Client、全量串行 Card 获取、旧版调用和原始错误输出。
- `api/app/core/agent/agent_task_runner.py`：每个 Runner 构造一个 A2ATool，没有应用级 Runtime 注入。
- `api/app/dependencies/infrastructure.py`：已有 MCP 应用级 Pool 的依赖与生命周期模式，可复用注入方式。
- `api/app/core/entities/failure.py`：已有 Provider 类型化失败合同。
- `api/app/core/tools/provider_catalog.py`：已有离线聚合 A2A Provider，不能因 Card 动态发现改成在线 Catalog。

### 可复用能力

- Stage 1B 的固定 A2A Tool Schema、统一 ToolFactory、RuntimeToolScope 和 Trace。
- Stage 2 的 `FailureInfo`、Provider failure 语义、配置指纹和应用级资源关闭模式。
- `httpx.AsyncClient` 的连接池、请求级 timeout 与 MockTransport 测试能力。

### 当前约束

- A2A 配置目前只有 `id/base_url/enabled`，没有认证信息和显式协议偏好。
- 现有远程服务可能仍使用旧版 `message/send` 与 `role=user/part.kind=text` 格式，必须兼容。
- 静态 Lead Catalog 必须保持零网络 I/O；动态 Card 不能在规划前注入 Prompt。

## 可选方案

### 方案 A：保留 Run 私有 Manager，仅增加 TTL

- 实现方式：在单个 `A2AClientManager` 内增加目标缓存和并发请求。
- 优点：改动最小。
- 缺点：跨 Run 仍无法复用 Client/Card，多轮对话仍重复发现，应用无法统一关闭连接。
- 风险：看似有缓存，实际生命周期仍与短 Run 绑定。

### 方案 B：共享 HTTP Runtime + 目标级 Snapshot（推荐）

- 实现方式：应用级共享 Client；按 Runtime Key 缓存 Card；同 Key 使用 asyncio Lock 合并刷新；Tool 只持配置和用户命名空间。
- 优点：跨 Run 复用、目标故障隔离、并发模型简单、符合 HTTP 连接与缓存语义。
- 缺点：需要明确缓存代际、关闭和 stale 规则。
- 风险：若没有容量和配置指纹限制，可能跨租户污染或无限增长；本设计通过有界 Cache 与代际键消除。

### 方案 C：每个 A2A Target 建 Actor

- 实现方式：复制 MCP Provider Actor，每个目标由单 Task 串行发现、调用和关闭。
- 优点：生命周期所有权高度统一。
- 缺点：HTTP Client 本身支持并发，串行 Actor 会降低同目标吞吐，并引入队列、取消和 idle Task 管理。
- 风险：把 MCP 的 AnyIO Task 所有权约束错误套用到普通 HTTP，复杂度大于收益。

## 方案对比

| 维度 | 方案 A | 方案 B | 方案 C |
| --- | --- | --- | --- |
| 跨 Run 复用 | 否 | 是 | 是 |
| 同目标刷新去重 | Run 内 | 是 | 是 |
| 同目标并发调用 | 是 | 是 | 被串行化 |
| 生命周期复杂度 | 低 | 中 | 高 |
| 与 HTTP 语义匹配 | 一般 | 最佳 | 一般 |
| 主要风险 | 缓存形同虚设 | 缓存隔离错误 | Actor/取消复杂化 |

## 推荐方案

采用方案 B。A2A 的共享资源是可并发的 HTTP 连接池和可缓存的 Card，不存在 MCP Session/AnyIO cancel scope 必须由同一 Task 进入退出的约束。因此只对同一 Card 的刷新做 single-flight，远程调用保持并发，是更小且更可靠的边界。

## 数据结构

### A2ARuntimeKey

| 字段 | 类型 | 说明 |
| --- | --- | --- |
| `user_id` | `str` | 租户隔离命名空间 |
| `target_id` | `str` | 用户配置中的稳定目标 ID |
| `config_fingerprint` | `str` | 完整目标配置的 SHA-256 摘要，不含原始配置 |
| `policy_version` | `str` | 客户端接口选择/兼容策略版本 |

### A2ACardSnapshot

| 字段 | 类型 | 说明 |
| --- | --- | --- |
| `key` | `A2ARuntimeKey` | 隔离与配置代际键 |
| `card` | `dict` | 进程内深拷贝 Card；不进入 Prompt |
| `interface` | `SelectedA2AInterface` | 已选择的绑定、版本、URL、tenant 与 legacy 标记 |
| `etag/last_modified` | 可选字符串 | 条件请求元数据 |
| `discovered_at/expires_at/stale_until` | monotonic 时间 | 新鲜和降级窗口 |

### DelegationTargetDescriptor

| 字段 | 类型 | 说明 |
| --- | --- | --- |
| `target_id/provider_id/target_type` | `str` | 稳定委派身份；远程类型为 `remote_a2a` |
| `name/description` | `str` | 有界外部摘要 |
| `skills` | 列表 | 有界技能名、描述和 tags |
| `protocol_binding/protocol_version` | `str` | 已选择接口，不含 URL |
| `snapshot_state` | `fresh/stale` | Card 新鲜度 |
| `metadata_trust` | `untrusted_external` | 明确提示该元数据不是系统指令 |

无数据库结构变化。

## 接口设计

### A2AProviderRuntime.discover

- 输入：`user_id`、目标配置、可选 `force_refresh`。
- 输出：深拷贝的 `A2ACardSnapshot`。
- 并发：同 Key 刷新去重，不同 Key 并行。
- 失败：抛出仅携带 `FailureInfo` 的 `A2ARuntimeError`；原始异常只进入服务端日志/cause。

### A2AProviderRuntime.invoke

- 输入：用户、目标配置、query。
- 输出：`ToolResult`；调用前只发现该目标。
- 协议：现代 JSONRPC 使用 `SendMessage`，HTTP+JSON 使用 `POST /message:send`，legacy Card 保留旧请求格式。
- 失败：超时、不可达、无兼容接口、无效响应与远端协议错误均映射为稳定 A2A failure。

### A2ATool

- `get_remote_agent_cards()`：并行获取所有 enabled Target 的安全描述，返回 `targets + unavailable_target_ids`。
- `call_remote_agent(id, query)`：校验 enabled 配置，只调用指定 Target。
- `cleanup()`：共享 Runtime 不关闭；Tool 自建 Runtime 时负责关闭，保持独立测试和兼容调用可用。

## 错误处理与可观测性

- 新增稳定错误码：目标不存在、Card 发现失败、Card 无效、不支持的 Binding、A2A 超时、调用失败、协议错误、响应过大。
- 用户可见消息不包含 URL、query、响应正文、Header 或原始异常；日志只记录 target ID、错误类别和 debug ID。
- 列目录采用部分成功语义；不可用目标仅返回 ID，不返回端点或异常。
- `CancelledError` 不在 HTTP Runtime 中捕获，确保用户停止和应用关闭仍能终止父 Run。

## 迁移与回滚

- 迁移：无需数据库迁移。A2ATool Schema 名称和参数不变；旧版顶层 URL Card 继续使用原协议请求。
- 回滚：回退本 Stage 3 单一提交即可恢复 Run 私有 Manager；不存在持久化数据回滚。

## 风险

| 风险 | 可能性 | 影响 | 缓解措施 | 验证方式 |
| --- | --- | --- | --- | --- |
| 跨用户/配置复用错误 Card | 低 | 高 | Runtime Key + 代际协调 + 深拷贝 | 隔离与配置变化测试 |
| Card 宣称恶意调用 URL | 中 | 高 | HTTP(S)、无 userinfo、与 base_url 同源 | URL 安全测试 |
| 并发刷新放大流量 | 中 | 中 | 每 Key single-flight | 并发请求计数测试 |
| 旧远程 Agent 被协议升级打断 | 中 | 高 | 顶层 URL legacy 分支保持旧 payload | legacy 回归测试 |
| 外部 Card 向模型注入指令 | 中 | 中 | 有界摘要、字段白名单、untrusted 标签 | 安全投影测试 |
| 应用关闭时仍有请求 | 低 | 中 | lifespan 顺序关闭 Agent Task 后再关闭 A2A Runtime | 生命周期测试 |

## 重要假设

- A2A 配置由当前用户拥有，`user_id` 可作为进程内租户隔离键。
- 本阶段只支持无需额外 Credential 的 A2A 目标；认证留给后续 Provider Policy/Credential Broker。
- Card 的接口 URL通常与配置发现地址同源；跨源接口需要后续显式平台策略，不能默许。
- 远程 Agent 返回同步 Message/Task 即可满足当前 `call_remote_agent` 工具合同。

## 待决策项

无。Streaming、认证、签名验证与本地 Sub Agent 编排均已明确留在后续阶段，不阻塞 Stage 3。

## 验收标准

- [x] 简单对话和未调用 A2A 的 Run 不创建 A2A HTTP Client。
- [x] 调用目标 A 时不会请求目标 B 的 Card。
- [x] 同用户/目标/配置在 TTL 内跨 Run 命中 Snapshot；不同用户或配置不共享。
- [x] 并发发现同一目标只发一次 HTTP 请求；过期后发送条件请求并正确处理 304。
- [x] JSONRPC、HTTP+JSON 与 legacy 三条调用路径有自动化测试。
- [x] Card/调用超时、无效 Card、不支持 Binding、过大响应和远端错误均成为类型化 Tool failure，不取消父 Run。
- [x] 模型可见目录不含 URL、安全声明、任意 Card 字段和原始异常。
- [x] 应用关闭共享 Runtime，Tool 清理不会误关共享 Client。
- [x] Stage 3 定向、后端全量、静态、编译与差异检查通过，并作为唯一一次 Git 提交。

## 实施结果

Stage 3 已按推荐方案落地。`A2AProviderRuntime` 由应用作用域持有，HTTP Client 真实惰性创建；Card Snapshot 与配置代际、single-flight 锁均有界并按用户/目标/指纹隔离。Runtime 支持 `Cache-Control`（含 no-store/no-cache）、ETag、Last-Modified、304 与 bounded stale-if-error；现代 JSONRPC、HTTP+JSON 和旧版 JSON-RPC 均有协议测试。

`A2ATool` 继续只暴露两个固定函数，动态目录返回 `DelegationTargetDescriptor` 白名单投影。单个目标失败不会阻断其他目标，全部失败与调用失败均使用稳定 A2A FailureInfo。共享 Runtime 在所有 Agent Task 之后、数据库之前关闭；单 Runner cleanup 不拥有共享 Client。

未纳入的 A2A streaming、远程 Task 续订、认证/Credential Broker、Agent Card JWS、本地 Sub Agent 编排及跨进程 Cache 继续作为后续阶段，不应由本状态误判为已完成。

## 规范依据

- A2A Specification 1.0：<https://github.com/a2aproject/A2A/blob/main/docs/specification.md>
- A2A Agent Discovery：<https://github.com/a2aproject/A2A/blob/main/docs/topics/agent-discovery.md>
- A2A Protocol Buffers：<https://github.com/a2aproject/A2A/blob/main/specification/a2a.proto>
