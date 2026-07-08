# Agentic 增强型 Agent 路线

本文档用于把 `agentic` 的近期方向从“企业平台化蓝图”收敛为“增强型 Agent 产品路线”。当前判断是：先不以 `llmops` 为主线，也不优先补完整 Workflow，而是基于 `agentic` 现有 Planner/ReAct、Sandbox、Browser、Shell、File、MCP、A2A 和 SSE 事件流，做一个更能执行、更可配置、更可复盘的增强型 Agent。

## 1. 核心判断

`llmops` 的控制面比较完整，但它的 Workflow 和应用配置心智偏重，容易把产品推向“平台配置系统”。如果当前目标是先做一个真正能干活、能自部署、能灵活接企业工具的 Agent，`agentic` 更适合作为主线。

推荐定位：

```text
增强型 Agent =
Planner/ReAct 执行内核
+ Tool / MCP / A2A / Sandbox
+ Agent Profile
+ Skill / Runbook
+ Knowledge
+ Tool Policy
+ Run / Trace
+ 发布入口
```

短期不要把它做成完整 LLMOps 平台，也不要把 Workflow 作为第一抽象。第一抽象应该是 Agent Profile 和 Skill。

## 2. 产品边界

第一阶段做的是“一个增强型 Agent”，不是“多租户企业数字员工平台”。

它应该先回答：

```text
这个 Agent 是谁？
默认模型和行为是什么？
能调用哪些工具？
有哪些可复用 Skill？
能查哪些知识？
执行过程是否可追踪？
高风险动作是否可确认？
能否通过 Web / API / A2A 使用？
```

暂时不优先回答：

```text
多个企业租户如何隔离？
复杂 RBAC 如何设计？
流程画布如何拖拽？
多个部门如何分级管理？
完整审批流如何配置？
```

这些可以后续演进，但不应该挡住增强型 Agent 的第一版。

## 3. 为什么不先做 Workflow

当前不建议在 `agentic` 中优先加入完整 Workflow 引擎，原因是：

```text
Workflow 会把灵活执行变成流程配置。
Workflow 对业务建模要求高，早期容易过度设计。
Workflow 的稳定性来自长期沉淀，不适合一开始套所有任务。
`agentic` 的核心优势是自主执行、浏览器、Shell、文件、MCP、A2A 和沙箱。
```

更合适的顺序是：

```text
自然语言任务
  -> Planner/ReAct
  -> Skill 约束能力边界
  -> Runbook 提供轻量步骤指导
  -> Tool Policy 控制风险
  -> Trace 记录过程
```

等某个 Skill 被频繁使用、步骤稳定、输入输出固定、需要审批或回滚时，再沉淀为 Workflow。

## 4. 核心抽象

### 4.1 Agent Profile

Agent Profile 是增强型 Agent 的身份和默认行为，不等同于一次会话的 prompt。

建议字段：

```text
agent_profiles
  id
  name
  description
  system_prompt
  model_config
  default_tool_policy_id
  default_knowledge_scope
  default_skill_ids
  publish_config
  status
```

第一版可以先不入库，继续使用配置文件或现有 AppConfig 承载；但代码结构上应把它当成独立概念。

### 4.2 Skill

Skill 是用户和 Agent 都能理解的能力单元，不是 Workflow 节点。

建议字段：

```text
skills
  id
  name
  description
  trigger_examples
  input_schema
  output_schema
  instruction
  allowed_tools
  knowledge_scope
  risk_level
  runbook
  status
```

`implementation_type` 第一阶段建议支持：

```text
prompt
rag
tool
mcp
a2a
runbook
composite
```

暂不把 `workflow` 放在第一阶段主路径里。

### 4.3 Runbook

Runbook 是轻量 SOP，不是流程引擎。

它可以是 Skill 内的一组步骤提示：

```text
runbook:
  - clarify_input
  - retrieve_knowledge
  - inspect_files
  - call_tool
  - generate_result
  - ask_confirmation
```

运行时仍由 ReAct Agent 判断和执行，不需要先实现 DAG 调度器、长事务、回滚、流程画布。

### 4.4 Tool Policy

增强型 Agent 最大的风险来自强执行工具。必须把工具治理前置。

建议先按现有 `tool-management-landing-plan.md` 落地：

```text
ToolRegistry
ToolConfig
FilteredTool
ToolFactory
CapabilitySummary
Preflight
```

第一阶段策略：

```text
allow
deny
confirm_required
```

高风险工具：

```text
shell_execute
shell_write_input
shell_kill_process
write_file
replace_in_file
browser_console_exec
MCP 写操作
A2A 远程调用
API 写操作
```

### 4.5 Knowledge

增强型 Agent 如果没有知识，只是通用执行器。

第一版 Knowledge 不需要完整企业 ACL，但要能绑定到 Agent Profile 或 Skill：

```text
knowledge_bases
knowledge_documents
knowledge_chunks
knowledge_indexes
knowledge_bindings
```

检索结果至少返回：

```text
content
source
document_id
chunk_id
score
updated_at
```

### 4.6 Run / Trace

当前 `sessions.events` 可以继续保留，但增强型 Agent 需要逐步沉淀标准运行记录。

建议新增或规划：

```text
agent_runs
run_steps
tool_calls
model_calls
trace_events
artifacts
```

第一版 Trace 重点不是报表，而是复盘：

```text
用户输入是什么？
Planner 计划是什么？
ReAct 执行了哪些步骤？
调用了哪些工具？
工具输入输出摘要是什么？
有没有确认或拒绝？
最终产物在哪里？
失败原因是什么？
```

## 5. 推荐实施顺序

### Phase 1：工具治理先落地

目标：保留现有执行能力，但让工具可见、可诊断、可配置。

优先任务：

```text
ToolRegistry
ToolConfig schema
CapabilitySummary
Preflight
Settings Tools tab
FilteredTool
ToolFactory
```

完成标准：

```text
UI 能看到所有内置工具、风险等级和启用状态。
禁用工具后，LLM 不再看到该工具 schema。
调用被禁用工具时返回结构化失败。
高风险工具可以进入 confirm_required 策略。
旧配置默认保持兼容。
```

### Phase 2：Agent Profile

目标：让系统从“一个硬编码通用 Agent”变成“可配置增强型 Agent”。

优先任务：

```text
Agent Profile 数据结构
默认 Agent Profile
profile 级 system prompt
profile 级 model config
profile 级 tool policy
profile 级 MCP/A2A 配置引用
会话绑定 agent_profile_id
```

第一版可以单用户、单默认 Profile，不急于做多租户。

### Phase 3：Skill / Runbook

目标：把可复用能力沉淀出来，但不引入复杂 Workflow。

优先任务：

```text
Skill 定义
Skill 列表和启停
Skill instruction 注入
Skill allowed_tools
Skill runbook
Skill 触发匹配
```

执行方式：

```text
用户请求
  -> skill selector
  -> 注入 skill instruction / runbook / allowed_tools
  -> Planner/ReAct 执行
  -> Trace 记录 skill_id
```

### Phase 4：Knowledge

目标：让增强型 Agent 能使用本地或企业资料。

优先任务：

```text
知识库创建
文档上传
文本抽取
chunking
embedding / keyword index
检索工具
引用来源展示
Agent / Skill 绑定 knowledge scope
```

第一版可先做本地知识库，不急于做企业 ACL。

### Phase 5：Run / Trace 标准化

目标：把执行过程从 `sessions.events` 中逐步拆出，支持复盘和调试。

优先任务：

```text
agent_runs
run_steps
tool_calls
model_calls
trace_events
artifacts
```

前端先做执行时间线，不急于做复杂运营报表。

### Phase 6：发布入口

目标：让增强型 Agent 可以被外部使用。

优先级：

```text
Web App
OpenAPI Chat
A2A Agent Card / message/send
Chat Widget
```

发布配置至少包含：

```text
发布名称
默认 Agent Profile
访问 token
是否允许上传文件
是否展示工具过程
是否允许高风险工具
```

## 6. 数据库演进建议

当前 `agentic` 只有 `sessions` 和 `files`，不要一次性搬入 `llmops` 的全套表。

推荐顺序：

```text
tool_config 先继续配置文件化
agent_profiles
skills
knowledge_bases / documents / chunks
agent_runs / run_steps / tool_calls / trace_events
publish_endpoints / api_tokens
users / auth
organizations / workspaces
```

如果短期是自部署单用户产品，认证可以后置；但文件访问、VNC、Shell、发布 token 一旦暴露到外部，就必须补最小认证和授权。

## 7. 与 llmops 的关系

`llmops` 可以继续作为参考，但不是当前主线。

可借鉴：

```text
工具注册和绑定
能力摘要
preflight
任务 Trace
发布入口
模型配置 UI
```

不建议照搬：

```text
重型 App / Workflow 配置心智
复杂空间/团队/权限模型
完整审批流
过早的平台运营分析
```

当前更重要的是保持 `agentic` 的执行优势，不要把它做成另一个配置平台。

## 8. 近期最小闭环

建议最近一个开发周期只做这个闭环：

```text
增强型 Agent v0 =
现有 Planner/ReAct
+ 可视化工具清单
+ 工具启停和风险策略
+ preflight 诊断
+ 默认 Agent Profile
+ 轻量 Skill instruction
+ 执行 Trace 初步结构化
```

这条线完成后，`agentic` 就不再只是通用 Agent Demo，而是一个可管理、可解释、可逐步产品化的增强型 Agent。

## 9. 当前结论

```text
先基于 agentic 做增强型 Agent 是合理路线。
Workflow 暂缓，不作为第一阶段核心能力。
优先做 Tool Policy、Agent Profile、Skill/Runbook、Knowledge、Trace 和发布。
不要复制 llmops 的重控制面，但要吸收它的治理经验。
第一阶段保持单用户/自部署心智，后续再扩展到多 Agent、多用户和企业治理。
```
