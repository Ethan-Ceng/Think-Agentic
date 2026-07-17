# Agentic 产品路线

整理日期：2026-07-09

本文合并旧的数字员工产品规划和增强型 Agent 路线，保留一个主线：先把 `agentic` 做成可自部署、会执行、可配置、可复盘的增强型 Agent，不照搬重型 LLMOps 平台。

## 1. 产品定位

推荐定位：

```text
自部署增强型 Agent =
Planner / ReAct 执行内核
+ Sandbox / Browser / Shell / File
+ MCP / A2A / API Tool
+ 用户级配置
+ Tool Policy
+ Run / Trace
+ Agent Profile
+ Skill / Runbook
+ Knowledge
+ 发布入口
```

`agentic` 的优势不是配置项数量，而是真正能执行任务：沙箱、浏览器、Shell、文件、MCP、A2A 和 SSE 过程展示已经构成运行时基础。

## 2. 不做什么

第一阶段不建议做：

- 重型 LLMOps 控制台。
- 复杂多租户组织/工作区/RBAC。
- Workflow 画布和完整流程引擎。
- 完整审批流和企业运营分析。

这些能力可以后续演进，但不应阻塞增强型 Agent 的第一版产品闭环。

## 3. 已完成基线

以下内容已从“规划”变成当前基线：

- 用户注册、登录、JWT 当前用户。
- `sessions` / `files` 用户隔离。
- 用户级 `configs` 表。
- LLM、Agent、MCP、A2A、Tool 配置按用户读取。
- 工具管理 UI/API。
- 工具启停、注册、能力摘要、preflight。
- 工具执行过滤。

因此旧文档中“先做用户隔离”和“工具管理 Phase 1/2”的大部分内容应视为已完成或部分完成。

## 4. 推荐实施顺序

对比 `llmops` 后，当前优先级需要前移的是 Run / Trace 最小账本。原因是内置工具治理和自定义 API 工具源已经进入运行时，但还缺少稳定的 `agent_runs`、`run_steps`、`tool_calls`、`model_calls` 和 `trace_events` 来支撑复盘、审计和后续审批。

详细落地调研见：[run-trace-tooling-research.zh-CN.md](run-trace-tooling-research.zh-CN.md)。

### Phase 1：Run / Trace 标准化

目标：把执行过程从 `sessions.events` 中逐步拆出，支持复盘、调试和轻量审计。

当前状态：最小闭环已经落地，包含 migration、ORM、repository、TraceService、运行时事件投影、`model_calls` 观测、`/api/runs` 查询接口，以及会话页 Trace 侧边面板；更细审计策略仍待补。

建议对象：

```text
agent_runs
run_steps
tool_calls
model_calls
trace_events
```

第一版重点不是复杂报表，而是回答：

- 用户输入是什么？
- Planner 计划是什么？
- ReAct 执行了哪些步骤？
- 调用了哪些工具？
- 工具输入输出摘要是什么？
- 调用了哪些模型，token、耗时、失败原因是什么？
- 是否发生确认、拒绝或失败？
- 最终产物在哪里？

落地方式应贴合 `agentic` 当前实现：

- 保留 `sessions.events` 作为 UI/SSE 兼容层。
- 在 `AgentTaskRunner._put_and_add_event()` 投影 `PlanEvent`、`StepEvent`、`ToolEvent`、`MessageEvent`、`WaitEvent`、`ErrorEvent`、`DoneEvent`。
- 在 `BaseAgent._invoke_llm()` 或 `OpenAILLM.invoke()` 附近补 `model_calls`。
- `tool_calls` 使用 `ToolRegistry.resolve_binding()` 解析稳定 `tool_id`、`executor_type`、`risk_level`。
- 自定义 API 工具调用必须保存 `provider_id`、`registration_id` 和调用时配置快照，避免用户后续修改注册配置导致历史记录失真。

剩余工作：

- 审计保存策略配置。
- 工具配置变更审计。
- 高风险工具确认与 Trace/审批记录关联。

### Phase 2：Agent Profile

目标：让系统从“一个通用 Agent”变成“可配置的增强型 Agent”。

建议能力：

```text
agent_profiles
  id
  user_id
  name
  description
  system_prompt
  model_config
  default_tool_policy
  default_knowledge_scope
  default_skill_ids
  status
```

第一版可以只做单用户、多 profile，不急于引入组织/工作区。

关键改造：

- 会话绑定 `agent_profile_id`。
- Agent Profile 可以覆盖 system prompt、model config、tool config 引用。
- UI 能创建、复制、启停和选择默认 Profile。

### Phase 3：Skill / Runbook

目标：把可复用能力沉淀出来，但不引入复杂 Workflow。

实施状态（2026-07-16，按验收阶段分别确认）：

- Phase A 已完成：个人 Skill 的导入、隔离编辑、校验、不可变版本、手动/自动选择、Sandbox 物化和 Trace 已通过回归与双用户验收。
- Phase B 已完成：内置 `skill-creator` 已通过官方格式校验，可创建和修订当前用户草稿；发布保持用户显式操作，失败会话可继续或重启。
- Phase C 已完成：部署方 Marketplace、用户级固定安装、显式更新和个人 Fork lineage 已通过端到端回归；首版不包含支付、评分、评论或开放自助发布。

Skill 是用户和 Agent 都能理解的能力单元，例如“整理候选人简历”“查询知识库并生成报告”“准备客户拜访材料”。

建议字段：

```text
skills
  id
  user_id
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

运行方式：

```text
用户请求
  -> skill selector
  -> 注入 skill instruction / runbook / allowed_tools
  -> Planner / ReAct 执行
  -> Trace 记录 skill_id
```

Runbook 只是轻量 SOP，不是 DAG 调度器：

```text
clarify_input
retrieve_knowledge
inspect_files
call_tool
generate_result
ask_confirmation
```

### Phase 4：Knowledge

目标：让 Agent 能使用本地或企业资料，而不是只做通用执行器。

第一版建议能力：

- 知识库创建。
- 文档上传。
- 文本抽取。
- chunking。
- embedding 或关键词索引。
- 检索工具。
- 引用来源展示。
- Agent / Skill 绑定知识范围。

建议表：

```text
knowledge_bases
knowledge_documents
knowledge_chunks
knowledge_indexes
knowledge_bindings
```

第一版不急于做完整企业 ACL，但应预留 `user_id`，后续再扩展 `organization_id`、`workspace_id`。

### Phase 5：发布入口

目标：让一个 Agent Profile 或 Agent Instance 可以被外部使用。

优先级：

```text
1. Web App 发布
2. OpenAPI Chat
3. A2A Agent Card / message/send
4. Chat Widget
```

发布配置至少包含：

- 发布名称。
- 绑定 Agent Profile。
- 访问 token。
- 是否允许上传文件。
- 是否展示工具过程。
- 是否允许高风险工具。

### Phase 6：治理增强

目标：在现有工具启停基础上补真正的治理能力。

建议能力：

- 高风险工具执行确认。
- `approval=ask/deny` 或等价策略。
- 工具调用审计日志。
- 配置变更审计。
- API key 加密存储。
- 组织、工作区、成员、角色。

这些适合在 Agent Profile、Skill、Knowledge、Trace 稳定后再做，否则容易把产品提前拖成重平台。

## 5. Workflow 判断

Workflow 暂缓，不作为第一阶段核心能力。

更合适的演进路径是：

```text
自然语言任务
  -> Planner / ReAct
  -> Skill 约束能力边界
  -> Runbook 提供步骤提示
  -> Tool Policy 控制风险
  -> Trace 记录过程
  -> 成熟 Skill 再沉淀为 Workflow
```

只有当某个 Skill 长期高频、步骤稳定、输入输出固定，并且需要审批、重试、回滚、SLA 或强审计时，才考虑 Workflow executor。

## 6. 与 llmops 的关系

`llmops` 可以继续作为参考，但不是当前主线。

可以借鉴：

- 通用 provider/tool 注册中心的产品形态和绑定关系。
- 能力摘要。
- preflight。
- Trace。
- 发布入口。
- 模型配置 UI。

不建议照搬：

- 重型 App / Workflow 配置心智。
- 复杂空间/团队/权限模型。
- 完整审批流。
- 过早运营分析。

当前更重要的是保持 `agentic` 的执行优势。
