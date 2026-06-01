# Agent 架构主流设计：Router / Worker 双类型模型

更新时间：2026-05-13

本文独立说明企业级 Agent 平台的主流多 Agent 架构设计，并给出本项目推荐采用的收敛方案：

```text
1. Agent 类型只保留 Router 与 Worker。
2. Router 默认采用 manager 模式，不把对话控制权永久交给 Worker。
```

这里的“主流”不是指某一个框架的完整复刻，而是从 OpenAI Agents SDK、LangGraph、AutoGen、Google ADK 等多 Agent 设计中提炼出的共性模式：用一个可控的调度者管理任务拆解和结果汇总，用多个专业执行单元完成具体任务，再用工具、工作流、知识库、MCP、沙箱等能力层承载外部动作。

## 1. 核心结论

企业级 Agent 平台不建议把每一种能力都设计成 Agent，也不建议让所有 Agent 自由互相调用。

推荐模型：

```text
用户入口
  -> Router Agent
  -> Task Engine
  -> Worker Agent
  -> Capability Layer
  -> 企业系统 / 知识库 / 沙箱 / 外部服务
```

Agent 运行时只保留两类：

| 类型 | 定位 | 核心职责 |
| --- | --- | --- |
| Router Agent | 调度型 Agent | 理解意图、拆解任务、选择 Worker、控制执行流程、汇总最终答案 |
| Worker Agent | 执行型 Agent | 完成专业子任务、调用工具和知识、返回结构化结果 |

非 Agent 能力：

| 能力 | 定位 |
| --- | --- |
| Task Engine | 状态机、调度、重试、超时、审批、恢复、事件流 |
| Capability Registry | 工具、工作流、知识库、Skill、MCP、沙箱的统一注册中心 |
| Tool Gateway | 工具调用、参数校验、二次鉴权、幂等、审计 |
| Knowledge Service | RAG 检索、权限过滤、引用、检索审计 |
| Approval / Policy | 高风险动作审批、数据范围、字段脱敏、限流和预算 |
| Trace / Evaluation | 调用链、成本、失败定位、效果评测 |

## 2. 主流设计模式对照

主流多 Agent 框架通常会提供以下几类能力：

| 主流模式 | 常见叫法 | 本项目映射 |
| --- | --- | --- |
| 中央调度者 | supervisor、manager、coordinator、planner | Router Agent |
| 专家执行者 | specialist、assistant、worker、delegate | Worker Agent |
| Agent 作为工具 | agent-as-tool、delegate call | Router 调用 Worker，Worker 返回结果 |
| 会话移交 | handoff、handover、transfer | 受控例外，不作为默认模式 |
| 群聊协调 | group chat manager、round robin、selector | Task Engine + Router 控制执行顺序 |
| 工具调用 | function calling、tool calling、MCP tool | Capability + Tool Gateway |
| 守护与审批 | guardrails、human approval、policy | Approval / Policy |

本项目推荐采用“manager / supervisor”作为默认模式：

```text
Router 保持对会话和任务的控制权。
Worker 只处理被分配的子任务。
Worker 完成后返回结构化结果。
Router 汇总后再决定下一步或最终回复。
```

不推荐把“handoff”作为默认模式：

```text
Router 不应把用户会话永久移交给某个 Worker。
Worker 不应长期接管对话上下文。
多个 Worker 不应自由轮流控制用户对话。
```

## 3. 为什么只保留两类 Agent

如果平台把 Router、Worker、Workflow、Tool、Skill、Knowledge、MCP、Sandbox、Hybrid 都设计成 Agent，会带来几个问题：

1. 产品概念膨胀，用户难理解“我到底在创建什么”。
2. 运行时拓扑失控，Agent 之间自由通信难以审计。
3. 权限边界模糊，工具、知识和外部系统调用容易绕过治理。
4. 任务失败难定位，不清楚是计划、执行、工具还是数据问题。
5. 版本、评测、回滚、成本统计都变复杂。

两类 Agent 足够表达主流企业场景：

```text
Router 解决“谁来做、按什么顺序做、结果怎么汇总”。
Worker 解决“具体任务怎么做、调用什么能力、返回什么证据”。
Capability 解决“真正访问系统、知识、工具、沙箱的动作”。
Task Engine 解决“可靠执行和状态管理”。
```

产品上可以有很多“业务 Agent 类型”，例如销售、财务、HR、合同、知识问答、数据分析，但这些应是模板或分类，不是新的运行时类型。

```text
销售助手 Agent    = Router 模板 + 销售 Worker 组合
财务分析 Agent    = Router 模板 + 数据分析 Worker 组合
知识问答 Agent    = Worker 模板 + Knowledge Capability
合同审查 Agent    = Worker 模板 + 合同知识库 + 审查 Skill
工单处理 Agent    = Router 模板 + 分类 Worker + 执行 Worker
```

## 4. Router Agent 设计

### 4.1 定位

Router Agent 是任务调度者和会话控制者。

它负责：

1. 理解用户意图。
2. 判断是否需要追问、拒绝或审批。
3. 生成结构化 Plan。
4. 选择一个或多个 Worker。
5. 决定串行、并行或条件执行。
6. 接收 Worker 结果。
7. 处理失败、降级、重试、澄清、审批。
8. 汇总最终答案。
9. 控制对用户可见的信息。

它不负责：

1. 直接调用企业 API。
2. 直接修改数据库。
3. 直接执行代码。
4. 直接读取未授权知识。
5. 保存底层执行状态。
6. 长时间把会话交给 Worker。

### 4.2 Manager 模式

Router 默认使用 manager 模式。

```text
User -> Router
Router -> Worker A
Worker A -> Router
Router -> Worker B
Worker B -> Router
Router -> User
```

特点：

1. Router 始终拥有任务控制权。
2. Worker 调用像“函数调用”或“子任务调用”。
3. Worker 只返回结构化结果，不直接决定最终用户回复。
4. Router 可以组合多个 Worker 的结果。
5. Trace 和权限链路更清晰。

### 4.3 Handoff 例外

handoff 不是默认模式，只作为受控例外。

适用场景：

1. 某个专业 Worker 需要和用户短时间多轮澄清。
2. 用户明确进入某个垂直业务域。
3. Router 已经确认该 Worker 有完整权限和上下文。

必须加限制：

```text
delegated_chat = true
max_turns = 3
return_to_router_on = task_completed / need_approval / uncertainty / timeout
worker_visible_scope = current_task_only
audit_required = true
```

handoff 结束后必须回到 Router，由 Router 决定最终输出或下一步。

## 5. Worker Agent 设计

### 5.1 定位

Worker Agent 是专业执行者。

```text
Worker Agent = Role + Goal + Domain Context + Capability Scope + Loop Policy + Output Schema
```

它负责：

1. 理解 Router 派发的子任务。
2. 判断任务是否在自身职责范围内。
3. 调用允许的 Capability。
4. 执行 ReAct / tool calling 循环。
5. 根据停止条件结束。
6. 返回结构化结果、证据、产物和错误。

它不负责：

1. 修改 Router 的全局计划。
2. 自由调用其他 Worker。
3. 绕过 Capability Gateway。
4. 绕过权限和审批。
5. 直接决定最终用户答复。
6. 无限循环或无限工具调用。

### 5.2 Worker 分类

Worker 可以有多种业务模板，但底层类型仍然是 Worker。

| Worker 模板 | 典型能力 |
| --- | --- |
| Knowledge Worker | RAG、引用、摘要、问答 |
| Tool Worker | 企业 API、OpenAPI Tool、MCP Tool |
| Workflow Worker | 固定 SOP、流程执行、表单流转 |
| Data Worker | SQL、表格、图表、数据报告 |
| Review Worker | 合同、合规、质量审查 |
| Content Worker | 文案、邮件、报告、翻译 |
| Sandbox Worker | Python、SQL、文件处理、隔离执行 |
| Integration Worker | CRM、ERP、OA、消息系统集成 |

### 5.3 Worker Loop Policy

Worker 必须有明确的执行上限。

```json
{
  "mode": "react",
  "max_steps": 8,
  "max_tool_calls": 6,
  "timeout_seconds": 120,
  "stop_conditions": [
    "task_completed",
    "need_clarification",
    "need_approval",
    "tool_limit_reached",
    "confidence_too_low",
    "policy_violation"
  ],
  "retry_policy": {
    "max_retries": 2,
    "retry_on": ["timeout", "rate_limited", "temporary_tool_error"]
  }
}
```

### 5.4 Worker 结果协议

Worker 不应只返回自然语言。

推荐结果：

```json
{
  "schema_version": "worker_result_v1",
  "worker_id": "quotation_worker",
  "status": "success",
  "summary": "已生成报价草案。",
  "data": {
    "quote_total": 128000,
    "currency": "CNY"
  },
  "evidence": [
    {
      "type": "tool_result",
      "source": "price_policy_query",
      "ref_id": "capability_call_001"
    }
  ],
  "artifacts": [
    {
      "type": "file",
      "name": "quote_draft.xlsx",
      "object_key": "artifacts/quote_draft.xlsx"
    }
  ],
  "actions": [
    {
      "action_type": "send_quote_to_customer",
      "status": "not_executed",
      "requires_approval": true
    }
  ],
  "confidence": 0.86,
  "retryable": false,
  "error_code": null,
  "errors": [],
  "used_capabilities": ["price_policy_query", "inventory_query"]
}
```

## 6. Task Engine 设计

Task Engine 不是 Agent。

它负责确定性执行：

```text
Plan 持久化
Step 状态机
Worker Call 调度
Capability Call 记录
审批等待
超时控制
重试
取消
恢复
回放
事件流
成本统计
```

状态建议：

```text
created
queued
running
waiting_approval
waiting_user_clarification
succeeded
partially_succeeded
failed_retryable
failed_final
cancelled
expired
```

Router 负责智能决策，Task Engine 负责可靠执行。两者不要混在一起。

## 7. Capability Layer 设计

Capability 是 Worker 可调用的能力，不是 Agent。

类型：

```text
tool
workflow
skill
knowledge_base
mcp_tool
mcp_resource
sandbox
agent_tool
```

其中 `agent_tool` 只是受控例外：把某个 Worker 包装成能力供另一个 Worker 调用，必须限制深度和权限。

Capability 元数据必须包含：

```text
input_schema
output_schema
permission
risk_level
side_effect
requires_approval
idempotency_required
timeout_seconds
retry_policy
data_scope_policy
audit_policy
version
enabled
```

副作用分级：

| 等级 | 含义 | 默认治理 |
| --- | --- | --- |
| none | 纯计算或格式转换 | 自动执行 |
| read | 读取数据 | 权限校验后执行 |
| write | 修改内部系统数据 | 按风险审批 |
| external | 对外发送或外部影响 | 默认审批 |
| critical | 高危动作 | 强制人工确认 |

## 8. 推荐主链路

### 8.1 同步调试链路

```text
User
  -> Router Agent
  -> Router Plan
  -> Task Engine creates steps
  -> Worker Agent executes step
  -> Capability Gateway calls tool / knowledge / workflow
  -> Worker Result
  -> Router Summary
  -> User
```

### 8.2 异步生产链路

```text
User / API
  -> Create Task
  -> Celery enqueue
  -> Task Engine runs Plan
  -> Worker Runtime executes
  -> Redis Stream publishes events
  -> SSE / WebSocket streams progress
  -> Final Result
```

### 8.3 审批链路

```text
Worker proposes high-risk action
  -> Capability Gateway detects approval requirement
  -> Task Engine pauses step
  -> Approval Request created
  -> Approver approves / rejects
  -> Tool Gateway executes with approval token
  -> Task Engine resumes
  -> Router summarizes final result
```

## 9. 权限与审计

权限链路：

```text
User
  -> Tenant / Workspace
  -> Router visibility
  -> Router allowed Workers
  -> Worker allowed Capabilities
  -> Capability permission and risk policy
  -> Tool Gateway / Knowledge Service / Sandbox Gateway
  -> Enterprise system final auth
```

审计链路：

```text
trace_id
session_id
task_id
plan_id
step_id
worker_call_id
capability_call_id
approval_request_id
artifact_id
```

必须记录：

1. Router 生成的 Plan。
2. Worker Invocation 和 Worker Result。
3. Capability 调用输入输出。
4. 权限、脱敏、审批决策。
5. token、成本、耗时。
6. 失败原因和重试记录。

## 10. 反模式

需要避免：

1. 设计一个无所不能的超级 Agent。
2. 允许所有 Agent 自由互调。
3. 把 Workflow、Tool、Skill、Knowledge 都包装成 Agent。
4. Router 直接调用企业 API 或数据库。
5. Worker 返回不可解析的纯文本。
6. 默认 handoff，让 Worker 长期接管用户会话。
7. 没有 Task Engine，把状态交给大模型记忆。
8. 工具调用没有权限、审批、幂等和审计。
9. RAG 只做向量检索，不做权限过滤和引用。
10. 一开始就拆成大量微服务。

## 11. 本项目落地建议

结合当前 `llmops` 项目，建议映射为：

| 当前能力 | 目标架构位置 |
| --- | --- |
| `app/model/app.py` App / AppConfig | 迁移或映射为 Agent / AgentVersion |
| `core/agent/*` ReAct / FunctionCall | Worker Runtime 基础 |
| `service/assistant_agent_service.py` | 可演进为 Router 调试入口或内置助手 |
| `core/workflow/*` | Workflow Capability |
| `core/tools/*` | Tool Capability + Tool Gateway |
| `service/retrieval_service.py` / Weaviate | Knowledge Capability |
| `app/task/*` Celery | Task Engine 异步执行层 |
| `MessageAgentThought` | TraceEvent 的早期基础 |

落地顺序：

1. 定义 Agent Registry：`router` / `worker` 两类。
2. 定义 Capability Registry：包装现有 Tool、Workflow、Dataset。
3. 定义 Router Plan 和 Worker Result JSON Schema。
4. 新增 Task Engine 最小状态机。
5. 让 Router 以 manager 模式调用 Worker。
6. Worker 经 Capability Gateway 调用工具和知识。
7. 接入 Approval、Trace、Evaluation。

## 12. 参考资料

以下资料用于提炼主流设计模式，落地时不要求作为底层强依赖：

1. OpenAI Agents SDK Orchestration：`https://developers.openai.com/api/docs/guides/agents/orchestration`
2. OpenAI Agents SDK Guardrails and Approvals：`https://developers.openai.com/api/docs/guides/agents/guardrails-approvals`
3. LangGraph Multi-agent / Supervisor：`https://langchain-ai.github.io/langgraphjs/reference/modules/langgraph-supervisor.html`
4. Microsoft AutoGen Group Chat Design Pattern：`https://microsoft.github.io/autogen/stable/user-guide/core-user-guide/design-patterns/group-chat.html`
5. Google Agent Development Kit Multi-agent Systems：`https://google.github.io/adk-docs/agents/multi-agents/`

