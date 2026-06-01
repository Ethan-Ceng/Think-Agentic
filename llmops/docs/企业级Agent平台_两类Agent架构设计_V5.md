# 企业级 Agent 交付平台设计方案 V5：两类 Agent + Task Engine + 能力治理

> 定位：完全自研企业级 Agent 交付平台。Dify、Coze、OpenAI Agents SDK、MCP 等仅作为产品形态、交互模式和协议方向参考，不作为底层强依赖。
>
> 核心收敛：平台只定义两类 Agent：Router Agent 与 Worker Agent。所有 Workflow、Tool、Skill、MCP、Knowledge、Sandbox 都作为 Capability 管理。
>
> V5 重点：在 V4 的两类 Agent 架构上，补齐 Task Engine、运行协议、权限治理、审批、人类介入、可观测性和 MVP 落地路径。

---

## 1. 核心结论

企业 Agent 平台不应该演化成一张自由通信的 Agent 网络，也不应该把所有能力硬塞进一个“总 Agent”。

推荐架构：

```text
用户入口
  ↓
AI Gateway
  ↓
Router Agent Runtime
  ↓
Task Engine
  ↓
Worker Agent Runtime
  ↓
Capability Layer
  ↓
企业业务系统 / 知识库 / 隔离执行环境
```

核心角色：

```text
Router Agent：调度型 Agent，负责理解意图、规划、选择 Worker、汇总结果。
Worker Agent：执行型 Agent，负责专业任务执行、ReAct Loop、工具调用、结构化返回。
Task Engine：非 Agent，负责状态持久化、调度、重试、恢复、审批、超时控制。
Capability：非 Agent，承载 Workflow、Tool、Skill、MCP、Knowledge、Sandbox 等具体能力。
```

关键原则：

```text
1. Agent 类型只保留 Router 与 Worker。
2. Router 默认采用 manager 模式，不把对话控制权永久交给 Worker。
3. Worker 默认不主动调用其他 Worker。
4. Task Engine 管执行状态，Router 管智能决策。
5. Capability Registry 是所有工具、流程、知识和沙箱能力的统一入口。
6. 安全控制必须贯穿 User → Router → Worker → Capability → System 全链路。
```

---

## 2. 相比 V4 的关键增强

| 维度 | V4 | V5 |
|---|---|---|
| Agent 类型 | Router / Worker 两类 | 保留两类，不新增 Agent 类型 |
| 状态管理 | 提到任务中心 | 明确 Task Engine 是独立非 Agent 组件 |
| Router 模式 | 调度 Worker | 明确为 manager 模式，负责最终汇总 |
| Worker 边界 | 执行专业任务 | 增加调用协议、停止条件、失败语义 |
| Capability | 统一注册 | 增加风险等级、副作用、审批、重试、幂等字段 |
| 安全 | 权限链路 | 增加 RAG 权限、Tool 二次鉴权、审批闭环 |
| MVP | 功能列表 | 改成单一业务场景的端到端闭环 |
| 工程架构 | 多服务拆分 | 建议 MVP 先做模块化单体，后续服务化 |

---

## 3. 总体架构

```text
┌──────────────────────────────────────────┐
│ 用户入口层                                │
│ Web Chat / 企业微信 / 飞书 / API          │
└────────────────────┬─────────────────────┘
                     ↓
┌──────────────────────────────────────────┐
│ AI Gateway                               │
│ 鉴权 / 租户识别 / 限流 / 安全过滤 / 会话入口 │
└────────────────────┬─────────────────────┘
                     ↓
┌──────────────────────────────────────────┐
│ Router Agent Runtime                     │
│ 意图识别 / 任务规划 / Worker 选择 / 结果汇总 │
└────────────────────┬─────────────────────┘
                     ↓
┌──────────────────────────────────────────┐
│ Task Engine                              │
│ Plan State / Step State / Retry / Approval│
│ Async Job / Timeout / Resume / Replay     │
└────────────────────┬─────────────────────┘
                     ↓
┌──────────────────────────────────────────┐
│ Worker Agent Runtime                     │
│ ReAct Loop / Tool Calling / Stop Condition│
│ Structured Result / Evidence / Artifacts  │
└────────────────────┬─────────────────────┘
                     ↓
┌──────────────────────────────────────────┐
│ Capability Layer                         │
│ Workflow / Tool / Skill / MCP / RAG / Sandbox│
└────────────────────┬─────────────────────┘
                     ↓
┌──────────────────────────────────────────┐
│ 企业系统与执行环境                        │
│ ERP / CRM / OA / HIS / DB / Object Storage│
│ Vector DB / Container Sandbox             │
└──────────────────────────────────────────┘
```

架构核心不是“谁能调谁”，而是“谁对什么负责”：

```text
Router 负责判断和编排。
Task Engine 负责执行状态。
Worker 负责专业行动。
Capability Gateway 负责能力调用边界。
Policy / Audit 贯穿所有调用。
```

---

## 4. 角色边界

| 组件 | 类型 | 主要职责 | 不应该承担 |
|---|---|---|---|
| Router Agent | Agent | 意图识别、任务拆解、选择 Worker、汇总结果、追问用户 | 直接改业务数据、直接调企业 API、保存底层执行状态 |
| Worker Agent | Agent | 专业任务执行、ReAct Loop、调用 Capability、返回结构化结果 | 自由调度其他 Worker、修改全局 Plan、绕过权限 |
| Task Engine | 非 Agent | 状态机、异步任务、重试、恢复、审批等待、超时、回放 | 做智能决策、替代 Router 规划 |
| Capability Registry | 非 Agent | 注册能力元数据、权限、风险、输入输出 Schema | 执行业务动作 |
| Tool Gateway | 非 Agent | 工具调用、二次鉴权、参数校验、幂等、审计 | 自主规划任务 |
| Workflow Engine | 非 Agent | 固定 SOP、审批流、业务流程编排 | 替代 Worker 做开放式推理 |
| Knowledge Service | 非 Agent | 检索、权限过滤、引用、内容召回 | 无权限地暴露全文 |
| Sandbox Gateway | 非 Agent | 隔离执行代码、SQL、文件、浏览器任务 | 访问未授权网络或系统 |

---

## 5. Router Agent 设计

### 5.1 定位

Router Agent 是平台里的调度型智能体。它可以有多个，每个 Router 对应一个业务入口或业务域：

```text
企业总入口 Router
销售助手 Router
财务分析 Router
医疗质控 Router
HR 助手 Router
售后服务 Router
```

Router 不是唯一顶层 Agent，而是一类可配置、可治理、可版本化的 Agent。

### 5.2 核心职责

```text
1. 理解用户意图和上下文。
2. 判断任务是否在自身业务边界内。
3. 判断是否需要追问、拒绝、审批或继续执行。
4. 生成结构化 Plan。
5. 为每个 Step 选择合适 Worker。
6. 决定串行、并行或条件执行。
7. 接收 Worker 结构化结果。
8. 处理失败、部分成功、需要澄清、需要审批等状态。
9. 汇总最终答案，并控制对用户可见的信息。
```

### 5.3 Router 不直接做的事

```text
不直接调用数据库。
不直接调用企业 API。
不直接执行代码。
不直接发邮件、改数据、下单、审批。
不直接读取未授权知识库内容。
不负责底层任务状态持久化。
```

所有业务动作必须通过 Worker 和 Capability 完成。

### 5.4 Router 决策模式

推荐默认采用 manager 模式：

```text
Router 保持对任务的控制权。
Worker 作为被调用的专业执行单元。
Router 汇总多个 Worker 的结果后再输出给用户。
```

不建议默认采用 handoff 模式：

```text
不建议让 Worker 长时间接管用户会话。
不建议让多个 Worker 自由轮流控制对话。
```

允许受控例外：

```text
当某个业务域需要专家 Worker 直接与用户多轮沟通时，可以启用 delegated_chat 模式。
该模式必须配置会话边界、最大轮次、退出条件和审计策略。
```

### 5.5 Router Plan 输出协议

Router 不应该只输出自然语言计划，而应该输出结构化 Plan：

```json
{
  "schema_version": "router_plan_v1",
  "plan_id": "plan_20260512_001",
  "router_id": "sales_router",
  "user_intent": "为客户生成报价并检查合同风险",
  "risk_assessment": {
    "level": "medium",
    "reasons": ["可能涉及客户数据导出", "可能生成外发报价"]
  },
  "steps": [
    {
      "step_id": "step_1",
      "worker_id": "customer_analysis_worker",
      "task": "分析客户历史订单、信用和偏好",
      "dependencies": [],
      "execution_mode": "sync",
      "required_approval": false
    },
    {
      "step_id": "step_2",
      "worker_id": "quotation_worker",
      "task": "基于产品、库存和价格政策生成报价草案",
      "dependencies": ["step_1"],
      "execution_mode": "sync",
      "required_approval": false
    },
    {
      "step_id": "step_3",
      "worker_id": "contract_review_worker",
      "task": "检查合同条款风险",
      "dependencies": ["step_2"],
      "execution_mode": "sync",
      "required_approval": false
    }
  ],
  "final_response_policy": {
    "include_evidence": true,
    "include_internal_trace": false,
    "mask_sensitive_fields": true
  }
}
```

---

## 6. Task Engine 设计

### 6.1 定位

Task Engine 是 V5 中最关键的新增组件。它不是 Agent，不调用大模型做推理，而是平台执行可靠性的基础设施。

它负责：

```text
Plan 持久化
Step 调度
Worker Call 状态管理
Tool Call 状态管理
审批等待
重试
超时
取消
恢复
回放
成本统计
事件流输出
```

### 6.2 为什么不能让 Router 承担 Task Engine

Router 是智能决策单元，输出可能受模型波动影响。状态机、重试、审批和恢复必须是确定性的工程能力。

如果 Router 同时承担状态管理，会带来几个问题：

```text
1. 复杂任务中断后难以恢复。
2. 审批等待期间上下文容易丢失。
3. 重试逻辑不可控。
4. 审计链路不稳定。
5. 成本、耗时和失败原因难以统计。
```

### 6.3 状态对象

```text
Session State：用户会话、入口、租户、用户身份。
Plan State：Router 生成的计划。
Step State：计划中的每一步。
Worker Call State：Worker 调用记录。
Capability Call State：Tool、Workflow、RAG、Sandbox 等调用记录。
Approval State：审批请求、审批人、审批结果。
Artifact State：文件、表格、图片、报告、代码执行产物。
Final Result：最终返回给用户的结果。
```

### 6.4 Step 生命周期

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

### 6.5 执行策略

Task Engine 应支持：

```text
串行执行：step_2 依赖 step_1。
并行执行：多个独立 Worker 同时执行。
条件执行：基于上一步结果决定是否继续。
人工审批：高风险动作执行前暂停。
用户澄清：信息不足时回到用户。
失败重试：仅对 retryable=true 的失败进行重试。
降级执行：工具失败时使用备用 Worker 或备用 Capability。
```

---

## 7. Worker Agent 设计

### 7.1 定位

Worker Agent 是专业执行型智能体。

```text
Worker Agent = Role + Goal + Domain Context + Capability Scope + ReAct Loop + Stop Condition + Output Schema
```

Worker 接收 Router 派发的子任务，在受控能力范围内完成专业执行，并返回结构化结果。

### 7.2 Worker 核心职责

```text
1. 理解子任务。
2. 检查任务是否在自身能力边界内。
3. 构造执行上下文。
4. 决定是否调用 Workflow、Tool、Skill、MCP、Knowledge 或 Sandbox。
5. 执行 ReAct Loop。
6. 判断停止条件。
7. 返回结构化结果、证据、产物和错误信息。
```

### 7.3 Worker 不建议做的事

```text
不主动调用其他 Worker。
不修改 Router 的全局 Plan。
不决定跨领域流程。
不绕过权限调用企业系统。
不无限循环。
不返回无法解析的纯自然语言结果。
```

### 7.4 受控的 Worker 调 Worker 例外

默认禁止 Worker 自由调用 Worker。

如确实需要复用某个 Worker 能力，应通过 Capability Registry 暴露为受控能力：

```text
type = agent_tool
target_worker_id = xxx
max_depth = 1
requires_router_permission = true
requires_audit = true
```

这样可以保留复用能力，同时避免 Agent 网络失控。

### 7.5 Worker Loop Policy

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

---

## 8. Router 与 Worker 调用协议

### 8.1 Worker Invocation

Router 或 Task Engine 调用 Worker 时，应传入结构化上下文：

```json
{
  "schema_version": "worker_invocation_v1",
  "trace_id": "trace_xxx",
  "session_id": "session_xxx",
  "plan_id": "plan_xxx",
  "step_id": "step_xxx",
  "router_id": "sales_router",
  "worker_id": "quotation_worker",
  "tenant_id": "tenant_a",
  "user": {
    "user_id": "u_001",
    "roles": ["sales_manager"],
    "department_id": "sales_east"
  },
  "task": {
    "title": "生成报价草案",
    "description": "基于客户、产品、库存和价格政策生成报价建议",
    "inputs": {
      "customer_id": "c_001",
      "product_ids": ["p_001", "p_002"]
    }
  },
  "context": {
    "previous_step_results": [],
    "conversation_summary": "用户希望给重点客户生成报价",
    "attachments": []
  },
  "execution_policy": {
    "max_steps": 8,
    "timeout_seconds": 120,
    "approval_mode": "required_for_high_risk"
  }
}
```

### 8.2 Worker Result

Worker 必须返回结构化结果：

```json
{
  "schema_version": "worker_result_v1",
  "trace_id": "trace_xxx",
  "task_id": "task_xxx",
  "plan_id": "plan_xxx",
  "step_id": "step_xxx",
  "worker_id": "quotation_worker",
  "status": "success",
  "summary": "已生成报价草案，建议折扣为 8%。",
  "data": {
    "quote_total": 128000,
    "currency": "CNY",
    "discount_rate": 0.08
  },
  "evidence": [
    {
      "type": "tool_result",
      "source": "price_policy_query",
      "ref_id": "tool_call_001"
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
  "next_suggestions": [
    "请销售经理确认是否发送给客户"
  ],
  "confidence": 0.86,
  "retryable": false,
  "error_code": null,
  "errors": [],
  "used_capabilities": [
    "product_query",
    "inventory_query",
    "price_policy_query"
  ],
  "policy_decisions": [
    {
      "policy": "external_send_requires_approval",
      "decision": "approval_required"
    }
  ]
}
```

推荐状态：

```text
success
failed
partial
need_clarification
need_approval
need_handoff
policy_blocked
timeout
cancelled
```

---

## 9. Capability Registry 设计

### 9.1 定位

Capability Registry 统一注册平台可用能力，不把能力来源暴露给 Router 和 Worker。

能力类型：

```text
workflow
tool
skill
mcp_tool
mcp_resource
knowledge_base
sandbox
agent_tool
```

其中 `agent_tool` 只作为受控例外，用于把某个 Worker 包装成能力，不改变平台只有两类 Agent 的原则。

### 9.2 Capability 元数据

```json
{
  "id": "inventory_query",
  "name": "库存查询",
  "type": "tool",
  "description": "查询产品实时库存",
  "provider": "erp_gateway",
  "input_schema": {},
  "output_schema": {},
  "permission": "tool.inventory.query",
  "risk_level": "low",
  "side_effect": "read",
  "requires_approval": false,
  "idempotency_required": false,
  "timeout_seconds": 10,
  "retry_policy": {
    "max_retries": 2,
    "backoff": "exponential"
  },
  "data_scope_policy": {
    "tenant_filter_required": true,
    "department_filter_required": true,
    "field_masking": ["customer_phone", "customer_email"]
  },
  "audit_policy": {
    "log_input": true,
    "log_output": true,
    "mask_sensitive_fields": true
  },
  "version": "1.0.0",
  "enabled": true
}
```

### 9.3 副作用分级

```text
none：纯计算、格式转换，不访问外部系统。
read：读取数据，例如查询库存、检索知识库。
write：修改内部系统数据，例如更新 CRM。
external：对外部产生影响，例如发邮件、下单、提交合同。
```

治理规则：

```text
none/read 通常允许自动执行。
write 需要根据业务风险判断是否审批。
external 默认需要审批或明确授权。
critical 操作必须人工确认。
```

---

## 10. Skill 边界

Skill 容易被设计成第三种 Agent，因此必须收敛定义。

推荐定义：

```text
Skill = Prompt 模板 + Tool 白名单 + 业务规则 + 输入输出 Schema + 示例 + 评测集
```

Skill 不应该拥有：

```text
长期自主状态
跨任务记忆
主动调度权
直接调用其他 Worker 的能力
最终对用户输出的控制权
```

Skill 的价值：

```text
1. 封装领域技巧。
2. 复用业务规则。
3. 复用提示词和工具组合。
4. 降低 Worker 配置复杂度。
5. 支持版本化和效果评测。
```

---

## 11. 权限与安全设计

### 11.1 权限链路

```text
用户身份
  ↓
租户与组织权限
  ↓
Router 可访问性
  ↓
Router 可调用 Worker 范围
  ↓
Worker 可调用 Capability 范围
  ↓
Capability 风险与审批策略
  ↓
Tool Gateway / Sandbox Gateway 二次鉴权
  ↓
企业系统最终鉴权
```

### 11.2 必须支持的安全能力

```text
租户隔离
角色权限
部门权限
数据范围权限
字段级脱敏
高风险动作审批
Tool 二次鉴权
RAG 检索权限过滤
Sandbox 网络白名单
调用审计
预算与限流
模型输出安全过滤
```

### 11.3 RAG 权限要求

知识库不能只在库级别做权限控制，还需要支持：

```text
document_acl：文档级权限。
chunk_acl：分片级权限。
metadata_filter：租户、部门、项目、客户等元数据过滤。
field_masking：敏感字段脱敏。
citation_required：重要回答必须带引用。
retrieval_audit：记录检索 query、命中文档和过滤结果。
```

### 11.4 高风险动作审批

高风险动作流程：

```text
Worker 生成 action proposal
  ↓
Task Engine 创建 approval request
  ↓
Router 向用户或审批人展示待确认内容
  ↓
审批通过
  ↓
Tool Gateway 使用审批 token 执行动作
  ↓
记录审计
```

审批对象示例：

```json
{
  "approval_request_id": "approval_001",
  "trace_id": "trace_xxx",
  "risk_level": "high",
  "action_type": "send_quote_to_customer",
  "title": "发送报价单给客户",
  "summary": "将 quote_draft.xlsx 发送给客户 c_001",
  "proposed_payload": {},
  "expires_at": "2026-05-12T23:30:00+08:00",
  "approvers": ["sales_manager"]
}
```

---

## 12. 上下文与记忆设计

MVP 阶段建议只做短期上下文，不做复杂长期记忆。

上下文分层：

```text
Conversation Context：当前会话摘要和最近消息。
Task Context：当前 Plan、Step、Worker Result。
Business Context：用户授权范围内的业务数据。
Knowledge Context：RAG 检索结果和引用。
Execution Context：工具调用结果、文件产物、审批状态。
```

长期记忆建议延后：

```text
第一阶段不做用户画像型长期记忆。
第一阶段不做 Agent 自我优化记忆。
第一阶段不做跨租户经验共享。
```

可以先保留可扩展接口：

```text
memory_read
memory_write
memory_policy
memory_retention
```

---

## 13. 可观测性与审计

平台必须能回答以下问题：

```text
用户问了什么？
哪个 Router 处理了？
Router 生成了什么 Plan？
调用了哪些 Worker？
Worker 调用了哪些 Capability？
每次调用输入输出是什么？
是否触发权限、脱敏或审批？
成本是多少？
失败在哪里？
最终结果基于哪些证据？
```

核心 Trace：

```text
trace_id
session_id
plan_id
step_id
worker_call_id
capability_call_id
approval_request_id
artifact_id
```

核心指标：

```text
任务成功率
部分成功率
失败率
澄清率
审批触发率
平均响应时间
平均工具调用次数
平均 token 成本
Worker 命中率
Capability 失败率
用户采纳率
人工接管率
```

---

## 14. 评测体系

企业 Agent 平台不能只依靠人工体验判断质量，需要内置评测。

### 14.1 Router 评测

```text
意图识别准确率
Worker 选择准确率
Plan 步骤合理性
是否过度调用 Worker
是否正确触发审批
是否正确追问
```

### 14.2 Worker 评测

```text
任务完成率
工具选择准确率
参数构造准确率
输出 Schema 合规率
证据完整性
业务规则遵守率
幻觉率
```

### 14.3 Capability 评测

```text
调用成功率
平均耗时
错误率
重试成功率
权限拒绝准确率
脱敏正确率
```

### 14.4 端到端评测

```text
业务任务完成率
用户满意度
人工介入率
平均处理时长
成本
合规事件数
```

---

## 15. 工程模块建议

### 15.1 MVP 推荐模块化单体

第一阶段不建议一开始拆成大量微服务。建议先做模块化单体，边界清晰，部署简单。

```text
agent-platform
├── apps
│   ├── web-console
│   ├── chat-web
│   └── api-server
│
├── modules
│   ├── identity
│   ├── agent-registry
│   ├── router-runtime
│   ├── worker-runtime
│   ├── task-engine
│   ├── capability-registry
│   ├── tool-gateway
│   ├── knowledge
│   ├── approval
│   ├── audit-trace
│   ├── model-gateway
│   └── observability
│
└── infra
    ├── postgres
    ├── redis
    ├── vector-db
    ├── object-storage
    └── queue
```

### 15.2 后续服务化拆分

当系统出现独立扩缩容、团队边界或稳定性隔离需求时，再拆为服务：

```text
agent-registry-service
router-runtime-service
worker-runtime-service
task-engine-service
capability-registry-service
tool-gateway-service
knowledge-service
sandbox-gateway-service
audit-trace-service
model-gateway-service
auth-rbac-service
```

拆分原则：

```text
先有模块边界，再有服务边界。
先有稳定协议，再拆网络调用。
先保证端到端闭环，再追求平台完整性。
```

---

## 16. MVP 落地建议

### 16.1 MVP 目标

不要第一阶段做“通用 Agent 平台全功能”。建议选择一个强业务场景，跑通端到端闭环。

推荐场景：

```text
销售报价助手
```

业务闭环：

```text
用户输入客户和产品需求
  ↓
Sales Router 拆解任务
  ↓
Customer Analysis Worker 分析客户
  ↓
Quotation Worker 查询产品、库存、价格政策并生成报价草案
  ↓
Contract Review Worker 检查条款风险
  ↓
Router 汇总结果
  ↓
用户确认
  ↓
审批通过后发送报价或生成文件
  ↓
全链路审计
```

### 16.2 MVP 必做能力

```text
1. Agent Registry：支持 Router / Worker 两类 Agent。
2. Capability Registry：支持 Tool / Knowledge / Skill 三类能力。
3. Router Runtime：支持结构化 Plan 和 Worker 选择。
4. Task Engine：支持 Plan、Step、Worker Call、Tool Call 状态。
5. Worker Runtime：支持 ReAct Loop、工具调用、停止条件。
6. Tool Gateway：支持 HTTP / OpenAPI Tool 注册和调用。
7. Knowledge Service：支持基础 RAG、引用和权限过滤。
8. Approval：支持高风险动作人工确认。
9. Audit Trace：记录 Router → Worker → Capability 调用链。
10. Web Chat：选择一个 Router Agent 对话。
```

### 16.3 MVP 暂不做

```text
多 Worker 自由通信
复杂低代码 Workflow 画布
长期记忆
Agent 自我优化
完整 PromptOps
复杂浏览器自动化
多模型自动竞价
跨租户经验共享
```

### 16.4 MVP 成功标准

```text
一个真实业务场景可以端到端完成。
所有关键调用都有 trace。
高风险动作可以审批后执行。
Worker 结果全部结构化。
失败可以定位到具体 Step 或 Capability。
权限过滤和脱敏可验证。
```

---

## 17. 配置示例

### 17.1 Router Agent

```json
{
  "id": "sales_router",
  "name": "销售助手 Router",
  "type": "router",
  "description": "负责销售场景的意图识别、任务拆解、Worker 选择和结果汇总",
  "allowed_worker_agents": [
    "customer_analysis_worker",
    "quotation_worker",
    "contract_review_worker"
  ],
  "routing_strategy": "llm_plus_rules",
  "max_plan_steps": 6,
  "max_worker_calls": 8,
  "manager_mode": true,
  "requires_approval_for": [
    "send_quote",
    "export_customer_data",
    "submit_contract"
  ],
  "final_response_policy": {
    "mask_sensitive_fields": true,
    "include_evidence": true,
    "include_trace_summary": true
  }
}
```

### 17.2 Worker Agent

```json
{
  "id": "quotation_worker",
  "name": "报价生成 Worker",
  "type": "worker",
  "description": "根据客户、产品、库存和价格政策生成报价建议",
  "allowed_workflows": ["quote_generation_workflow"],
  "allowed_tools": [
    "product_query",
    "inventory_query",
    "price_policy_query"
  ],
  "allowed_skills": [
    "quote_reasoning_skill",
    "sales_discount_skill"
  ],
  "allowed_knowledge_bases": [
    "product_knowledge",
    "sales_policy"
  ],
  "loop_policy": {
    "mode": "react",
    "max_steps": 8,
    "max_tool_calls": 6,
    "timeout_seconds": 120
  },
  "output_schema": "worker_result_v1",
  "approval_required_actions": [
    "send_quote_to_customer"
  ]
}
```

### 17.3 Capability

```json
{
  "id": "price_policy_query",
  "name": "价格政策查询",
  "type": "tool",
  "description": "查询客户、产品和销售区域对应的价格政策",
  "provider": "erp_gateway",
  "input_schema": {
    "type": "object",
    "required": ["customer_id", "product_ids"],
    "properties": {
      "customer_id": { "type": "string" },
      "product_ids": {
        "type": "array",
        "items": { "type": "string" }
      }
    }
  },
  "output_schema": {},
  "permission": "tool.price_policy.query",
  "risk_level": "medium",
  "side_effect": "read",
  "requires_approval": false,
  "timeout_seconds": 10,
  "version": "1.0.0"
}
```

---

## 18. 需要避免的反模式

```text
1. 设计一个无所不能的顶层总 Agent。
2. 允许所有 Agent 自由互调。
3. 把 Workflow、Tool、Skill 都设计成 Agent。
4. 让 Router 直接操作数据库或企业 API。
5. Worker 只返回自然语言，不返回结构化结果。
6. 先做复杂画布，再做业务闭环。
7. 只做模型 Prompt，不做权限、审计和审批。
8. RAG 只做向量检索，不做文档权限过滤。
9. 工具调用没有幂等、超时和重试策略。
10. 一开始就拆成过多微服务。
```

---

## 19. 推荐实施顺序

```text
第 1 步：定义 Agent、Capability、Task、Trace 的核心数据模型。
第 2 步：实现 Agent Registry 和 Capability Registry。
第 3 步：实现 Tool Gateway 的 HTTP / OpenAPI Tool 调用。
第 4 步：实现 Worker Runtime 的 ReAct Loop 和 Worker Result 协议。
第 5 步：实现 Router Runtime 的 Plan 输出和 Worker 选择。
第 6 步：实现 Task Engine 的 Plan / Step / Call 状态机。
第 7 步：接入 Knowledge Service 的基础 RAG 和权限过滤。
第 8 步：接入 Approval 和高风险动作确认。
第 9 步：完成 Web Chat 和 Trace 查看。
第 10 步：用销售报价场景做端到端验收。
```

---

## 20. 最终定位

这套平台不是“一个超级 Agent 调所有东西”，而是：

```text
多 Router Agent
+ 多 Worker Agent
+ Task Engine
+ Capability Registry
+ 企业安全治理
+ 全链路审计
```

一句话：

```text
Router Agent 负责判断和控场；
Task Engine 负责可靠执行；
Worker Agent 负责专业任务；
Capability 负责具体能力；
Policy 和 Audit 负责企业级治理。
```

