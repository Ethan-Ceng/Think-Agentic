# Provider 连接诊断与失败修复闭环

## 文档状态

- 状态：`IMPLEMENTED`
- 负责人：Codex
- 创建日期：2026-08-19
- 最近更新：2026-08-19
- 上位设计：`docs/designs/agent-runtime-hitl-provider-reliability.zh-CN.md`
- 前置设计：`docs/designs/failure-recovery-ux.zh-CN.md`
- 实施阶段：Stage 4B

## 背景

Stage 4A 已让模型、Provider 和 Run 失败形成稳定 `FailureInfo`，错误卡也能把 `check_config / reauthorize` 定向到 LLM、MCP、A2A 或 API Tool 设置页。但修复流程仍停在“打开配置”：

- 设置页不知道用户是因哪个稳定错误码进入，也看不到对应 `debug_id`。
- LLM、MCP、A2A 没有统一、可控的“测试已保存配置”入口。
- API Tool 虽已有注册测试，但“Schema 校验”和“真实 Operation 调用”混在同一弹窗语义中。
- `ProviderDescriptor.health_state` 已存在，却仍是离线目录的默认 `unknown`；现在直接把它升级为后台健康监控，会同时引入状态持久化、TTL、多进程一致性和路由反馈，范围过大。

因此下一步应先完成用户主动触发的诊断闭环：从失败卡进入正确设置页，保留安全失败上下文，使用同一诊断合同测试当前用户已保存的 Provider 配置，并给出可操作、安全且不会误触发外部副作用的结果。

## 目标

- 从错误卡进入设置页时展示稳定错误码、安全消息和 `debug_id`，不展示原始异常或敏感配置。
- 为 LLM、MCP、A2A 和 API Provider 提供统一的按需诊断结果合同。
- LLM 只执行一次极小生成请求；MCP 只连接并发现 Tool Schema；A2A 只刷新 Agent Card；API 只校验注册与 OpenAPI Schema。
- 诊断有明确超时、并发门禁和安全 FailureInfo，不创建 Agent Run、不改变 Session 状态。
- 设置页能区分“连接成功”“配置有效但未联网验证”“暂时降级”和“诊断失败”。
- 配置变化后旧诊断结果立即失效，避免显示与当前配置不一致的状态。

## 功能范围

- 新增统一 `ProviderDiagnosticRequest / ProviderDiagnosticResult`。
- 新增当前用户级 Provider 诊断接口和服务层 Adapter。
- 复用 Stage 4A Model/Provider/A2A FailureInfo，不解析上游错误文本。
- LLM、MCP、A2A、API Tool 设置页增加“测试已保存配置”及结果卡。
- RecoveryAction 打开设置页时携带当前 FailureInfo，仅作为前端瞬时修复上下文。
- API Tool 保留现有显式 Operation 测试；统一诊断只做无副作用的 Schema 校验。
- 覆盖权限隔离、超时、禁用 Provider、重复点击、敏感信息和运行状态不受影响的测试。

## 非功能范围

- 不做后台轮询、定时探活、自动重试或启动时全量连接。
- 不在本阶段持久化健康历史、最近错误列表、成功率或延迟趋势。
- 不让 Lead/Planner 根据本次手工诊断结果自动改写 Provider 路由。
- 不实现自动切换模型、自动选择其他 Provider 或 `choose_provider` 执行器。
- 不自动调用 MCP Tool、A2A Agent 或 API Operation；这些动作可能有外部副作用。
- 不测试未保存的表单配置；用户必须先保存，再测试权威配置。
- 不新增数据库字段或迁移。

## 业务流程

1. 用户在错误卡点击“检查配置”或“重新配置连接”。
2. 前端打开对应设置页，并在顶部显示本次安全 FailureInfo 摘要。
3. 用户修改并保存配置；未保存时诊断按钮禁用或提示先保存。
4. 用户点击“测试已保存配置”。
5. 后端按当前用户、Provider 类型和目标 ID 重新读取权威配置，不接受客户端提交 URL、Header、API Key 或命令。
6. 诊断服务执行该 Provider 的最小无副作用检查，并在固定超时内返回统一结果：
   - LLM：一次极小 Chat Completion，不进入 Agent 重试链。
   - MCP：通过共享 Provider Pool 强制刷新 Schema Snapshot，不调用任何 Tool。
   - A2A：强制刷新 Agent Card，手工诊断不允许 stale-if-error 伪装成当前连接成功。
   - API：解析注册和 OpenAPI Schema，只报告配置有效与 Operation 数量。
7. 前端展示状态、检查类型、耗时、安全消息、能力数量和可选 FailureInfo。
8. 用户修复成功后关闭设置页，回到错误卡选择“重新执行任务”；诊断本身不自动恢复 Run。

## 核心规则

1. 诊断只读取当前用户已保存配置；客户端只传 Provider 类型和不透明目标 ID。
2. 诊断不创建 Session Event、Agent Task、Trace Plan 或 Waiting 状态。
3. “测试连接”不等于调用业务能力：MCP/A2A/API 禁止自动执行 Tool、委派或 Operation。
4. API Schema 校验成功必须标为 `configuration` 检查，UI 文案使用“配置有效”，不能冒充“远端连接正常”。
5. 手工 A2A 诊断必须验证当前远端可达；过期快照不能把失败结果转成成功。
6. LLM 诊断最多调用一次，使用极小输出预算，并由诊断层外部超时终止；不得复用 Agent 的多次重试。
7. 后端只返回固定安全消息、稳定错误码和低基数元数据；URL、Header、Env、命令参数、API Key、响应正文和堆栈不得进入响应。
8. 同一用户、同一 Provider 的并发诊断共享一个在途结果，不重复产生模型费用或连接风暴。
9. 设置配置、启停或删除 Provider 后，页面中的旧诊断结果必须清空。
10. 诊断可以安全预热 MCP Schema/A2A Card 快照，但不得触发未选 Provider 的后台连接。

## 现有实现分析

### 相关代码与文档

- `api/app/core/llm/openai_llm.py`：已有安全 Model Failure 映射，但默认请求超时不适合直接作为诊断超时。
- `api/app/core/tools/provider_runtime.py`：MCP Provider Pool 已支持 `discover(force_refresh=True)`、超时、退避和类型化 Failure。
- `api/app/core/tools/a2a_runtime.py`：A2A Runtime 已支持 Card 强制刷新、single-flight、响应上限和 stale-if-error。
- `api/app/services/tool_config_service.py`：API registration 已支持 Schema 解析和可选 Operation 调用。
- `api/app/core/tools/provider_catalog.py`：已有安全稳定的 MCP Provider ID 和离线 ProviderDescriptor。
- `api/app/schemas/tool_config.py`：已有 `health_state` 字段，但目前没有权威动态健康数据源。
- `web/src/lib/failure-recovery.ts`：已把 RecoveryAction 映射为设置页或 resume 命令。
- `web/src/composables/useSettingsModal.ts`：已支持定向打开设置 Tab，尚未携带失败上下文。
- `web/src/components/settings/SettingsModelPanel.vue`、`SettingsMcpPanel.vue`、`SettingsA2aPanel.vue`、`SettingsApiToolsPanel.vue`：已有各类配置 UI，只有 API Tool 具备测试入口。

### 可复用能力

- ModelFailureCode、ProviderFailureCode、A2AFailureCode 和 FailureInfo 安全投影。
- 应用级 MCPProviderPool 与 A2AProviderRuntime，不需要建立第二套连接生命周期。
- UserConfigService 的用户隔离、敏感字段脱敏和权威配置读取。
- API Tool registration 的 Schema 解析与显式 Operation 测试。
- Settings Modal 定向 Tab、dirty 状态和统一 Toast/UI 卡片样式。

### 当前约束

- OpenAI-compatible Provider 不保证实现 `/models`，LLM 连接只能用最小 Chat Completion 可靠验证。
- MCP 包含 stdio、SSE 和 Streamable HTTP，诊断必须复用现有 Manager/Actor，而不是另写协议探针。
- A2A 的 stale-if-error 对实际 Agent Run 有价值，但手工“当前连接测试”不能被 stale snapshot 掩盖。
- API OpenAPI Schema 不能提供通用、无副作用的远端探活 Operation。
- 当前部署已有 Redis，但本 Stage 不需要新增健康历史存储。

## 可选方案

### 方案 A：各设置页分别增加专用测试接口

- 实现方式：LLM、MCP、A2A 各自在现有 app-config controller 增加 `/test`，API 沿用 registration test；前端各自处理返回结构。
- 优点：改动直观，单页交付快。
- 缺点：四套结果结构、错误映射、超时和 UI 状态会持续分叉。
- 风险：后续做健康历史或路由反馈时需要再次统一，容易出现“同一错误不同提示”。

### 方案 B：统一按需诊断服务与 Provider Adapter

- 实现方式：新增统一请求/结果合同和 ProviderDiagnosticService；内部按类型调用现有 LLM/MCP/A2A/API 能力，前端复用同一结果卡。
- 优点：安全、超时、并发、FailureInfo 和 UI 语义一致；不引入持久化，且可增量复用现有 Runtime。
- 缺点：需要跨后端服务、Runtime 小扩展和四个设置页。
- 风险：若 Adapter 边界不严，可能把 API Schema 校验误标成远端健康。

### 方案 C：直接建设持久化 Provider 健康平台

- 实现方式：所有运行时被动上报成功/失败到 Redis 或数据库，后台主动探活，Provider Catalog 和 Lead 路由消费健康状态，管理页展示历史趋势。
- 优点：能真正支持最近错误、成功率、告警和自动降级路由。
- 缺点：需要 TTL、配置代际、多进程一致性、采样、写放大和路由策略，范围远大于当前修复闭环。
- 风险：在没有稳定诊断语义前先持久化数据，会把错误分类和健康定义固化错。

## 方案对比

| 维度 | 方案 A | 方案 B | 方案 C |
| --- | --- | --- | --- |
| 实现复杂度 | 低 | 中 | 高 |
| 维护成本 | 四套逻辑持续分叉 | 单一合同，适中 | 状态平台与路由长期维护 |
| 兼容性 | 高，但难统一演进 | 高；新增接口、不改现有接口 | 需新增存储和运行时观察者 |
| 测试难度 | 低中 | 中 | 高 |
| 交付成本 | 最低 | 可控，一个 Stage | 多 Stage |
| 主要风险 | 语义漂移 | Adapter 状态定义错误 | 过度设计与错误路由反馈 |

## 推荐方案

采用方案 B，并把方案 C 明确留给后续 Stage 4C。

当前最需要的是让用户能够完成“看到错误 → 修配置 → 验证 → 重跑”的闭环。统一按需诊断能直接解决这个问题，又不会在每次会话或打开设置页时连接所有 Provider。方案 A 虽快，但会重新制造已经通过 FailureInfo 消除的语义分叉；方案 C 最终有价值，但应建立在本 Stage 已验证的诊断合同之上。

## 数据结构

### ProviderDiagnosticRequest

| 字段 | 类型 | 必填 | 说明 | 约束/默认值 |
| --- | --- | --- | --- | --- |
| `provider_type` | `llm/mcp/a2a/api` | 是 | 诊断 Adapter | 固定枚举 |
| `target_id` | `str/null` | 否 | MCP server name、A2A target id 或 API registration id | LLM 必须为空；其他类型必填，最大 160 字符 |

请求不允许携带配置、凭据、URL、Header、命令或测试参数。

### ProviderDiagnosticResult

| 字段 | 类型 | 必填 | 说明 | 约束/默认值 |
| --- | --- | --- | --- | --- |
| `provider_type` | enum | 是 | Provider 类型 | 与请求一致 |
| `provider_id` | `str` | 是 | 安全稳定 Provider ID | 不返回 URL |
| `check_kind` | `inference/discovery/configuration` | 是 | 本次实际验证层级 | API 固定 configuration |
| `status` | `healthy/degraded/unhealthy` | 是 | 本次诊断结果 | 不作为持久化健康历史 |
| `message` | `str` | 是 | 用户安全结果摘要 | 固定文案，最大 300 字符 |
| `checked_at` | UTC datetime | 是 | 完成时间 | ISO 8601 |
| `latency_ms` | `int` | 是 | 本次耗时 | 非负、有界 |
| `capability_count` | `int/null` | 否 | Tool/Skill/Operation 数量 | 不返回 Schema |
| `snapshot_state` | `fresh/stale/null` | 否 | MCP/A2A Snapshot 状态 | 手工成功通常 fresh |
| `failure` | `FailureInfo/null` | 否 | 失败或降级原因 | 安全稳定投影 |

`status` 只描述本次检查观察到的结果：成功为 `healthy`；可重试的暂时失败为 `degraded`；鉴权、权限、无效配置等确定性失败为 `unhealthy`。它不写回持久化 Provider 健康状态。

### 诊断新增稳定错误码

| 错误码 | 典型来源 | retryable | 默认动作 |
| --- | --- | --- | --- |
| `PROVIDER_CONFIGURATION_INVALID` | API registration/OpenAPI Schema 无效 | 否 | `check_config` |
| `PROVIDER_DIAGNOSTIC_FAILED` | 诊断层未分类内部失败 | 是 | `retry`, `check_config` |

LLM、MCP 和 A2A 优先复用已有 `MODEL_*`、`PROVIDER_*`、`MCP_*` 和 `A2A_*` 错误码；诊断外层超时时也按具体 Provider 映射到已有 timeout code，不创造同义错误。

### SettingsFailureContext（前端内部）

| 字段 | 类型 | 必填 | 说明 |
| --- | --- | --- | --- |
| `tab` | `SettingTab` | 是 | 目标设置页 |
| `failure` | `FailureInfo/null` | 否 | 触发本次打开的安全失败上下文 |

该结构只存在于当前浏览器内存，设置弹窗关闭或普通入口重新打开时清除。

## 接口设计

### POST `/provider-diagnostics/test`

- 输入：`ProviderDiagnosticRequest`；后端根据登录用户重新读取权威配置。
- 输出：成功与业务诊断失败均返回 `ProviderDiagnosticResult`；只有未登录、目标不存在、请求结构非法等接口错误使用 HTTP 4xx。
- 权限：必须登录；target 必须属于当前用户配置，禁止跨用户探测。
- 幂等/并发：检查无业务副作用；同一 `user_id + provider_type + target_id` 使用有界 single-flight，共享同一个在途结果。
- 超时：LLM 15 秒；MCP/A2A 30 秒；API 配置解析 10 秒。超时返回对应安全 FailureInfo。
- 兼容性：新增接口，不修改现有 app-config、Tool registration 或 resume API。

### Recovery settings command

- 输入：`FailureRecoveryCommand(kind=settings)` 增加可选 `failure`。
- 输出：Settings Modal 在目标页顶部显示安全修复上下文。
- 兼容性：普通 `openSettings()` 和不含 failure 的旧调用保持现有行为。

### 现有 API registration test

- 保留 `/tools/registrations/{id}/test` 的显式 Operation 测试能力。
- 统一 Provider 诊断只校验 registration/OpenAPI Schema，不传 function arguments、不调用远端 Operation。
- UI 必须分别标注“校验配置”和“调用 Operation”，避免副作用误解。

## 错误处理与可观测性

- 所有 Adapter 异常在 ProviderDiagnosticService 边界转换为现有 FailureInfo；原始异常仅进入服务端受控日志。
- 日志只记录 `provider_type/provider_id/status/code/debug_id/latency_ms`，不记录目标 URL、Header、Env、命令参数或响应体。
- 诊断失败不写 Session Event，不改变 Agent Task、Session status、Provider enabled 状态或 Tool binding。
- 并发请求共享同一个诊断 Future；等待者取消不会取消共享的底层检查。
- 首期只写低基数结构化日志，不建设指标或历史存储。

## 迁移与回滚

- 迁移：无数据库迁移；新增 API 与前端瞬时状态，不读取或改写历史事件。
- 回滚：可整体回滚 Stage 4B；Stage 4A 的错误卡和设置定向仍可工作，只失去测试与失败上下文展示。
- 配置兼容：MCP/A2A/API 的现有配置结构和 Provider ID 规则不变。

## 风险

| 风险 | 可能性 | 影响 | 缓解措施 | 验证方式 |
| --- | --- | --- | --- | --- |
| LLM 测试产生额外费用 | 中 | 低中 | 明确用户点击、一次调用、极小 token、无重试、15 秒超时 | Fake LLM 调用次数与参数测试 |
| API 校验被误解为连接成功 | 中 | 中 | check_kind=configuration，UI 固定“配置有效” | 组件文案与合同测试 |
| A2A stale snapshot 掩盖当前故障 | 中 | 高 | 手工诊断禁止 stale fallback | stale fixture 回归 |
| MCP 重复点击导致连接风暴 | 中 | 中高 | Provider Runtime single-flight + 诊断 keyed gate + UI busy | 并发请求共享结果和调用计数测试 |
| 诊断响应泄露 Secret/URL/异常正文 | 低中 | 高 | 白名单结果结构、固定 FailureInfo、敏感 fixture 扫描 | API 序列化安全测试 |
| 诊断错误终止正在运行的 Agent | 低 | 高 | 服务与 AgentTaskRunner 完全解耦，不写 Session | 并行运行状态回归测试 |
| 已修改未保存配置与测试结果不一致 | 中 | 中 | dirty 时禁用测试并提示先保存；保存后清空旧结果 | 前端状态测试 |

## 重要假设

- 用户接受 LLM“测试连接”会产生一次极小模型请求；按钮文案会明确说明。
- MCP Schema discovery、A2A Agent Card discovery 和 API Schema parsing 可视为无业务副作用检查。
- 当前 Provider 配置继续由 UserConfigService 按用户隔离；诊断接口不接收候选配置。
- Stage 4B 仍作为一个独立提交交付，不与 `form_input`、健康历史或自动路由混合。
- 真正的最近错误列表、成功率和 Provider 路由反馈需要 Redis/持久化健康记录，留到 Stage 4C 单独设计。

## 待决策项

无。Stage 4B 固定采用按需诊断；是否建设 Stage 4C 持久化健康与路由反馈，在收集本阶段实际使用反馈后决定。

## 验收标准

- [x] 从 ErrorEvent 打开设置页时显示正确的安全错误码、消息和 debug_id；普通设置入口不残留旧失败上下文。
- [x] LLM 诊断只调用一次、使用极小输出预算、15 秒内结束且失败保持 Model Failure 类型。
- [x] MCP 诊断只刷新所选 Server 的 Schema，不连接其他 MCP Server、不调用 Tool。
- [x] A2A 诊断只刷新所选 Agent Card，当前远端失败时不以 stale snapshot 报成功、不调用远程 Agent。
- [x] API 诊断只解析配置和 Schema，UI 明确显示“配置有效”，现有显式 Operation 测试仍需用户选择函数和参数。
- [x] target 不存在或不属于当前用户时无法触发网络请求；禁用 Provider 可被显式测试但不会被启用。
- [x] 同 Provider 并发测试只有一个实际诊断并共享结果；等待者取消不取消底层检查，超时返回稳定安全 FailureInfo。
- [x] 响应、日志和页面不包含 API Key、Header、Env、URL、命令参数、上游响应正文或堆栈。
- [x] 诊断成功或失败均不创建 Agent Run/Event、不改变 Session 状态。
- [x] 后端全量测试、Ruff、compileall、前端全量测试、类型检查和生产构建通过。

## 实施结果

Stage 4B 已按本设计完成：新增统一诊断契约和认证接口，四类 Provider 使用最小、显式、有界的检查；设置页保留瞬时失败上下文并提供一致的诊断结果卡。实现不新增迁移、后台探活、健康持久化或 Lead 路由反馈。

最终自动门禁为后端 605 项、前端 205 项测试全部通过，Ruff、compileall、前端类型检查、生产构建与 `git diff --check` 均通过。审查记录见 `docs/reviews/provider-connection-diagnostics-review.md`；真实用户凭据对应的外部端点连接留给部署后的 8088 手工验收。
