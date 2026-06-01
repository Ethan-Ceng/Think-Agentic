# 企业级 Agent 平台设计文档

## 1. 背景与目标

当前系统已经具备通用 Agent 的基础形态：FastAPI 后端、Vue 前端、Planner + ReAct 执行流、Docker 沙箱、文件/Shell/浏览器/搜索工具、MCP 与 A2A 扩展、SSE 事件流和会话持久化。它适合作为 Demo、内部试用或单团队工具。

如果要打造成企业可用的 Agent 平台，仅有“能执行任务”还不够。企业场景更关注身份、权限、审计、安全隔离、数据治理、可靠性、可运维、成本控制、管理后台、合规和多团队协作。目标不是把一个 Agent 做得更聪明，而是把 Agent 放进可控、可审计、可扩展、可持续运维的企业系统里。

本文档给出当前系统缺口、目标架构、核心模块设计和分阶段落地方案。

## 2. 当前系统已有能力

当前 `api` 已具备以下能力：

1. 会话式 Agent 交互：通过 `/api/sessions/{id}/chat` 使用 SSE 返回消息、计划、步骤、工具调用、等待、错误和完成事件。
2. Planner + ReAct 流程：Planner 负责拆解任务和更新计划，ReAct 负责调用工具执行步骤并最终总结。
3. 工具体系：内置文件、Shell、浏览器、搜索、消息工具，并支持 MCP 工具和 A2A 远程 Agent。
4. 沙箱执行：通过 Docker 沙箱隔离 Shell、文件、浏览器操作。
5. 文件处理：用户附件可同步到沙箱，Agent 生成的文件可同步到对象存储。
6. 会话持久化：PostgreSQL 保存会话、事件、文件、记忆；Redis Stream 承载任务输入输出事件。
7. 基础设置页：前端已有设置弹窗，可管理模型配置、Agent 参数、MCP Server、A2A Agent。

这些能力是企业化的起点，但还缺少控制面、治理面和运维面。

## 3. 企业级主要缺口

### 3.1 身份、组织和权限

当前系统缺少完整的企业身份体系。企业用户通常需要：

- SSO 登录，支持 OIDC、OAuth2、SAML、LDAP/AD。
- 多租户或多组织隔离，至少支持企业、部门、项目空间。
- RBAC/ABAC 权限模型，控制谁能创建 Agent、运行工具、查看会话、管理密钥、调用模型。
- 服务账号和 API Key，用于系统集成和自动化任务。
- 用户组和角色继承，便于企业管理员批量授权。

缺少这些能力时，系统只能面向可信用户开放，无法满足企业多人协作和权限隔离要求。

### 3.2 工具权限和风险治理

当前内置工具对 Agent 来说基本是全量可用，Shell、文件、浏览器、MCP、A2A 都可能带来风险。企业级系统需要：

- 工具注册表，记录每个工具的来源、版本、能力、风险等级和负责人。
- 工具权限策略，例如某个部门只能使用搜索和文件读取，不能执行 Shell。
- 高风险操作审批，例如外网访问、下载文件、执行写操作、调用生产系统 API。
- 工具参数策略，例如限制 Shell 命令、文件路径、浏览器访问域名、MCP Server 范围。
- 工具调用审计，记录谁、何时、哪个 Agent、用什么参数、得到什么结果。
- MCP/A2A 服务准入机制，避免用户随意添加未知外部工具。

这部分是企业 Agent 的核心。没有工具治理，Agent 的能力越强，安全风险越高。

### 3.3 密钥和配置安全

当前配置主要落在 `config.yaml` 和环境变量中，其中存在明文密钥风险。企业化需要：

- Secret Manager，密钥加密存储，运行时按权限注入。
- 密钥分级和作用域，例如组织级、项目级、Agent 级、工具级。
- 密钥轮换、过期、撤销和访问审计。
- 配置变更历史和回滚。
- 前端隐藏敏感字段，后端避免把密钥写入日志、事件和错误响应。

密钥管理必须优先处理，否则无法进入生产环境。

### 3.4 数据治理与合规

企业数据可能包含客户资料、合同、代码、财务、人事、医疗或其他敏感信息。系统需要：

- 数据分类分级，例如公开、内部、机密、受监管。
- 文件和会话的保留策略、删除策略、导出策略。
- 敏感信息检测与脱敏，例如手机号、身份证、邮箱、密钥、客户名称。
- 按权限过滤知识库和附件，避免 Agent 检索到用户无权访问的数据。
- 会话、文件、工具结果、模型输入输出的审计和追踪。
- 合规支持，例如加密、数据驻留、访问记录、删除请求。

当前系统把事件和记忆放入 session JSONB，适合快速开发，但不适合长期合规治理。

### 3.5 任务可靠性和可恢复性

当前 `RedisStreamTask` 使用进程内 registry 管理运行中的任务。企业部署通常需要多副本、高可用和可恢复任务，因此需要：

- 独立 Worker 服务处理 Agent 任务，而不是依赖 API 进程内任务。
- 任务状态持久化，支持服务重启后恢复、取消或标记失败。
- 分布式队列，例如 Redis Streams Consumer Group、Celery、Arq、Temporal、Dramatiq。
- 幂等事件写入，避免 SSE 重连或任务重试造成重复消息。
- 明确的状态机，统一管理 session、task、flow、step、tool call 状态。
- 超时、重试、熔断、降级策略。

如果企业用户正在执行长任务，API 重启不应直接丢失任务上下文。

### 3.6 模型治理

当前 `OpenAILLM` 直接使用 OpenAI-compatible Chat Completions 接口。企业级系统通常需要模型网关：

- 多模型供应商管理，例如 OpenAI、Azure OpenAI、DeepSeek、Claude、本地模型。
- 模型路由和 fallback，例如按成本、延迟、任务类型、工具调用能力选择模型。
- 统一限流、超时、重试和熔断。
- Prompt 模板版本管理和灰度发布。
- 模型输入输出审计、脱敏和敏感内容拦截。
- Token、费用、延迟、成功率统计。
- 离线评测和线上质量监控。

模型不是一个静态配置项，而应该是企业平台中的受管资源。

### 3.7 可观测性和运维

当前日志可以定位部分问题，但企业运维需要完整观测面：

- Agent run trace：每次运行的模型调用、工具调用、耗时、token、错误。
- Metrics：成功率、失败率、平均耗时、任务队列长度、沙箱创建耗时、工具调用分布。
- Logs：结构化日志，带 tenant、user、session、task、trace id。
- Tracing：跨 API、Worker、Sandbox、LLM、MCP、A2A 的链路追踪。
- Replay：基于事件和输入重放一次 Agent 执行，用于调试。
- 告警：模型失败率升高、沙箱创建失败、队列堆积、费用异常、工具风险调用。

没有可观测性，企业场景很难定位 Agent 为什么失败、为什么变慢、为什么变贵。

### 3.8 管理后台

当前已有设置弹窗，但企业管理后台需要更完整的控制面：

- 用户、组织、角色、权限管理。
- Agent 模板和 Agent 实例管理。
- 工具市场、MCP/A2A 注册、审批、启停、权限分配。
- 模型供应商、模型路由、额度和成本管理。
- 密钥管理。
- 知识库和连接器管理。
- 沙箱资源池和运行策略管理。
- 审计日志、运行日志、异常告警。
- Prompt、策略、评测集和发布管理。

当前设置页更像个人配置面板，还不是企业管理员控制台。

## 4. 目标架构

建议将系统拆成控制面、执行面、数据面和观测面。

```text
┌────────────────────────────────────────────────────────────┐
│ Web / Admin Console                                        │
│ Chat UI, Agent Builder, Tool Registry, Audit, Settings     │
└──────────────────────────────┬─────────────────────────────┘
                               │
┌──────────────────────────────▼─────────────────────────────┐
│ API Gateway / BFF                                           │
│ Auth, Tenant Context, RBAC, Rate Limit, SSE/WebSocket       │
└───────────────┬──────────────────────────────┬─────────────┘
                │                              │
┌───────────────▼──────────────┐  ┌────────────▼──────────────┐
│ Control Plane                 │  │ Agent Runtime Plane        │
│ Users, Orgs, Agents, Tools,   │  │ Planner/ReAct, Workers,    │
│ Policies, Secrets, Configs    │  │ Task Queue, State Machine  │
└───────────────┬──────────────┘  └────────────┬──────────────┘
                │                              │
┌───────────────▼──────────────┐  ┌────────────▼──────────────┐
│ Integration Plane             │  │ Sandbox Plane              │
│ Model Gateway, MCP, A2A,       │  │ Docker/K8s Sandboxes,      │
│ Enterprise Connectors          │  │ Browser, Shell, File APIs  │
└───────────────┬──────────────┘  └────────────┬──────────────┘
                │                              │
┌───────────────▼──────────────────────────────▼─────────────┐
│ Data Plane                                                  │
│ Postgres, Redis/Queue, Object Storage, Vector DB, Audit Log │
└──────────────────────────────┬─────────────────────────────┘
                               │
┌──────────────────────────────▼─────────────────────────────┐
│ Observability                                               │
│ Metrics, Logs, Traces, Cost, Evaluation, Alerts             │
└────────────────────────────────────────────────────────────┘
```

### 4.1 控制面

控制面负责定义“谁可以做什么”。它管理组织、用户、角色、Agent、工具、策略、模型、密钥、知识库和发布版本。控制面输出运行时策略，Agent 执行前和工具调用前都要查询策略。

### 4.2 执行面

执行面负责实际运行任务。建议把当前 API 进程内 task 拆成独立 Worker。API 只负责接收请求、鉴权、写入任务、推送事件；Worker 从队列取任务并运行 Agent。

### 4.3 集成面

集成面负责外部系统接入，包括模型供应商、MCP Server、A2A Agent、企业知识库、企业 SaaS 和内部 API。所有外部调用都应走统一适配层，便于限流、审计、重试和策略控制。

### 4.4 数据面

数据面需要从“会话单表 JSONB”升级为更适合企业查询和治理的结构。会话、事件、任务、工具调用、模型调用、文件、审计日志应拆开存储。

### 4.5 观测面

观测面贯穿所有模块。每次 Agent 运行都应该有唯一 `run_id` 和 `trace_id`，所有模型调用、工具调用、文件操作、策略判断和审批流程都能串起来。

## 5. 核心模块设计

### 5.1 身份与租户模块

建议新增：

- `organizations`：企业或租户。
- `workspaces`：团队、部门或项目空间。
- `users`：用户。
- `groups`：用户组。
- `roles`：角色。
- `permissions`：权限点。
- `role_bindings`：角色绑定，支持组织级、空间级、Agent 级资源作用域。
- `service_accounts`：服务账号。
- `api_keys`：程序化访问凭证。

权限模型建议从 RBAC 起步，保留 ABAC 扩展字段。例如工具调用时可以判断：用户角色、资源归属、工具风险等级、数据分类、网络域名、审批状态。

### 5.2 Agent 管理模块

企业中 Agent 应该是可管理资源，而不是只有系统内置一个通用 Agent。建议新增：

- Agent 模板：定义名称、描述、系统 Prompt、默认模型、默认工具、知识库、策略。
- Agent 实例：基于模板创建，绑定到 workspace。
- Agent 版本：Prompt、工具、模型、策略变更都产生版本。
- 发布状态：draft、staging、published、deprecated。
- 运行权限：哪些用户或组可以使用该 Agent。

这样可以形成“财务分析 Agent”“客服知识库 Agent”“研发助手 Agent”“运营报表 Agent”等企业内部角色。

### 5.3 策略与审批模块

建议引入 Policy Engine。每次工具调用前执行策略判断：

```text
Agent 请求调用工具
        │
        ▼
Policy Engine
        │
        ├── allow：直接执行
        ├── deny：拒绝并返回原因
        └── require_approval：创建审批任务，等待人工确认
```

策略维度包括：

- 用户、角色、组织、workspace。
- Agent、Agent 版本、任务来源。
- 工具名称、工具风险等级、参数。
- 数据分类、文件来源、目标系统。
- 网络域名、命令类型、写操作/读操作。
- 时间、频率、预算和审批状态。

典型审批场景：

- 执行 Shell 写操作。
- 访问非白名单域名。
- 调用生产系统 MCP 工具。
- 导出或发送含敏感信息的文件。
- 单次任务预计成本超过阈值。

### 5.4 工具注册与治理模块

建议把工具分为四类：

1. 内置工具：file、shell、browser、search、message。
2. MCP 工具：由 MCP Server 动态提供。
3. A2A 工具：由远程 Agent 提供。
4. 企业连接器：例如飞书、钉钉、Jira、Confluence、GitLab、数据库、CRM、ERP。

工具注册表应记录：

- 工具来源、协议、版本、描述。
- 输入输出 schema。
- 风险等级：low、medium、high、critical。
- 是否允许默认启用。
- 可见范围：全局、组织、workspace。
- 所需密钥和权限。
- 超时、重试、限流、并发限制。
- 审计策略和审批策略。

当前管理页已有 MCP/A2A 的添加、删除、启停能力，但缺少工具级别的权限、风险等级、审批和运行统计。

### 5.5 密钥管理模块

企业级实现中，`config.yaml` 只能保存非敏感配置。密钥应进入 Secret Manager。

建议设计：

- 后端存储只保存加密密文或外部 secret 引用。
- 每个 secret 有 owner、scope、version、created_at、rotated_at。
- Agent 运行时按策略解密或拉取 secret，注入到对应工具。
- 前端永远不回显完整 secret。
- 所有读取 secret 的行为写入审计日志。

可先用数据库加密字段实现，后续再接 Vault、云厂商 KMS 或 Kubernetes Secret。

### 5.6 模型网关模块

新增 `ModelGateway`，替代业务代码直接实例化 `OpenAILLM`。

能力包括：

- 多供应商配置。
- 模型能力声明：是否支持 tool call、JSON mode、多模态、长上下文。
- 路由策略：按 Agent、任务类型、用户组、成本预算路由。
- Fallback：主模型失败后自动切换备用模型。
- 请求审计：记录 prompt hash、token、耗时、费用、错误。
- 内容安全：输入输出脱敏、敏感内容检测、违规阻断。
- Prompt 模板版本化。

后续可支持企业内网模型和云模型混合部署。

### 5.7 任务和状态机模块

建议把任务运行重构为显式状态机：

```text
created -> queued -> running -> waiting_approval -> waiting_user
        -> completed
        -> failed
        -> cancelled
        -> expired
```

需要拆分：

- `agent_runs`：一次用户请求触发的一次 Agent 运行。
- `run_steps`：计划步骤。
- `tool_calls`：工具调用记录。
- `model_calls`：模型调用记录。
- `run_events`：对前端展示的事件。

API 进程不直接拥有运行中任务对象，Worker 持久化读取状态。SSE 客户端断开后，任务继续运行；客户端重连时按 event id 继续读取。

### 5.8 沙箱资源管理模块

企业级沙箱需要从“按需 Docker 容器”升级为受管资源池：

- 沙箱模板：基础镜像、可用工具、网络策略、资源限制。
- 资源限制：CPU、内存、磁盘、运行时长、并发数。
- 网络隔离：默认禁止访问内网，按策略允许域名或目标服务。
- 文件隔离：每个 run 独立 workspace，任务结束后清理或归档。
- 镜像安全：镜像扫描、依赖审计、固定版本。
- 会话接管：浏览器/VNC 接管需要授权和日志。

如果未来部署到 Kubernetes，可把每个沙箱变成短生命周期 Pod，并用 NetworkPolicy 做隔离。

### 5.9 知识库与企业数据连接器

企业 Agent 通常需要接入内部知识，而不是只靠网页搜索。建议新增知识库模块：

- 数据源连接器：文件、网页、Confluence、飞书文档、Notion、SharePoint、Git、数据库。
- 增量同步和权限同步。
- 文档解析、分块、向量化。
- 检索时权限过滤，确保用户只能检索自己有权访问的内容。
- 引用来源返回，便于用户验证。
- 数据过期、删除和重建索引机制。

知识库可以先作为一个受管工具提供给 ReAct，再逐步成为 Agent 规划阶段可感知的资源。

### 5.10 审计与观测模块

建议审计日志至少覆盖：

- 登录、登出、失败登录。
- 配置变更、密钥变更、策略变更。
- Agent 创建、发布、删除。
- 工具注册、启用、禁用。
- Agent 运行开始、结束、失败、取消。
- 模型调用和工具调用摘要。
- 文件上传、下载、导出、删除。
- 审批创建、通过、拒绝。

观测指标至少覆盖：

- Run 成功率、失败率、平均耗时。
- 每个工具调用次数、失败率、耗时。
- 每个模型 token、费用、错误率。
- 沙箱创建耗时、失败率、资源占用。
- 队列长度和 Worker 消费延迟。
- 每个租户/用户/Agent 的成本和使用量。

## 6. 管理后台设计

当前设置弹窗可以保留作为个人或轻量配置入口，但企业场景建议新增独立 Admin Console。

### 6.1 总览页

展示：

- 今日运行次数、成功率、平均耗时。
- Token 和费用趋势。
- 工具调用排行。
- 失败任务和高风险调用。
- 沙箱资源状态。
- 最近告警。

### 6.2 用户与权限页

功能：

- 用户、用户组、组织、workspace 管理。
- 角色创建和权限点分配。
- 资源级授权，例如某 Agent 只允许某部门使用。
- 服务账号和 API Key 管理。

### 6.3 Agent 管理页

功能：

- 创建 Agent 模板。
- 编辑系统 Prompt、模型、工具、知识库、策略。
- 版本管理、灰度发布、回滚。
- Agent 运行历史和质量指标。

### 6.4 工具管理页

功能：

- 内置工具开关和风险等级。
- MCP Server 注册、连接测试、工具列表同步。
- A2A Agent 注册、Agent Card 拉取、健康检查。
- 工具权限策略。
- 工具调用统计和审计。

### 6.5 模型管理页

功能：

- 模型供应商配置。
- 模型能力声明。
- 路由和 fallback 策略。
- 额度、限流、费用统计。
- 模型调用日志。

### 6.6 密钥管理页

功能：

- 创建、更新、轮换、禁用 secret。
- 绑定 secret 到模型供应商、MCP、连接器或 Agent。
- 查看 secret 使用记录。
- 设置过期时间和轮换提醒。

### 6.7 知识库页

功能：

- 创建知识库。
- 添加数据源和同步任务。
- 查看同步状态、解析错误、索引数量。
- 配置访问权限。
- 测试检索结果。

### 6.8 审计与告警页

功能：

- 审计日志查询。
- 按用户、Agent、工具、时间、风险等级过滤。
- 告警规则管理。
- 导出审计报告。

## 7. 建议的数据模型

以下是第一阶段可新增的核心表：

```text
organizations
workspaces
users
groups
group_members
roles
permissions
role_bindings

agents
agent_versions
agent_permissions

tools
tool_versions
tool_permissions
mcp_servers
a2a_servers

model_providers
models
model_routes

secrets
secret_bindings

agent_runs
run_steps
run_events
tool_calls
model_calls
approvals

files
knowledge_bases
knowledge_sources
knowledge_documents
audit_logs
```

当前 `sessions.events`、`sessions.files`、`sessions.memories` 可以在过渡期保留，但新的运行数据应逐步迁移到独立表。

## 8. API 设计建议

### 8.1 认证与租户

```text
POST /api/auth/login
POST /api/auth/logout
GET  /api/auth/me
GET  /api/orgs
GET  /api/workspaces
```

### 8.2 Agent 管理

```text
GET    /api/agents
POST   /api/agents
GET    /api/agents/{agent_id}
POST   /api/agents/{agent_id}/versions
POST   /api/agents/{agent_id}/publish
POST   /api/agents/{agent_id}/rollback
```

### 8.3 工具管理

```text
GET    /api/tools
POST   /api/tools/{tool_id}/enabled
POST   /api/tools/{tool_id}/policy
GET    /api/mcp-servers/{id}/tools
POST   /api/mcp-servers/{id}/sync-tools
POST   /api/tools/{tool_id}/test
```

### 8.4 运行与事件

```text
POST /api/agents/{agent_id}/runs
GET  /api/runs/{run_id}
GET  /api/runs/{run_id}/events
POST /api/runs/{run_id}/cancel
POST /api/runs/{run_id}/resume
```

### 8.5 审批

```text
GET  /api/approvals
POST /api/approvals/{approval_id}/approve
POST /api/approvals/{approval_id}/reject
```

### 8.6 审计与观测

```text
GET /api/audit-logs
GET /api/metrics/summary
GET /api/runs/{run_id}/trace
```

## 9. 分阶段落地路线

### 阶段 1：生产安全底座

目标是让系统能在受控内网环境给小团队使用。

建议优先做：

1. 移除仓库明文密钥，接入环境变量或 Secret Manager。
2. 增加用户登录和基础 RBAC。
3. 内置工具加开关和权限控制，至少能禁用 Shell、浏览器、外部网络。
4. MCP/A2A 按 `enabled` 严格过滤运行时可用工具。
5. 增加审计日志表，记录配置变更、Agent 运行、工具调用。
6. 拆分 tool call 和 model call 记录，支持问题追踪。
7. 给沙箱增加 CPU、内存、磁盘、TTL 和网络限制。

### 阶段 2：企业管理控制台

目标是让管理员可自助管理 Agent 和工具。

建议实现：

1. 独立 Admin Console。
2. Agent 模板、版本和发布管理。
3. 工具注册表、风险等级、权限策略。
4. 模型供应商和模型路由管理。
5. 密钥管理页面。
6. 审计日志查询。
7. 基础使用量和费用统计。

### 阶段 3：可靠执行与多租户

目标是支持多人、多团队、长任务和服务重启恢复。

建议实现：

1. 将 Agent 运行迁移到独立 Worker。
2. 用持久化任务状态替代进程内 task registry。
3. 设计标准 run/step/tool_call/model_call 状态机。
4. 支持 SSE 重连和事件幂等。
5. 增加任务取消、恢复、超时、重试和失败归档。
6. 引入组织、workspace 和资源隔离。

### 阶段 4：知识库与企业连接器

目标是让 Agent 能安全访问企业内部知识和业务系统。

建议实现：

1. 知识库模块和向量检索。
2. 企业文档连接器。
3. 权限同步和检索时过滤。
4. 数据源同步任务和错误处理。
5. 企业 SaaS/内部 API 连接器。
6. 高风险连接器审批。

### 阶段 5：治理、评测和规模化

目标是持续提升 Agent 质量和可运维能力。

建议实现：

1. Prompt 和策略版本灰度发布。
2. 离线评测集和自动回归评测。
3. 模型质量、成本、延迟对比。
4. 全链路 tracing。
5. 告警和 SLO。
6. 合规导出、保留策略、数据删除流程。

## 10. 当前代码优先改造清单

结合当前项目，建议按以下顺序改：

1. 密钥治理：把 `api/config.yaml` 中所有密钥迁移出去，保留 `config.example.yaml`。
2. 工具开关：为内置工具、MCP、A2A 加统一 `ToolRegistry` 和 `ToolPolicy`。
3. 运行时过滤：Agent 初始化工具前根据用户、Agent、workspace、enabled 状态过滤工具。
4. 审计日志：新增 `audit_logs`，所有配置变更和工具调用写入审计。
5. 任务持久化：新增 `agent_runs`、`run_events`、`tool_calls`、`model_calls`。
6. Worker 化：把 `AgentTaskRunner` 从 API 进程内执行迁移到后台 Worker。
7. 权限系统：先实现账号、角色、workspace，再逐步接 SSO。
8. 管理后台：从现有 `SettingsModal` 演进为独立 Admin Console。
9. 沙箱硬化：增加资源限制、网络白名单和高风险命令策略。
10. 观测指标：统计 run 成功率、模型 token、工具失败率、沙箱耗时。

## 11. 关键设计原则

企业级 Agent 的核心不是“允许 Agent 做任何事”，而是“让 Agent 在明确边界内可靠地做事”。建议坚持以下原则：

1. 默认拒绝，高风险能力必须显式授权。
2. 所有外部调用都可审计。
3. 用户权限必须传递到 Agent、工具和知识检索。
4. 密钥不进代码、不进日志、不进事件流。
5. 长任务必须可恢复、可取消、可追踪。
6. 工具、Prompt、模型、策略都要版本化。
7. 沙箱隔离只是底线，还需要网络、资源和数据策略。
8. 管理员需要可视化控制面，普通用户只看到被授权的能力。

## 12. 结论

当前系统已经有通用 Agent 的执行核心，适合继续演进。要成为企业可用的 Agent 平台，最缺的不是某一个工具，而是企业控制面：身份权限、工具治理、密钥管理、审计、任务可靠性、沙箱硬化、模型治理、知识权限和管理后台。

优先级建议是先补安全底座，再做管理后台和任务可靠性，最后扩展知识库、连接器、评测和规模化运维。这样能避免在能力快速扩张的同时放大安全和治理风险。
