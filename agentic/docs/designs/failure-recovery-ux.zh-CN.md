# Agent Failure 语义与恢复 UX

## 文档状态

- 状态：`IMPLEMENTED`
- 负责人：Codex
- 创建日期：2026-08-19
- 最近更新：2026-08-19
- 上位设计：`docs/designs/agent-runtime-hitl-provider-reliability.zh-CN.md`
- 实施阶段：Stage 4A

## 背景

Stage 2 已为 `ErrorEvent` 与 `ToolResult` 建立兼容的 `FailureInfo`，MCP/A2A Provider 也能返回稳定错误码；但用户体验仍未闭环：

- LLM Adapter 把鉴权、限流、超时、连接和服务端错误统一包装成普通 500，Agent 重试耗尽后又降级为 `RUN_INTERNAL_ERROR`。
- `BaseAgent` 和 `AgentService.chat()` 仍存在只写字符串的 `ErrorEvent`；后者还可能把原始异常直接写入会话事件和 SSE。
- 前端只根据 `retryable` 固定显示“重新生成回复 / 重新执行任务”，没有消费 `recovery_actions`。
- `check_config`、`reauthorize` 等动作没有连接到已有设置页；`choose_provider` 尚无可强制执行的后端语义。
- 错误卡虽持有 `debug_id`，但用户无法看到用于支持排查的参考编号。

结果是失败数据合同已经存在，但错误原因、可执行恢复动作和最终页面行为仍可能不一致。

## 目标

- LLM 的常见失败在 Adapter 边界转换为稳定、安全的 Model Failure，不再全部显示为内部运行错误。
- 应用产生的用户可见终止 `ErrorEvent` 均携带 `FailureInfo`，原始异常不进入 SSE 或持久化事件。
- 前端严格按 `recovery_actions` 和本地可执行能力展示按钮，不根据错误文案猜测动作。
- `retry / continue / start_new_run` 复用现有恢复接口；`check_config / reauthorize` 打开与失败来源对应的设置面板。
- 暂无可靠执行能力的 `choose_provider` 不展示，避免“按钮可点但语义未生效”。
- 错误卡展示安全消息与 `debug_id` 参考编号，历史错误保持只读。

## 功能范围

- Model Failure 稳定错误码、默认安全消息、可重试性和恢复动作。
- OpenAI-compatible Adapter 的错误类型映射，覆盖块调用与流式调用。
- Agent 模型重试链保留最后一个类型化失败；不可重试错误不做无意义重试。
- Runner 和订阅边界的安全 ErrorEvent 投影。
- 前端恢复动作注册表、错误卡动作渲染和设置面板定向打开。
- 后端、前端合同测试与回归验证。

## 非功能范围

- 不实现 `form_input`；它作为独立 Stage 4B 评估。
- 不实现 Provider 健康管理页、测试连接或最近错误列表。
- 不新增通用恢复工作流引擎，也不改变 Session 状态机。
- 不实现真正的 Provider 排除、强制换 Provider 或模型自动切换；因此本阶段不执行 `choose_provider`。
- 不改变现有 `/sessions/{id}/resume` 的公共请求结构，不新增数据库字段或迁移。
- 不向终端用户展示原始异常、URL、Header、API Key、响应体或堆栈。

## 业务流程

1. LLM Adapter 发起块调用或流式调用。
2. SDK 异常在 Adapter 边界按异常类型/HTTP 状态映射为 `ModelRuntimeError(FailureInfo)`。
3. Agent 只对 `retryable=true` 的失败执行既有有界重试；失败耗尽时保留最后一个 Model Failure。
4. Runner 把类型化失败写成权威 `ErrorEvent.failure`，把 Session 收敛为 `completed`；未知异常只投影安全的 `RUN_INTERNAL_ERROR`。
5. 前端从持久化事件或 SSE 构建同一错误卡，显示后端安全消息和参考编号。
6. 前端按后端动作顺序过滤本地支持项：
   - `retry`：以现有 `continue` 模式重试本次回复。
   - `continue`：从已有结果继续。
   - `start_new_run`：经现有确认后重新执行任务。
   - `check_config / reauthorize`：打开模型、MCP、A2A 或 API Tool 设置页。
   - `choose_provider`：本阶段隐藏。
7. 只有当前会话最后一个失败事件显示动作；历史错误仅展示事实。

## 核心规则

1. 后端 `FailureInfo` 是失败原因和建议动作的事实来源；前端不得根据本地化错误字符串反推错误类型。
2. `recovery_actions` 是建议集合，不代表客户端必然支持；客户端只展示有真实处理器的白名单动作。
3. `retryable=false` 只禁止同操作重试，不应隐藏 `start_new_run`、`check_config` 等不同语义动作。
4. `retry` 与 `continue` 当前都复用 `resume(mode=continue)`，但保留不同文案；后端继续负责避免重复副作用。
5. `choose_provider` 只有在执行层能强制排除失败 Provider 或选择指定 Provider 后才能开放。
6. 所有 Agent 执行边界的未知异常只能形成安全通用 Failure；原始异常可写受控服务端日志/Trace，但不得写用户事件。
7. SSE/Redis 输出订阅是消费者传输边界；失败只关闭当前订阅并由客户端重连对账，不得持久化 ErrorEvent 或终止仍在运行的 Agent Run。
8. `debug_id` 是用户与服务端排查的关联标识，不承载内部细节。

## 现有实现分析

### 相关代码与文档

- `api/app/core/entities/failure.py`：已有通用 FailureInfo、Run Failure 和 RecoveryAction。
- `api/app/core/llm/openai_llm.py`：目前把所有 SDK 异常包装为 `ServerRequestsError`，丢失失败类别。
- `api/app/core/agent/base.py`：拥有模型重试和流式草稿回滚，但最终抛出普通 RuntimeError。
- `api/app/core/agent/agent_task_runner.py`：能处理 Provider Failure，尚无 Model Failure 专用分支。
- `api/app/services/agent_service.py`：订阅异常路径仍创建 `ErrorEvent(error=str(e))`。
- `web/src/components/chat/ChatMessage.vue`：能显示 FailureInfo 的标题/消息，但动作固定为两个按钮。
- `web/src/components/SessionDetailView.vue`：已有 `continue/restart` 恢复与 restart 二次确认。
- `web/src/composables/useSettingsModal.ts`：只能打开默认设置首页，不能指定面板。
- `docs/designs/chat-reply-failure-recovery.zh-CN.md`：已完成无稳定错误码时期的通用失败卡，本设计在其上增量演进。

### 可复用能力

- `FailureInfo`、`RecoveryAction` 和 `debug_id` 序列化合同。
- Provider Runtime 的“安全 Failure + 内部 cause”异常封装模式。
- 现有 Session resume SSE、`continue/restart` 语义及并发门禁。
- Settings Modal 中已有 `llm / mcp / a2a / tools` 面板。
- Timeline 已能同时保留实时与历史事件中的 FailureInfo。

### 当前约束

- OpenAI SDK 同时服务于 OpenAI 和兼容协议 Provider，映射必须依赖稳定 SDK 异常类型/HTTP 状态，不能解析错误文本。
- 前端当前没有 Provider Picker；仅靠提示词要求换 Provider 不是强制语义。
- Session 仍以 `completed` 表示成功、失败或停止后的非运行状态，本阶段不引入 `failed` 状态。

## 可选方案

### 方案 A：仅改前端动作渲染

- 实现方式：保留后端现状，只把已有 `recovery_actions` 映射为按钮。
- 优点：改动小、交付快。
- 缺点：模型错误仍被压成 Internal；部分 ErrorEvent 仍无 FailureInfo 或泄露原始异常。
- 风险：页面更精致，但恢复建议仍可能基于错误类别缺失而不准确。

### 方案 B：端到端类型化失败 + 客户端动作白名单

- 实现方式：补 Model Failure、收口 ErrorEvent 边界，再由纯前端注册表映射支持的恢复动作。
- 优点：错误原因、Trace、持久化事件和 UI 一致；复用现有接口，无数据库迁移。
- 缺点：涉及 LLM、Agent Runner、Service 和前端多个模块。
- 风险：修改重试异常类型可能影响既有测试，需要完整回归。

### 方案 C：通用 Recovery Command 工作流

- 实现方式：新增恢复命令 API，由后端执行换 Provider、重授权、配置跳转和副作用补偿。
- 优点：动作能力最完整，可为未来 Durable Runtime 复用。
- 缺点：需要 Provider 选择策略、Effect Ledger 和新的公共状态机，范围显著扩大。
- 风险：在 Durable Finalizer 前先引入半套工作流，会造成新的恢复语义分叉。

## 方案对比

| 维度 | 方案 A | 方案 B | 方案 C |
| --- | --- | --- | --- |
| 实现复杂度 | 低 | 中 | 高 |
| 维护成本 | 前后端语义继续分裂 | 单一 Failure 合同，适中 | 新工作流长期成本高 |
| 兼容性 | 高但缺陷保留 | 高；字段与 resume API 不变 | 需要新 API/状态迁移 |
| 测试难度 | 低 | 中 | 高 |
| 主要风险 | 错误动作不准确 | 重试边界回归 | 过度设计、状态不一致 |

## 推荐方案

采用方案 B。当前缺口不是单纯按钮样式，而是模型失败在后端被过早抹平；只改前端无法让错误原因真实。方案 B 利用已经落地的 FailureInfo 和恢复接口，补齐端到端语义而不引入数据库或新工作流。方案 C 等 Durable Finalizer、Effect Ledger 和可强制 Provider 选择具备后再评估。

## 数据结构

### Model Failure Code

| 错误码 | 典型来源 | retryable | 默认动作 |
| --- | --- | --- | --- |
| `MODEL_AUTHENTICATION_FAILED` | 401/鉴权失败 | 否 | `check_config, start_new_run` |
| `MODEL_PERMISSION_DENIED` | 403/权限不足 | 否 | `check_config, start_new_run` |
| `MODEL_RATE_LIMITED` | 429/限流或额度限制 | 是 | `retry`, `check_config` |
| `MODEL_TIMEOUT` | 请求超时 | 是 | `retry` |
| `MODEL_CONNECTION_FAILED` | DNS/TLS/连接异常 | 是 | `retry`, `check_config` |
| `MODEL_REQUEST_INVALID` | 其他 4xx 请求配置错误 | 否 | `check_config, start_new_run` |
| `MODEL_SERVICE_UNAVAILABLE` | 5xx | 是 | `retry` |
| `MODEL_INVALID_RESPONSE` | 非法流事件/未完成流 | 是 | `retry` |
| `MODEL_EMPTY_RESPONSE` | 有效请求但无可用内容 | 是 | `retry` |
| `MODEL_UNKNOWN_ERROR` | 未分类模型边界异常 | 是 | `retry`, `check_config` |

不修改 `FailureInfo` 字段；Model Failure 使用 `category=model`、`scope=run`、低基数 `source=llm.openai_compatible`。

### FailureRecoveryCommand（前端内部）

| 字段 | 类型 | 必填 | 说明 |
| --- | --- | --- | --- |
| `action` | `RecoveryAction` | 是 | 后端建议动作 |
| `kind` | `resume/settings` | 是 | 本地执行器 |
| `mode` | `continue/restart` | 否 | resume 动作参数 |
| `settingsTab` | `llm/mcp/a2a/tools/common` | 否 | 设置目标面板 |
| `label` | `string` | 是 | 用户可见文案 |
| `primary` | `boolean` | 是 | 主操作样式 |

该结构不通过网络传输。

## 接口设计

### ErrorEvent / FailureInfo

- 输入：内部类型化 Failure 或未知异常。
- 输出：保持 `{ type: "error", error, failure? }` 兼容结构；新事件必须含 `failure`，且 `error == failure.message`。
- 权限：沿用 Session 用户隔离。
- 幂等/并发：沿用事件追加和 Session 终止逻辑。
- 兼容性：历史无 `failure` 事件继续显示通用安全提示和 legacy 恢复动作。

### POST `/sessions/{session_id}/resume`

- 输入：仍为 `{ mode: "continue" | "restart" }`。
- 输出：现有 SSE 事件流。
- 权限、幂等/并发：沿用已有 Session 行锁和 running 冲突处理。
- 兼容性：无公共接口变化。

### `useSettingsModal.openSettings(tab?)`

- 输入：可选设置 Tab；省略时保持默认外观页行为。
- 输出：打开全局设置弹窗并激活目标面板。
- 兼容性：现有无参调用不变。

## 错误处理与可观测性

- SDK 原始异常仅作为 `ModelRuntimeError.__cause__` 和受控日志信息，不进入 FailureInfo。
- Model Call Trace 的 error 字段接收安全 Failure message；Run Error Trace 继续记录稳定 code/category/source/debug_id。
- 输出订阅异常只记录服务端日志并关闭当前 SSE，不生成 Agent Failure；前端沿用现有流结束对账/重连。
- 设置面板打开失败不触发新的 Agent Run；未知/暂不支持的 RecoveryAction 被忽略。
- 历史无 FailureInfo 的错误继续使用既有通用模型提示，避免把旧内部字符串重新展示出来。

## 迁移与回滚

- 迁移：无数据库迁移；新错误事件增量携带已有可选字段，旧事件继续可读。
- 回滚：可整体回滚 Stage 4A 提交；旧客户端仍读取 `error`，现有 resume API 不受影响。

## 风险

| 风险 | 可能性 | 影响 | 缓解措施 | 验证方式 |
| --- | --- | --- | --- | --- |
| SDK 异常子类顺序导致误分类 | 中 | 中 | timeout 先于 connection，具体 HTTP 类型先于通用 APIStatus | 分类参数化测试 |
| 不可重试错误仍重复请求 | 中 | 中 | Agent 捕获 ModelRuntimeError 后读取 retryable | 调用次数测试 |
| 前端展示后端建议但无执行器 | 中 | 高 | 纯函数白名单过滤；choose_provider 明确隐藏 | 动作矩阵测试 |
| retry/continue 重复语义造成重复按钮 | 低 | 中 | 同一 Failure 的相同执行语义去重，优先保留后端顺序第一项 | 前端单测 |
| 订阅传输失败被误判为 Agent 失败 | 中 | 高 | 仅关闭当前 SSE，不写事件、不改 Session；客户端重连对账 | 状态与事件回归测试 |
| 设置页来源映射错误 | 低 | 中 | model→llm、mcp→mcp、a2a→a2a、api→tools 的显式映射 | 纯函数测试 |

## 重要假设

- 当前 OpenAI SDK 版本提供稳定的异常类层级；项目锁定版本为 1.107.2。
- `resume(mode=continue)` 是当前最接近“重试回复/继续执行”的安全实现，并已有避免重复副作用的系统提示。
- Settings Modal 是当前配置修复入口；本阶段不需要独立连接授权中心。
- Stage 4A 作为一个完整提交交付，不与 Stage 4B 表单或 Provider 管理混合。

## 待决策项

无。真正的 `choose_provider` 行为留到执行层能强制排除/选择 Provider 的后续设计，不阻塞本阶段。

## 验收标准

- [x] 鉴权、权限、限流、超时、连接、非法请求、5xx 和未知模型错误产生不同稳定错误码，且不暴露原始异常。
- [x] 不可重试 Model Failure 不重复调用；可重试失败遵守现有最大重试次数并保留最后 Failure。
- [x] 应用源码中的用户可见终止 ErrorEvent 均有安全 FailureInfo；订阅异常不写 ErrorEvent、不改变仍运行的 Session。
- [x] 前端只展示当前 Failure 声明且本地支持的恢复动作，`retryable=false` 不会错误隐藏配置或新 Run 动作。
- [x] `check_config / reauthorize` 打开正确设置面板；`choose_provider` 在无真实执行器时不显示。
- [x] 错误卡展示安全消息和 debug_id；历史无 FailureInfo 事件继续安全兼容。
- [x] 后端全量测试、Ruff、compileall、前端全量测试、类型检查和生产构建通过。
