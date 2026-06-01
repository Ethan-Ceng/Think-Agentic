# Agent 平台工程设计规划

补充说明：基于现有 `api` 目录迁移到 `backend` 的详细目录功能边界，以 `docs/BACKEND_API_DIRECTORY_DESIGN.md` 为准。

更新时间：2026-05-13

本文面向当前 `llmops` 项目升级改造，目标是在保留现有 FastAPI、Vue、Celery、Weaviate、LangChain/LangGraph 基础能力的前提下，演进为支持多业务 Agent 形态的企业级 Agent 平台。

技术选择声明：本项目后端只采用 FastAPI，不采用 Flask、Flask-RESTX、Flask-SQLAlchemy、Flask-Migrate、Flask-Login 或 Flask Blueprint。Dify 只作为平台边界和产品机制参考，不作为后端框架参考。

## 1. 当前项目基线

后端现状：

```text
api/
  app/main.py                 FastAPI 应用入口
  app/server/http.py          FastAPI 子类与扩展初始化
  app/api/routes/*            当前路由按业务资源拆分
  app/service/*               应用服务层
  app/model/*                 SQLAlchemy 模型
  app/schema/*                Pydantic Schema
  app/core/agent/*            ReAct / FunctionCall Agent Runtime
  app/core/workflow/*         LangGraph 工作流
  app/core/tools/*            Builtin Tool / API Tool
  app/core/retrievers/*       语义和全文检索
  app/task/*                  Celery 异步任务
```

基础设施：

```text
FastAPI
SQLAlchemy / Alembic
PostgreSQL
Redis
Celery
Weaviate
LangChain / LangGraph
Vue 3 / Element Plus / Vue Flow
Docker Compose
```

已有业务能力：

1. Account、OAuth、JWT、API Key。
2. App、AppConfig、发布历史、调试会话。
3. Dataset、Document、Segment、Weaviate 检索。
4. Builtin Tool、API Tool、OpenAPI。
5. Workflow 图编排和节点执行。
6. Assistant Agent 会话。
7. Message、MessageAgentThought 记录 Agent 推理过程。

主要差距：

1. 当前隔离边界主要是 `account_id`，还不是真正的 Tenant / Workspace。
2. Agent 还没有统一 Registry，App 与 Agent 概念混合。
3. Tool、Workflow、Knowledge 还未统一为 Capability。
4. 缺少独立 Task Engine，复杂任务状态、重试、审批、恢复不足。
5. Router / Worker 调用协议和结构化结果还不稳定。
6. Trace 有 MessageAgentThought 基础，但缺少跨 Router、Worker、Capability 的统一链路。
7. API 面当前按资源注册，尚未按 console、service_api、web、files、inner、triggers 隔离。

## 2. 目标架构

推荐先采用模块化单体，不急于拆微服务。

```text
用户入口
  -> API 面
      console / service_api / web / files / inner / triggers
  -> AI Gateway
      鉴权 / 租户上下文 / 限流 / 安全过滤
  -> Router Agent Runtime
      意图识别 / Plan / Worker 选择 / 结果汇总
  -> Task Engine
      Plan / Step / Call 状态机 / 重试 / 审批 / 事件流
  -> Worker Agent Runtime
      ReAct Loop / Tool Calling / Structured Result
  -> Capability Layer
      Tool / Workflow / Skill / Knowledge / MCP / Sandbox
  -> Infrastructure
      PostgreSQL / Redis / Celery / Weaviate / Object Storage / LLM Provider
```

工程原则：

1. API 层只做 HTTP 适配、鉴权、Schema 校验。
2. Service 层负责编排用例和事务。
3. Runtime / Core 层不依赖 FastAPI 请求对象。
4. Infrastructure 层封装 DB、Redis、Celery、存储、LLM、向量库、外部 HTTP。
5. 所有共享资源查询最终都要带 `tenant_id`。
6. 所有长任务都必须有 task state、trace event、幂等键和可恢复策略。

## 3. 模块边界

第一阶段按当前项目风格新增模块，减少大规模迁移风险。

| 模块 | 建议位置 | 职责 |
| --- | --- | --- |
| Identity / Tenant | `model/account.py` 扩展，新增 `tenant.py` | 租户、成员、角色、当前工作区 |
| Agent Registry | `model/agent.py`、`service/agent_registry_service.py` | Router / Worker 定义、版本、发布 |
| Capability Registry | `model/capability.py`、`service/capability_registry_service.py` | Tool、Workflow、Knowledge、Skill 统一注册 |
| Router Runtime | `core/agent_platform/router_runtime/` | Router Plan 生成、Worker 选择、汇总 |
| Worker Runtime | `core/agent_platform/worker_runtime/` | Worker Invocation、Loop、结构化结果 |
| Task Engine | `model/task.py`、`service/task_engine_service.py`、`task/agent_task.py` | Plan、Step、Call 状态机和异步调度 |
| Tool Gateway | `core/agent_platform/capabilities/tool_gateway.py` | 工具调用、鉴权、Schema、审计、重试 |
| Knowledge Service | 复用 `service/retrieval_service.py` 并增强 | 权限过滤、引用、检索审计 |
| Workflow Engine | 复用 `core/workflow/` | 固定 SOP 能力，作为 Capability 被调用 |
| Approval | `model/approval.py`、`service/approval_service.py` | 审批请求、审批 token、执行确认 |
| Audit Trace | `model/trace.py`、`service/trace_service.py` | trace event、成本、耗时、回放 |
| Evaluation | `model/evaluation.py`、`service/evaluation_service.py` | 测试集、批量评测、质量指标 |

中期可以再按业务域整理为：

```text
api/app/modules/
  identity/
  agent_registry/
  router_runtime/
  worker_runtime/
  task_engine/
  capability_registry/
  approval/
  audit_trace/
  evaluation/
```

但不建议在 MVP 前做大规模目录重排。

## 4. API 面规划

借鉴 Dify 的 API 面隔离，但按当前项目逐步迁移。

目标 API 面：

| API 面 | 前缀 | 调用方 | 鉴权方式 |
| --- | --- | --- | --- |
| Console API | `/console/api` | 平台控制台 | JWT / Session |
| Service API | `/v1` | 外部开发者 | API Key |
| Web App API | `/api` | 发布后的 Web Chat | App token / end user |
| Files API | `/files` | 文件上传和预览 | JWT / signed URL |
| Inner API | `/inner/api` | 内部服务、回调 | 内部 token |
| Trigger API | `/triggers` | Webhook、定时任务 | trigger token |

迁移策略：

1. 保留现有路由，新增新前缀，不立即破坏前端。
2. 新 Agent 平台接口全部放到 `/console/api/agent-*`、`/v1/agents/*` 等新面。
3. 前端逐步迁移到新 Service 封装。
4. 最后再清理旧路由或做兼容层。

核心接口草案：

```text
Console:
POST   /console/api/agents
GET    /console/api/agents
GET    /console/api/agents/{agent_id}
PATCH  /console/api/agents/{agent_id}
POST   /console/api/agents/{agent_id}/publish
POST   /console/api/agents/{agent_id}/debug

POST   /console/api/capabilities
GET    /console/api/capabilities
POST   /console/api/capabilities/{capability_id}/test

GET    /console/api/tasks
GET    /console/api/tasks/{task_id}
POST   /console/api/tasks/{task_id}/cancel
POST   /console/api/tasks/{task_id}/retry

GET    /console/api/approvals
POST   /console/api/approvals/{approval_id}/approve
POST   /console/api/approvals/{approval_id}/reject

Service API:
POST   /v1/agents/{agent_id}/invoke
POST   /v1/agents/{agent_id}/chat-messages
GET    /v1/tasks/{task_id}
GET    /v1/tasks/{task_id}/events
```

## 5. 数据模型规划

### 5.1 租户与权限

当前大量表以 `account_id` 作为隔离字段。建议新增 Tenant，但允许过渡期 `tenant_id = account_id`。

新增表：

```text
tenants
tenant_members
roles
permissions
role_permissions
member_roles
```

迁移策略：

1. 第一阶段创建默认 tenant，所有历史账号自动加入。
2. 旧表新增 nullable `tenant_id`，回填后再逐步改为 not null。
3. 查询层先同时校验 `account_id` 和 `tenant_id`，稳定后再切主逻辑。

### 5.2 Agent Registry

```text
agents
  id
  tenant_id
  created_by
  name
  icon
  description
  runtime_type        router / worker
  product_category    sales / finance / knowledge / data / custom
  status              draft / published / archived
  draft_version_id
  published_version_id
  visibility_scope
  created_at
  updated_at

agent_versions
  id
  tenant_id
  agent_id
  version
  config_type         draft / published
  model_config
  prompt_config
  router_config
  worker_config
  capability_bindings
  policies
  output_schema
  created_at
  updated_at

agent_bindings
  id
  tenant_id
  router_agent_id
  worker_agent_id
  enabled
  priority
  conditions
```

与现有 App 的关系：

1. 短期可以让 `App` 继续承载已有应用入口。
2. 新 Agent 表作为 Agent 平台主模型。
3. 对现有 App 提供迁移工具：App -> Worker Agent 或单 Worker Agent App。
4. 后续 App 可以退化为“发布入口”，Agent 承载运行配置。

### 5.3 Capability Registry

```text
capabilities
  id
  tenant_id
  name
  type                tool / workflow / skill / knowledge_base / mcp_tool / sandbox / agent_tool
  provider
  target_ref_type     api_tool / builtin_tool / workflow / dataset / mcp_server / sandbox
  target_ref_id
  description
  input_schema
  output_schema
  permission
  risk_level          low / medium / high / critical
  side_effect         none / read / write / external / critical
  requires_approval
  idempotency_required
  timeout_seconds
  retry_policy
  data_scope_policy
  audit_policy
  version
  enabled
  created_at
  updated_at

agent_capability_bindings
  id
  tenant_id
  agent_version_id
  capability_id
  alias
  params
  enabled
```

现有 Builtin Tool、API Tool、Workflow、Dataset 不立即迁移存储，只通过 `target_ref_type` 和 `target_ref_id` 被 Capability 包装。

### 5.4 Task Engine

```text
agent_tasks
  id
  tenant_id
  session_id
  conversation_id
  router_agent_id
  user_id
  status
  user_input
  final_result
  error_code
  error_message
  started_at
  finished_at
  created_at
  updated_at

agent_plans
  id
  tenant_id
  task_id
  router_agent_id
  schema_version
  plan_json
  risk_level
  status
  created_at

agent_steps
  id
  tenant_id
  task_id
  plan_id
  step_key
  worker_agent_id
  dependencies
  execution_mode
  status
  input_json
  output_json
  retry_count
  timeout_seconds
  started_at
  finished_at
  created_at
  updated_at

worker_calls
  id
  tenant_id
  task_id
  step_id
  worker_agent_id
  invocation_json
  result_json
  status
  token_count
  cost
  latency
  created_at
  updated_at

capability_calls
  id
  tenant_id
  task_id
  step_id
  worker_call_id
  capability_id
  input_json
  output_json
  status
  risk_level
  approval_id
  idempotency_key
  latency
  created_at
  updated_at
```

### 5.5 Approval、Artifact、Trace

```text
approval_requests
  id
  tenant_id
  task_id
  step_id
  capability_call_id
  action_type
  title
  summary
  proposed_payload
  risk_level
  status
  approver_policy
  approved_by
  approval_token_hash
  expires_at
  created_at
  updated_at

artifacts
  id
  tenant_id
  task_id
  step_id
  type
  name
  object_key
  metadata
  created_at

trace_events
  id
  tenant_id
  trace_id
  task_id
  plan_id
  step_id
  worker_call_id
  capability_call_id
  event_type
  payload
  token_count
  cost
  latency
  created_at
```

## 6. 运行协议

### 6.1 Router Plan

Router 输出必须是结构化 JSON，不允许只输出自然语言计划。

```json
{
  "schema_version": "router_plan_v1",
  "router_id": "sales_router",
  "user_intent": "生成客户报价并检查合同风险",
  "risk_assessment": {
    "level": "medium",
    "reasons": ["可能生成外发报价"]
  },
  "steps": [
    {
      "step_id": "step_1",
      "worker_id": "customer_analysis_worker",
      "task": "分析客户历史订单和偏好",
      "dependencies": [],
      "execution_mode": "sync",
      "required_approval": false
    }
  ],
  "final_response_policy": {
    "include_evidence": true,
    "mask_sensitive_fields": true
  }
}
```

### 6.2 Worker Invocation

```json
{
  "schema_version": "worker_invocation_v1",
  "trace_id": "trace_xxx",
  "tenant_id": "tenant_xxx",
  "task_id": "task_xxx",
  "plan_id": "plan_xxx",
  "step_id": "step_1",
  "router_id": "sales_router",
  "worker_id": "quotation_worker",
  "user": {
    "user_id": "user_xxx",
    "roles": ["sales"]
  },
  "task": {
    "title": "生成报价草案",
    "inputs": {}
  },
  "context": {
    "conversation_summary": "",
    "previous_step_results": [],
    "attachments": []
  },
  "execution_policy": {
    "max_steps": 8,
    "timeout_seconds": 120
  }
}
```

### 6.3 Worker Result

```json
{
  "schema_version": "worker_result_v1",
  "trace_id": "trace_xxx",
  "task_id": "task_xxx",
  "step_id": "step_1",
  "worker_id": "quotation_worker",
  "status": "success",
  "summary": "已生成报价草案。",
  "data": {},
  "evidence": [],
  "artifacts": [],
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
  "used_capabilities": []
}
```

状态枚举：

```text
success
failed
partial
need_clarification
need_approval
policy_blocked
timeout
cancelled
```

## 7. 核心执行链路

### 7.1 Console 调试链路

```text
POST /console/api/agents/{agent_id}/debug
  -> get_current_user / get_current_tenant
  -> AgentDebugService.create_task()
  -> RouterRuntime.plan()
  -> TaskEngine.persist_plan()
  -> TaskEngine.dispatch_steps()
  -> WorkerRuntime.invoke()
  -> CapabilityGateway.call()
  -> TraceService.record()
  -> SSE stream events
```

### 7.2 Service API 调用链路

```text
POST /v1/agents/{agent_id}/invoke
  -> API Key auth
  -> resolve tenant / app / end_user
  -> create task
  -> enqueue Celery task
  -> return task_id or stream events

Celery worker
  -> load task
  -> execute Router / Worker / Capability
  -> write trace_events
  -> publish Redis Stream events
```

### 7.3 高风险动作链路

```text
Worker proposes action
  -> Tool Gateway detects risk
  -> Task Engine marks step waiting_approval
  -> ApprovalService creates request
  -> Router returns approval card
  -> approver approves
  -> Tool Gateway executes with approval token
  -> Task Engine resumes
```

## 8. 事件流设计

建议使用 Redis Stream 作为任务事件中间层，SSE 只负责输出。

事件类型：

```text
task.created
plan.created
step.queued
step.started
worker.started
worker.message_delta
capability.started
capability.succeeded
capability.failed
approval.required
artifact.created
step.succeeded
step.failed
task.succeeded
task.failed
```

事件格式：

```json
{
  "event_id": "evt_xxx",
  "trace_id": "trace_xxx",
  "tenant_id": "tenant_xxx",
  "task_id": "task_xxx",
  "step_id": "step_1",
  "event_type": "capability.succeeded",
  "payload": {},
  "created_at": "2026-05-13T10:00:00+08:00"
}
```

## 9. 目录演进建议

短期新增目录：

```text
api/app/core/agent_platform/
  router_runtime/
  worker_runtime/
  task_engine/
  capability_gateway/
  protocols/
  policies/

api/app/model/
  tenant.py
  agent.py
  capability.py
  task.py
  approval.py
  trace.py

api/app/schema/
  agent_schema.py
  capability_schema.py
  task_schema.py
  approval_schema.py
  trace_schema.py

api/app/service/
  tenant_service.py
  agent_registry_service.py
  capability_registry_service.py
  task_engine_service.py
  approval_service.py
  trace_service.py

api/app/api/routes/
  agent.py
  capability.py
  task.py
  approval.py
  trace.py

api/app/task/
  agent_task.py
```

前端新增或改造：

```text
ui/src/views/space/agents/
ui/src/views/space/capabilities/
ui/src/views/space/tasks/
ui/src/views/space/approvals/
ui/src/views/space/observability/

ui/src/services/agent.ts
ui/src/services/capability.ts
ui/src/services/task.ts
ui/src/services/approval.ts
ui/src/services/trace.ts

ui/src/models/agent.ts
ui/src/models/capability.ts
ui/src/models/task.ts
```

## 10. 实施阶段

### Phase 0：架构地基

目标：先把对象模型和边界建稳。

交付：

1. 新增 Tenant / Workspace 最小模型。
2. 新增 Agent、AgentVersion、AgentBinding。
3. 新增 Capability、AgentCapabilityBinding。
4. 新增 Task、Plan、Step、WorkerCall、CapabilityCall。
5. 新增 TraceEvent。
6. 新增基础 API 和空 UI 页面。

验收：

1. 可以创建 Router / Worker。
2. 可以注册 Capability 并绑定到 Worker。
3. 可以创建 Task 并查看状态。

### Phase 1：最小 Agent 闭环

目标：跑通 Router -> Worker -> Capability -> Result。

交付：

1. Router Runtime 输出 `router_plan_v1`。
2. Task Engine 持久化 Plan / Step。
3. Worker Runtime 接收 `worker_invocation_v1`。
4. Capability Gateway 包装现有 Builtin Tool、API Tool、Workflow、Dataset。
5. Worker 返回 `worker_result_v1`。
6. Redis Stream + SSE 输出任务事件。

验收：

1. Web Chat 可以选择 Router Agent 对话。
2. Router 可以调用至少 2 个 Worker。
3. Worker 可以调用现有工具或知识库。
4. Trace 能展示完整调用链。

### Phase 2：企业治理闭环

目标：补齐权限、审批、审计、知识权限过滤。

交付：

1. RBAC 和 Agent 可见范围。
2. Capability 权限、风险、副作用策略。
3. Approval Request 和审批执行。
4. Knowledge 权限过滤和引用输出。
5. Tool Gateway 二次鉴权、脱敏、审计。

验收：

1. 高风险动作必须审批后执行。
2. 未授权 Capability 无法调用。
3. 知识检索不会返回无权限文档。
4. Trace 可回放审批前后的执行链路。

### Phase 3：产品化增强

目标：把平台从能用升级为可运营。

交付：

1. Agent 模板。
2. 版本回滚和灰度发布。
3. Task Center 的取消、重试、恢复。
4. Evaluation 数据集和批量评测。
5. MCP Tool 接入。
6. 成本统计和质量报表。

验收：

1. 新业务 Agent 可以从模板创建。
2. 发布失败可回滚。
3. 每次版本变更可跑评测集。
4. 成本、成功率、审批率、失败原因可统计。

## 11. 测试策略

后端：

1. Unit Test：协议解析、状态机、权限策略、Schema 校验。
2. Service Test：Agent 创建、Capability 绑定、Task 调度、Approval。
3. Integration Test：PostgreSQL、Redis、Celery、Weaviate。
4. Contract Test：Router Plan、Worker Result、Capability input/output schema。
5. Regression Eval：固定业务样例回归。

前端：

1. Agent Studio 表单和发布流程。
2. Task Center 状态展示。
3. SSE 事件流渲染。
4. Approval 卡片确认。
5. Trace 调用链展示。

质量门禁：

```text
uv run pytest -q
yarn type-check
yarn lint
yarn test:unit --run
yarn build
```

## 12. 风险与取舍

| 风险 | 影响 | 建议 |
| --- | --- | --- |
| `account_id` 到 `tenant_id` 迁移 | 影响几乎所有资源查询 | 先兼容双字段，默认 tenant 回填后逐步切换 |
| 同步 / 异步 SQLAlchemy 混用 | 容易出现事务和 session 混乱 | 新模块明确主路径，避免同一 repository 两套实现 |
| Router 输出不稳定 | Task Engine 无法可靠执行 | 强制 JSON Schema 校验，不合格则重试或降级 |
| Worker 结果纯文本 | Router 无法可靠汇总 | Worker Result 必须结构化 |
| 工具调用越权 | 企业安全事故 | Tool Gateway 二次鉴权和审计前置 |
| 长任务中断 | 用户体验和数据一致性问题 | Task State + Redis Stream + Celery 幂等 |
| 过早微服务化 | 交付变慢，协议未稳定 | MVP 保持模块化单体 |
| 复刻 Dify 过重 | 项目复杂度超出当前阶段 | 只借鉴 API 面、Provider、异步任务、RAG、Workflow 边界 |

## 13. 推荐落地顺序

1. 补 Tenant / Workspace 最小模型。
2. 做 Agent Registry，支持 Router / Worker 两类。
3. 做 Capability Registry，包装现有 Tool、Workflow、Dataset。
4. 做 Task Engine 最小状态机。
5. 做 Worker Runtime 结构化调用和结果。
6. 做 Router Runtime 结构化 Plan。
7. 打通 Redis Stream + SSE。
8. 做 Web Chat 选择 Router Agent。
9. 加 Approval 和 Tool Gateway 风险治理。
10. 加 Trace 页面和基础 Evaluation。

最终目标不是把当前 App 功能替换掉，而是让现有 App、Workflow、Dataset、Tool 都成为 Agent 平台的底座能力。新增 Agent 层负责统一编排、治理和交付。
