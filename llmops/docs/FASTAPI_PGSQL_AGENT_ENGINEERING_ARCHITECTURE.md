# FastAPI + PostgreSQL Agent 平台工程架构设计

补充说明：基于现有 `api` 目录迁移到 `backend` 的详细目录功能边界，以 `docs/BACKEND_API_DIRECTORY_DESIGN.md` 为准。

更新时间：2026-05-13

本文基于当前 `llmops` 项目现状，以及以下设计文档收敛出的工程框架：

- `docs/DIFY_BACKEND_ARCHITECTURE_FASTAPI.md`
- `docs/AGENT_PLATFORM_PRODUCT_DESIGN.md`
- `docs/AGENT_PLATFORM_ENGINEERING_PLAN.md`
- `docs/AGENT_ARCHITECTURE_MAINSTREAM_ROUTER_WORKER.md`

目标是提出一套以 `FastAPI + PostgreSQL` 为主技术栈、贴合当前项目演进的工程架构。它不是重写方案，而是把现有 App、Workflow、Dataset、Tool、Assistant Agent、Celery、Weaviate 能力纳入一个更清晰的 Agent 平台框架。

## 1. 架构结论

推荐采用：

```text
FastAPI 模块化单体
+ PostgreSQL 系统事实库
+ SQLAlchemy 2.x / Alembic
+ Redis / Celery 异步任务和事件流
+ Weaviate 或 pgvector 作为向量检索 Provider
+ 对象存储抽象
+ Router / Worker 双类型 Agent Runtime
+ Task Engine
+ Capability Registry
+ Approval / Policy / Audit Trace
```

第一阶段不建议拆成大量微服务。当前项目功能还在快速演进，Agent、Capability、Task、Approval 等协议也未稳定。先做模块边界，再做服务边界。

明确不采用：

```text
Flask
Flask-RESTX
Flask-SQLAlchemy
Flask-Migrate
Flask-Login
Flask Blueprint
Flask app context
```

核心原则：

1. FastAPI 是唯一 HTTP 服务入口。
2. PostgreSQL 是业务事实库，所有核心状态、配置、任务、审计都落库。
3. Redis 只承担缓存、锁、队列事件和短期流式事件，不作为事实库。
4. Celery 承担文档索引、Agent 任务、工作流执行等长任务。
5. Router / Worker 是仅有的 Agent 运行时类型。
6. Workflow、Tool、Knowledge、Skill、MCP、Sandbox 全部作为 Capability。
7. Task Engine 管确定性状态，Router 只管智能决策。
8. 所有核心资源最终都要有 `tenant_id`。

## 2. 当前项目适配判断

当前后端已有：

```text
api/app/main.py
api/app/server/http.py
api/app/api/routes/*
api/app/service/*
api/app/model/*
api/app/schema/*
api/app/core/agent/*
api/app/core/workflow/*
api/app/core/tools/*
api/app/core/retrievers/*
api/app/task/*
```

当前技术栈已经接近目标主栈：

```text
FastAPI >= 0.115
SQLAlchemy >= 2.0
Alembic >= 1.13
PostgreSQL 15
Redis
Celery
Weaviate
LangChain / LangGraph
Vue 3 / Element Plus
Docker Compose
```

需要重点补齐：

1. `account_id` 到 `tenant_id / workspace_id` 的演进。
2. Agent Registry：统一 Router / Worker 定义和版本。
3. Capability Registry：统一工具、工作流、知识库、Skill。
4. Task Engine：统一 Plan、Step、WorkerCall、CapabilityCall 状态。
5. Approval / Policy：高风险动作审批、权限、脱敏。
6. Trace：跨 Router、Worker、Capability 的统一调用链。
7. API 面：从资源路由逐步演进为 console、service_api、web、files、inner、triggers。

## 3. 总体工程架构

```text
┌──────────────────────────────────────────────┐
│ Frontend                                     │
│ Vue Console / Web Chat / Embedded WebApp      │
└──────────────────────┬───────────────────────┘
                       │
┌──────────────────────▼───────────────────────┐
│ FastAPI API Service                           │
│ APIRouter / Dependencies / Middleware / SSE    │
│ Auth / Tenant Context / Rate Limit / Errors    │
└──────────────────────┬───────────────────────┘
                       │
┌──────────────────────▼───────────────────────┐
│ Application Services                          │
│ AgentService / TaskService / CapabilityService │
│ ApprovalService / DatasetService / ToolService │
└──────────────────────┬───────────────────────┘
                       │
┌──────────────────────▼───────────────────────┐
│ Domain Runtime                                │
│ Router Runtime / Worker Runtime / Task Engine │
│ Workflow Engine / RAG / Tool Gateway / Policy │
└──────────────────────┬───────────────────────┘
                       │
┌──────────────────────▼───────────────────────┐
│ Infrastructure                                │
│ PostgreSQL / Redis / Celery / Object Storage   │
│ Weaviate or pgvector / LLM Providers / HTTP    │
└──────────────────────────────────────────────┘
```

运行进程：

| 进程 | 职责 | 当前项目对应 |
| --- | --- | --- |
| `backend` | FastAPI HTTP、SSE、OpenAPI | `llmops-backend-api` |
| `worker` | Celery 长任务 | `llmops-backend-celery` |
| `beat` | 周期任务，后续增加 | 可后续新增 |
| `migration` | Alembic 数据库迁移 | 当前 `MIGRATION_ENABLED` 可演进 |

## 4. 推荐目录框架

### 4.1 短期兼容目录

为了贴合当前项目，第一阶段建议在现有目录下新增模块，不做大规模搬迁。

```text
api/app/
  api/
    routes/
      agent.py
      capability.py
      task.py
      approval.py
      trace.py
    routers/
      console.py
      service_api.py
      web.py
      files.py
      inner.py
      triggers.py

  service/
    tenant_service.py
    agent_registry_service.py
    capability_registry_service.py
    task_engine_service.py
    approval_service.py
    trace_service.py

  model/
    tenant.py
    agent.py
    capability.py
    task.py
    approval.py
    trace.py

  schema/
    tenant_schema.py
    agent_schema.py
    capability_schema.py
    task_schema.py
    approval_schema.py
    trace_schema.py

  core/
    agent_platform/
      protocols/
      router_runtime/
      worker_runtime/
      task_engine/
      capability_gateway/
      policy/
      event_stream/

  task/
    agent_task.py
```

### 4.2 中期目标目录

当 Agent 平台模块稳定后，可以整理为模块化包。

```text
api/app/modules/
  identity/
    api.py
    models.py
    schemas.py
    service.py

  agent_registry/
    api.py
    models.py
    schemas.py
    service.py

  capability_registry/
    api.py
    models.py
    schemas.py
    service.py

  task_engine/
    api.py
    models.py
    schemas.py
    service.py
    tasks.py

  runtime/
    router/
    worker/
    protocols/

  approval/
  audit_trace/
  evaluation/
```

建议先不执行这次目录重排，避免和业务改造同时发生。

## 5. FastAPI 工程设计

### 5.1 应用创建

当前 `app/main.py` + `app/server/http.py` 已经承担应用创建和扩展初始化。建议向更标准的 app factory + lifespan 演进：

```text
create_app()
  -> load settings
  -> create FastAPI
  -> init logging
  -> init database engine/session
  -> init redis
  -> init storage
  -> init celery config
  -> register exception handlers
  -> register middleware
  -> register routers
  -> lifespan startup/shutdown
```

要点：

1. 配置统一从 `Settings` 读取，不让业务代码直接读环境变量。
2. 数据库、Redis、对象存储、向量库客户端在基础设施层集中初始化。
3. Exception Handler 统一返回项目响应格式。
4. Middleware 统一注入 `trace_id`、`tenant_context`、请求日志。
5. SSE 使用专门的事件生成器，不把业务执行塞在响应生成里。

### 5.2 APIRouter 分面

目标 API 面：

```text
/console/api   控制台管理，JWT/session
/v1            外部服务 API，API Key
/api           WebApp / 嵌入式应用调用
/files         文件上传、预览、签名 URL
/inner/api     内部服务回调
/triggers      Webhook / schedule trigger
```

工程结构：

```text
app/api/routers/console.py
app/api/routers/service_api.py
app/api/routers/web.py
app/api/routers/files.py
app/api/routers/inner.py
app/api/routers/triggers.py
```

分面价值：

1. 不同鉴权方式隔离。
2. CORS 和限流策略隔离。
3. 错误响应和可见字段隔离。
4. 更容易暴露对外 OpenAPI。

### 5.3 Dependency 规范

推荐依赖：

```text
get_db_session
get_current_user
get_current_tenant
get_current_member
get_api_key_context
check_permission
get_trace_context
```

注意当前项目混用了 async dependency 和同步 service / db 封装。短期建议明确主路径：

```text
Phase 1:
  以同步 SQLAlchemy Session 作为 service 和 Celery 的主路径。
  FastAPI endpoint 可以是 async，但不要在一个事务中混用 async session 和 sync session。

Phase 2:
  如果确实需要 async SQLAlchemy，再为新模块建立完整 async repository。
  不要同一业务模块同时维护 sync / async 两套仓储。
```

## 6. PostgreSQL 数据库架构

PostgreSQL 是系统事实库，适合承载：

1. 租户、成员、权限。
2. Agent、版本、发布配置。
3. Capability 元数据。
4. Task、Plan、Step、Call 状态。
5. Approval、Artifact。
6. Trace、Evaluation、成本统计。
7. 会话、消息、运行结果。

### 6.1 通用表规范

核心业务表统一字段：

```text
id UUID primary key
tenant_id UUID not null
created_by UUID null
status varchar not null
created_at timestamp not null
updated_at timestamp not null
deleted_at timestamp null
```

索引规范：

```text
tenant_id + id
tenant_id + status
tenant_id + created_at
tenant_id + created_by
tenant_id + business_unique_key
```

所有跨租户资源查询必须带 `tenant_id`。

### 6.2 JSONB 使用边界

适合放 JSONB：

1. Agent 版本配置。
2. Router Plan。
3. Worker Invocation / Result。
4. Capability input/output schema。
5. 策略配置。
6. Trace payload。

不适合只放 JSONB：

1. 高频筛选字段。
2. 权限过滤字段。
3. 任务状态字段。
4. 时间范围查询字段。
5. 成本统计字段。

设计规则：

```text
高频查询字段列化。
低频扩展字段 JSONB。
JSONB 字段需要查询时再加 GIN 或表达式索引。
```

### 6.3 分区建议

以下表会快速膨胀，建议中期按时间分区：

```text
trace_events
capability_calls
worker_calls
agent_steps
agent_tasks
message_agent_thought
```

分区策略：

```text
按月 RANGE(created_at) 分区。
保留最近 3-6 个月热数据。
历史数据归档到对象存储或低成本库。
```

MVP 阶段可以先不分区，但表结构要预留清理和归档能力。

### 6.4 事务边界

事务放在 Service 层，不放在 Router 层或 Core Runtime 深处。

建议：

```text
Service:
  创建 Task、Plan、Step、审批请求。
  更新业务状态。
  负责事务提交或回滚。

Runtime:
  只返回决策或执行结果。
  不直接 commit。

Repository:
  只封装复杂查询和持久化细节。
  不做跨用例业务编排。
```

### 6.5 并发控制

Task Engine 需要防止并发重复执行。

建议：

1. 对任务状态更新使用乐观锁字段 `version`。
2. 对 Worker / Capability 调用使用 `idempotency_key`。
3. 对待执行 Step 可使用 `SELECT ... FOR UPDATE SKIP LOCKED`。
4. Celery task 必须可重试且幂等。
5. 外部写操作必须记录请求和结果，避免重复执行。

## 7. 核心数据模型

### 7.1 Identity / Tenant

```text
tenants
tenant_members
roles
permissions
role_permissions
member_roles
```

过渡策略：

```text
tenant_id 初期可等于 account_id。
历史表先新增 nullable tenant_id。
回填完成后逐步改为 not null。
旧权限逻辑 account_id 校验继续保留一段兼容期。
```

### 7.2 Agent Registry

```text
agents
  id
  tenant_id
  name
  icon
  description
  runtime_type          router / worker
  product_category      sales / finance / knowledge / data / custom
  status                draft / published / archived
  draft_version_id
  published_version_id
  visibility_scope
  created_by
  created_at
  updated_at

agent_versions
  id
  tenant_id
  agent_id
  version
  config_type           draft / published
  model_config          JSONB
  prompt_config         JSONB
  router_config         JSONB
  worker_config         JSONB
  capability_bindings   JSONB
  policies              JSONB
  output_schema         JSONB
  created_at
  updated_at

agent_bindings
  id
  tenant_id
  router_agent_id
  worker_agent_id
  enabled
  priority
  conditions            JSONB
```

### 7.3 Capability Registry

```text
capabilities
  id
  tenant_id
  name
  type                  tool / workflow / skill / knowledge_base / mcp_tool / sandbox / agent_tool
  provider
  target_ref_type       builtin_tool / api_tool / workflow / dataset / mcp_server / sandbox
  target_ref_id
  description
  input_schema          JSONB
  output_schema         JSONB
  permission
  risk_level            low / medium / high / critical
  side_effect           none / read / write / external / critical
  requires_approval
  idempotency_required
  timeout_seconds
  retry_policy          JSONB
  data_scope_policy     JSONB
  audit_policy          JSONB
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
  params                JSONB
  enabled
```

### 7.4 Task Engine

```text
agent_tasks
agent_plans
agent_steps
worker_calls
capability_calls
```

核心状态：

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

### 7.5 Approval / Trace / Evaluation

```text
approval_requests
artifacts
trace_events
evaluation_sets
evaluation_cases
evaluation_runs
evaluation_results
```

## 8. Agent 运行时框架

### 8.1 Router Runtime

职责：

1. 根据用户输入和上下文生成结构化 Plan。
2. 选择 Worker。
3. 判断是否追问、拒绝、审批或继续执行。
4. 汇总 Worker 结果。
5. 输出最终响应。

输入：

```text
tenant_context
user_context
conversation_context
router_agent_version
user_message
attachments
```

输出：

```text
router_plan_v1
final_response
need_clarification
policy_blocked
```

### 8.2 Worker Runtime

职责：

1. 接收 `worker_invocation_v1`。
2. 执行 ReAct / tool calling loop。
3. 调用 Capability Gateway。
4. 返回 `worker_result_v1`。

限制：

```text
max_steps
max_tool_calls
timeout_seconds
allowed_capability_ids
output_schema
```

### 8.3 Task Engine

职责：

1. 持久化 Task / Plan / Step。
2. 调度 Worker。
3. 管理并发、超时、重试、取消、恢复。
4. 创建 Approval。
5. 发布事件到 Redis Stream。
6. 写 Trace。

Task Engine 不调用 LLM 做规划。LLM 规划归 Router，工程状态归 Task Engine。

### 8.4 Capability Gateway

职责：

1. 解析 Capability 元数据。
2. 校验权限、风险、副作用、参数 schema。
3. 执行工具、工作流、知识库、MCP、沙箱。
4. 处理超时、重试、幂等、审计和脱敏。
5. 返回结构化 Capability Result。

当前项目映射：

```text
Builtin Tool       -> tool capability
API Tool           -> tool capability
Workflow           -> workflow capability
Dataset / Weaviate -> knowledge_base capability
Assistant Agent    -> 可演进为 router debug 或内置 router
```

## 9. 异步任务和事件流

### 9.1 Celery 队列

建议按业务隔离队列：

```text
agent_runtime
workflow_runtime
document_indexing
tool_calls
evaluation
mail
cleanup
```

任务规范：

1. task 参数只传 Pydantic 可序列化对象或 ID，不传 ORM 对象。
2. 所有 task 必须幂等。
3. 重试只针对可重试错误。
4. 外部写动作必须有 `idempotency_key`。
5. 长任务进度写入 `trace_events` 和 Redis Stream。

### 9.2 Redis Stream

建议 Redis Stream 用于 Agent 任务事件流：

```text
agent_task:{task_id}:events
```

事件类型：

```text
task.created
plan.created
step.started
worker.started
worker.message_delta
capability.started
capability.succeeded
approval.required
artifact.created
task.succeeded
task.failed
```

事实记录仍写 PostgreSQL，Redis Stream 只承担短期实时推送。

### 9.3 SSE 输出

FastAPI SSE endpoint：

```text
GET /console/api/tasks/{task_id}/events
GET /v1/tasks/{task_id}/events
```

职责：

1. 验证用户或 API Key 是否可访问 task。
2. 从 Redis Stream 读取事件。
3. 补偿读取 PostgreSQL 中已有最终状态。
4. 输出标准 SSE。

## 10. RAG 和向量检索

当前项目已使用 Weaviate。建议：

```text
Phase 1:
  保留 Weaviate，不迁移已有向量能力。
  PostgreSQL 只保存 Dataset、Document、Segment、ACL、索引状态。

Phase 2:
  增加 VectorStore Provider 抽象。
  支持 Weaviate 和 pgvector 双 Provider。

Phase 3:
  根据部署复杂度选择默认 Provider。
  如果强调单库简化部署，可将 pgvector 设为默认。
```

知识库权限必须由 PostgreSQL 元数据控制：

```text
tenant_id
dataset_acl
document_acl
chunk_acl
metadata_filter
field_masking
retrieval_audit
```

检索链路：

```text
Worker
  -> Knowledge Capability
  -> Knowledge Service
  -> PostgreSQL permission filter
  -> VectorStore Provider
  -> rerank
  -> citation assembly
  -> Worker Result
```

## 11. 配置和基础设施

### 11.1 配置

建议引入 `pydantic-settings`，替代业务代码直接读环境变量。

配置分组：

```text
AppSettings
DatabaseSettings
RedisSettings
CelerySettings
StorageSettings
VectorStoreSettings
LLMProviderSettings
SecuritySettings
ObservabilitySettings
```

### 11.2 部署

当前 Docker Compose 可以保留：

```text
llmops-ui
llmops-backend-api
llmops-backend-celery
llmops-db
llmops-redis
llmops-weaviate
llmops-nginx
```

建议补充：

1. API health check。
2. Celery worker health check。
3. migration 独立 job。
4. Redis 和 PostgreSQL 连接池参数。
5. 环境变量模板按模块分区。
6. 生产关闭 `SQLALCHEMY_ECHO`。

## 12. 前端工程适配

当前前端已有：

```text
ui/src/views/space/apps
ui/src/views/space/workflows
ui/src/views/space/datasets
ui/src/views/space/tools
ui/src/services/*
ui/src/models/*
```

建议新增：

```text
ui/src/views/space/agents
ui/src/views/space/capabilities
ui/src/views/space/tasks
ui/src/views/space/approvals
ui/src/views/space/observability

ui/src/services/agent.ts
ui/src/services/capability.ts
ui/src/services/task.ts
ui/src/services/approval.ts
ui/src/services/trace.ts

ui/src/models/agent.ts
ui/src/models/capability.ts
ui/src/models/task.ts
```

页面顺序：

1. Agent 列表和创建。
2. Worker 能力绑定。
3. Router 调试台。
4. Task 详情和事件流。
5. Approval 待办。
6. Trace 调用链。

## 13. 测试和质量门禁

后端测试：

```text
unit:
  schema validation
  policy decision
  task state transition
  router plan parser
  worker result parser

service:
  agent create / publish
  capability bind / call
  task create / dispatch
  approval approve / reject

integration:
  PostgreSQL
  Redis Stream
  Celery task
  Weaviate retrieval
```

命令：

```bash
cd backend
uv run pytest -q
uv run ruff check app tests
```

前端：

```bash
cd ui
yarn type-check
yarn lint
yarn test:unit --run
yarn build
```

数据库：

```bash
cd backend
uv run alembic -c app/alembic/alembic.ini upgrade head
uv run alembic -c app/alembic/alembic.ini heads
```

## 14. 实施路径

### Phase 0：技术地基

1. 引入 Settings 分组。
2. 规范 app factory、router 注册、exception handler。
3. 新增 tenant 最小模型。
4. 统一 PostgreSQL session 使用规范。
5. 新增 Agent / Capability / Task 基础表。

### Phase 1：Agent 最小闭环

1. Agent Registry 支持 Router / Worker。
2. Capability Registry 包装现有 Tool、Workflow、Dataset。
3. Router Runtime 输出结构化 Plan。
4. Worker Runtime 返回结构化 Result。
5. Task Engine 持久化 Task / Step / Call。
6. Redis Stream + SSE 输出事件。

### Phase 2：企业治理

1. RBAC 和 Agent 可见范围。
2. Capability 权限、风险、副作用策略。
3. Approval 高风险动作审批。
4. Knowledge 权限过滤和引用。
5. Trace 调用链和成本统计。

### Phase 3：可运营平台

1. Agent 模板。
2. 版本回滚和灰度。
3. Task 重试、取消、恢复。
4. Evaluation 回归评测。
5. MCP 和 Sandbox Provider。
6. pgvector Provider 可选接入。

## 15. 工程取舍

| 选择 | 结论 | 原因 |
| --- | --- | --- |
| 架构形态 | 模块化单体优先 | 当前协议未稳定，拆微服务会拖慢迭代 |
| 主数据库 | PostgreSQL | JSONB、事务、索引、分区、生态完整 |
| ORM | SQLAlchemy 2.x | 当前项目已使用，生态成熟 |
| 迁移 | Alembic | 当前项目已有 |
| 队列 | Celery + Redis | 当前项目已有，适合长任务 |
| 事件流 | Redis Stream + SSE | 实现简单，贴合 Agent 流式任务 |
| 向量库 | Weaviate 保留，pgvector 可选 | 当前已有 Weaviate，pgvector 可降低部署复杂度 |
| Agent 类型 | Router / Worker | 产品清晰，治理简单 |
| 工作流 | Capability | 不再设计成第三类 Agent |
| 租户 | tenant_id 标准化 | 企业级平台必须具备租户隔离 |

## 16. 参考资料

主流技术设计参考：

1. FastAPI Bigger Applications / APIRouter：`https://fastapi.tiangolo.com/tutorial/bigger-applications/`
2. FastAPI Lifespan Events：`https://fastapi.tiangolo.com/advanced/events/`
3. SQLAlchemy 2.0 ORM Session：`https://docs.sqlalchemy.org/en/20/orm/session.html`
4. Alembic Documentation：`https://alembic.sqlalchemy.org/en/latest/`
5. PostgreSQL JSON Types：`https://www.postgresql.org/docs/current/datatype-json.html`
6. PostgreSQL Table Partitioning：`https://www.postgresql.org/docs/current/ddl-partitioning.html`
7. Celery Tasks：`https://docs.celeryq.dev/en/stable/userguide/tasks.html`
8. Redis Streams：`https://redis.io/docs/latest/develop/data-types/streams/`
9. Pydantic Settings：`https://docs.pydantic.dev/latest/concepts/pydantic_settings/`
