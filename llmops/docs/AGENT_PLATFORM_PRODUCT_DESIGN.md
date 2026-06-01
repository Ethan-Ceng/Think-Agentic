# Agent 平台产品设计规划

更新时间：2026-05-13

本文基于当前项目 `api/`、`ui/`、`docker/` 现状，以及 `docs/DIFY_BACKEND_ARCHITECTURE_FASTAPI.md`、`docs/企业级Agent平台_两类Agent架构设计_V5.md` 的设计提炼。目标是把现有 LLMOps 平台升级为企业级 Agent 平台，支持多种业务 Agent 形态，同时保持底层运行模型可治理、可扩展、可审计。

## 1. 产品定位

平台定位为“企业级 Agent 交付与运行平台”，不是单个聊天机器人，也不是简单工作流工具。

核心价值：

1. 让业务团队可以配置、发布和运营多种 Agent。
2. 让开发团队可以把模型、工具、知识库、工作流、MCP、沙箱等能力注册为可治理能力。
3. 让企业可以控制权限、审批、数据范围、审计、成本和质量。
4. 让终端用户通过 Web Chat、企业微信、飞书、API 等入口完成真实业务任务。

当前项目已有 App、Workflow、Dataset、Tool、OpenAPI、Assistant Agent、Celery、Weaviate 等基础能力，升级重点不是推倒重做，而是把这些能力收敛到统一 Agent 平台模型中。

## 2. 核心产品判断

产品层可以呈现多种 Agent 类型，但运行时不应无限扩展 Agent 类型。

推荐设计：

```text
产品层 Agent 模板：
  企业入口 Agent
  销售助手 Agent
  财务分析 Agent
  知识问答 Agent
  数据分析 Agent
  合同审查 Agent
  工单处理 Agent
  代码执行 Agent
  审批协同 Agent

底层运行时 Agent 类型：
  Router Agent
  Worker Agent
```

这样既满足“多种 Agent 类型”的产品表达，也避免 Router、Worker、Workflow、Tool、Skill、Hybrid Agent 等概念同时出现造成用户和工程复杂度失控。

核心原则：

1. Router Agent 负责理解意图、拆解任务、选择 Worker、汇总结果。
2. Worker Agent 负责专业执行、ReAct Loop、调用能力、返回结构化结果。
3. Workflow、Tool、Skill、Knowledge、MCP、Sandbox 都是 Capability，不再包装成新的 Agent 类型。
4. Task Engine 负责状态、调度、重试、审批、恢复、事件流，不让模型承担确定性工程职责。
5. Policy、Approval、Audit 必须贯穿用户到企业系统的全链路。

## 3. 目标用户

| 角色 | 主要诉求 | 典型功能 |
| --- | --- | --- |
| 平台管理员 | 管理租户、成员、模型、权限、审计 | 工作区、RBAC、模型供应商、全局策略 |
| 业务负责人 | 把业务流程配置成可用 Agent | Agent Studio、Worker 编排、审批策略 |
| 开发者 | 接入企业系统和外部能力 | Tool Gateway、OpenAPI Tool、MCP、API Key |
| 运营人员 | 查看效果、成本、失败原因 | Trace、评测、统计分析、版本回滚 |
| 终端用户 | 用自然语言完成业务任务 | Web Chat、任务中心、文件产物、审批确认 |

## 4. 核心产品对象

```text
Tenant / Workspace
  企业或团队隔离边界。

Account / Member / Role
  用户、成员、角色、权限和数据范围。

Agent
  可发布、可版本化的智能体配置。底层 type 只有 router / worker。

Agent Template
  面向用户展示的业务 Agent 类型，例如销售、财务、知识问答、合同审查。

Capability
  被 Worker 调用的能力，包括 tool、workflow、skill、knowledge_base、mcp_tool、sandbox。

Task / Plan / Step
  Router 生成的任务计划和执行状态，由 Task Engine 管理。

Approval
  高风险动作执行前的人工确认对象。

Artifact
  任务产物，例如文件、表格、报告、代码结果、图片。

Trace / Evaluation
  调用链、成本、证据、质量评测和回放数据。
```

## 5. Agent 产品形态

### 5.1 Router Agent

Router Agent 是一个业务入口或业务域调度者。

典型形态：

| 产品形态 | 定位 | 可调用 Worker |
| --- | --- | --- |
| 企业总入口 Agent | 统一接待用户请求并分流 | HR、财务、IT、销售等 Worker |
| 销售 Router | 处理客户、报价、合同、跟进任务 | 客户分析、报价、合同审查 Worker |
| 知识运营 Router | 面向知识检索、内容生成、FAQ 维护 | 知识问答、文档分析、内容生成 Worker |
| 数据分析 Router | 面向报表、SQL、经营分析 | SQL 分析、图表生成、报告生成 Worker |
| 审批协同 Router | 处理高风险动作确认与流转 | 审批解释、风险审查、通知 Worker |

Router 的配置项：

```text
基础信息：名称、图标、描述、业务域。
可见范围：租户、部门、成员、角色。
可调用 Worker 白名单。
计划策略：最大步骤数、是否允许并行、是否允许追问。
风险策略：哪些动作必须审批，哪些数据必须脱敏。
输出策略：是否展示引用、是否展示 trace 摘要、是否屏蔽内部推理。
版本策略：草稿、发布、回滚、灰度。
```

### 5.2 Worker Agent

Worker Agent 是专业执行单元。

典型形态：

| 产品形态 | 主要职责 | 常用 Capability |
| --- | --- | --- |
| 知识问答 Worker | 检索知识库并给出带引用答案 | knowledge_base、rerank、citation |
| 数据分析 Worker | 查询数据、生成图表和分析结论 | SQL tool、sandbox、report skill |
| 工具操作 Worker | 调用 ERP、CRM、OA 等系统 | OpenAPI tool、MCP tool |
| 工作流执行 Worker | 执行固定 SOP 或流程 | workflow |
| 合同审查 Worker | 审查合同条款和风险 | knowledge_base、review skill |
| 报价生成 Worker | 查询库存、价格政策并生成报价 | tool、workflow、artifact |
| 代码沙箱 Worker | 执行 Python、SQL、文件处理 | sandbox |
| 内容生成 Worker | 生成文案、邮件、报告 | skill、template、knowledge_base |

Worker 的配置项：

```text
角色与目标：Worker 的职责边界。
能力范围：允许调用的 Tool、Workflow、Skill、Knowledge、MCP、Sandbox。
Loop Policy：最大思考步数、最大工具调用次数、超时、停止条件。
输出 Schema：结构化结果、证据、产物、动作建议。
风险策略：哪些动作需要审批，哪些工具需要二次鉴权。
评测集：典型输入、期望输出、业务规则检查。
```

## 6. 核心功能模块

### 6.1 Agent Studio

用于创建、配置、调试和发布 Router / Worker。

必备能力：

1. 创建 Agent：从模板创建或空白创建。
2. 配置 Agent：角色、模型、提示词、上下文、能力白名单。
3. 调试 Agent：单 Agent 调试和 Router + Worker 联调。
4. 版本管理：草稿、发布版本、回滚、复制。
5. 运行限制：最大步骤、最大成本、超时、并发。

当前项目的 App 配置能力可以演进为 Agent Studio 的基础，但需要新增 Agent 类型、能力绑定和版本语义。

### 6.2 Capability Center

统一管理可调用能力，替代“工具、工作流、知识库散落在不同入口”的体验。

能力类型：

```text
tool：HTTP / OpenAPI / 内置工具。
workflow：固定 SOP 或业务流程。
skill：Prompt 模板 + 工具白名单 + 业务规则 + Schema。
knowledge_base：知识库检索能力。
mcp_tool：MCP Server 暴露的工具。
mcp_resource：MCP Server 暴露的资源。
sandbox：代码、SQL、文件、浏览器等隔离执行能力。
agent_tool：受控例外，把 Worker 包装成能力供其他 Worker 复用。
```

每个 Capability 必须声明：

```text
输入输出 Schema
权限标识
风险等级
副作用等级
是否需要审批
幂等键要求
超时和重试策略
审计字段和脱敏策略
版本
```

### 6.3 Task Center

Task Center 是用户和运营人员查看复杂 Agent 任务的地方。

功能：

1. 查看任务 Plan、Step、Worker Call、Capability Call。
2. 查看运行状态：排队、执行中、等待审批、等待用户澄清、成功、失败、取消。
3. 查看产物：文件、表格、报告、图表、代码执行结果。
4. 支持人工取消、重试、恢复。
5. 支持审批待办和审批历史。

### 6.4 Knowledge Center

在现有 Dataset、Document、Segment、Weaviate 能力上增强权限治理。

功能：

1. 知识库管理：上传、解析、切分、索引、重建。
2. 权限过滤：租户、部门、项目、客户、文档级 ACL。
3. 检索配置：语义、全文、混合检索、rerank。
4. 引用输出：重要回答必须带来源。
5. 检索审计：记录 query、命中文档、过滤原因。

### 6.5 Tool Gateway

统一工具调用入口。

功能：

1. 内置工具、API Tool、OpenAPI Tool 统一注册。
2. 调用前做权限、参数 Schema、风险、审批、幂等校验。
3. 调用后做审计、脱敏、重试、错误归一。
4. 支持企业系统连接器：CRM、ERP、OA、数据库、消息系统。

当前项目已有 Builtin Tool、API Tool 和 OpenAPI 相关能力，后续应从“Agent 直接绑定工具”升级为“Agent 绑定 Capability，运行时经 Tool Gateway 调用”。

### 6.6 Approval 与 Policy

企业级 Agent 平台必须把高风险动作做成产品能力。

审批触发场景：

```text
发送邮件、消息、报价、合同等外发动作。
修改 CRM、ERP、OA 数据。
导出客户、财务、人事等敏感数据。
执行高风险代码、SQL 或批量操作。
调用 external / critical 副作用能力。
```

审批体验：

1. Worker 生成 action proposal。
2. Task Engine 创建 approval request。
3. Router 向审批人展示摘要、风险、参数和产物。
4. 审批通过后 Tool Gateway 使用审批 token 执行动作。
5. 全链路审计。

### 6.7 Trace 与 Evaluation

平台需要能回答：

```text
用户问了什么？
哪个 Router 处理？
生成了什么 Plan？
调用了哪些 Worker？
Worker 调用了哪些 Capability？
每一步输入输出是什么？
是否触发权限、脱敏、审批？
成本和耗时是多少？
失败发生在哪里？
最终答案基于哪些证据？
```

评测能力：

1. Router 评测：意图识别、Worker 选择、Plan 合理性、审批触发。
2. Worker 评测：任务完成、工具选择、参数构造、Schema 合规、证据完整。
3. Capability 评测：成功率、耗时、权限拒绝、脱敏正确性。
4. 端到端评测：业务完成率、人工介入率、平均耗时、成本、用户采纳。

## 7. 产品信息架构

建议前端主导航：

```text
首页
工作台
  Agent
    Router Agents
    Worker Agents
    Agent Templates
  Tasks
    运行中
    待审批
    历史任务
  Knowledge
  Workflows
  Tools
  Capability Center
  API Keys / OpenAPI
  Observability
    Trace
    Evaluation
    Cost
  Settings
    Members
    Roles
    Model Providers
    Policies
```

当前 `ui/src/views/space/apps`、`workflows`、`datasets`、`tools` 可以复用并逐步改名或聚合到 Agent Studio 与 Capability Center。

## 8. 关键用户旅程

### 8.1 创建一个销售报价 Router

```text
业务负责人进入 Agent Studio
  -> 选择“销售助手 Router”模板
  -> 绑定客户分析 Worker、报价生成 Worker、合同审查 Worker
  -> 配置高风险动作：发送报价必须审批
  -> 在调试台输入客户和产品需求
  -> 查看 Router Plan、Worker Result、引用和产物
  -> 发布给销售部门
```

### 8.2 用户执行报价任务

```text
销售在 Web Chat 输入需求
  -> Router 生成 Plan
  -> Task Engine 调度 Worker
  -> 报价 Worker 查询库存和价格政策
  -> 合同审查 Worker 检查风险
  -> Router 汇总报价草案和风险提示
  -> 用户确认发送
  -> 触发审批
  -> 审批通过后 Tool Gateway 执行发送动作
  -> Task Center 记录全链路
```

### 8.3 开发者接入企业工具

```text
开发者进入 Capability Center
  -> 创建 OpenAPI Tool Provider
  -> 导入企业系统 OpenAPI 文档
  -> 为每个 Tool 配置权限、风险、副作用、超时、脱敏
  -> 在 Worker Agent 中加入工具白名单
  -> 用测试用例验证参数构造和调用结果
```

## 9. MVP 范围

MVP 应选择一个真实业务闭环，而不是同时做完整通用平台。

推荐 MVP：企业销售报价助手。

P0 必做：

1. Agent Registry：Router / Worker 两类 Agent。
2. Capability Registry：支持 tool、workflow、knowledge_base、skill。
3. Router Runtime：输出结构化 Plan，选择 Worker。
4. Worker Runtime：支持 ReAct Loop、工具调用、结构化结果。
5. Task Engine：持久化 Plan、Step、Worker Call、Capability Call。
6. Tool Gateway：支持现有 Builtin Tool、API Tool、OpenAPI Tool 的统一调用。
7. Knowledge Service：复用现有 Dataset + Weaviate，补权限过滤和引用。
8. Approval：支持发送报价、导出数据等高风险动作审批。
9. Audit Trace：记录 Router -> Worker -> Capability 调用链。
10. Web Chat：用户选择一个 Router Agent 对话。

P1 增强：

1. Agent 模板市场。
2. Agent 版本回滚和灰度。
3. Task Center 可视化重试、取消、恢复。
4. 评测集与回归评测。
5. MCP Tool 接入。
6. 更完整的 RBAC 和数据范围权限。

P2 延后：

1. 插件市场。
2. 多 Worker 自由通信。
3. 复杂长期记忆。
4. Agent 自我优化。
5. 多模型自动竞价。
6. 跨租户经验共享。
7. 完整浏览器自动化。

## 10. 产品成功标准

MVP 验收标准：

1. 一个真实业务场景可以端到端完成。
2. 用户能理解 Router、Worker、Capability 的配置关系。
3. Worker 结果全部结构化，不依赖纯自然语言解析。
4. 高风险动作可以审批后执行。
5. 所有关键调用都有 trace 和成本记录。
6. 失败能定位到 Step、Worker 或 Capability。
7. 知识检索有权限过滤、引用和审计。
8. 现有 App、Workflow、Dataset、Tool 能平滑迁移到新模型。

## 11. 设计取舍

1. 不复制完整 Dify：借鉴 API 面、Provider、RAG、Workflow、异步任务和多租户思想，但优先服务当前项目演进。
2. 不做自由 Agent 网络：默认 Router 调 Worker，Worker 不自由调 Worker。
3. 不把所有能力叫 Agent：Workflow、Tool、Skill、Knowledge 是 Capability。
4. 不一开始拆微服务：先用模块化单体跑通业务闭环。
5. 不先做复杂画布：当前 Workflow 画布可以继续增强，但 MVP 主线应是 Agent 任务闭环。
6. 不把安全留到后期：审批、权限、审计、脱敏从第一阶段进入对象模型。

