# 企业级 Agent 交付平台设计方案 V4：两类 Agent 架构

> 定位：完全自研企业 Agent 平台。Dify、OpenClaw、Coze 仅作为产品与交互参考，不作为底层依赖。
>
> 核心收敛：平台只定义两类 Agent：Router Agent 与 Worker Agent。

---

## 1. 核心结论

平台不再设计一个特殊硬编码的“顶层总 Agent”，而是把“总入口能力”抽象成一种 Agent 类型：Router Agent。

```text
Router Agent = 调度型 Agent
Worker Agent = 执行型 Agent
```

最终分层：

```text
用户入口
  ↓
Router Agent
  ↓
Worker Agent
  ↓
Workflow / Tool / Skill / MCP / Knowledge / Sandbox
  ↓
企业业务系统
```

关键原则：

```text
Router Agent 只负责选 Agent、拆任务、编排、汇总。
Worker Agent 负责专业任务执行，支持 ReAct + Loop，可调用 Workflow、Tool、Skill、MCP、Knowledge。
Worker Agent 默认不调用其他 Worker Agent。
```

---

## 2. 为什么只保留两类 Agent

之前如果拆成 Router / Worker / Workflow / Tool / Skill / Hybrid Agent，产品会越来越复杂，用户理解成本高，运行时也难治理。

现在收敛为两类：

| 类型 | 主要职责 | 可调用对象 | 不建议做 |
|---|---|---|---|
| Router Agent | 意图识别、任务拆解、选择 Worker、汇总结果 | Worker Agent | 直接调用 Tool / Workflow / Skill |
| Worker Agent | 专业任务执行、ReAct Loop、工具调用、结果输出 | Workflow / Tool / Skill / MCP / Knowledge / Sandbox | 主动调度其他 Worker Agent |

这样产品清晰、架构稳定、权限好管、审计好做，也方便未来添加新的能力类型。

---

## 3. 总体架构

```text
┌──────────────────────────────┐
│ 用户入口层                    │
│ Web Chat / 企业微信 / 飞书 / API │
└───────────────┬──────────────┘
                ↓
┌──────────────────────────────┐
│ AI Gateway                    │
│ 鉴权 / 租户 / 限流 / 安全过滤 │
└───────────────┬──────────────┘
                ↓
┌──────────────────────────────┐
│ Router Agent Runtime          │
│ 意图识别 / Plan / 选 Worker / 汇总 │
└───────────────┬──────────────┘
                ↓
┌──────────────────────────────┐
│ Worker Agent Runtime          │
│ ReAct / Loop / 专业执行 / 结构化反馈 │
└───────────────┬──────────────┘
                ↓
┌──────────────────────────────┐
│ Capability Layer              │
│ Workflow / Tool / Skill / MCP / RAG │
└───────────────┬──────────────┘
                ↓
┌──────────────────────────────┐
│ 企业系统与执行环境            │
│ ERP / CRM / OA / DB / Sandbox │
└──────────────────────────────┘
```

---

## 4. Router Agent 设计

### 4.1 定位

Router Agent 是平台里的“调度型智能体”。它不是唯一的，可以有多个：

```text
企业总入口 Router
销售助手 Router
医疗质控 Router
财务分析 Router
HR 助手 Router
售后服务 Router
```

每个 Router Agent 都有自己的业务边界和可用 Worker 范围。

### 4.2 核心职责

```text
1. 理解用户意图
2. 判断任务类型
3. 拆解复杂任务
4. 选择合适 Worker Agent
5. 控制执行顺序
6. 接收 Worker 结构化反馈
7. 判断是否继续、重试、追问、审批或终止
8. 汇总最终答案
```

### 4.3 Router Agent 不建议直接做的事

```text
不直接调用数据库
不直接调用企业 API
不直接执行代码
不直接发邮件、改数据、下单、审批
不直接处理复杂业务细节
```

所有业务动作应交给 Worker Agent。

### 4.4 Router Agent 配置示例

```json
{
  "id": "sales_router",
  "name": "销售助手 Router",
  "type": "router",
  "description": "负责销售场景的任务识别、Worker 选择和结果汇总",
  "allowed_worker_agents": [
    "customer_analysis_worker",
    "quotation_worker",
    "visit_plan_worker",
    "contract_review_worker"
  ],
  "routing_strategy": "llm_plus_rules",
  "max_plan_steps": 6,
  "max_worker_calls": 8,
  "requires_approval_for": [
    "send_quote",
    "export_customer_data",
    "submit_contract"
  ]
}
```

---

## 5. Worker Agent 设计

### 5.1 定位

Worker Agent 是平台里的“专业执行型智能体”。它类似 OpenClaw 的执行单元，但要加企业边界。

```text
Worker Agent = Role + Goal + Context + Tools + Workflows + Skills + ReAct Loop + Stop Condition
```

### 5.2 核心职责

```text
1. 接收 Router 派发的子任务
2. 在专业边界内理解任务
3. 判断是否需要调用 Workflow / Tool / Skill / MCP / Knowledge
4. 执行 ReAct + Loop
5. 在达到停止条件后返回结构化结果
```

### 5.3 Worker Agent 能调用什么

```text
Workflow：固定 SOP，例如报价生成、合同审查、报告生成
Tool：原子系统能力，例如查库存、查订单、发通知
Skill：一组 Prompt + Tool + 业务规则，例如销售话术、病历摘要
MCP：标准化外部工具协议
Knowledge/RAG：企业知识库、制度、产品资料、合同模板
Sandbox：代码执行、文件处理、SQL 查询、浏览器自动化
```

### 5.4 Worker Agent 不建议做什么

```text
不主动调用其他 Worker Agent
不修改 Router 的全局 Plan
不决定跨领域流程
不无限制循环
不绕过权限直接访问业务系统
```

### 5.5 Worker Agent 配置示例

```json
{
  "id": "quotation_worker",
  "name": "报价生成 Worker",
  "type": "worker",
  "description": "根据客户、产品、库存、价格策略生成报价建议",
  "allowed_workflows": ["quote_generation_workflow"],
  "allowed_tools": ["product_query", "inventory_query", "price_policy_query"],
  "allowed_skills": ["quote_reasoning_skill", "sales_discount_skill"],
  "allowed_knowledge_bases": ["product_knowledge", "sales_policy"],
  "loop_policy": {
    "mode": "react",
    "max_steps": 8,
    "max_tool_calls": 6,
    "timeout_seconds": 120
  },
  "output_schema": "worker_result_v1",
  "approval_required_actions": ["send_quote_to_customer"]
}
```

---

## 6. Worker ReAct Loop

Worker Agent 的执行循环：

```text
Receive Task
  ↓
Understand Context
  ↓
Decide Next Action
  ↓
Call Workflow / Tool / Skill / MCP / Knowledge
  ↓
Observe Result
  ↓
Continue / Retry / Ask Clarification / Need Approval / Final
```

推荐状态：

```text
running
success
failed
partial
need_clarification
need_approval
need_handoff
```

---

## 7. Router 与 Worker 的反馈协议

Worker 不应该只返回自然语言，必须返回结构化结果。

```json
{
  "status": "success | failed | partial | need_clarification | need_approval",
  "summary": "任务处理摘要",
  "data": {},
  "evidence": [],
  "actions": [],
  "next_suggestions": [],
  "confidence": 0.86,
  "used_capabilities": [],
  "errors": [],
  "trace_id": "trace_xxx"
}
```

Router 根据 Worker 返回结果继续决策：

```text
success → 进入下一步或汇总
partial → 标记部分完成，决定是否继续
failed → 重试、换 Worker、降级或告知用户
need_clarification → 向用户追问
need_approval → 进入人工确认
```

---

## 8. Capability Registry 设计

平台内部统一注册能力，不区分来源。

```text
Agent Registry
  - Router Agent
  - Worker Agent

Capability Registry
  - Workflow
  - Tool
  - Skill
  - MCP Server / MCP Tool
  - Knowledge Base
  - Sandbox Capability
```

能力注册对象：

```json
{
  "id": "inventory_query",
  "name": "库存查询",
  "type": "tool",
  "description": "查询产品实时库存",
  "input_schema": {},
  "output_schema": {},
  "permission": "tool.inventory.query",
  "risk_level": "low",
  "provider": "erp_gateway"
}
```

这样以后市面出现新的智能体形态或工具形态，不需要重构 Agent 类型，只需要新增 Capability 类型或 Runtime Adapter。

---

## 9. 权限与安全边界

权限链路：

```text
用户身份
  ↓
Router Agent 可访问性
  ↓
Router 可调用 Worker 范围
  ↓
Worker 可调用 Capability 范围
  ↓
Tool Gateway / Sandbox Gateway 二次鉴权
  ↓
企业系统最终鉴权
```

必须支持：

```text
租户隔离
角色权限
部门权限
数据范围权限
字段级脱敏
高风险动作审批
调用审计
预算与限流
```

---

## 10. 任务中心与状态管理

复杂任务建议持久化：

```text
Session State
Plan State
Worker Call State
Step State
Tool Call State
Approval State
Final Result
```

这样支持：

```text
异步执行
重试
恢复
人工接管
失败回放
成本统计
效果评估
```

---

## 11. 推荐工程模块

```text
agent-platform
├── apps
│   ├── web-console
│   ├── chat-web
│   └── api-server
│
├── services
│   ├── agent-registry-service
│   ├── router-runtime-service
│   ├── worker-runtime-service
│   ├── capability-registry-service
│   ├── workflow-engine-service
│   ├── tool-gateway-service
│   ├── skill-runtime-service
│   ├── mcp-gateway-service
│   ├── knowledge-service
│   ├── sandbox-gateway-service
│   ├── task-engine-service
│   ├── auth-rbac-service
│   ├── audit-trace-service
│   └── model-gateway-service
│
└── infra
    ├── postgres
    ├── redis
    ├── vector-db
    ├── object-storage
    ├── queue
    └── observability
```

---

## 12. MVP 建议

第一阶段只做：

```text
1. Agent Registry：支持 Router / Worker 两类 Agent
2. Capability Registry：支持 Tool / Workflow / Skill 三类能力
3. Router Runtime：支持选择 Worker 和简单 Plan
4. Worker Runtime：支持 ReAct Loop + Tool 调用
5. Tool Gateway：支持 OpenAPI / HTTP Tool 注册和调用
6. 审计日志：记录 Router → Worker → Tool 调用链
7. Web Chat：选择一个 Router Agent 对话
```

暂不做：

```text
多 Worker 自由通信
长期记忆
复杂自我优化
全量 PromptOps
完整低代码 Workflow 画布
复杂 Sandbox 浏览器自动化
```

---

## 13. 最终产品定位

这不是“一个总 Agent 调所有东西”的平台，而是：

```text
多 Router Agent + 多 Worker Agent + 统一能力注册中心 + 企业安全治理
```

一句话：

```text
Router Agent 负责选人和控场；Worker Agent 负责专业执行；Workflow / Tool / Skill / MCP 负责具体能力。
```
