# Agent Runtime：统一工具平面、Sandbox 按需执行、HITL 与 Provider 可靠性

## 文档状态

- 状态：`PARTIALLY_IMPLEMENTED`
- 负责人：Codex
- 创建日期：2026-08-18
- 最近更新：2026-08-19
- 前置设计：`lead-agent-runtime-unification.zh-CN.md`
- 实施进度：通用 `tool_approval` 移除、历史状态安全收敛、`ask_user` Composer/问题卡统一原子自动续跑、Lazy Sandbox Runtime，以及阶段 1A/1B 的统一 Tool Plane 与外部 Provider 惰性接入已落地；阶段 2 的 MCP Provider Actor、跨 Run 有界 Schema Snapshot、类型化错误与取消来源隔离已落地；阶段 3 的 A2A 目标级 Card Snapshot、条件刷新、共享 HTTP Runtime、安全委派目录和现代/旧协议兼容已落地；完整平台 Capability Grant、Durable Finalizer、A2A streaming/认证和完整错误 UX 仍待后续批次

## 结论先行

需要优化，而且应当作为 Lead Agent 下一批 P0/P1 运行时改造处理。

1. 目标架构移除通用 `tool_approval`。`waiting` 只用于 Agent 确实缺少业务输入的 `ask_user`，以及后续可选的多字段 `form_input`；平台安全不能依赖终端用户逐次点击批准。
2. `WaitEvent` 表示逻辑 Run 正在等待用户业务输入，不表示对话关闭，也不表示必须保留一个活着的协程或 Task。底层执行 Task 可以释放，用户再次输入后由系统自动继续同一逻辑 Run，不暴露“恢复对话”操作。
3. 内置工具、API、MCP Tool 和 A2A 委派目标共用统一 Catalog、Selection、Scope、Schema Injection 和 Trace；内部/外部只是能力来源与执行方式不同，不能继续维护两套上下文注入链路。
4. Tool 的来源和执行后端必须拆开表达。`builtin.shell` 的 `source_type=builtin`，但 `execution_backend=sandbox`；Sandbox 是按需取得的隔离运行资源，不是普通 Tool Provider，也不应作为一个含混的万能工具暴露给模型。
5. Lead 只读取不含参数 Schema 的静态 Provider/Capability Catalog；选出最小 `capability_groups + provider_ids + tool_ids` 后，执行层才解析并注入当前步骤需要的 Schema。目录读取、选择和 Schema 解析均不得启动 Sandbox 或连接外部 Provider。
6. Sandbox 一律晚激活，但不一律最后选择：通用 Shell/Python/浏览器脚本属于优先使用专用能力后的通用执行后备；用户任务本身明确要求代码执行、文件处理或交互式浏览器时，Sandbox-backed Tool 可以直接成为首选。晚激活与最后手段是两个独立策略。
7. Sandbox 内的 Shell/File/Browser 工具在通过平台隔离策略后默认自动执行；MCP/A2A/API 等外部能力由平台级权限、网络出口和 Provider Policy 决定 allow/deny。无法安全支持的能力直接拒绝，不退化为用户审批。
8. MCP/A2A 传输失败必须被限制在 Provider 或 Tool Call 边界。它可以触发降级、重试、换 Provider、Replan 或明确的任务失败，但不能伪装成整个 Agent Task 被用户取消。
9. `asyncio.CancelledError` 是控制流信号，不是通用网络错误。必须记录取消来源；只有用户停止、服务关闭或明确 Run 取消才能成为 `RUN_CANCELLED_*`，Provider 内部 cancel scope 异常应被隔离并转换成 `PROVIDER_*` 错误。
10. 当前只有字符串的 `ErrorEvent` 无法支撑正确提示和恢复操作。应新增稳定错误码、来源、作用域、是否可重试和恢复动作，同时保留 `error` 字段兼容旧前端。

## 背景

Lead Agent 已经能在 `direct / react / plan` 之间选择策略，也能用 Capability Catalog 和 Runtime Tool Scope 减少无关 Tool Schema。但是 Provider 生命周期仍在旧架构中：`AgentTaskRunner.invoke()` 在读取并执行当前消息之前，无条件初始化 MCP 和 A2A。

已复现的多轮故障并不是模型 API 不可用：Lead 和 React 模型调用均成功，随后无关 MCP 服务器在重新连接时发生传输异常，AnyIO cancel scope 抛出 `asyncio.CancelledError`。该异常越过 `except Exception`，被顶层 Runner 当作整个任务取消；Task Registry 随后移除任务，订阅端又把它误判为“服务重启后运行上下文丢失”，前端最终统一显示为“模型服务暂时不可用”。

这说明当前问题包含四个相互关联的边界：

- HITL：什么时候是正常等待，如何持久化和恢复。
- Tool Plane：Lead 应看到什么目录，当前步骤应选择、注入和约束什么 Tool。
- Execution Backend：选中 Tool 最终在进程内、Sandbox、远端 Provider 还是委派 Runtime 执行。
- Provider Lifecycle：什么时候连接 MCP/A2A，连接由谁拥有、复用和清理。
- Failure Semantics：Provider、Tool、Model、Run 和 Cancel 应如何区分。

只增加一条 `except asyncio.CancelledError` 或只修改前端提示，都无法消除根因。

## 目标

- 无工具、内置工具或只使用 Shell 的 Run，不连接任何 MCP/A2A Provider。
- Lead 决策阶段只接收紧凑目录，不接收完整 Tool Schema，也不发起外部 Provider I/O。
- React/Plan Step 只激活并注入当前选择的 Capability、Provider 和 Tool Schema。
- Catalog、选择和 Schema 注入不会创建/恢复 Sandbox；只有第一次真实调用 Sandbox-backed Tool 才取得 Sandbox Lease。
- 内置和外部 Tool 使用同一套 Descriptor、Scope、Context Injection、执行前校验、结果协议和 Trace。
- 同一进程内复用已连接 Provider 和安全的 Schema/Card 快照，不在每次多轮消息、HITL 恢复时重复全量发现。
- 单个 MCP/A2A Provider 失败不取消父 Agent Task，不影响无关 Provider。
- 用户看到与真实原因一致的错误提示和恢复动作，不再把所有错误归为模型故障。
- 新 Run 不再产生 `tool_approval`；Sandbox 内允许的工具自动执行，减少无价值的人机中断。
- HITL 等待仅用于缺少业务输入；刷新、跨 Task 和进程重启后仍可继续回答，同一个 Action 只允许成功解决一次。
- 用户重新打开旧会话并输入消息时，系统根据 pending Ask/Form 自动路由；没有 pending Interaction 时直接带对话上下文启动新 Run。
- 为后续本地 Sub Agent 和远程 A2A Agent 提供统一的选择/观测边界，但不在本批实现新的多 Agent 调度器。

## 非功能范围

- 不重做 Sandbox 惰性创建；复用现有 `LazySandboxRuntime`，本设计只固定它在统一工具平面中的位置和激活契约。
- 不实现跨节点、跨进程共享的完整 Tool Gateway 服务。
- 不实现通用工作流引擎、分布式 Run 恢复或副作用对账。
- 不把所有 MCP Tool Schema 永久写入对话 Memory。
- 不允许 Lead 直接看到 Provider 凭据、Header、URL、环境变量或原始异常堆栈。
- 不在本批新增本地 Sub Agent 编排；A2A 只作为远程委派 Provider 接入。
- 不继续维护“按风险等级向终端用户逐次审批”的产品交互；历史事件只读兼容。

## 术语与边界

| 术语 | 含义 | 是否进入 Lead Prompt |
| --- | --- | --- |
| Capability | `shell`、`search`、`mcp`、`a2a` 等粗粒度能力 | 是，仅摘要 |
| Provider | Tool/委派能力的来源，例如内置模块、具体 MCP Server、API 集成或 A2A Agent | 是，仅安全元数据 |
| Source Type | 能力来自 `builtin / api / mcp / a2a`；不决定在哪里执行 | 是，可作为安全元数据 |
| Execution Backend | `in_process / sandbox / sandbox_browser / remote_http / external_provider / delegation`；决定运行时路由和资源生命周期 | 否，仅进入执行策略 |
| Tool Schema | 可调用函数及参数 JSON Schema | 否；仅进入选定执行步骤 |
| Provider Runtime | 连接、发现、缓存、健康状态、调用和清理的运行时 | 否 |
| Sandbox Runtime | 按需创建/恢复、租用和回收隔离环境的资源 Runtime；不是 Tool Provider | 否 |
| Interaction | 一次可持久化、可解决的人机动作 | 作为事件，不进入无关 Prompt |
| Wait | Run 已安全暂停，等待外部人类事件 | 作为状态/事件 |
| Cancel | Run 被明确终止 | 是终止控制流，不等同于失败或等待 |

## HITL 语义

### 哪些情况应该等待用户

改造前，`ask_user` 和 `tool_approval` 都会产生 `InteractionEvent` 和 `WaitEvent`。当前运行链路只保留“缺少业务输入”这一种等待原因，通用工具审批已移除。

| Interaction Type | 用途 | 合法决定 | 输入结构 | 恢复动作 |
| --- | --- | --- | --- | --- |
| `ask_user` | 一个逻辑问题、单选、多选或自由文本 | `answer` | 当前 `options / allow_multiple / allow_text` | 把回答作为原 Tool Call 结果继续 |
| `form_input` | 多字段结构化信息采集 | `submit / cancel` | `input_schema + values` | 校验字段后恢复原步骤；首期可作为后续增量 |

当前代码中的 `ask_user` 是“一道结构化问题”，不是完整的多字段表单。如果产品需要同时收集多个字段，不应继续把 JSON 字符串塞进 `answer`，应新增 `form_input` 及明确 Schema；它仍复用相同的 `waiting` 状态和解决接口。

`tool_approval` 作为历史事件仍可读取，但新 Run 不再创建。为兼容既有事件枚举，历史 pending 审批在用户下一次普通输入、领取新 Run 的行锁事务内追加 `REJECT/RESOLVED` 事件，语义明确为“机制停用、旧调用未执行”；同时为 Memory 中悬空的 Tool Call 补失败 Tool Result。它不是用户拒绝，也不会调用旧工具。随后 Lead 带已有对话上下文启动新 Run。

### 状态机

```text
RUNNING
  |-- interaction.pending 持久化成功
  |-- session.status = WAITING
  |-- WaitEvent 输出
  `-- 当前 Task 正常结束

WAITING
  |-- 用户直接回答或提交表单
  |-- Interaction Router 按 action_id 原子解决
  `-- 系统自动继续同一逻辑 Run

RUNNING
  |-- COMPLETED
  |-- FAILED
  `-- CANCELLED
```

核心规则：

1. `WAITING` 是正常、可恢复状态，不是 Error，也不是 Cancel。
2. 等待期间不保留活跃 Agent Task，不占用 Provider Lease、数据库事务或 LLM 流。
3. `InteractionEvent` 是等待内容的事实来源；`WaitEvent` 是本次 SSE/Task 暂停边界，不是对话终止事件。
4. Ask/Form 自动继续时使用持久化的 `action_id`、Lead 模式、步骤、Capability/Provider Scope 和原 Tool Call 身份，不重新让模型猜测暂停前状态。
5. 重复解决、过期 Action、错误决定和越权解决分别返回稳定的 Interaction 错误码，不生成新的 Agent Run。

### 对话输入路由

用户不需要执行“恢复对话”。每条新输入先经过 Interaction Router：

```text
new user input
  |-- pending ask_user   -> 作为 answer，自动继续逻辑 Run
  |-- pending form_input -> 作为 submit，自动继续逻辑 Run
  `-- no pending interaction -> 带已有上下文启动新 Run
```

如果用户明确表示放弃原问题并提出新任务，旧 Ask/Form 标记为 `superseded`，新消息正常进入 Lead。底层可以创建新的执行 Task，但这是调度实现，不是用户可见的会话恢复。

## 平台安全模型：用强制策略替代用户审批

### 为什么移除通用 Tool Approval

终端用户点击“批准”不是可靠的安全边界：用户通常无法判断 Shell 参数、重定向、网络请求或 MCP Tool 的真实影响，频繁弹窗只会形成机械点击。Agent 平台应在执行前自行证明该能力被允许，证明不了就拒绝执行。

对于 Web 产品，主要风险不是“Agent 直接入侵用户本机”，而是：

- Sandbox 逃逸或访问 API 宿主机、Docker Socket、内部网络。
- 一个租户读取或修改另一个租户的 Workspace、文件、Memory 或凭据。
- Prompt Injection 诱导 Agent 外传上传文件、会话数据或 Provider Credential。
- MCP/A2A/API 对用户连接的第三方账户产生删除、发布、转账、发信等外部副作用。
- Shell/Browser 无限执行造成 CPU、内存、进程、带宽和付费 API 成本失控。
- 持久化 Workspace 中的用户数据被误删；即使没有影响用户本机，也仍然是用户损失。

这些风险都不能靠逐次审批可靠解决，必须由服务端强制控制。

### 执行分类

| Execution Class | 示例 | 目标策略 |
| --- | --- | --- |
| `sandbox_local` | Shell、File、Sandbox Browser | 满足隔离基线后自动执行 |
| `external_read` | 搜索、只读 API、只读 MCP | 完成授权、SSRF/出口限制和租户校验后自动执行 |
| `external_write` | 发信、发布、删除第三方数据、写 API | 仅当 Provider 注册时获得明确 Capability Grant；调用时自动执行并审计、限流、幂等 |
| `platform_forbidden` | 宿主机管理、跨租户、内部控制面、未授权 Credential | 永久拒绝，不向用户弹审批 |

`risk_level` 可以保留用于日志、测试优先级和治理展示，但不再触发 `ask`。`ToolBinding.approval`、`require_approval_for_high_risk` 和 `approve/reject` 交互进入废弃流程，目标配置只保留确定性的 `allow/deny` 与 Capability Grant。

### Sandbox 最小隔离基线

“使用了 Docker 容器”不自动等于隔离已经成立。移除审批后的发布门禁至少需要自动验证：

- 每个用户/会话 Workspace 的租户绑定和路径边界，禁止跨 Sandbox 复用错误目录。
- 不挂载 Docker Socket、宿主机敏感目录或平台 Credential；Secret 不进入 Prompt、环境快照和 Tool Result。
- 非特权容器、最小 Linux Capability、`no-new-privileges`、进程数/CPU/内存/磁盘/执行时长限额。
- 对 API 宿主机、云 Metadata、私网和控制面的网络隔离；外网通过可审计 Egress Policy。
- Browser 下载、文件上传和持久化产物经过 Workspace 边界与内容限制。
- 任务取消、超时和服务关闭可以回收进程及容器，不遗留后台执行。

这不是要求本批重做 Sandbox，而是将上述验证作为“自动执行”的平台前置条件。当前代码已经有独立 Docker Sandbox 和 API Tool 的基础 SSRF 检查，但仍应通过配置与运行测试证明完整基线，而不能用用户审批弥补缺口。

### 外部 Provider 权限

MCP/A2A/API 不一定运行在 Sandbox 内，因此适用独立 Provider Policy：

1. Provider 注册/连接时声明可用 Capability、数据范围和外部副作用类型。
2. Credential 由服务端 Credential Broker 持有，按用户和 Provider 最小范围注入，不进入模型上下文。
3. 每次调用执行租户授权、目标/方法 allowlist、参数大小、速率和成本预算校验。
4. 写操作使用幂等键和审计事件；无法提供可靠边界的 Provider 标记为 `platform_forbidden`。
5. 这些校验失败直接返回确定性的 ToolResult，不请求终端用户批准。

## 当前实现分析

### 已有可复用能力

- `agentic/api/app/core/entities/event.py`：已有 `InteractionEvent`、`InteractionResolution`、`WaitEvent` 和 `InteractionType`。
- `agentic/api/app/core/entities/session.py`：已有追加式 pending/resolved 事件、一次性解决和 `SessionStatus.WAITING` 校验。
- `agentic/api/app/services/agent_service.py`：已有原子解决和创建新 Task 恢复的服务入口。
- `agentic/api/app/core/tools/registry.py`：已有不含参数 Schema 的 Capability Catalog。
- `agentic/api/app/core/tools/scope.py` 和 `filter.py`：已有按 Capability/Function 裁剪模型可见工具的基础能力。
- MCP Tool 名称已带 Server 前缀，可继续用于 Provider 级隔离和冲突避免。
- A2A 当前只向模型暴露固定的发现/调用函数，不需要为每个 Remote Agent 生成一个函数。

### 缺陷一：Provider 初始化早于 Lead 选择

`agentic/api/app/core/agent/agent_task_runner.py` 在每个 Task 开头执行：

```text
initialize all MCP
refresh dynamic MCP schemas
initialize all A2A / fetch all Agent Cards
read message
Lead decide capability
apply runtime scope
```

因此 Runtime Tool Scope 只减少了“模型看到什么”，没有减少“系统连接什么”。无关 Provider 的延迟和故障仍然进入每一个 Run。

### 缺陷二：MCP Catalog 依赖在线发现

MCP Schema 只有初始化后才通过 `refresh_mcp_tools()` 加入 Registry。若完全删除预初始化，Lead 又可能不知道 MCP 能力存在。需要把“配置目录”和“在线 Schema”拆成两个平面，不能继续用一次全量连接同时承担两种职责。

### 缺陷三：Provider 生命周期和 Run Task 绑定

MCP 使用 `AsyncExitStack` 和 AnyIO cancel scope，并要求初始化、调用和清理处于兼容的 Task 上下文。当前每个 Run 创建并销毁 Manager，既重复连接，又容易在 Task 切换/取消时触发生命周期错误。

### 缺陷四：取消来源丢失

Python 3.12 的 `asyncio.CancelledError` 继承 `BaseException`，MCP 多处 `except Exception` 无法捕获。异常到达 Runner 后又只有“任务取消”一条分支，无法判断它来自：

- 用户点击停止；
- 服务关闭；
- 父 Run 超时；
- 客户端/SSE 断开；
- MCP/AnyIO 内部 cancel scope；
- 代码错误导致的意外取消。

### 缺陷五：错误只有字符串

后端 `ErrorEvent` 只有 `error: str`，ToolResult 也只有 `success/message/data`；前端则对所有错误显示固定的模型故障文案。这会同时破坏：

- 用户判断是否值得重试；
- 前端选择“重试、继续、检查配置、重新授权”等操作；
- Lead 判断是否可换 Provider 或 Replan；
- Trace 按错误类型聚合告警。

### 缺陷六：Registry 丢失被等同于服务重启

当前订阅逻辑看到数据库仍为 `running`、但进程内 Task Registry 已无句柄，就直接生成“服务重启后运行上下文丢失”。本次故障中容器没有重启；真正原因是 Provider 异常被误判为取消，随后状态收尾又被取消打断。

进程内句柄缺失只能证明“当前进程无法继续这个 Run”，不能单独证明“服务重启”。

### 缺陷七：内置来源与 Sandbox 执行语义混合

当前内置目录将 File/Shell/Browser 标记为 `provider_id=builtin.*`、`executor_type=builtin`，再通过 `requires_sandbox/requires_browser` 补充真实依赖。`ToolFactory` 构造时又直接把 Sandbox/Browser 代理注入这些 Tool。现有 Lazy Runtime 已避免在构造时真正创建 Sandbox，但元数据仍混合了两个独立问题：

- Tool 从哪里定义和注册；
- Tool 最终在哪里执行、需要哪些运行资源。

如果继续把两者合并，统一工具平面会错误地把 Sandbox 当成 Tool Provider，路由层也无法准确比较“内置进程内 Search”“内置但 Sandbox 执行的 Shell”和“外部 MCP Tool”的成本、隔离与生命周期。

## 可选方案

### 方案 A：仅补异常捕获和前端文案

- 实现方式：在 MCP 初始化处捕获更多异常；修改固定的模型故障提示；其他生命周期不变。
- 优点：改动小，可快速降低当前错误的可见频率。
- 缺点：每个 Run 仍全量连接 MCP/A2A；无法避免无关 Provider 延迟；Cancel 来源仍模糊；多 Provider 隔离不完整。
- 风险：吞掉真正的用户取消或服务关闭，使资源无法及时释放；新传输库仍可能从其他边界泄漏 Cancel。
- 结论：只能作为紧急止血，不构成目标架构。

### 方案 B：进程内 Provider Runtime（推荐）

- 实现方式：拆分静态 Catalog、Tool Selection、Schema Resolver 和 Provider Runtime Pool。Lead 先选择 Provider；MCP 由 Provider Actor 惰性连接并复用，A2A Card 使用 TTL 快照和共享 HTTP Client；错误在 Provider 边界类型化。
- 优点：直接解决全量连接、全量注入、取消泄漏和错误误报；能复用现有 Registry、Runtime Scope、Lead/HITL；可渐进迁移。
- 缺点：需要新增 Provider 生命周期所有者、Scope 结构和错误契约；并发与清理测试要求较高。
- 风险：Actor/Pool 若没有引用计数、空闲回收和配置失效机制，会产生连接泄漏或使用旧 Schema。
- 结论：作为当前单体部署的最佳平衡方案。

### 方案 C：独立 Tool/Agent Gateway

- 实现方式：MCP/A2A 连接、发现、缓存、鉴权、熔断和调用全部放入独立服务；Agent API 只访问 Gateway。
- 优点：故障隔离、跨进程复用、水平扩展和统一治理最好。
- 缺点：引入新服务、网络跳数、部署和认证边界；当前项目尚未证明需要跨节点共享连接。
- 风险：过早平台化，把当前 P0 可靠性修复扩展成大型基础设施项目。
- 结论：保留为多实例规模化阶段，不作为首批实现。

## 方案对比

| 维度 | 方案 A | 方案 B（推荐） | 方案 C |
| --- | --- | --- | --- |
| 消除无关 Provider 连接 | 否 | 是 | 是 |
| Provider 级 Schema 注入 | 否 | 是 | 是 |
| Cancel 故障隔离 | 部分 | 是 | 是 |
| 同进程连接复用 | 否 | 是 | 是 |
| 跨进程连接复用 | 否 | 否 | 是 |
| 兼容现有 Lead/Registry/HITL | 高 | 高 | 中 |
| 实施复杂度 | 低 | 中高 | 高 |
| 部署复杂度 | 低 | 低 | 高 |
| 当前收益/成本 | 低 | 最高 | 中 |

## Sandbox 定位方案

### 方案 S1：把 Sandbox 当成 Tool Provider

- 表面上可与 MCP/API 使用相同 Provider 接口。
- 但 Sandbox 本身不提供业务能力，Shell/File/Browser 才是模型可选择的 Tool；把资源容器包装成 Provider 会混淆发现、选择和执行生命周期。
- 结论：不采用。

### 方案 S2：Sandbox 作为 Execution Backend 和按需资源（推荐）

- Tool 仍按来源注册，例如 `builtin.shell`、`builtin.file`；Descriptor 独立声明 `execution_backend=sandbox` 或 `sandbox_browser`。
- Catalog、Tool Selection 和 Schema Injection 只处理静态元数据，不启动 Sandbox。
- Executor Router 在真实 Tool Call 通过 Scope/Policy 校验后，才向 `SandboxRuntime` 取得 Lease；现有 `LazySandboxRuntime` 作为首版实现。
- 结论：既统一上下文工具管理，又保留 Sandbox 专属的创建、恢复、附件同步、配额、超时和回收语义。

### 方案 S3：只暴露一个万能 Sandbox Tool

- 模型通过一个宽泛 Tool 自行决定命令、文件和浏览器动作，看似工具数量最少。
- 参数边界、最小权限、结果展示、Trace 和策略判断都会退化，且更容易把简单任务路由到 Shell。
- 结论：不采用；保留结构化 Shell/File/Browser Tool，通用 Shell/Python 仅作为必要时的通用执行后备。

这里需要严格区分：

- **晚激活**：Sandbox-backed Tool 永远在真实调用前一刻才创建/恢复环境，这是资源策略。
- **最后手段**：通用 Shell/Python/Browser Script 只在没有更合适的专用能力、专用能力失败可降级，或用户明确要求时选择，这是路由策略。

因此 Sandbox 可以称为 Agent 的“通用执行底座”，但不能整体设置成固定最后一级。对于“运行 Python 分析文件”“修改项目代码”“操作网页”这类任务，它本来就是匹配度最高的执行后端，应直接选择；对于“今天几号”“解释一个概念”“调用已有天气 API”，则不应选择或激活 Sandbox。

## 推荐架构

```text
LeadAgent
  |-- Decide: direct / react / plan
  |     `-- Unified Tool Catalog（纯元数据，无网络 I/O、无 Tool 参数 Schema）
  |
  `-- Execute React / Plan Step
        |-- ToolScopeSelection
        |     |-- capability_groups
        |     |-- provider_ids
        |     `-- tool_ids / exact_functions
        |
        |-- ToolSchemaResolver
        |     `-- 只返回当前 Step 所选 Tool 的 Schema
        |
        `-- ToolExecutorRouter（执行前再次校验 Scope/Policy）
              |-- InProcessExecutor
              |     `-- Message / 本地纯函数能力
              |-- SandboxExecutor
              |     `-- LazySandboxRuntime -> Shell / File
              |-- SandboxBrowserExecutor
              |     `-- LazySandboxRuntime -> Browser
              |-- ExternalProviderRuntime
              |     |-- API Executor
              |     `-- MCPProviderPool
              |           `-- MCPProviderActor × N
              `-- DelegationRuntime
                    `-- A2AProviderPool -> Agent Card Snapshot/TTL
```

架构位置说明：

- MCP 位于 Tool 执行层，是外部 Tool Provider。
- A2A 位于委派执行层，是远程 Agent Provider；它不是 Lead 内部 Planner，也不是本地 Sub Agent Scheduler。
- Sandbox 位于执行资源层，不进入 Provider 选择；Lead 选择的是 Shell/File/Browser 等能力，Executor Router 再根据 Tool Descriptor 取得 Sandbox。
- `source_type`、`execution_backend` 和 `resource_requirements` 是三个正交字段，不能再由一个 `executor_type=builtin` 代替。
- 未来本地 Sub Agent 可以和 A2A 共用 `DelegationTargetCatalog`，但本地进程/上下文/权限仍由独立的 Sub Agent Runtime 管理。
- Lead 只负责选择和协调，不持有远端连接。

## 两平面设计

### 1. Catalog Plane

Catalog 在应用配置加载/更新时构建，不发起远程连接，也不创建/恢复 Sandbox。内部和外部能力都先归一化为 ProviderDescriptor + ToolDescriptor；Lead 只读取安全摘要，Schema Resolver 才读取具体 Schema。目录内容包括：

- `provider_id`：稳定、命名空间化，例如 `mcp.github`、`a2a.researcher`。
- `provider_type`：`builtin / mcp / a2a / api`。
- `label / description`：安全、紧凑的用途摘要。
- `capability_groups / semantic_tags`：供 Lead 选择。
- `enabled`、授权是否已配置、是否存在 Schema/Card 快照。
- 最近健康状态的低基数字段，不含原始 URL、Header、Env 和异常文本。
- `tool_id / source_type / execution_backend / resource_requirements`：区分能力来源、执行位置和资源依赖。
- `generality / cost_class`：帮助 Lead 优先匹配专用能力，并识别 Shell/Python 等通用执行后备；它们只影响选择，不是安全授权。

MCP 的 Config `description` 可直接作为首个静态摘要；A2A 首次没有 Agent Card 时使用配置 ID/管理员标签，Card 获取成功后更新安全快照。

### 2. Runtime Plane

Runtime 只在某个 Step 选择 Tool 后工作：

1. 校验 Tool 已启用，属于允许的 Capability、Provider 和 Tool Scope。
2. 解析所选 Tool 的 Schema；外部动态 Tool 没有快照时，仅激活被选 Provider 完成发现。内部静态 Tool 不需要运行资源。
3. 将通过 ToolConfig/平台 Policy 的 Schema 注入当前模型调用；此步骤仍不得取得 Sandbox Lease。
4. Runtime Scope 按 `capability + provider + tool_id/function` 三层过滤。
5. 模型发起 Tool Call 后，Executor Router 再次校验 Scope/Policy，并根据 `execution_backend` 路由。
6. `sandbox/sandbox_browser` 后端此时才取得 Sandbox Lease；`external_provider/delegation` 后端才取得 Provider Handle；`remote_http` 使用受平台出口策略约束的 HTTP Executor。
7. 调用结束释放 Lease；Sandbox 是否保留到 Session TTL、Provider Actor 是否保留到 idle TTL，分别由各自 Runtime 管理。

## 筛选与注入规则

筛选顺序必须固定，后层不能绕过前层：

| 顺序 | 过滤器 | 作用 |
| --- | --- | --- |
| 1 | 配置与权限 | 去除 disabled、未授权、执行器类型不允许的 Provider/Tool |
| 2 | Capability | Lead 选择完成任务所需的最小能力组 |
| 3 | Provider | 在能力组中选择具体 MCP Server 或 A2A Target |
| 4 | 健康与熔断 | 去除处于短期 open circuit 的非强制 Provider |
| 5 | ToolConfig Binding | 应用 allow/deny、Execution Class、Capability Grant 和租户权限规则 |
| 6 | Exact Function | Ask/Form 继续时恢复原 Tool Call；普通 Step 可为空 |
| 7 | Schema 注入预算 | 限制工具数量/Token，必要时二阶段 Tool Search |
| 8 | 执行前 Scope/Policy | 防止模型或历史 Tool Call 绕过选择结果；通过后才能取得 Sandbox/Provider Lease |

Lead Decision/Plan Step 不再只有 `capabilities`，而是逐步兼容为：

```json
{
  "capability_groups": ["mcp"],
  "provider_ids": ["mcp.github"],
  "tool_ids": ["mcp.github.search_issues"],
  "exact_functions": []
}
```

兼容期继续接受旧 `capabilities`，并映射到 `capability_groups`。若只选择了粗粒度 `mcp` 而未指定 Provider：

- 用户明确点名 Provider 时，确定性匹配，不增加模型调用。
- 只有一个合格 Provider 时，确定性选择。
- 多个候选时，使用 Catalog 的标签/描述/语义标签做轻量选择；仍不连接 Provider。
- 不能可靠选择时，Lead 询问用户，或返回可行动的能力缺失信息；不得默认激活全部 Provider。

当某个 Provider 工具过多时，不能把全部 Schema 注入 React：

1. 先注入一个通用的 Provider Tool Search/Describe 接口，或使用本地 Schema 索引检索。
2. 根据目标选出 Top-K 函数。
3. 下一次模型调用只注入 Top-K Schema。

首期可设置较小的 Provider/Tool 上限，超限时进入二阶段检索，不做静默截断。

### Sandbox-backed Tool 路由规则

Sandbox 不单独出现在 `provider_ids` 中，也不存在让 Lead 选择“是否使用 Sandbox”的额外步骤。Lead 选择具体 Tool，系统根据 Descriptor 确定执行后端：

| 任务意图 | 首选 | Sandbox 策略 |
| --- | --- | --- |
| 无需外部事实的解释、改写、闲聊 | `direct` | 不选择、不激活 |
| 已有专用 API/MCP/Search 能准确完成 | 专用 Tool | 通常不注入通用 Shell；专用能力可恢复失败时才 Replan |
| 明确要求运行代码、计算、操作项目或处理 Sandbox 文件 | Shell/File 等结构化 Tool | 可直接选择，但仍只在真实调用时激活 |
| 需要网页交互而非仅搜索结果 | Browser Tool | 可直接选择 Sandbox Browser；不先做无意义 Shell 绕行 |
| 专用能力缺失或返回可降级错误 | 通用 Shell/Python/Browser Script | Lead/ReAct 记录 `fallback_reason` 后升级一次，受步数与成本预算限制 |

“优先专用能力”由 Tool 的 `generality`、任务匹配度和成本共同决定，不能仅按内部/外部排序。外部 Tool 不天然优于 Sandbox，Sandbox 也不天然比外部 Tool 更可靠。

## MCP Provider 生命周期

### 为什么采用 Provider Actor

MCP SDK 的传输上下文和 AnyIO cancel scope 对 Task 所有权敏感。直接把一个 `AsyncExitStack` 从 Run A 复用到 Run B，再在应用关闭 Task 中清理，会再次触发跨 Task 退出问题。

推荐每个 MCP Server 使用一个长生命周期 Actor Task：

- Actor 自己创建、使用和关闭传输上下文。
- Agent Run 通过请求队列/Future 调用 Actor，不直接进入其 cancel scope。
- 某个 Actor 因 Provider 内部 Cancel/协议错误退出时，Pool 只把该 Provider 的在途请求完成为类型化失败；父 Run Task 不被取消。
- 配置变更、空闲超时和应用关闭通过 Actor 控制消息完成有序清理。
- 每个 Provider 独立 Actor，一个 Server 失败不关闭其他 Server。

Actor 状态：

```text
DISCONNECTED -> CONNECTING -> READY
      ^              |          |
      |              v          v
      `---------- DEGRADED <- UNHEALTHY
                         |
                         `-> CLOSING -> CLOSED
```

同一 Provider 的首次并发请求共享一个连接尝试，避免连接风暴。连接失败进入带退避的 `DEGRADED`，而不是每个 Tool Call 立即重连。

### Schema 快照

- Key：`provider_id + config_fingerprint + protocol_version`。
- 内容：安全 Tool Schema、发现时间、版本/etag（若有）、过期时间。
- 不存：Credential、Header、Env、用户参数、Tool Result。
- 进程内缓存为首期必需；持久化快照可作为后续优化，避免应用重启后的首次发现延迟。
- 有未过期快照时可以先完成 Schema 注入，实际 Tool Call 再惰性连接；若调用失败，返回可恢复的 Provider ToolResult。
- 配置指纹变化立即使旧连接和快照失效。

## A2A Provider 生命周期

A2A 不需要为每个 Run 连接全部 Agent：

- `get_remote_agent_cards` 和 `call_remote_agent` 的函数 Schema 是本地静态资产，可在选择 `a2a` 后直接注入。
- Agent Card 是 Provider 元数据，使用 TTL 快照；后台刷新或首次选中时刷新，不在每次 Run 开头全量请求。
- 用户/Lead 已指定 Agent ID 时，只解析该目标；只有真正执行“列出可用 Agent”时才并发刷新启用目标，并对每个目标独立超时和降级。
- A2A HTTP Client 由应用生命周期共享，调用通过 Provider ID 隔离日志、超时、认证和熔断。
- 某个 A2A Agent 不可用时，其他 Agent Card 和调用保持可用。

## 数据结构

### ToolDescriptor

| 字段 | 类型 | 必填 | 说明 | 约束/默认值 |
| --- | --- | --- | --- | --- |
| `tool_id` | `str` | 是 | 稳定、命名空间化 Tool ID | 与函数显示名分离 |
| `provider_id` | `str` | 是 | 能力来源 | 内置示例 `builtin.shell` |
| `source_type` | enum | 是 | `builtin/api/mcp/a2a` | 不决定执行后端 |
| `capability_groups` | `list[str]` | 是 | Lead 选择的粗粒度能力 | 至少一个 |
| `execution_backend` | enum | 是 | `in_process/sandbox/sandbox_browser/remote_http/external_provider/delegation` | Executor Router 的稳定输入 |
| `resource_requirements` | `list[enum]` | 否 | `sandbox/browser/network/credentials` | 不能隐式推导授权 |
| `execution_class` | enum | 是 | `sandbox_local/external_read/external_write/delegation` | 平台 Policy 输入 |
| `generality` | enum | 是 | `specialized/general_fallback` | 只影响路由偏好 |
| `cost_class` | enum | 是 | `low/medium/high` | 综合启动、网络和付费成本 |
| `schema_ref` | `str` | 是 | 静态 Schema 或 Provider Snapshot 引用 | Catalog 不展开 Schema |
| `enabled` | `bool` | 是 | 是否允许进入候选集 | 默认 `true` |

`source_type` 与 `execution_backend` 的典型映射：

| Tool | `source_type` | `execution_backend` | `generality` |
| --- | --- | --- | --- |
| `message_ask_user` | `builtin` | `in_process` | `specialized` |
| `search_web` | `builtin` | `remote_http` | `specialized` |
| `read_file` | `builtin` | `sandbox` | `specialized` |
| `shell_execute` | `builtin` | `sandbox` | `general_fallback` |
| `browser_navigate` | `builtin` | `sandbox_browser` | `specialized` |
| `browser_console_exec` | `builtin` | `sandbox_browser` | `general_fallback` |
| MCP Tool | `mcp` | `external_provider` | 默认 `specialized` |
| `call_remote_agent` | `a2a` | `delegation` | `specialized` |

### ProviderDescriptor

| 字段 | 类型 | 必填 | 说明 | 约束/默认值 |
| --- | --- | --- | --- | --- |
| `provider_id` | `str` | 是 | 稳定 Provider ID | 命名空间化且不可含凭据 |
| `provider_type` | enum | 是 | `builtin/mcp/a2a/api` | 稳定枚举 |
| `label` | `str` | 是 | 用户/Lead 可见名称 | 安全摘要 |
| `description` | `str` | 否 | 用途描述 | 长度受限 |
| `capability_groups` | `list[str]` | 是 | 所属能力组 | 至少一个 |
| `semantic_tags` | `list[str]` | 否 | 轻量选择标签 | 去重、长度受限 |
| `enabled` | `bool` | 是 | 配置是否启用 | 默认 `true` |
| `credential_state` | enum | 是 | `not_required/configured/missing` | 不返回凭据本身 |
| `snapshot_state` | enum | 是 | `missing/fresh/stale` | 仅目录状态 |
| `health_state` | enum | 是 | `unknown/healthy/degraded/unhealthy` | 不进入错误原文 |

### ToolScopeSelection

| 字段 | 类型 | 必填 | 说明 | 约束/默认值 |
| --- | --- | --- | --- | --- |
| `capability_groups` | `list[str]` | 是 | 粗粒度能力 | 旧 `capabilities` 映射至此 |
| `provider_ids` | `list[str]` | 否 | 具体 Provider | 必须属于所选 Capability |
| `tool_ids` | `list[str]` | 否 | 当前 Step 选中的稳定 Tool ID | 必须属于所选 Provider/Capability |
| `exact_functions` | `list[str]` | 否 | 精确函数白名单 | Ask/Form 自动继续时保留原函数 |
| `selection_reason` | enum | 否 | `explicit/single_match/semantic/resume` | 仅 Trace 使用 |

### FailureInfo

`FailureInfo` 同时供 `ErrorEvent`、失败的 `ToolResult` 和内部 Trace 投影使用；SSE 只投影安全字段。

| 字段 | 类型 | 必填 | 说明 | 约束/默认值 |
| --- | --- | --- | --- | --- |
| `code` | `str` | 是 | 稳定机器错误码 | 不直接使用异常类名 |
| `category` | enum | 是 | `model/provider/tool/runtime/interaction/config` | 稳定枚举 |
| `scope` | enum | 是 | `operation/step/run` | 决定是否终止 Run |
| `source` | `str` | 是 | `lead/llm/mcp/a2a/tool/runtime` | 低基数 |
| `message` | `str` | 是 | 用户安全提示 | 不含 Secret/URL/Stack |
| `retryable` | `bool` | 是 | 相同输入重试是否合理 | 确定性定义 |
| `recovery_actions` | `list[enum]` | 否 | 前端可显示的动作 | 受白名单控制 |
| `provider_id` | `str` | 否 | 失败 Provider | 安全 ID |
| `tool_call_id` | `str` | 否 | 关联 Tool Call | 可选 |
| `debug_id` | `str` | 是 | 查询内部日志/Trace | 不暴露内部细节 |

### ErrorEvent V2

```python
class ErrorEvent(BaseEvent):
    type: Literal["error"] = "error"
    error: str = ""                  # 兼容旧客户端，等于 failure.message
    failure: FailureInfo | None = None
```

旧前端继续读取 `error`；新前端优先读取 `failure`，再按 `code/recovery_actions` 渲染。不能把原始 Exception `str(e)` 直接写入 SSE。

### ToolResult V2

```python
class ToolResult(BaseModel):
    success: bool
    message: str | None = None
    data: Any | None = None
    failure: FailureInfo | None = None
```

Provider/Tool 的可恢复失败优先返回 `ToolResult(success=False)`，交给 React 或 Plan Step 决定换工具、换 Provider 或 Replan；只有目标无法继续时才升级为 Run 级 `ErrorEvent`。

### WaitEvent V2

```python
class WaitEvent(BaseEvent):
    type: Literal["wait"] = "wait"
    reason: Literal["human_input"] = "human_input"
    action_id: str | None = None
    interaction_type: InteractionType | None = None
```

字段为可选以兼容旧事件；等待详情仍以相邻 `InteractionEvent` 为权威来源。

## 错误码基线

| Code | Scope | Retryable | 默认处理 |
| --- | --- | --- | --- |
| `MODEL_UNAVAILABLE` | run | 是 | 提示稍后重试，不伪装成 Provider 错误 |
| `MODEL_AUTH_FAILED` | run | 否 | 检查模型配置/授权 |
| `MODEL_RATE_LIMITED` | run | 是 | 按 Retry-After 重试 |
| `MODEL_CONTEXT_LIMIT` | run | 否/可压缩后重试 | 建议新对话或压缩上下文 |
| `MODEL_RESPONSE_INVALID` | operation/step | 是 | 有限纠正重试或 Replan |
| `PROVIDER_CONNECT_FAILED` | operation/step | 是 | 标记 Provider degraded，换 Provider 或重试 |
| `PROVIDER_AUTH_FAILED` | operation/step | 否 | 请求重新授权/配置 |
| `PROVIDER_TIMEOUT` | operation/step | 是 | 熔断计数，允许替代 Provider |
| `PROVIDER_PROTOCOL_ERROR` | operation/step | 视情况 | 隔离该 Provider，不取消父 Run |
| `MCP_SCHEMA_DISCOVERY_FAILED` | step | 是 | 使用有效旧快照或换 Provider |
| `A2A_CARD_DISCOVERY_FAILED` | operation | 是 | 使用有效旧快照或跳过目标 |
| `TOOL_NOT_FOUND` | operation/step | 否 | 刷新 Schema 或让 Lead 重新选择 |
| `TOOL_EXECUTION_FAILED` | operation/step | 视 Tool | 返回模型/Step，不自动终止 Run |
| `INTERACTION_NOT_FOUND` | operation | 否 | 404，不启动 Run |
| `INTERACTION_ALREADY_RESOLVED` | operation | 否 | 409，不重复执行 Tool |
| `INTERACTION_INVALID_RESPONSE` | operation | 否 | 422，保留 WAITING |
| `RUN_CANCELLED_BY_USER` | run | 否 | 正常停止，不显示模型故障 |
| `RUN_CANCELLED_BY_SHUTDOWN` | run | 视恢复能力 | 标记中断/可恢复 |
| `RUN_CONTEXT_LOST` | run | 视副作用 | 明确上下文丢失，不声称原因一定是重启 |
| `RUN_INTERNAL_ERROR` | run | 视情况 | 通用安全提示 + debug_id |

## 取消与异常传播规则

1. 所有主动取消都必须先写入 `RunCancellationContext(reason, requested_by, requested_at)`，再调用底层 `task.cancel()`。
2. Runner 收到 `CancelledError` 时，只能依据 Cancellation Context 判定为用户停止或服务关闭，不能依据异常类型猜测来源。
3. MCP Provider Actor 的失败由 Actor 结束回调转换为 `PROVIDER_PROTOCOL_ERROR` 或 `PROVIDER_CONNECT_FAILED`，并完成其请求 Future；不得向等待它的 Agent Task 传播裸 `CancelledError`。
4. Provider Adapter 可以捕获 `BaseException` 做资源收尾和错误转换，但遇到已记录的 Actor Shutdown 必须重新传播/完成关闭，不能吞掉真正停机取消。
5. 一个 Provider 失败只改变自身健康状态；禁止调用全局 `cancel()`、关闭共享 Task Group 或清理其他 Provider。
6. Run 状态、终止事件和 Trace 结果由幂等 `RunFinalizer` 在新的取消中立上下文中提交，避免已取消协程中的 UoW 再次被取消。
7. SSE 客户端断开不等于 Agent Run 取消。若产品选择“断开即停”，必须显式发出对应 Cancellation Context。

## 接口设计

### UnifiedToolCatalog.list_for_lead

```python
def list_for_lead(
    tool_config: ToolConfig,
    user_context: UserContext,
) -> LeadToolCatalog:
    ...
```

- 只读、无网络 I/O。
- 应用配置、用户权限和 Credential 状态过滤后返回。
- 返回 Provider 摘要和 Tool 能力摘要，不返回 URL、Headers、Env、Tool 参数 Schema 和原始健康错误。
- 内置、API、MCP、A2A 使用同一个 Catalog 接口；实现可以由不同 Adapter 提供描述符。

### ToolSelectionPolicy.resolve

```python
def resolve(
    requested: ToolScopeSelection,
    catalog: LeadToolCatalog,
) -> ResolvedToolScope:
    ...
```

- 确定性校验未知 Capability/Provider/Tool、禁用 Provider/Tool 和越权选择。
- 旧 `capabilities` 自动迁移。
- Ask/Form 自动继续使用持久化 Provider/Function，不重新做语义选择。

### ProviderRuntime.acquire

```python
async def acquire(
    provider_id: str,
    *,
    purpose: Literal["schema", "invoke"],
) -> ProviderLease:
    ...
```

- 首次并发激活去重。
- 返回的 Lease 不暴露底层 Session。
- 连接失败抛出类型化 `ProviderRuntimeError`，其中包含安全 FailureInfo。
- MCP Actor 保证连接与清理由同一所有者 Task 执行。

### ToolExecutorRouter.invoke

```python
async def invoke(
    tool_call: ToolCall,
    scope: ResolvedToolScope,
    context: ExecutionContext,
) -> ToolResult:
    ...
```

- 先根据不可扩大的 Scope Snapshot 和平台 Policy 重新校验 `tool_id`，失败时不得取得任何运行资源。
- 根据 ToolDescriptor.execution_backend 路由到进程内、Sandbox、Sandbox Browser、外部 Provider 或 Delegation Executor。
- 只有 Sandbox Executor 可以取得 Sandbox Lease；Catalog、Selector、Schema Resolver 和外部 Provider Adapter 均不得依赖 Sandbox 对象。
- 所有 Executor 返回统一 ToolResult/FailureInfo，并记录 `tool_id/provider_id/source_type/execution_backend`。

### SandboxRuntime.acquire

```python
async def acquire(
    session_id: str,
    *,
    requirement: Literal["sandbox", "sandbox_browser"],
    tool_id: str,
) -> SandboxLease:
    ...
```

- 首版适配现有 `LazySandboxRuntime.get_sandbox/get_browser`，不要求立即重写底层容器实现。
- 并发首次激活只能创建一个实例；激活失败不写入无效 handle，并允许按错误策略重试。
- Lease 记录首次触发 Tool、启动耗时、附件同步量和资源预算；不把命令、文件内容或 Secret 写入低权限 Trace。

### ToolSchemaResolver.resolve

```python
async def resolve(
    scope: ResolvedToolScope,
    *,
    max_tools: int,
    max_schema_tokens: int,
) -> ResolvedToolSchemas:
    ...
```

- 只返回选中 Tool 的 Schema；静态内置 Schema 不需要取得 Sandbox Lease，动态外部 Schema 只允许连接已选 Provider。
- 返回快照版本、被过滤数量和降级 Provider，供 Trace 使用。
- 超预算返回明确的二阶段检索要求，不静默注入全量 Schema。

### Interaction input

普通用户消息先经过 Interaction Router。现有 `/sessions/{session_id}/interactions/{action_id}/resolve` 可继续作为 Ask/Form 卡片的结构化提交接口，并对 `form_input` 增加 `values`；用户直接在 Composer 回答 Ask 时使用相同的领域命令自动解决 pending Action。

旧 `tool_approval` 事件仅用于读取迁移状态；公共解决接口不再接受 approve/reject。历史 pending 审批在用户后续普通消息领取新 Run 时自动收敛为“未执行”，随后进入正常 Lead Run。

## 前端错误呈现

前端不再使用统一的“模型服务暂时不可用”：

| Category/Code | 默认标题 | 主要动作 |
| --- | --- | --- |
| Model unavailable/rate limit | 模型服务暂时不可用 | 重试 |
| Provider connect/timeout | 外部工具服务暂时不可用 | 重试、换工具或检查连接 |
| Provider auth | 外部工具需要重新授权 | 前往配置 |
| Tool execution | 工具执行未完成 | 继续、重试或查看步骤 |
| User cancel | 已停止本次执行 | 重新生成 |
| Context lost | 本次运行上下文已丢失 | 从当前结果继续、重新执行 |
| Internal | 本次回复未完成 | 重试并显示 debug_id |

前端只展示后端提供的安全 `message` 和白名单恢复动作；不得展示原始堆栈、Provider URL、Header 或凭据。

## 可观测性

建议 Trace 事件：

- `tool.scope_selected`：capability_count、provider_count、tool_count、selection_reason、fallback_reason。
- `tool.execution_started/completed/failed`：tool_id、provider_id、source_type、execution_backend、lease_reused、error_code。
- `sandbox.activation_started/completed/failed`：first_tool_id、latency_ms、attachment_sync_bytes；Catalog/Schema 阶段若出现该事件应告警。
- `provider.activation_started/completed/failed`：provider_type、latency_ms、snapshot_hit、error_code。
- `provider.circuit_opened/closed`：provider_id、error_code、cooldown_ms。
- `tool.schema_resolved`：provider_count、schema_count、schema_tokens、filtered_count、snapshot_age_ms。
- `run.cancellation_requested`：reason、requested_by；禁止只记录 `CancelledError`。
- `run.finalized`：outcome、error_code、finalizer_source。
- `interaction.waiting/resolved`：interaction_type、wait_duration_ms；不记录用户敏感回答原文。

指标：

- `provider_activation_total{type,outcome}`
- `provider_activation_latency_ms{type}`
- `provider_schema_snapshot_hit_ratio{type}`
- `provider_failure_total{type,code}`
- `provider_cancel_leak_total`，目标恒为 0
- `tool_schema_injected_count{mode}`
- `tool_schema_injected_tokens{mode}`
- `run_terminal_total{outcome,code}`
- `interaction_wait_duration_ms{type}`

日志和 Trace 使用 `provider_id/run_id/debug_id` 关联；原始异常仅进入受控服务端日志，并统一脱敏。

## 迁移策略

### 阶段 0：回归基线与紧急止血（P0）

1. 固定“Shell-only/Ask User 自动继续因无关 MCP 失败而取消”的回归测试。
2. 引入 FailureInfo 和错误码，前端停止把所有错误映射为模型不可用。
3. Provider 初始化失败不再进入 Runner 的通用取消分支。
4. 终止状态、ErrorEvent 和 Trace 通过幂等 Finalizer 原子收敛，避免 `running + registry missing` 二次误判。
5. 删除 `require_approval_for_high_risk` 及逐工具审批配置，新 Run 不再创建 `tool_approval`；Shell/File/Browser 在隔离门禁通过后自动执行。
6. 历史 pending Tool Approval 在下一次普通输入的原子领取路径中收敛为未执行，不执行旧调用；用户后续消息作为普通新输入处理。

该阶段可暂时仍按 Run 持有选中的 Provider，但必须停止全量初始化。

### 阶段 1A：统一 Tool Plane 与内置工具迁移（P0，已实施）

1. 新增统一 ToolDescriptor，拆分 `source_type`、`execution_backend`、`resource_requirements` 和 `execution_class`。
2. 扩展 Registry/FilteredTool/RuntimeToolScope，从 Capability 过滤升级为 Capability + Provider + Tool ID + Function。
3. 建立统一 ToolSchemaResolver、Context Injector 和 ToolExecutorRouter；模型可见范围与执行允许范围使用同一个不可扩大的 Scope Snapshot。
4. 先迁移 Message/Search/File/Shell/Browser：它们共用相同注册和注入流程，但分别路由到 In-process、Remote HTTP、Sandbox 和 Sandbox Browser Executor。
5. 复用现有 `LazySandboxRuntime`。Catalog、选择、Schema 解析和 Tool 构造均断言不会激活 Sandbox；只有通过 Scope/Policy 的真实调用可以取得 Lease。
6. 给 Shell/Browser Script 标记 `general_fallback`，但显式代码执行、项目操作和交互浏览任务允许直接选择，避免“固定最后一级”损害正确性。

### 阶段 1B：外部 Provider 接入统一 Tool Plane（P0，已实施）

1. 从 API/MCP/A2A 配置构建无网络 I/O 的 Provider/Tool 摘要目录。
2. 扩展 Lead Decision、Plan Step、Ask/Form Continuation 的 Provider/Tool Scope。
3. API/MCP/A2A 通过 Adapter 接入同一 Catalog、Schema Resolver、Context Injector、Result 和 Trace，不再拥有平行注入链路。
4. 删除 `AgentTaskRunner.invoke()` 的全量 MCP/A2A 初始化。

### 阶段 2：MCP Provider Actor 和 Schema Snapshot（P1，已实施）

1. 每个租户/配置代际的 MCP Server 使用独立 Actor，连接、Schema 发现、调用和清理由同一 asyncio Task 所有；Actor 提供连接去重、有界指数退避、操作超时和 idle TTL。
2. 只在选中 Provider 无可用快照时发现 Schema；Snapshot 按 `user_id + provider_id + config_fingerprint + protocol_version` 隔离，并使用 TTL、容量上限和配置切换失效。
3. Provider 调用使用 Pool/Actor Proxy，不向 Agent 暴露 ClientSession、AsyncExitStack 或 AnyIO cancel scope；Provider 内部 Cancel 被投影为类型化失败。
4. 应用关闭时先取消并等待 Run 退出，再关闭共享 Pool；单个 Runner/Sandbox 清理失败不会阻止其他 Runner、Provider Pool、数据库或 Redis 关闭。
5. `ErrorEvent` 与 `ToolResult` 新增兼容的 `FailureInfo`，前端按 Provider/Tool/Run 类别展示安全信息，不再把所有失败解释为模型配置、余额或网络问题。

### 阶段 3：A2A Card 惰性刷新和委派目录（P1，已实施）

1. 固定 A2A Tool Schema 与动态 Agent Card 分离；构造 Catalog、Runner 或 Tool 不创建 HTTP Client，也不发现 Card。
2. 应用级共享 HTTP Runtime 按 `user_id + target_id + config_fingerprint + negotiation_policy_version` 隔离；Card Snapshot、配置代际和刷新锁均有界。
3. 按 Target single-flight 刷新，支持平台 TTL 上限、`Cache-Control`、ETag/Last-Modified、304、stale-if-error、独立发现/调用超时和响应体上限。
4. 按 Agent Card 顺序选择现代 `JSONRPC` 或 `HTTP+JSON`，同时保留旧顶层 URL 与 `message/send` 请求兼容；Card 调用 URL限制 HTTP(S)、无 userinfo 且与配置发现源同源。
5. 模型只读取 `DelegationTargetDescriptor` 白名单摘要并明确标记 `untrusted_external`；单目标发现/调用失败投影为 A2A FailureInfo，不取消父 Run。
6. 为未来本地 Sub Agent/A2A 统一 Delegation Target 摘要，但保持执行 Runtime 分离；本阶段未实现本地多 Agent 编排、A2A streaming、认证或 JWS 验签。

### 阶段 4：多字段表单与完整错误 UX（P1/P2）

1. 若产品需要，新增 `form_input + input_schema + values`。
2. 前端按稳定错误码和 recovery_actions 展示操作。
3. 管理页展示 Provider 健康、最近错误码和测试连接，不暴露敏感配置。

### 与 Durable Solo Lead Runtime 的关系

`durable-solo-lead-runtime-plan.md` 当前为 `PLAN_READY`，范围更大。本文是其前置可靠性边界：先确保等待、Provider 和错误不会互相误判，再实施跨进程 Run Lease、Effect 对账和真正 Durable Continuation。两者不应并行改写同一状态收尾逻辑。

## 兼容与回滚

- `ErrorEvent.error` 保留；新增 `failure` 为可选字段，旧客户端继续工作。
- `WaitEvent` 新字段可选；旧事件仍可反序列化。
- 旧 `capabilities` 继续读取并映射；新 Run 写入 Provider Scope，旧 pending Ask/Form 没有 Provider 时根据原函数名前缀确定性继续。
- 历史 `tool_approval` 事件继续只读显示；新 Run 禁止写入。历史 pending 审批在下一条普通消息的领取事务中追加兼容的 `REJECT/RESOLVED` 事件、闭合 Memory，Session 回到可继续执行的状态。
- `ToolBinding.approval` 和 `require_approval_for_high_risk` 已从新 API、前端和写入模型删除；仅在 `tool_config_v1` 历史 JSON 反序列化时迁移，其中旧 `deny` 保留为 `execution_policy=deny`。
- 内部 `execution_policy` 不向终端用户开放写权限；`/tools/bindings` 对旧 `approval/approval_tools/require_approval_for_high_risk` 和内部 `execution_policy` 均返回 422，防止旧客户端假成功、静默放行或用户覆盖平台判定。
- Session 的 `waiting` 只表示等待 Ask/Form，不迁移历史已解决 InteractionEvent。
- Provider Runtime 置于 Feature Flag 下；回滚时可退回“只初始化本轮已选择 Provider”，但禁止回到“所有 Run 全量初始化”。
- Schema Snapshot 可直接丢弃并重新发现，不影响会话事实数据。
- 若 Actor 复用出现资源问题，可将 idle TTL 临时设为 0，退化为所选 Provider 的 Run 级连接，仍保持选择和错误隔离。

## 风险

| 风险 | 可能性 | 影响 | 缓解措施 | 验证方式 |
| --- | --- | --- | --- | --- |
| Actor 生命周期处理不当导致连接泄漏 | 中 | 高 | 单所有者 Task、idle TTL、关闭握手、资源计数 | 并发/取消/关闭压力测试 |
| 缓存旧 Schema 导致 Tool Call 不匹配 | 中 | 中高 | config fingerprint、TTL、Tool not found 时单次刷新 | Schema 变更集成测试 |
| Provider Catalog 描述不足导致选错 | 中 | 中 | 管理员标签、语义 tags、显式点名优先、无法确定时询问 | 多 Provider 路由任务集 |
| 把真实用户取消转换成 Provider Error | 低中 | 高 | Cancellation Context + Actor shutdown reason | 用户停止/停机/Provider cancel 三分测试 |
| Tool 数量仍导致 Prompt 膨胀 | 中 | 中高 | Top-K、Token Budget、二阶段 Tool Search | Schema Token 指标和上限测试 |
| 把 Sandbox 设为固定最后手段导致代码/文件任务绕路 | 中 | 中 | 区分晚激活与路由优先级；显式任务意图可直接选择 Sandbox-backed Tool | 代码执行、文件处理和浏览任务集 |
| Catalog/Schema 阶段意外激活 Sandbox | 中 | 中高 | Lease 只允许 Executor Router 获取；构造与解析阶段使用零激活断言 | Fake Runtime 调用计数测试 |
| 旧 Interaction 无 Provider Scope 无法恢复 | 低中 | 高 | 根据命名空间和历史 Tool Call 确定性推导 | 历史 waiting fixture 回归 |
| 错误码过细且不稳定 | 中 | 中 | 对外稳定小枚举，内部 cause 单独记录 | API 合同测试 |
| Registry Missing 仍被误报成重启 | 中 | 中 | P0 原子 Finalizer；后续持久化 Run Lease/Heartbeat | 进程存活但 Task 异常结束测试 |
| 移除审批后 Sandbox 隔离缺口直接暴露 | 中 | 高 | 最小隔离基线成为发布门禁；门禁失败则禁用对应执行类 | 容器逃逸面、租户隔离、资源和网络测试 |
| 外部写 Provider 被误当作 Sandbox 工具 | 中 | 高 | Provider 声明 execution_class；外部写需要 Capability Grant、幂等和审计 | MCP/API/A2A 授权与副作用测试 |

## 重要假设

- 当前主要部署仍是单 API 进程或每个实例独立 Provider Pool；暂不要求跨实例共享连接。
- MCP/A2A 配置在应用配置层可获得稳定 ID 和安全描述；凭据不会进入 Catalog。
- Lead 的 Provider 选择只使用摘要，不需要看到 Tool 参数 Schema。
- 当前 A2A 函数 Schema 可以保持静态，动态变化主要来自 Agent Card。
- Ask/Form 回答后系统自动继续逻辑 Run；底层可创建新执行 Task，不要求暂停前 Task 常驻，也不向用户暴露恢复操作。
- 新 Run 不使用终端用户审批作为安全边界；平台对不满足隔离或授权要求的工具直接 deny。
- 真正的跨进程自动恢复和有副作用 Tool 对账由 Durable Runtime 后续实现。

## 待决策项

无阻塞核心设计的待决策项。

实施计划中可按现有 Provider 数量确定两个可配置默认值：Schema Snapshot TTL 和单 Step Tool Schema Token Budget；它们不改变本文架构。

## 验收标准

- [x] 普通 Direct 问答、Shell-only、File-only 和 Ask User Run 的日志中没有 MCP/A2A 连接尝试。
- [x] 新 Run 不产生 `tool_approval`；Shell/File/Browser 在现有隔离门禁通过后自动执行，不出现批准弹窗。
- [x] `risk_level` 不再触发等待；当前平台 `execution_policy=allow|deny` 在工具调用前确定性执行。
- [ ] Execution Class 和 Capability Grant 在模型调用前确定性执行。
- [ ] 未满足 Sandbox 隔离基线或外部 Provider 权限的工具直接拒绝，不能通过用户点击绕过。
- [x] Lead Decide Prompt 只包含 Capability/Provider/Tool 安全摘要，不包含 Tool 参数 Schema、URL、Header 或凭据。
- [x] React/Plan Step 按已选 Capability、Provider 和 Tool 裁剪 Schema；缺少新字段的历史数据继续按 capability-only 兼容。
- [x] Tool Descriptor 明确区分来源和执行后端：`builtin.shell` 为 `source_type=builtin + execution_backend=sandbox`，不再用 `executor_type=builtin` 混合表达。
- [x] Direct、Catalog 构建、Lead 选择和 Schema 解析阶段的 Sandbox create/get/ensure/browser 调用数均为 0。
- [x] 只有通过当前 Scope/Policy 的真实 File/Shell/Browser Tool Call 才激活 Sandbox；未选 Tool 即使模型构造出调用也被 Executor Router 拒绝且不激活。
- [x] 路由契约优先选择最小专用 Tool；明确代码执行、文件操作或交互浏览任务可直接选择 Sandbox-backed Tool，不强制先失败一次。
- [x] 内置、API、MCP Tool 使用相同 Tool ID/Scope/Context Injection/Result/Trace 合同；A2A 共用目录和选择合同但走独立 Delegation Runtime。
- [x] 多轮对话和 Ask/Form 自动继续不重复全量初始化 Provider；有效连接/快照可复用。
- [x] 一个 MCP Server 连接失败时，父 Agent Task 不收到裸 `CancelledError`，其他 Provider 和无关 Tool 可继续运行。
- [x] 用户停止、服务关闭和 Provider cancel scope 产生可区分结果；客户端断开不取消已接受并启动的后台 Run/Continuation。
- [x] Provider 失败不会被前端显示为模型余额或模型配置错误。
- [x] `ErrorEvent.error` 兼容旧客户端；新客户端能按 `failure.code`、`retryable` 和 `recovery_actions` 渲染。
- [x] `ask_user` 只接受 answer；非法提交保留 Session `waiting`；历史 pending Tool Approval 被安全收敛且不执行旧调用。
- [x] Ask 等待期间没有活跃 Agent Task；刷新后 pending Ask 可见，Composer/问题卡回答均按同一 Action 原子领取并只自动继续一次。
- [ ] `form_input` 的持久化、刷新展示、结构化校验和自动继续仍待后续批次。
- [x] 旧 pending Interaction 和旧 Session 历史无需数据库迁移即可读取；旧 Tool Approval 只读且可安全收敛。
- [ ] Provider 激活失败后 Session/Run/Event/Trace 状态原子收敛，不产生虚假的“服务重启”结论。
- [x] 并发首次连接只建立一次；配置更新、idle timeout 和应用关闭均能无泄漏清理 Provider。
- [ ] 定向测试、Agent/Tool/HITL 全量回归、前端类型/组件测试和真实多轮场景通过后，才进入实施完成状态。
