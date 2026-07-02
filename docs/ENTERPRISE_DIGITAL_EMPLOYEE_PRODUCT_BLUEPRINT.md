# 企业数字员工产品蓝图

本文档用于沉淀当前关于 Think-Agent 产品方向、Agent 平台能力、企业数字员工形态、认证权限、SOP/Workflow、企业知识/RAG、外部 Agent 框架选型等讨论结论。后续相关产品和架构讨论以本文档作为共同上下文。

## 1. 核心结论

Think-Agent 不应被定位为单纯的聊天机器人，也不应被定义为某个开源 Agent 框架的二次封装。更合适的产品定位是企业数字员工平台。

企业数字员工不是“一个更聪明的 LLM”，而是“带岗位身份、权限边界、企业知识、SOP 流程、工具能力和审计记录的工作执行单元”。

因此，产品的核心不是让 Agent 能调用更多工具，而是回答以下问题：

```text
这个数字员工是谁？
属于哪个组织、部门、岗位或 workspace？
能访问哪些企业资料？
能执行哪些 SOP？
能调用哪些业务系统？
哪些操作必须人工审批？
它做过什么？
结果是否可追踪、可复核、可治理？
```

当前建议的产品公式是：

```text
企业数字员工平台 =
岗位角色 + SOP/Workflow + 企业知识/RAG + 工具连接器 + 权限审计 + Agent Runtime
```

其中 Agent Runtime 只是运行时能力之一，不是完整产品本身。

## 2. 当前项目基础

当前 Think-Agent 已经具备通用 Agent 平台的基础形态：

```text
FastAPI 后端
Vue 前端
Planner + ReAct 执行流
Docker sandbox
文件、Shell、浏览器、搜索工具
MCP/A2A 扩展
SSE 事件流
会话、文件和执行过程展示
配置管理页面
```

这些能力适合作为企业数字员工的执行底座继续演进。它已经不是简单 LLM wrapper，而是有任务规划、工具调用、过程事件、文件交付和 sandbox 的 Agent 系统。

但当前距离企业级产品仍有关键缺口：

```text
用户认证缺失
组织、部门、workspace、租户隔离缺失
RBAC/ABAC 权限体系缺失
工具权限和工具策略缺失
审计日志缺失
密钥管理不完善
任务恢复能力不足
会话事件长期堆积在 JSONB 中
测试覆盖不足
```

这些缺口优先级高于继续增加更多 Agent 技巧。

## 3. 产品定位

Think-Agent 的目标应是企业数字员工平台，而不是通用聊天入口。

平台应该允许企业按岗位创建数字员工，例如：

```text
销售助理
客服助理
HR 助理
财务助理
法务助理
研发助理
运营助理
数据分析助理
项目管理助理
```

每个数字员工都应该具有明确的岗位边界：

```text
岗位名称
所属部门
服务对象
职责描述
可访问知识库
可执行 SOP
可调用工具
可访问业务系统
审批策略
转人工策略
审计策略
运行指标
```

产品差异化不应只来自模型能力，而应来自：

```text
岗位模板沉淀
企业 SOP 沉淀
权限感知知识库
企业系统连接器
工具治理
任务审计
可持续运营指标
```

## 4. 多岗位角色设计

企业会有多个岗位角色，因此“数字员工”应该是一等实体，而不是一段系统 prompt。

建议拆成模板和实例两层。

模板用于沉淀可复用岗位能力：

```text
digital_employee_templates
  id
  name
  department_type
  description
  default_prompt
  default_tool_policy_id
  default_workflow_ids
  default_knowledge_scopes
  default_approval_policy_id
  version
  status
```

实例用于绑定到具体企业、部门或 workspace：

```text
digital_employee_instances
  id
  template_id
  organization_id
  workspace_id
  name
  owner_user_id
  runtime_config
  tool_policy_id
  approval_policy_id
  status
```

岗位角色不只影响 prompt，还应影响：

```text
能查哪些知识
能跑哪些 workflow
能调用哪些工具
能操作哪些业务对象
是否需要审批
日志保存多久
异常时升级给谁
```

## 5. SOP 与 Workflow

复用 SOP 应该考虑 Workflow。高频、可复用、可审计的企业流程不应只靠 Agent 自由规划。

任务可以分成三类：

```text
临时探索任务：Agent 自主规划执行
半结构化任务：Workflow + Agent 节点
标准 SOP：Workflow 主导，Agent 处理理解、生成、异常判断
```

对于企业数字员工，Workflow 应该成为后台核心产品资产，而不是普通用户的主入口。原因是企业 SOP 需要稳定、可审计、可复用、可改版，而纯 prompt 或纯 ReAct loop 很难保证这一点。

前台产品形态应是对话和 Skill。普通用户看到的是“销售助理会做客户拜访准备”“客服助理会做工单归类”“项目助理会做会议纪要和任务跟踪”，而不是节点画布。后台再根据风险和稳定性，把一部分 Skill 落到 Workflow、审批、工具策略和审计日志上。

Workflow 应至少支持：

```text
流程定义
版本管理
输入输出 schema
步骤编排
条件分支
人工审批
超时处理
失败重试
失败回滚
运行日志
权限校验
指标统计
```

推荐模型：

```text
workflow_definitions
workflow_versions
workflow_steps
workflow_runs
workflow_run_events
workflow_approvals
```

Workflow 节点类型可以包括：

```text
manual_input
approval
agent_task
llm_extract
llm_generate
tool_call
http_request
condition
wait
notification
human_handoff
```

Agent 的价值不是替代 workflow，而是补足 workflow 中的不确定部分。例如：

```text
理解用户自然语言需求
从文档中提取关键信息
生成邮件、报告、摘要
判断异常原因
选择下一步建议
处理非标准输入
```

标准企业流程在后台应尽量 workflow 化。Agent 自主规划更适合非标准、低频、探索性任务。产品表达上应优先使用 Skill、SOP、任务剧本、岗位能力等概念，不建议把 Workflow 作为普通业务用户的第一入口。

## 6. 企业知识与 RAG

企业资料需要 RAG，但不能是简单上传文档后做向量检索。

企业 RAG 的核心是权限感知、来源可信、可引用、可审计。

必须考虑：

```text
组织隔离
workspace 隔离
用户权限
文档 ACL 同步
文档版本
文档有效期
知识分级
敏感信息脱敏
引用来源
检索日志
命中内容审计
```

重要原则：

```text
权限先于相关性。
```

不能因为某个文档语义最相关，就把用户或数字员工无权访问的内容送入模型上下文。

建议企业知识层拆成：

```text
knowledge_bases
knowledge_sources
knowledge_documents
knowledge_chunks
knowledge_permissions
knowledge_sync_jobs
retrieval_logs
```

检索策略建议采用混合检索：

```text
关键词检索
向量检索
元数据过滤
权限过滤
时间过滤
来源权重
人工认证知识优先级
```

RAG 返回给 Agent 的内容应包含：

```text
content
source_url 或 source_file
document_id
chunk_id
updated_at
permission_scope
confidence 或 score
```

前端交付时应尽量展示引用来源，方便用户复核。

## 7. 工具与连接器

企业数字员工的执行能力来自工具和连接器。

工具不应只是一组函数 schema，而应是受治理资源：

```text
tool_registry
tool_versions
tool_permissions
tool_policies
tool_call_logs
connector_configs
connector_credentials
```

工具类型包括：

```text
内置工具：file、shell、browser、search、message
MCP 工具
A2A 远程 Agent
企业 SaaS 连接器
企业内部 API
数据库连接器
知识库检索工具
Workflow 调用工具
```

每个工具应记录：

```text
来源
版本
输入输出 schema
风险等级
是否默认启用
适用岗位
适用组织或 workspace
是否需要审批
超时
重试策略
审计策略
```

高风险工具必须有策略约束：

```text
Shell
Browser
外网访问
文件写入
MCP
A2A
生产系统 API
发邮件
发消息
提交审批
修改业务数据
```

## 8. 认证、权限与治理

当前用户认证缺失，这是企业化第一优先级。

建议采用单 FastAPI 应用下的模块化单体架构，而不是一开始拆多个 FastAPI sub-app。

推荐模块：

```text
identity
agent
workflow
knowledge
tools
admin
audit
shared
```

`identity` 是控制面基础模块，负责：

```text
organizations
workspaces
users
groups
roles
permissions
role_bindings
api_keys
service_accounts
```

统一依赖：

```python
current_user = Depends(get_current_user)
tenant = Depends(get_tenant_context)
permission = Depends(require_permission("agent.session.chat"))
```

权限不能只在 API 入口做。Agent 工具调用前必须二次检查：

```text
用户请求
  -> API 鉴权
  -> 创建 agent run
  -> Agent 执行
  -> 每次 tool call 前检查 ToolPolicy
  -> allow / deny / require_approval
```

这很关键。用户不能直接调 Shell API，不代表他不能通过 prompt 让 Agent 调 Shell。

## 9. OpenClaw 与 Hermes 的定位

外部有人建议使用 OpenClaw 或 Hermes。当前判断是：可以参考，但不建议直接替代现有系统作为企业数字员工平台底座。

如果这里的 openclow 指 OpenClaw，那么它更像个人或小团队 always-on AI assistant，适合快速验证多渠道入口、技能机制、个人自动化体验。但企业数字员工需要组织、权限、审计、审批、隔离和可追责。OpenClaw 这类个人助理框架不应直接成为企业控制面。

Hermes Agent 的方向更偏自我改进和重复任务沉淀技能。这个方向对企业 SOP 沉淀有价值，但“自我写技能、自我改进、自我执行”在企业环境里必须受治理。技能应该经历：

```text
draft
test
review
approve
publish
rollback
```

而不是自动上线。

当前建议：

```text
Think-Agent 做企业数字员工平台底座。
OpenClaw/Hermes 作为参考实现、外部 Agent 后端或 adapter 接入。
不要让它们接管身份、权限、审计、知识权限和工具治理。
```

未来可以通过以下方式接入外部 Agent：

```text
A2A adapter
MCP adapter
HTTP connector
Workflow node
ExternalAgentRuntime
```

## 10. 推荐产品架构

建议长期架构如下：

```text
Web / Admin Console
  - 数字员工中心
  - SOP/Workflow 中心
  - 企业知识中心
  - 工具与连接器中心
  - 审计与运营中心

API / BFF
  - Auth
  - Tenant Context
  - RBAC
  - Rate Limit
  - SSE / WebSocket

Control Plane
  - Identity
  - Digital Employees
  - Tool Policy
  - Knowledge Scope
  - Workflow Definition
  - Approval Policy

Runtime Plane
  - Agent Runtime
  - Workflow Runtime
  - Tool Executor
  - Sandbox Manager
  - Worker

Knowledge Plane
  - Connectors
  - Document Sync
  - Chunking
  - Embedding
  - Hybrid Retrieval
  - ACL Filtering

Data Plane
  - Postgres
  - Redis / Queue
  - Object Storage
  - Vector Store
  - Audit Log

Observability
  - Run Trace
  - Tool Calls
  - Model Calls
  - Cost
  - Quality Metrics
  - Alerts
```

## 11. 核心产品模块

### 11.1 数字员工中心

用于创建和管理岗位型数字员工。

能力：

```text
创建岗位模板
创建岗位实例
配置职责说明
绑定知识库
绑定 SOP
绑定工具
设置审批策略
设置转人工策略
查看运行历史
查看质量指标
```

### 11.2 SOP/Workflow 中心

用于把企业流程沉淀成可运行资产。

能力：

```text
流程设计
节点配置
版本管理
输入输出定义
人工审批
运行记录
异常处理
流程指标
```

### 11.3 企业知识中心

用于接入企业资料并提供权限感知 RAG。

能力：

```text
知识库创建
数据源接入
文档同步
权限同步
分块与索引
混合检索
引用展示
知识有效期
敏感信息处理
```

### 11.4 工具与连接器中心

用于管理数字员工可调用能力。

能力：

```text
内置工具管理
MCP Server 管理
A2A Agent 管理
企业 SaaS 连接器
内部 API 连接器
工具权限
工具风险等级
工具调用审计
```

### 11.5 治理与运营中心

用于企业管理员管理风险、质量和成本。

能力：

```text
用户与角色
权限策略
审批任务
审计日志
运行指标
成本统计
质量评估
异常告警
```

## 12. 数据模型草案

第一阶段建议新增或规划以下表：

```text
organizations
workspaces
users
groups
group_members
roles
permissions
role_bindings
api_keys

digital_employee_templates
digital_employee_instances
digital_employee_versions
digital_employee_permissions

workflow_definitions
workflow_versions
workflow_steps
workflow_runs
workflow_run_events
workflow_approvals

knowledge_bases
knowledge_sources
knowledge_documents
knowledge_chunks
knowledge_permissions
knowledge_sync_jobs
retrieval_logs

tools
tool_versions
tool_policies
tool_permissions
tool_call_logs
mcp_servers
a2a_servers
connectors
connector_credentials

agent_runs
run_steps
run_events
tool_calls
model_calls
approvals
audit_logs
```

现有 `sessions.events`、`sessions.files`、`sessions.memories` 可以短期保留，但长期应逐步迁移到独立运行数据表。

## 13. 技术架构取舍

### 13.1 FastAPI 单应用优先

当前阶段建议一个 `FastAPI()` 应用，下面按模块挂载 `APIRouter`。

不建议一开始使用多个 mounted sub-app，除非模块具备完全不同的生命周期、中间件、安全边界、OpenAPI 边界或部署节奏。

### 13.2 Workflow 先内建抽象，后续可替换执行引擎

早期可以先实现轻量 workflow definition 和 run 记录，不必马上引入复杂工作流引擎。

但设计上要保留未来接入 durable workflow engine 的空间，例如 Temporal 这类长任务可恢复、事件历史可回放的执行引擎。

### 13.3 Agent Runtime 与产品控制面解耦

Agent Runtime 可以替换、增强或接入外部实现，但 identity、RBAC、knowledge ACL、tool policy、audit 不应交给外部 Agent 框架。

### 13.4 RAG 必须权限感知

企业知识检索必须先做权限过滤，再做相关性排序和上下文注入。

## 14. 落地路线

### 阶段 1：企业安全底座

目标是让当前系统能在受控企业环境下给小团队使用。

优先事项：

```text
移除明文密钥
新增 identity 模块
新增组织、workspace、用户、角色、权限
给现有 session/file/config/agent API 补权限
新增 audit_logs
新增 ToolPolicy
管住 Shell、Browser、MCP、A2A
```

### 阶段 2：数字员工模型

目标是从“通用 Agent”升级为“岗位数字员工”。

优先事项：

```text
新增 digital_employee_templates
新增 digital_employee_instances
为岗位绑定工具、知识、SOP、审批策略
前端增加数字员工中心
支持按岗位发起任务
```

### 阶段 3：SOP/Workflow

目标是把可复用企业流程沉淀为产品资产。

优先事项：

```text
workflow definition
workflow run
agent_task 节点
approval 节点
tool_call 节点
运行事件记录
流程版本管理
```

### 阶段 4：企业知识/RAG

目标是让数字员工可以安全使用企业资料。

优先事项：

```text
知识库模块
文档上传与同步
chunking
embedding
元数据过滤
权限过滤
引用来源展示
检索日志
```

### 阶段 5：企业连接器与治理

目标是连接真实业务系统并形成运营闭环。

优先事项：

```text
CRM/工单/ERP/IM/文档系统连接器
连接器密钥管理
审批流
成本统计
质量评估
告警
运行回放
```

## 15. 后续讨论基准

后续关于产品和架构的讨论，建议默认采用以下前提：

```text
Think-Agent 的目标是企业数字员工平台。
数字员工是岗位型工作执行单元，不是单纯聊天机器人。
Agent Runtime 是能力组件，不是完整产品。
前台应是对话式数字员工和 Skill，后台应具备 Workflow 级执行、权限、审批和审计能力。
企业资料应建设权限感知 RAG。
OpenClaw/Hermes 等外部 Agent 框架最多作为 adapter 或参考实现。
身份、权限、审计、工具治理必须由平台自身控制。
当前优先级是企业安全底座，其次是数字员工模型，再其次是 Skill/SOP、Workflow 和 RAG。
```

## 16. 本轮产品决策归档：企业数字员工怎么做

本轮讨论进一步明确：不要从“Agent 平台”或“Workflow 平台”开始做，而应从一个可交付、可使用、可治理的岗位数字员工开始做。

核心公式保持为：

```text
企业数字员工 =
岗位角色 + 企业知识 + SOP/Skill + 工具执行 + 权限审批 + 审计运营
```

### 16.1 产品主线

普通用户的第一体验应是：

```text
我有一个销售助理、招聘助理、客服助理、项目助理或运营助理。
我直接和它对话，让它帮我完成岗位工作。
```

用户不应该先看到 Prompt、节点、插件、Workflow 配置。那些属于后台实施、管理员和开发者视角。

后台需要提供：

```text
岗位模板
数字员工实例
Skill/SOP 库
企业知识库 RAG
工具连接器
权限策略
审批规则
执行日志
质量评估
成本统计
```

### 16.2 第一阶段不要做万能员工

MVP 应选择一个容易闭环的岗位，而不是一开始做万能数字员工。

优先候选岗位：

```text
销售助理：查资料、写跟进、生成方案、整理客户纪要、推进 CRM。
招聘助理：筛简历、约面试、生成面评、沉淀候选人资料。
客服助理：查知识库、生成回复、工单分类、升级人工。
行政/项目助理：会议纪要、任务拆解、进度跟踪、文档归档。
```

不建议第一阶段选择财务付款、合同审批、薪酬等高风险岗位。这些岗位对权限、审批、合规和系统连接要求更高，容易把 MVP 拖成大型平台工程。

### 16.3 当前项目的模块演进

当前 Think-Agent 可以按以下模块演进：

```text
identity：用户、组织、租户、角色、权限。
agent_core：Agent 运行时、任务、会话、工具调用。
employee：数字员工模板、数字员工实例、岗位配置。
skill：技能/SOP、触发条件、输入输出、版本。
knowledge：企业资料、RAG、权限过滤、引用来源。
workflow：后台流程执行，不作为普通用户主入口。
tool_policy：工具权限、审批、人类确认。
audit：执行日志、工具日志、知识引用、审批记录。
```

FastAPI 先采用单应用模块化单体即可，不需要一开始拆多个应用或微服务。

### 16.4 Skill 与 Workflow 的关系

前台应叫 Skill、技能、作业能力或岗位能力。后台可以有 Workflow，但不要把 Workflow 作为产品主入口。

一个用户请求可以触发多个 Skill。例如：

```text
用户：帮我准备明天拜访 A 客户的材料。

数字员工内部可能触发：
客户资料查询 Skill
历史沟通总结 Skill
产品方案生成 Skill
风险点检查 Skill
CRM 更新 Tool
```

其中有些 Skill 背后可以是 Workflow，有些只是 RAG + Prompt，有些是工具调用。用户不需要知道具体实现。

推荐规则：

```text
简单知识型任务：Skill + RAG。
经验方法型任务：Skill + SOP。
强流程、高风险、要审计的任务：Skill + Workflow。
需要系统操作的任务：Skill + Tool Policy + 审批。
岗位级能力沉淀：岗位模板安装一组 Skills。
```

### 16.5 扣子方向的启发

扣子的产品思路可以理解为生产侧和消费侧分层：

```text
生产侧：业务专家、实施人员、开发者沉淀 Skill、Workflow、工具和知识。
消费侧：普通用户通过对话调用 Agent，Agent 自动选择合适的 Skill。
```

这对 Think-Agent 的启发是：前台应学习“对话 + Skill”的自然体验，后台不能放弃企业级治理能力。

因此推荐方向不是 Dify 式配置优先，也不是完全自由的 OpenClaw/Hermes 式 Agent，而是：

```text
前台：conversation-first digital employee + Skill。
后台：Workflow-grade execution + RAG + Tool Policy + Approval + Audit。
```

### 16.6 RAG 是企业数字员工的必需能力

企业数字员工如果没有企业知识，只是通用聊天机器人。

RAG 从第一天就要考虑权限：

```text
用户只能检索自己有权看的资料。
数字员工只能访问岗位范围内的资料。
回答必须带引用来源。
文档要有版本、更新时间、所属部门。
高风险结论要能追溯。
权限过滤必须先于相关性排序。
```

企业中最危险的不是“答错”，而是“拿了不该拿的资料答对了”。

### 16.7 多岗位与多 Agent

不要一开始把岗位模板设计成多 Agent 系统。

第一阶段建议：

```text
一个数字员工实例 =
一个主 Agent + 一组岗位 Skills + 一组知识权限 + 一组工具权限
```

多 Agent 只在复杂岗位中作为内部实现，例如：

```text
资料检索 Agent
方案生成 Agent
风险审核 Agent
系统执行 Agent
```

但产品上仍然表现为一个数字员工。用户购买、配置、使用和评价的对象都应该是“岗位数字员工”，而不是一组技术 Agent。

### 16.8 MVP 范围

建议 MVP 做到以下闭环：

```text
企业管理员创建组织和用户。
管理员创建一个岗位数字员工，例如销售助理。
给数字员工绑定企业知识库。
给数字员工配置 3 到 5 个 Skills。
给数字员工开放少量工具，例如搜索、文档生成、CRM 查询。
用户通过对话让它完成任务。
每次执行都有日志、引用、工具调用记录。
高风险动作需要用户确认。
```

这已经不是普通 Agent Demo，而是企业数字员工产品雏形。

### 16.9 当前优先级

建议实施顺序：

```text
1. 用户认证、组织、权限。
2. 数字员工模板和实例。
3. Skill/SOP 数据模型。
4. 权限感知 RAG。
5. 工具权限和审批。
6. 执行日志和审计。
7. 后台 Skill 编排能力。
8. 多岗位模板市场。
9. 多 Agent 内部协作。
```

结论：Think-Agent 应做“对话式企业数字员工产品”，不是 Dify 式配置平台，也不是纯自由 Agent。前台要像会干活的员工，后台要有企业级流程、权限、知识和审计。

## 17. 本轮架构决策归档：前台 Agent、专业 Agent 与企业系统接入

本轮讨论进一步明确：Think-Agent 可以做成类似 OpenClaw 的用户入口，接入企业微信、飞书、Web Chat 等员工日常入口；底层则建设类似扣子的 Skill/Workflow/多 Agent 运维平台，并通过 A2A、MCP、Tool Gateway 打通专业 Agent 和企业系统。

但产品边界不是“一个入口 + 一个外部底座”这么简单。更准确的定位是：

```text
Think-Agent =
企业数字员工门脸
+ 企业控制面
+ Agent 接入网关
+ Skill/Workflow/多 Agent 运维底座
```

### 17.1 推荐四层架构

```text
用户入口层
  - 企业微信
  - 飞书
  - Web Chat
  - 群聊机器人
  - 私聊数字员工
  - 任务卡片
  - 审批确认
  - 通知提醒

企业控制面
  - 组织、用户、部门、岗位
  - 数字员工模板
  - 数字员工实例
  - Skill/SOP 管理
  - 知识权限
  - 工具权限
  - 审批策略
  - 审计日志
  - 成本和质量运营

执行编排层
  - Skill Router
  - Workflow
  - 多 Agent 协作
  - Agent 任务调度
  - 工具调用
  - 人工审批节点
  - 运行回放
  - 失败重试

连接层
  - A2A Agent
  - MCP Server
  - CRM / ERP / OA / 工单系统
  - 文档系统
  - 数据库
  - 企业微信 / 飞书 API
  - 自研业务 API
```

一句话：前台像 OpenClaw，员工通过企业微信、飞书自然对话；后台像扣子但更企业化，负责 Skill、Workflow、多 Agent、RAG、工具、权限和审计；A2A/MCP 是底层连接协议，不是产品控制中心。

### 17.2 前台 Agent 的责任边界

Skill、工具、MCP 做多后，不能全部直接塞给前台 Agent。否则会出现工具选择错误、权限绕过、上下文膨胀、延迟升高和审计困难。

前台 Agent 应该少而稳，像岗位数字员工的门脸：

```text
识别用户身份和组织上下文
理解用户意图
判断要调用哪个岗位 Skill
补充追问缺失信息
发起任务
展示执行进度
请求用户确认或审批
把结果用业务语言返回
```

前台 Agent 只需要少量高层工具：

```text
search_skill
run_skill
create_task
handoff_to_agent
retrieve_knowledge
request_approval
get_task_status
```

不建议让前台 Agent 直接持有 CRM 查询、ERP 写入、数据库执行、飞书发消息、Shell、浏览器、MCP 全量工具等底层能力。

### 17.3 专业 Agent 的责任边界

专业 Agent 负责具体岗位或领域任务，例如：

```text
销售资料分析
合同风险审查
客服工单分类
数据查询
知识检索
方案生成
风险复核
系统执行
```

专业 Agent 可以拥有更垂直的工具和知识范围，但仍然必须受平台控制：

```text
岗位权限
知识范围
工具白名单
审批策略
调用日志
失败处理
成本限制
```

推荐的调用链：

```text
企业微信 / 飞书 / Web
  -> 前台数字员工 Agent
  -> Skill Router
  -> Workflow / 多 Agent / A2A
  -> Tool Gateway / MCP Gateway
  -> 企业系统连接器
  -> CRM / ERP / OA / 数据库 / 文档系统
```

### 17.4 前台 Agent 和专业 Agent 可以放在一个应用工程

第一阶段建议前台 Agent 和专业 Agent 放在同一个应用工程里。放在一个工程里不等于混成一个 Agent，而是一个 FastAPI 应用、多个清晰模块、多个 Agent profile/runtime 配置。

推荐结构：

```text
api/
  modules/
    identity/
    employee/
    agent_runtime/
    front_agent/
    specialist_agents/
    skill/
    workflow/
    knowledge/
    tools/
    audit/
```

逻辑边界：

```text
front_agent：
  负责用户对话、意图识别、Skill 路由、追问、确认、结果呈现。

specialist_agents：
  负责具体专业任务，例如销售资料分析、合同风险审查、客服工单分类、数据查询。

skill/workflow：
  负责把业务能力编排成稳定流程。

tools：
  负责通过 Tool Gateway/MCP Gateway 调企业系统。

identity/audit：
  负责权限和审计，所有 Agent 都必须经过这里。
```

第一阶段不建议拆成多个服务。单工程的优点是开发快、调试简单、权限上下文统一、审计链路容易串起来、数据模型不用跨服务同步、部署复杂度低。

真正要避免的是：

```text
一个大 Agent 拿所有工具、所有 Skill、所有系统权限。
```

正确做法是：

```text
一个应用工程
  -> 一个统一控制面
  -> 多个 Agent 定义
  -> 每个 Agent 有自己的职责、工具白名单、知识范围、审批策略
```

示例：

```text
front_digital_employee_agent
  tools:
    - run_skill
    - ask_user
    - request_approval
    - get_task_status

sales_research_agent
  tools:
    - retrieve_customer_knowledge
    - search_public_info
    - summarize_documents

crm_operation_agent
  tools:
    - get_customer_profile
    - create_followup_task
    - update_opportunity_stage

risk_review_agent
  tools:
    - retrieve_policy
    - check_sensitive_action
    - require_human_approval
```

演进路径：

```text
阶段 1：单工程、模块化单体、内部 Agent Registry。
阶段 2：专业 Agent 仍在同工程，但通过统一 Agent Gateway 调用。
阶段 3：高负载或强隔离的专业 Agent 独立成服务。
阶段 4：外部 Agent 通过 A2A 接入。
```

拆出独立服务的触发条件：

```text
某个专业 Agent 需要独立扩缩容。
某个 Agent 依赖特殊运行环境。
某个 Agent 风险高，需要强隔离。
某个 Agent 由外部团队维护。
某个客户要求私有化部署某个 Agent。
某个 Agent 运行时间长，影响主应用稳定性。
```

### 17.5 MCP、A2A 与 Tool Gateway 的关系

MCP 适合做 Agent 调工具和资源的标准接口。A2A 适合做 Agent 之间的任务协作。二者都不是权限、审计、租户隔离和工具治理的替代品。

推荐边界：

```text
A2A：Agent 与 Agent 协作。
MCP：Agent 调用工具、资源和外部能力。
Tool Gateway / MCP Gateway：统一权限、审批、审计、脱敏和治理。
```

不建议：

```text
Agent 直接连接客户系统。
客户系统裸露成一堆 MCP 给模型自由选择。
前台 Agent 直接持有所有 MCP 工具。
```

建议：

```text
前台 Agent
  -> A2A 调用专业 Agent
      -> 专业 Agent 内部通过 MCP / Tool Gateway 调工具
```

MCP Gateway / Tool Gateway 至少负责：

```text
工具白名单
租户隔离
用户权限
岗位权限
输入 schema 校验
审批判断
调用日志
结果脱敏
失败重试
超时控制
```

### 17.6 企业系统接入方式

底座不应该是“全靠 MCP 接企业”，也不应该是“Agent 直接读写数据库”。更好的做法是：

```text
企业系统 Adapter 层负责兼容 C++/.NET/Java/数据库/老系统；
Tool Gateway/MCP Gateway 负责标准化和治理；
Skill/Workflow 负责业务编排；
前台 Agent 只负责对话、路由、确认和呈现。
```

企业系统接入优先级：

```text
1. 优先用官方 API / SDK / Webhook。
2. 没有 API，就做 Adapter Service，把老系统包装成 HTTP/gRPC/消息队列。
3. 只读数据可以接数据库，但必须走只读账号、视图、脱敏、行权限。
4. 写操作尽量走业务 API、审批流、命令队列或存储过程。
5. 直接写数据库只能作为最后手段，而且必须强审计、强审批、可回滚。
6. 没有接口也不能读库时，最后才考虑 RPA/UI 自动化。
```

对于 C++、.NET、Java 等客户系统，不要要求它们直接支持 MCP。更现实的接入方式是：

```text
C++ 系统 -> 本地 Adapter -> HTTP/gRPC/MQ -> Tool Gateway -> MCP Tool
.NET 系统 -> .NET Adapter Service -> HTTP/gRPC/MQ -> Tool Gateway -> MCP Tool
Java 系统 -> Java Adapter Service -> HTTP/gRPC/MQ -> Tool Gateway -> MCP Tool
数据库 -> Read-only Adapter -> Tool Gateway -> MCP Tool
文档系统 -> Sync Connector -> RAG Index
```

对 Agent 暴露的应是业务语义工具：

```text
get_customer_profile(customer_id)
create_followup_task(customer_id, content)
query_order_status(order_id)
submit_expense_approval(data)
```

不应直接暴露：

```text
execute_sql(...)
call_legacy_dll(...)
run_shell(...)
write_database(...)
```

### 17.7 本轮结论

```text
前台 Agent：少而稳，负责接待、理解、路由、确认、呈现。
专业 Agent：垂直负责专业任务，但必须受平台权限、工具白名单和审计约束。
Skill/Workflow：负责业务能力沉淀和执行编排。
MCP：工具和资源标准接口。
A2A：Agent 协作协议。
Tool Gateway：企业级权限、审批、审计和脱敏中心。
Adapter：兼容客户复杂系统，包括 C++、.NET、Java、数据库和老系统。
单工程模块化单体：第一阶段推荐形态。
```

## 18. 本轮架构路径决策归档：agentic 与 llmops 的产品化取舍

本轮讨论进一步明确：`agentic` 和 `llmops` 不应被理解为两个完全平行的产品方向，而应被理解为两类不同层次的资产。

```text
agentic =
自主型 Agent Runtime / 自部署 Agent 学习模板 / 执行器参考实现

llmops =
面向外部发布、交付和运营的企业级 Agent 应用平台
```

### 18.1 agentic 的定位

`agentic` 更接近 MoocManus 风格的自主执行底座，核心价值在于让 Agent 真正具备执行能力。

它已经具备：

```text
Planner
ReAct loop
MCP
A2A
Tool
Sandbox
Shell
Browser
File
VNC
SSE 事件流
会话级任务执行
```

因此 `agentic` 适合作为：

```text
自用型 Agent 模板
单客户私有化快速验证底座
Runtime / Executor 能力来源
Sandbox / Browser / MCP / A2A 的参考实现
```

但 `agentic` 当前不应直接等同于企业数字员工平台。它的持久化、配置、权限、审计和发布形态仍偏单实例、单会话、运行时优先，而不是企业控制面优先。

### 18.2 llmops 的定位

`llmops` 更接近对外交付的产品平台。它已经具备较多企业产品所需的控制面和运营面能力：

```text
账号登录
AI 应用管理
WorkerAgent / PlannerAgent
模型配置
工具管理
Workflow
Dataset / RAG
文件
任务记录
Trace
运行分析
OpenAPI
Web App 发布
```

因此 `llmops` 更适合作为企业数字员工的主产品骨架。

它的问题不在于平台能力不足，而在于容易走向“配置平台”或“模板平台”：

```text
用户看到 App / Prompt / Tool / Workflow 配置，而不是数字员工。
岗位模板过重，业务稍有变化就需要改模板或改流程。
Workflow 容易抢主角，产品变成流程编排平台。
治理能力如果一次性铺开，MVP 容易变成大型平台工程。
Runtime 执行体验目前不如 agentic 自然和完整。
```

### 18.3 方案一：基于 agentic 补齐产品能力

方案一的思路是：在 `agentic` 上补齐 Skill、Workflow、Knowledge、模型配置、任务记录、Trace、分析、OpenAPI/Web App 发布，然后按需要部署多个数字员工，并通过一个总入口 Agent 使用 A2A 连接。

这个方案分成两种形态。

不推荐的形态：

```text
一个数字员工 = 一套独立 agentic 部署
多个数字员工 = 多套 agentic 实例
总入口 = 一个额外 Agent
协作方式 = A2A
```

这种形态适合 demo、小团队、自用或强隔离私有化验证，但不适合作为长期主产品架构。原因是复制部署不能解决统一治理问题：

```text
统一账号
统一权限
统一知识库 ACL
统一工具策略
统一密钥
统一任务记录
统一 Trace
统一审计
统一版本回滚
统一成本统计
统一发布渠道
```

A2A 可以解决 Agent 之间怎么调用，但不能替代企业控制面。

可接受的形态：

```text
一个 agentic 平台内部管理多个数字员工实例
每个数字员工只是 Agent Profile / Agent Instance
共享同一套身份、知识、工具、Trace、发布和治理能力
```

这时“复制数字员工”不是复制部署，而是：

```text
复制模板
生成员工实例
绑定 Skill
绑定 Knowledge Scope
绑定 Tool Policy
绑定审批策略
发布 endpoint
共享平台级 Run / Trace / Audit
```

如果走这个方向，`agentic` 至少需要补齐：

```text
AgentTemplate
AgentInstance
Skill
KnowledgeScope
ToolPolicy
Run / Trace
DeploymentChannel
ModelConfig
Credential / Secret 管理
```

这条路可以成立，但本质上是在把 `agentic` 做成一个小型 `llmops`。优势是 Runtime 灵活、工程心智简单；代价是要自己补齐 `llmops` 已经具备的一部分控制面能力。

### 18.4 方案二：基于 llmops 做企业数字员工主产品

方案二的思路是：用 `llmops` 作为企业数字员工主系统，将数字员工、Skill、Knowledge、Tool Policy、Trace、发布渠道和运营能力统一纳入产品平台。

该方案更适合作为长期产品主路径，原因是：

```text
已有账号和登录体系。
已有 App / Agent / Workflow / Dataset / Tool 产品对象。
已有任务记录、WorkerCall、TraceEvent 等运行记录。
已有 OpenAPI 和 Web App 发布入口。
已有 PlannerAgent / WorkerAgent 的产品化雏形。
更容易继续扩展权限、审批、审计、成本和分析。
```

但方案二必须避免以下风险：

```text
不要把数字员工做成固定岗位模板堆叠。
不要让用户先看到 Prompt、节点、插件、Workflow 配置。
不要让 Workflow 成为所有业务能力的默认实现。
不要一次性铺满组织、RBAC、审批、审计、成本等全部治理能力。
不要让平台能力强但 Runtime 执行体验弱。
```

推荐产品表达：

```text
用户购买和使用的是数字员工。
管理员配置的是岗位、Skill、知识范围、工具权限和发布渠道。
Workflow、RAG、Tool、WorkerAgent、A2A 都只是 Skill 的后端实现方式。
```

### 18.5 Workflow 的边界

本轮讨论明确：Workflow 很重要，但不能过早成为主入口。

Workflow 的优势是：

```text
稳定
可复用
可审计
可重试
可审批
可度量
```

Workflow 的风险是：

```text
灵活性差
业务逻辑重
变更成本高
容易把产品做成流程编排平台
容易让数字员工退化为 Workflow 的聊天壳
```

因此前台应优先抽象为 Skill，而不是 Workflow。

推荐边界：

```text
不确定、探索性、低频任务：Agent / Skill
半结构化任务：Skill + Agent + Tool
简单知识型任务：Skill + RAG
高频、稳定、强审计任务：Skill + Workflow
高风险动作：Skill + Workflow + Approval + Audit
```

不建议第一阶段把所有业务能力 workflow 化。应先用 Skill 承接业务能力，再把稳定 SOP 下沉为 Workflow。

建议的 Skill 数据抽象：

```text
skill_definitions
  id
  name
  description
  input_schema
  output_schema
  implementation_type
  implementation_ref
  risk_level
  approval_policy_id
  tool_policy_id
  status
```

`implementation_type` 可以包括：

```text
prompt
rag
tool
workflow
worker_agent
a2a_agent
composite
```

### 18.6 当前推荐路线

推荐主路径：

```text
llmops 做企业控制面和产品主系统。
agentic 做 Runtime / Executor 能力来源和参考实现。
```

也就是说：

```text
llmops:
  数字员工定义
  Skill
  Knowledge / RAG
  Tool Policy
  Workflow
  Approval
  Audit
  Trace
  发布渠道
  运营分析

agentic:
  Planner / ReAct 执行循环
  Sandbox
  Browser / Shell / File
  MCP
  A2A
  VNC
  事件流体验
```

长期应把 `agentic` 的成熟执行能力拆成 `llmops` 可治理的 executor，而不是把整个 `agentic` 应用直接搬进 `llmops`。

推荐 executor 形态：

```text
sandbox_worker
browser_worker
shell_worker
mcp_worker
a2a_worker
react_worker
workflow_worker
```

统一原则：

```text
数字员工不是一套独立部署，而是平台内的受治理实例。
A2A 是连接协议，不是治理中心。
MCP 是工具和资源协议，不是权限中心。
Tool Gateway / Policy / Audit 必须由平台掌握。
Workflow 是 Skill 的实现方式之一，不是普通用户主入口。
```

### 18.7 阶段建议

短期可以允许方案一作为验证路径，但要限定边界：

```text
可以用 agentic 快速验证自部署数字员工体验。
可以用 A2A 验证总入口调多个专业 Agent。
可以用 agentic 的 Sandbox / Browser / MCP / A2A 验证 Runtime 能力。
不要把“每个数字员工一套独立 agentic 部署”作为长期主架构。
```

中期应回到 `llmops` 主产品线：

```text
在 llmops 中新增数字员工实例模型。
在 llmops 中新增 Skill 层。
将 Knowledge / Tool / Workflow 统一挂到 Skill 和数字员工实例下。
将 agentic 的 Runtime 能力拆成受控 executor。
将任务、Trace、成本、审计统一落到 llmops。
```

长期形态：

```text
一个企业部署一套统一控制面。
多个数字员工是控制面中的多个实例。
每个实例有自己的岗位、Skill、知识范围、工具权限、审批策略和发布渠道。
只有强隔离、高负载、特殊运行环境或外部团队维护的专业 Agent，才独立部署并通过 A2A 接入。
```

本轮结论：

```text
方案一可作为验证路径，但长期不要走多套独立 agentic 部署拼接。
方案二更适合作为主产品路线，但必须克制模板化和 Workflow 化。
最佳路线是 llmops 统一管数字员工，agentic 提供可治理的执行能力。
```

## 19. 待继续明确的问题

后续需要继续讨论并落文档的问题：

```text
第一批目标岗位选择哪些？
岗位模板是面向行业还是通用职能？
Workflow 是先自研轻量版本还是直接接入现成引擎？
RAG 第一阶段选哪类企业资料接入？
是否需要多租户 SaaS，还是私有化部署优先？
数字员工是否需要独立账号身份？
高风险工具审批如何设计？
企业连接器优先接哪些系统？
前端产品形态是员工市场、任务台，还是管理控制台优先？
```

本文档作为后续产品定义、架构设计和迭代拆解的基准。
