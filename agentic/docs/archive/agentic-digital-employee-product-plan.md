# Agentic 自部署数字员工产品规划

> 归档说明：本文是早期产品规划，已被 `../roadmap.zh-CN.md` 合并收敛。

本文档归档本轮关于 `agentic` 产品方向的讨论结论。核心判断是：`agentic` 不只是学习模板，它已经具备成为自部署数字员工 / 自主 Agent 产品的基础。后续不应简单把它做成重型 LLMOps 配置平台，而应围绕“可自部署、会执行、可扩展、可发布、可复盘”的数字员工体验补齐产品能力。

## 1. 产品定位

`agentic` 的推荐定位：

```text
自部署数字员工产品 =
Agent Runtime
+ Skill
+ Knowledge
+ Tool / MCP / A2A
+ Trace
+ Web App / OpenAPI / A2A 发布
+ 轻量治理
```

它的优势不在于配置项多，而在于执行能力完整：

```text
Planner / ReAct
Sandbox
Browser
Shell
File
MCP
A2A
VNC
SSE 事件流
工具调用过程展示
```

因此 `agentic` 可以对标入口型、自部署型 Agent 产品。后续如果补齐 Skill、Knowledge、Trace、发布和轻治理能力，有机会比普通聊天 Agent 或单纯工具编排产品更适合企业私有化交付。

## 2. 与 llmops 的边界

`llmops` 更适合作为重型企业控制面和对外交付平台，强调账号、应用、Workflow、Dataset、Trace、发布、分析和治理。

`agentic` 更适合走轻量自部署产品路线，强调：

```text
真正会干活
快速部署
快速接入企业工具
支持 MCP / A2A
可观察执行过程
可发布为 Web App / OpenAPI / A2A Agent
```

因此，`agentic` 不应照搬 `llmops` 的重平台结构。它可以吸收必要的产品能力，但应保持 Runtime 优势和简单部署体验。

## 3. 不急于加入 Workflow

本轮讨论明确：`agentic` 第一阶段不建议直接加入完整 Workflow 引擎。

原因：

```text
Workflow 容易让业务逻辑变重。
Workflow 会降低探索性任务的灵活性。
企业早期对接更多依赖中间层、Adapter、MCP 或业务 API。
MCP / Tool / A2A 在很多场景下已经能覆盖早期 Workflow 的价值。
完整 Workflow 会把产品拉向流程编排平台，而不是自主数字员工。
```

企业对接的推荐方式：

```text
企业系统
  -> Adapter / 中间层
  -> MCP Tool / API Tool
  -> Skill
  -> Agent 执行
```

这种结构可以先解决大量业务自动化问题，而不必一开始构建复杂流程引擎。

Workflow 后续只在以下场景中再考虑：

```text
步骤高度稳定
输入输出结构固定
需要审批
需要超时 / 重试 / 回滚
需要 SLA
需要强审计
需要跨多人或多系统稳定协作
```

## 4. Skill 是核心抽象

`agentic` 后续应优先补齐 `Skill`，而不是先补 Workflow。

Skill 是数字员工可对外表达的能力，例如：

```text
准备客户拜访材料
总结会议纪要
分析网页竞品信息
整理候选人简历
查询企业知识库
生成报告
调用企业系统创建任务
```

推荐 Skill 模型：

```text
skills
  id
  name
  description
  input_schema
  output_schema
  implementation_type
  implementation_config
  allowed_tools
  knowledge_scope
  risk_level
  status
```

`implementation_type` 第一阶段建议支持：

```text
prompt
rag
tool
mcp
a2a
composite
```

暂不把 `workflow` 作为第一阶段实现类型。后续可以加入 `runbook` 或 `procedure` 作为轻量步骤描述，再根据实际需求演进到 Workflow。

## 5. Knowledge 能力

企业数字员工如果没有企业知识，只是通用 Agent。`agentic` 后续应补齐轻量 Knowledge 能力。

第一阶段建议能力：

```text
知识库创建
文档上传
文档解析
切分
索引
检索
引用来源展示
按 Agent / Skill 绑定知识范围
```

第一阶段可以先做轻量权限：

```text
每个 Agent Instance 绑定可访问 knowledge_bases。
每个 Skill 绑定 knowledge_scope。
回答时返回 source、document_id、chunk_id、score。
```

暂不强求完整企业 ACL，但数据结构应预留：

```text
organization_id
workspace_id
owner_id
visibility_scope
permission_scope
```

## 6. 多数字员工实例

`agentic` 不建议长期采用“一个数字员工一套独立部署”的方式。

推荐方式：

```text
一个 agentic 平台
  -> 多个 AgentTemplate
  -> 多个 AgentInstance
  -> 每个实例绑定 Skill / Knowledge / Tool Policy / ModelConfig
```

复制数字员工应是复制配置实例，而不是复制部署：

```text
复制模板
生成新实例
修改岗位说明
绑定知识库
绑定 Skills
配置工具范围
发布 endpoint
```

推荐新增模型：

```text
agent_templates
agent_instances
agent_instance_skills
agent_instance_knowledge
agent_instance_tool_policies
```

这样可以保留 `agentic` 的轻量部署优势，同时避免后期出现多套实例难以治理的问题。

## 7. Run / Trace / 分析

当前 `agentic` 已经有会话事件和工具事件，但还需要产品化的执行记录。

建议从 `sessions.events` 中逐步沉淀以下独立对象：

```text
agent_runs
run_steps
tool_calls
model_calls
trace_events
artifacts
```

第一阶段 Trace 目标：

```text
能看到用户输入。
能看到 Planner 生成的计划。
能看到每个 Step 的状态。
能看到每次 Tool / MCP / A2A 调用。
能看到模型调用耗时和错误。
能看到产物文件。
能复盘失败原因。
```

分析面板可以先做轻量指标：

```text
运行次数
成功率
平均耗时
工具调用次数
失败原因分布
高风险工具调用次数
模型 token / 成本
```

## 8. 模型配置与密钥管理

当前配置不应长期依赖单一 `config.yaml`。

建议补齐：

```text
模型供应商配置
默认模型
Agent 级模型覆盖
Skill 级模型覆盖
API Key 加密保存
敏感字段脱敏展示
运行时解密注入
```

第一阶段可以采用单租户本地加密配置，不必一开始做复杂多租户密钥系统。

## 9. 发布能力

`agentic` 应支持把一个 AgentInstance 发布为可用入口。

建议发布类型：

```text
Web App
OpenAPI
A2A Agent
嵌入式 Chat Widget
```

第一阶段优先级：

```text
1. Web App 发布
2. OpenAPI Chat
3. A2A Agent Card / message/send
4. Chat Widget
```

发布后应能配置：

```text
发布名称
公开 / 私有访问
访问 token
默认 AgentInstance
是否展示工具过程
是否允许上传文件
是否允许高风险工具
```

## 10. 轻量 Tool Policy

`agentic` 已有 ToolConfig、ToolRegistry 和 FilteredTool，后续应强化为轻量 Tool Policy。

建议能力：

```text
按 AgentInstance 控制可用工具。
按 Skill 控制可用工具。
按 executor_type 控制 builtin / api / mcp / a2a / sandbox。
标记风险等级。
高风险工具可要求用户确认。
记录每次工具调用。
```

第一阶段不需要完整企业审批流，但至少要支持：

```text
allow
deny
confirm_required
```

高风险工具包括：

```text
Shell
Browser 自动操作
文件写入
MCP 写操作
A2A 调用外部 Agent
API 写操作
```

## 11. Workflow-lite 后门

虽然第一阶段不建议加入完整 Workflow，但可以保留轻量 Runbook / Procedure 能力。

它不是流程引擎，而是 Skill 的执行指导：

```text
skill_steps
  - clarify_input
  - retrieve_knowledge
  - call_tool
  - generate_result
  - ask_confirmation
```

特征：

```text
不做可视化流程画布。
不做复杂 DAG。
不做长事务。
不做回滚引擎。
只作为 Agent 执行时的步骤提示和约束。
```

等某些 Skill 被客户长期稳定使用后，再考虑沉淀为真正 Workflow。

## 12. 推荐实施阶段

### 阶段 1：产品化最小闭环

目标：从通用 Agent Demo 升级为可自部署数字员工产品。

优先事项：

```text
AgentTemplate / AgentInstance
Skill 基础模型
Knowledge 基础模型
Agent 绑定 Skill / Knowledge / Tool
Run / Trace 独立记录
模型配置 UI
Web App 发布
OpenAPI Chat
```

### 阶段 2：企业接入能力

目标：让数字员工可以接入企业系统并稳定执行。

优先事项：

```text
MCP Server 管理增强
API Tool / Adapter 接入
A2A Agent 发布与调用
轻量 Tool Policy
高风险动作确认
引用来源展示
运行分析面板
```

### 阶段 3：多员工与治理

目标：支持一个部署内管理多个数字员工。

优先事项：

```text
员工模板市场
员工复制
Skill 复制与版本
Knowledge Scope
Agent 级 Tool Policy
发布渠道管理
轻量审计日志
成本统计
```

### 阶段 4：Workflow / SOP 演进

目标：只对成熟、稳定、高频、高风险的 Skill 增加 Workflow 能力。

优先事项：

```text
Runbook / Procedure
Skill Steps
Approval Point
Retry Policy
Workflow executor
```

## 13. 当前结论

```text
agentic 是值得继续强化的自部署 Agent 产品。
它不应过早变成重型 LLMOps 平台。
Skill 和 Knowledge 是第一优先级。
Workflow 暂缓，先用 MCP / Tool / A2A / Adapter / Skill 解决企业接入和业务执行。
多数字员工应通过平台内实例化管理，而不是复制多套独立部署。
Trace、发布、模型配置和轻量 Tool Policy 是产品化闭环的关键。
```
