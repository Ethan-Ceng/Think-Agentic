# Backend 新工程迁移执行计划（api-first 修订版）

目录功能边界见 `docs/BACKEND_API_DIRECTORY_DESIGN.md`。后续迁移必须先判断旧代码职责，再放入对应目录，避免凭空新增目录。

更新时间：2026-05-14

本计划用于把当前 `api` 工程迁移到新的 `backend` 工程。核心原则已经修订为：

```text
先迁移现有 api 已实现能力
再用新架构做边界整理
不绕开已有 worker agent / tool / workflow / dataset / app 实现
不从零重写一套平台能力
```

`docs/DIFY_BACKEND_ARCHITECTURE_FASTAPI.md` 作为稳定架构参考，但落地方式必须贴合当前项目已有代码。新 `backend` 的职责是承接和整理旧 `api`，不是另起炉灶。

## 0. 技术边界

目标技术栈：

```text
FastAPI
APIRouter
FastAPI dependency injection
FastAPI lifespan
Pydantic / Pydantic Settings
SQLAlchemy 2.x
Alembic
PostgreSQL
Redis
Celery
SSE / Redis Stream
Weaviate first, pgvector optional later
```

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

## 1. 修订后的迁移策略

原计划过于偏“新设计落表”。现在修订为 api-first：

```text
backend 工程骨架
  -> 迁移旧 api 基础设施
  -> 迁移旧 api 现有数据模型和表结构
  -> 迁移旧 api 现有 service / core runtime
  -> 迁移旧 api 现有 routes
  -> 保持旧 UI 和调用语义可兼容
  -> 再逐步加 Router / Worker / Capability / Task Engine 统一外壳
```

优先级：

1. **保留旧 api 已有能力**：App、Assistant Agent、FunctionCall/ReAct Agent、Tool、Workflow、Dataset、Conversation、OpenAPI、Weaviate。
2. **保留旧数据表语义**：短期优先兼容旧表名和字段，避免先做大规模数据迁移。
3. **保留旧接口行为**：新 backend 可以换 API 分面，但迁移阶段要保证 UI 可以逐步切换。
4. **新架构作为外壳**：Capability Registry、Task Engine、Trace 等作为已有能力的治理层，不替代已有实现。

## 2. 当前 api 能力映射

| 旧 api 模块 | 已有能力 | backend 目标位置 | 迁移策略 |
| --- | --- | --- | --- |
| `app/model/account.py` | Account / OAuth / 密码登录基础 | `backend/app/models/account.py` | 优先保留旧表兼容，后续再加 tenant |
| `app/service/account_service.py` | 账号查询、token 用户解析 | `backend/app/services/account_service.py` | 直接迁移并改依赖注入 |
| `app/service/jwt_service.py` | JWT | `backend/app/core/security.py` 或 service | 复用逻辑，统一 settings |
| `app/model/app.py` | Agent/App 配置、草稿、发布 | `backend/app/models/app.py` | 作为现有 Worker/App 能力迁移，不先替换成新 Agent 表 |
| `app/service/app_service.py` | App 创建、调试、发布、工具/知识/工作流绑定 | `backend/app/services/app_service.py` | 分块迁移，先保接口行为 |
| `app/core/agent/*` | ReAct Agent、FunctionCall Agent、队列事件 | `backend/app/core/agent/*` | 直接迁移，后续挂到 Worker Runtime |
| `app/service/assistant_agent_service.py` | 辅助 Agent，会话、工具调用、自动建 App | `backend/app/services/assistant_agent_service.py` | 迁移为已有 Agent 能力，不重写 |
| `app/core/tools/builtin_tools/*` | 内置工具 Provider | `backend/app/core/tools/builtin_tools/*` | 直接迁移，后续包装为 Capability |
| `app/core/tools/api_tools/*` | OpenAPI Tool 解析与调用 | `backend/app/core/tools/api_tools/*` | 直接迁移，后续通过 Tool Gateway 调用 |
| `app/model/api_tool.py` | API Tool Provider / Tool 表 | `backend/app/models/api_tool.py` | 保留旧表语义 |
| `app/service/api_tool_service.py` | API Tool CRUD 和 OpenAPI 解析 | `backend/app/services/api_tool_service.py` | 优先迁移 |
| `app/core/workflow/*` | LangGraph Workflow、节点、变量 | `backend/app/core/workflow/*` | 直接迁移，后续包装为 Workflow Capability |
| `app/model/workflow.py` | Workflow / WorkflowResult | `backend/app/models/workflow.py` | 保留旧表语义 |
| `app/service/workflow_service.py` | 工作流 CRUD、调试、发布 | `backend/app/services/workflow_service.py` | 优先迁移 |
| `app/model/dataset.py` | Dataset / Document / Segment / ProcessRule | `backend/app/models/dataset.py` | 保留旧表语义 |
| `app/service/dataset_service.py` | 知识库管理 | `backend/app/services/dataset_service.py` | 迁移后再增强权限 |
| `app/service/indexing_service.py` | 文档索引 | `backend/app/services/indexing_service.py` | 迁移 Celery 任务前置 |
| `app/service/retrieval_service.py` | RAG 检索 | `backend/app/services/retrieval_service.py` | 直接迁移，后续包装 Knowledge Capability |
| `app/model/conversation.py` | Conversation / Message / Thought | `backend/app/models/conversation.py` | 保留旧消息和 trace 基础 |
| `app/service/conversation_service.py` | 会话和消息保存 | `backend/app/services/conversation_service.py` | 迁移后作为 Agent trace 基础 |
| `app/task/*` | Celery app/document/dataset 任务 | `backend/app/tasks/*` | 迁移并按队列拆分 |
| `pkg/*` | response、paginator、sqlalchemy、oauth、password | `backend/app/shared/*` 或 `backend/app/infrastructure/*` | 先迁移必要包 |

## 3. 迁移里程碑

### M0：backend 工程骨架

- [x] 创建 `backend/`。
- [x] 创建 FastAPI app factory。
- [x] 创建 Settings。
- [x] 创建 API 分面路由。
- [x] 创建 DB / Redis / Celery 基础设施。
- [x] 创建 Alembic 基础配置。
- [x] 创建健康检查。
- [x] 创建最小测试。

说明：

当前 `backend` 中已创建的 Agent / Capability / Task 初始模型只作为后续治理层草案，不作为下一阶段迁移主线。下一阶段要优先迁移旧 `api` 已有模型和服务。

### M1：迁移基础包和基础设施

- [x] 迁移 `pkg/response` 到 `backend/app/shared/response`。
- [x] 迁移 `pkg/paginator` 到 `backend/app/shared/paginator`。
- [x] 迁移 `pkg/password` 到 `backend/app/shared/password`。
- [x] 迁移 `pkg/oauth` 到 `backend/app/integrations/oauth`。
- [x] 对齐旧 `pkg/sqlalchemy` 能力与新 SQLAlchemy session。
- [x] 迁移旧异常类型并统一 FastAPI exception handler。
- [x] 迁移旧配置项到 `pydantic-settings`。

验收标准：

- [x] 旧 service 迁移时不需要继续依赖 `api/pkg`。
- [x] 旧响应格式可兼容 UI。
- [x] 分页格式可兼容 UI。

### M2：迁移 Account / Auth / API Key

- [x] 迁移 `app/model/account.py`，优先兼容旧 `account` 表。
- [x] 迁移 `app/model/api_key.py`。
- [x] 迁移 `app/service/account_service.py`。
- [x] 迁移 `app/service/jwt_service.py`。
- [x] 迁移 `app/service/oauth_service.py`。
- [x] 实现 FastAPI `get_current_user`。
- [x] 实现 API Key 鉴权。
- [x] 迁移登录、OAuth、profile、API Key routes。

验收标准：

- [ ] 旧账号可在 backend 登录。
- [ ] UI 可以用旧 token 逻辑访问 backend。
- [ ] API Key 调用面可用。

### M3：迁移 Tool 能力

- [x] 迁移 `app/model/api_tool.py`。
- [x] 迁移 `app/core/tools/builtin_tools/*` 第一批：metadata / provider / category / no-LangChain runtime。
- [x] 迁移 `app/core/tools/api_tools/*` 第一批：OpenAPI Schema 解析实体。
- [x] 迁移 `app/service/builtin_tool_service.py`。
- [x] 迁移 `app/service/api_tool_service.py` 第一批：Provider CRUD / OpenAPI 解析 / Tool 记录生成。
- [x] 迁移 API Tool routes。
- [x] 新增 Tool Capability adapter，但不改变旧 Tool 行为。

验收标准：

- [x] 内置工具列表可用。
- [x] OpenAPI Tool 创建、解析、查询可用。
- [x] 已有 Agent/App 仍能绑定工具。

### M4：迁移 Workflow 能力

- [x] 迁移 `app/model/workflow.py`，保留旧 `workflow` / `workflow_result` 表语义。
- [x] 迁移 `app/entity/workflow_entity.py` 第一批：状态枚举、节点枚举、默认配置。
- [x] 迁移 `app/core/workflow/*` 第一批：轻量实体和图校验，不引入 LangGraph/LangChain。
- [x] 迁移 `app/service/workflow_service.py` 第一批：CRUD、草稿图、元数据补全、校验式 debug、发布/取消发布。
- [x] 迁移 Workflow routes，保留 `/workflows` 旧路径。
- [x] 迁移完整 Workflow runtime 第一批：Start / LLM / Knowledge Retrieval / HTTP / Code / Tool / End 节点真实执行。
- [x] 补齐 Workflow 图语义第一批：唯一入口/出口、上游变量引用校验、并行分支 join 批次执行。
- [x] 补齐 Workflow 异常图场景第一批：循环图、缺失变量引用、节点失败中断下游执行。
- [ ] 补齐 Workflow Docker smoke 和更复杂条件图场景。
- [x] 新增 Workflow Capability adapter，但不改变旧 Workflow 调试和发布行为。

验收标准：

- [x] 工作流创建、草稿更新、校验式调试、发布状态流转可用。
- [x] 现有节点 Start / LLM / Knowledge Retrieval / HTTP / Code / Tool / End 第一批 runtime 可用。
- [x] 工作流可以继续作为工具被 Agent/App 调用。
- [x] 工作流可以作为 Capability descriptor 被 Agent/App runtime 绑定。

### M5：迁移 Dataset / RAG 能力

- [x] 迁移 `app/model/dataset.py` 第一批：Dataset / Document / Segment / KeywordTable / DatasetQuery / ProcessRule。
- [x] 迁移 `app/service/dataset_service.py` 第一批：CRUD、查询记录、命中测试 DB fallback。
- [x] 迁移 `app/service/document_service.py` 第一批：文档记录 CRUD、批次状态、启停、删除。
- [x] 迁移 `app/service/segment_service.py` 第一批：分段 CRUD、启停、删除、文档统计回写。
- [x] 迁移 `app/service/indexing_service.py` 第一批。
- [x] 迁移 `app/service/retrieval_service.py` 第一批：全文/向量/混合检索接入 DatasetService runtime。
- [x] 迁移 `app/core/retrievers/*` 第一批：不引入 LangChain，使用 backend 原生检索路径承接。
- [x] 迁移 Weaviate extension / vector service 第一批：REST/GraphQL client、schema bootstrap、offline hash embedding、OpenAI embedding optional。
- [x] 迁移 document/dataset Celery tasks 第一批。

验收标准：

- [x] 知识库、文档、分段管理第一批 API 可用。
- [x] 文档索引任务第一批可用。
- [x] Agent/App 的知识库检索第一批 runtime 可用。
- [ ] Weaviate Docker smoke / real embedding provider smoke 通过。

### M6：迁移 App / Existing Agent Runtime

- [x] 迁移 `app/model/app.py` 第一批：App / AppConfig / AppConfigVersion / AppDatasetJoin。
- [x] 迁移 `app/model/conversation.py` 第一批：Conversation / Message / MessageAgentThought。
- [x] 迁移 `app/core/agent/*` 第一批：事件、停止标记、FunctionCall/ReAct 循环。
- [x] 迁移 `app/core/memory/*` 第一批：会话历史读取。
- [x] 迁移 `app/core/language_model/*` 第一批：Provider metadata、OpenAI-compatible runtime、tool-call 解析。
- [x] 迁移 `app/service/app_service.py` 第一批：App CRUD、草稿配置、发布、历史、token。
- [x] 迁移 `app/service/app_config_service.py` 相关能力第一批：配置元数据展示、runtime tool 构建、失效引用过滤。
- [x] 迁移 `app/service/conversation_service.py` 第一批：会话消息查询、软删除、会话属性更新。
- [x] 迁移 `app/service/assistant_agent_service.py` 第一批。
- [x] 迁移 App / Conversation routes 第一批。
- [x] 迁移 Assistant Agent routes 第一批。

验收标准：

- [x] 旧 App 创建、配置、发布第一批可用。
- [x] 旧 App debug-chat 第一批 runtime 可用。
- [x] FunctionCall Agent / ReAct Agent 第一批可用。
- [x] Assistant Agent 第一批可用。
- [x] 会话、消息、AgentThought 保存可用。
- [ ] 真实 provider credentials / streaming chunk / provider-specific tool-call 端到端 smoke 通过。

### M7：迁移文件、语音、渠道和发布能力

- [x] 迁移 upload file / local storage 第一批。
- [x] 迁移 audio 第一批。
- [x] 迁移 web app 第一批。
- [x] 迁移 wechat 第一批。
- [x] 迁移 openapi service 第一批。
- [x] 迁移 platform publishing / WeChat config 第一批。

验收标准：

- [ ] 文件上传和访问可用。
- [ ] WebApp 发布调用可用。
- [ ] OpenAPI 调用可用。

### M8：新架构治理层接入

在 M3-M6 已迁移能力稳定后，再接入新架构治理层。

- [x] 将旧 Tool 包装为 Capability。
- [x] 将旧 Workflow 包装为 Capability。
- [x] 将旧 Dataset/RAG 包装为 Knowledge Capability。
- [x] 将旧 App/Agent 归类为 Worker Agent。
- [x] 新增 Router Agent manager 模式。
- [x] 引入 Task Engine 管长任务状态第一批。
- [x] 引入 Approval / Policy / Audit Trace。

验收标准：

- [x] 不破坏旧 App/Workflow/Tool 行为。
- [x] Router 可以调度已有 Worker/App。
- [x] Capability 只是治理外壳，不替代原实现。

### M9：UI 和 Docker 切换

- [ ] Docker Compose 增加 `backend` 服务，与旧 `api` 双跑。
- [ ] UI service 层逐模块切换到 backend。
- [ ] 对外 `/v1` API 切换到 backend。
- [ ] 验证核心功能。
- [ ] 旧 `api` 进入只读或下线流程。

## 4. 执行规则

每迁移一个模块，必须按顺序做：

```text
1. 读取旧 api 的 model/schema/service/route/core/task。
2. 保留旧业务行为和数据表语义。
3. 在 backend 中适配 FastAPI / Settings / 新 session。
4. 补最小测试。
5. 跑 ruff 和 pytest。
6. 更新本文状态。
```

不要在同一步同时做：

```text
迁移旧模块 + 重命名表 + 改业务语义 + 引入新治理层
```

否则问题会难定位。

## 5. 当前执行状态

| 阶段 | 状态 | 说明 |
| --- | --- | --- |
| M0 | completed | `backend` 最小工程骨架已创建，测试和 ruff 通过 |
| M1 | completed | 已迁移 response / paginator / password / oauth / exception / SQLAlchemy facade / 旧配置映射 |
| M2 | in_progress | 已迁移 Account/Auth/API Key 第一批代码，下一步数据库联调与旧 UI 验证 |
| M3 | completed | 已迁移 API Tool、Builtin Tool metadata/service/runtime，并接入 Tool Capability adapter |
| M4 | in_progress | 已迁移 Workflow 第一批 API、轻量节点运行时、图语义和并行分支 join；待 Docker smoke |
| M5 | in_progress | 已迁移 Dataset / Document / Segment、索引链、PgSQL fallback、Weaviate/vector 第一批；待 Docker/真实 embedding smoke |
| M6 | in_progress | 已迁移 App/Agent debug runtime、FunctionCall/ReAct loop、Memory、Language Model 第一批；待真实 provider smoke |
| M7 | in_progress | 已迁移 UploadFile、OpenAPI、WebApp、Assistant、Audio、WeChat、AI 第一批；待真实凭证端到端 smoke |
| M8 | completed | Capability adapter、旧 App/Agent Worker 归类、Router manager、Task Engine、Approval / Policy / Audit Trace 第一批已接入 |
| M9 | pending | UI / Docker 切换 |

## 6. 已完成记录

### 2026-05-13 M0 执行记录

已完成：

- 新增 `backend/` FastAPI 工程骨架。
- 新增 `backend/pyproject.toml`。
- 新增 `backend/app/app_factory.py` 和 `backend/app/main.py`。
- 新增 API 分面路由。
- 新增健康检查。
- 新增 Settings、错误处理、日志、安全、tenant context 基础模块。
- 新增 PostgreSQL session、Redis client、Celery app 基础设施。
- 新增 Router / Worker 运行协议占位。
- 新增 Alembic 基础配置。
- 新增最小健康检查测试。
- 已执行 `backend/.venv/Scripts/pytest -q`，通过。
- 已执行 `backend/.venv/Scripts/ruff.exe check app tests`，通过。

纠偏说明：

- 当前 `backend` 里早期创建的 Agent / Capability / Task 模型暂时视为未来治理层草案。
- 后续执行顺序改为迁移旧 `api` 现有能力优先。
- 不再按“新表和新服务从零实现”的方式推进。

### 2026-05-13 M1 执行记录

已完成：

- 迁移 `api/pkg/response` 到 `backend/app/shared/response`。
- 迁移 `api/pkg/paginator` 到 `backend/app/shared/paginator`。
- `PaginatorReq`、`Paginator`、`PageModel` 保留旧接口名。
- `Paginator` 支持旧 `Query` 用法，也支持 SQLAlchemy 2.x `select(...)` 用法。
- 新增 shared response / paginator 单元测试。
- 已执行 `.\.venv\Scripts\ruff.exe check app tests`，通过。
- 已执行 `.\.venv\Scripts\python.exe -m pytest -q`，通过。
- 迁移 `api/pkg/password` 到 `backend/app/shared/password`。
- 迁移 `api/pkg/oauth` 到 `backend/app/integrations/oauth`，内部使用 backend 已依赖的 `httpx`。
- 迁移旧 `CustomException` / `FailException` / `NotFoundException` / `UnauthorizedException` / `ForbiddenException` / `ValidateErrorException` 到 `backend/app/core/exceptions.py`。
- FastAPI exception handler 已兼容旧业务响应结构。
- `backend/app/infrastructure/db.py` 增加轻量 `SQLAlchemy` facade，支持旧 service 迁移阶段继续使用 `db.session`、`db.auto_commit()`、`db.session_scope()`、`db.paginate()`。
- 新增 password / oauth / exception / db facade 单元测试。
- 再次执行 `.\.venv\Scripts\ruff.exe check app tests`，通过。
- 再次执行 `.\.venv\Scripts\python.exe -m pytest -q`，14 个测试通过。

### 2026-05-14 M1 旧配置映射收敛记录

已完成：

- `Settings` 补齐旧 `SQLALCHEMY_*`、`REDIS_*`、`CELERY_*`、`ASSISTANT_AGENT_ID`、`SERVICE_*`、`LOCAL_STORAGE_*`、`COS_*`、`DEFAULT_LLM_*`、Provider key/base-url、Weaviate GRPC 配置映射。
- `Settings` 支持旧 `CORS_ALLOW_ORIGINS` 逗号分隔格式。
- Redis / Celery URL 可由旧 Redis 分项配置自动组装，同时保留显式 URL 覆盖。
- `DEFAULT_APP_CONFIG`、Assistant Agent、Audio、UploadFile、Builtin Tool、ChatCompletionRuntime、LanguageModelService 已改为通过 settings 读取配置。
- backend 代码中已无直接 `os.getenv` / `os.environ` 配置读取。
- 新增 settings 配置映射回归测试。

验证：

- 已执行 `uv run pytest -q tests/test_core_config.py tests/test_upload_file.py tests/test_platform_wechat_ai_audio.py tests/test_language_model.py tests/test_builtin_tool.py`，16 个测试通过。
- 已执行 `uv run ruff check app tests`，通过。
- 已执行 `uv run pytest -q`，87 个测试通过。

### 2026-05-13 M2 执行记录

已完成：

- 将 backend `Account` 模型从草稿 `accounts` 表修正为旧 `api` 的 `account` 表语义。
- 迁移 `AccountOAuth`，保留 `account_oauth` 表名和核心字段。
- 新增 `ApiKey` 模型，保留旧 `api_key` 表名和核心字段。
- 修正 `TenantMember.user_id` 外键目标为 `account.id`。
- 更新 Alembic 初始迁移，创建 `account`、`account_oauth`、`api_key`。
- 迁移 `JwtService`，使用 backend 已依赖的 `python-jose`。
- 迁移 `AccountService`：账号查询、token 解析、密码更新、密码登录。
- 迁移 `ApiKeyService`：创建、查询、更新、启停、删除、分页。
- 迁移 `OAuthService`：GitHub OAuth redirect / authorize 登录流程。
- 新增 FastAPI 依赖：`get_current_account`、`get_api_key_account`。
- 迁移旧路径路由：`/auth`、`/account`、`/openapi/api-keys`、`/oauth`。
- 新增 OAuth route smoke test，确认旧路径和旧响应结构可用。
- 已执行 `.\.venv\Scripts\ruff.exe check app tests`，通过。
- 已执行 `.\.venv\Scripts\python.exe -m pytest -q`，15 个测试通过。
- 已执行 `.\.venv\Scripts\alembic.exe heads`，通过。

已完成数据库验证：

- Docker 启动后，确认 PostgreSQL / Redis / Weaviate 正常运行。
- 旧数据库当前业务表来自 `api`，Alembic 版本为 `b017b44df199`。
- 已将旧 `api/app/alembic/versions` 迁入 backend，作为 backend 的旧库基线。
- 已将 backend 新 migration 接到 `b017b44df199` 之后。
- 已执行 `alembic upgrade head`，数据库版本升级到 `20260513_0001`。
- 已确认新增表：`tenants`、`tenant_members`、`roles`、`permissions`、`agents`、`capabilities`、`agent_tasks` 等。

仍需验证：

- 用真实旧账号数据验证密码登录、更新资料、API Key CRUD。
- OAuth authorize 流程需要真实 GitHub OAuth 配置联调。

### 2026-05-13 M3 执行记录

已完成：

- 新增 `ApiToolProvider` / `ApiTool` 模型，保留旧 `api_tool_provider` / `api_tool` 表语义。
- 新增 `backend/app/core/tools/api_tools/entities/openapi_schema.py`，迁移 OpenAPI schema 校验和规范化逻辑。
- 新增 `ApiToolService`，支持 provider 列表、创建、更新、删除、详情、工具详情、OpenAPI schema 解析。
- 新增 `/api-tools` 路由，保留旧路径。
- 迁移 Builtin Tool YAML / asset metadata 到 `backend/app/core/tools/builtin_tools`。
- 新增 Builtin Tool provider/category manager、service 和 `/builtin-tools` 路由。
- 新增 no-LangChain runtime，已覆盖 `current_time`、`gaode_weather`、`google_serper`、`duckduckgo_search`、`wikipedia_search`、`dalle3` 的基础调用封装。
- 新增 API Tool 单元测试和 route smoke test。
- 已执行 `.\.venv\Scripts\ruff.exe check app tests`，通过。
- 已执行 `.\.venv\Scripts\python.exe -m pytest -q`，22 个测试通过。
- 已执行 `.\.venv\Scripts\alembic.exe current`，数据库版本为 `20260513_0001 (head)`。

后续补齐：

- Tool Capability adapter 与 App / Agent 工具绑定联调已在 2026-05-14 记录中完成。

### 2026-05-14 M3 Tool Capability adapter 记录

已完成：

- 新增 `ToolCapabilityAdapter`，将旧 Builtin Tool / API Tool 包装为 capability descriptor。
- descriptor 输出治理层需要的 `type`、`provider`、`target_ref_type`、`target_ref_id`、`input_schema`、`output_schema` 元数据。
- `AppService` 构建运行时工具 capability 时改为复用 adapter，但工具执行仍走旧 Builtin/API Tool runtime，不改变旧行为。
- 新增 adapter 和 AppService 绑定回归测试。

验证：

- 已执行 `uv run pytest -q tests/test_capability_adapter.py tests/test_agent_debug_runtime.py tests/test_app.py tests/test_api_tool.py tests/test_builtin_tool.py`，24 个测试通过。
- 已执行 `uv run ruff check app tests`，通过。
- 已执行 `uv run pytest -q`，90 个测试通过。

### 2026-05-13 M4 执行记录

已完成：

- 新增 `backend/app/models/workflow.py`，保留旧 `workflow` / `workflow_result` 表名、字段和索引语义。
- 新增 `backend/app/core/workflow/entities.py`，迁移 Workflow 状态、运行结果状态、节点类型、节点状态和默认配置。
- 新增 `WorkflowService`，支持创建、列表、详情、更新、删除、草稿图读取/更新、调试、发布、取消发布。
- 草稿图校验保留旧逻辑的“无效节点/边跳过”策略，并补齐 Tool / Dataset Retrieval 节点展示元数据。
- `debug` 当前采用校验式 SSE：验证图结构并写入 `workflow_result`，为后续完整节点执行 runtime 预留接口。
- 新增 `/workflows` 路由，保留旧 API 路径。
- 新增 Workflow 单元测试和 route smoke test。
- 已执行 `.\.venv\Scripts\ruff.exe check app tests`，通过。
- 已执行 `.\.venv\Scripts\python.exe -m pytest -q`，25 个测试通过。
- 已执行 `.\.venv\Scripts\alembic.exe heads`，当前 head 为 `20260513_0001`。
- 已执行 `.\.venv\Scripts\alembic.exe current`，数据库版本为 `20260513_0001 (head)`。

后续补齐：

- Workflow Docker smoke。
- 更复杂条件图场景。
- 真实 Provider / Tool / Dataset 组合端到端验证。

### 2026-05-14 M4 Workflow Capability adapter 记录

已完成：

- `ToolCapabilityAdapter` 补充 Workflow descriptor 包装能力，已发布 Workflow 可输出 `target_ref_type=workflow`、`target_ref_id`、输入 JSON schema 和输出 schema。
- Workflow 输入 schema 从 Start 节点 inputs 派生，保留旧 Workflow 图结构和发布语义。
- `AppService` 构建运行时 Workflow capability 时复用 adapter descriptor，但执行仍走旧 Workflow runtime，不改变旧调试和发布行为。
- 新增 Workflow descriptor、未发布/越权过滤、AppService workflow capability 绑定回归测试。

验证：

- 已执行 `uv run pytest -q tests/test_capability_adapter.py tests/test_agent_debug_runtime.py tests/test_workflow.py tests/test_app.py`，31 个测试通过。
- 已执行 `uv run ruff check app tests`，通过。
- 已执行 `uv run pytest -q`，93 个测试通过。

### 2026-05-14 M8 Knowledge Capability adapter 记录

已完成：

- Dataset/RAG 配置集合包装为 `knowledge_base` capability descriptor。
- descriptor 输出 `target_ref_type=dataset_collection`、dataset id 集合、查询输入 schema、数组输出 schema 和检索配置。
- `AppService` 构建运行时 Dataset capability 时复用 adapter descriptor，但执行仍走旧 DatasetService runtime，不改变 App/Agent 知识库检索行为。
- `AppService` 的 capability event 已兼容 `knowledge_base`，继续发 Dataset Retrieval 事件。
- 新增 Knowledge descriptor 和 AppService dataset capability 绑定回归测试。

验证：

- 已执行 `uv run pytest -q tests/test_capability_adapter.py tests/test_agent_debug_runtime.py tests/test_dataset.py tests/test_app.py`，30 个测试通过。
- 已执行 `uv run ruff check app tests`，通过。
- 已执行 `uv run pytest -q`，95 个测试通过。

### 2026-05-14 M8 Legacy App/Agent Worker 归类记录

已完成：

- 新增 `LegacyAppWorkerAdapter`，将旧 `App + AppConfig/AppConfigVersion` 包装为 Worker Agent descriptor。
- descriptor 输出 Agent 元数据、Version 元数据、模型配置、提示词配置、worker 配置、capability bindings 和旧 App 引用。
- Assistant Agent 可包装为 `product_category=assistant` 的 Worker Agent descriptor。
- `AppService` 新增 `app_to_worker_agent_descriptor` 内部方法，供后续 Router/Agent 管理层复用；不写入新 Agent 表，不改变旧 App 发布/调用行为。
- 新增旧 App、Assistant Agent、AppService descriptor 暴露回归测试。

验证：

- 已执行 `uv run pytest -q tests/test_agent_adapter.py tests/test_app.py tests/test_assistant_agent.py tests/test_agent_debug_runtime.py`，21 个测试通过。
- 已执行 `uv run ruff check app tests`，通过。
- 已执行 `uv run pytest -q`，98 个测试通过。

### 2026-05-14 M8 Task Engine 状态服务第一批记录

已完成：

- 新增 `TaskEngineService`，统一管理 `AgentTask` / `AgentStep` / `WorkerCall` / `CapabilityCall` 的创建和状态流转。
- 支持 `created` / `running` / `waiting_approval` / `succeeded` / `failed` / `cancelled` 状态，以及任务 `version` 递增。
- `AgentPlan` / `AgentStep` 创建会继承 task / tenant / router / worker 上下文，为后续 Router 调度和审计 trace 预留稳定入口。
- Worker / Capability 调用可记录 invocation/input、result/output、latency、cost、approval/idempotency 等治理元数据。
- 新增状态机、审批等待/恢复、非法流转、调用记录回归测试。

验证：

- 已执行 `uv run pytest -q tests/test_task_engine_service.py tests/test_agent_adapter.py tests/test_capability_adapter.py`，16 个测试通过。
- 已执行 `uv run ruff check app tests`，通过。
- 已执行 `uv run pytest -q`，103 个测试通过。

### 2026-05-14 M8 Router Agent manager 模式第一批记录

已完成：

- 新增 `RouterAgentManagerService`，支持创建 Router Agent、绑定 Worker Agent、创建 manager-run。
- 新增 `/router-agents` 路由第一批：Router 创建、Worker 绑定、manager-run 创建。
- `RouterRuntime.validate_plan` 补齐计划校验：唯一 step id、合法 Worker UUID、依赖引用存在、Worker 必须在绑定范围内。
- manager-run 会通过 `TaskEngineService` 持久化 `AgentTask` / `AgentPlan` / `AgentStep`，但不替代旧 App/Worker runtime。
- 高风险计划可先进入 `waiting_approval` 状态，为后续 Approval / Policy / Audit Trace 预留入口。

验证：

- 已执行 `.\.venv\Scripts\python.exe -m pytest tests\test_router_agent_manager_service.py tests\test_task_engine_service.py -q`，9 个测试通过。
- 已执行 `.\.venv\Scripts\ruff.exe check app tests`，通过。
- 已执行 `.\.venv\Scripts\python.exe -m pytest -q`，107 个测试通过。

### 2026-05-14 M8 Approval / Policy / Audit Trace 第一批记录

已完成：

- 新增 `ApprovalRequest` / `TraceEvent` 模型和 Alembic 迁移 `20260514_0002`。
- 新增 `ApprovalService`，支持审批请求创建、与 `CapabilityCall.approval_id` 关联、approve / reject / cancel 状态流转。
- 新增 `PolicyService`，第一批支持 capability enabled、idempotency、risk level、requires_approval、audit policy 的确定性决策。
- 新增 `TraceService`，支持按 `trace_id` 记录 Router / Task / Plan / Step / Capability / Approval 调用链事件。
- 新增 `/approvals` 和 `/traces` 路由第一批，提供待审批列表、审批/拒绝和 trace 查询入口。
- 保持治理层为外壳，不替代旧 App / Workflow / Tool / Dataset runtime。

验证：

- 已执行 `.\.venv\Scripts\python.exe -m pytest tests\test_approval_policy_trace.py tests\test_router_agent_manager_service.py tests\test_task_engine_service.py -q`，13 个测试通过。
- 已执行 `.\.venv\Scripts\ruff.exe check app tests`，通过。
- 已执行 `.\.venv\Scripts\alembic.exe heads`，当前 head 为 `20260514_0002`。
- 已执行 `.\.venv\Scripts\alembic.exe upgrade head`，数据库升级到 `20260514_0002`。
- 已执行 `.\.venv\Scripts\alembic.exe current`，当前数据库版本为 `20260514_0002 (head)`。
- 已执行 `.\.venv\Scripts\python.exe -m pytest -q`，111 个测试通过。

### 2026-05-14 M8 Router manager 接 legacy App Worker 执行第一批记录

已完成：

- 新增 `Agent.target_ref_type` / `Agent.target_ref_id`，用于持久化 Worker Agent 到旧 App / Assistant 等目标的映射。
- 新增 Alembic 迁移 `20260514_0003_agent_target_refs.py`。
- 新增 `/router-agents/workers/from-app`，可将旧 App descriptor 持久化为 Worker Agent。
- `POST /router-agents/{router_agent_id}/manager-runs` 支持 `execute=true`，创建 Task / Plan / Step 后执行已绑定 Worker。
- 第一批执行路径支持 `target_ref_type=app`，通过 `AppService.debug_chat` 调用旧 App debug runtime，并将结果写回 `WorkerCall` / `AgentStep` / `AgentTask`。
- manager-run 响应返回 `trace_id`，并写入 run created、step started/succeeded、worker call started/succeeded/failed、run succeeded 等 `trace_events`。

验证：

- 已执行 `.\.venv\Scripts\python.exe -m pytest tests\test_router_agent_manager_service.py tests\test_approval_policy_trace.py tests\test_task_engine_service.py -q`，14 个测试通过。
- 已执行 `.\.venv\Scripts\ruff.exe check app tests`，通过。
- 已执行 `.\.venv\Scripts\alembic.exe heads`，当前 head 为 `20260514_0003`。
- 已执行 `.\.venv\Scripts\alembic.exe upgrade head`，数据库升级到 `20260514_0003`。
- 已执行 `.\.venv\Scripts\alembic.exe current`，当前数据库版本为 `20260514_0003 (head)`。
- 已执行 `.\.venv\Scripts\python.exe -m pytest -q`，112 个测试通过。

### 2026-05-13 M5/M6/M7 第一批执行记录

已完成：

- 新增 Dataset / Document / Segment / KeywordTable / DatasetQuery / ProcessRule / UploadFile 模型，保留旧表名与核心字段。
- 新增 `/datasets`、`/datasets/{dataset_id}/documents`、`/datasets/{dataset_id}/documents/{document_id}/segments` 路由。
- 新增知识库 CRUD、查询记录、命中测试 DB fallback、文档记录管理、分段管理。
- 新增 `/upload-files` 与 `/upload-files/images`，采用 local storage fallback，不引入腾讯 COS SDK。
- 新增 App / AppConfig / AppConfigVersion / AppDatasetJoin 模型。
- 新增 `/apps` 第一批路由：创建、列表、详情、更新、复制、删除、草稿配置、发布、取消发布、发布历史、token。
- 新增 Conversation / Message / MessageAgentThought 模型和 `/conversations` 第一批路由。
- 已执行 `.\.venv\Scripts\ruff.exe check app tests`，通过。
- 已执行 `.\.venv\Scripts\python.exe -m pytest -q`，39 个测试通过。
- 已执行 `.\.venv\Scripts\alembic.exe current`，数据库版本为 `20260513_0001 (head)`。

仍需迁移：

- Weaviate / embedding Docker smoke 和真实 provider smoke。
- Workflow Docker smoke 和更复杂条件/异常图场景。
- App/Agent 真实 provider credentials、streaming chunk、provider-specific tool-call 端到端 smoke。
- Audio / WeChat / AI 真实凭证端到端 smoke。

### 2026-05-13 M6 FunctionCall/ReAct 兼容硬化记录

已完成：

- `ChatCompletionRuntime` 支持 OpenAI `tool_calls`、legacy `function_call`、单对象 tool-call payload、LangChain-style `additional_kwargs.tool_calls` 归一化。
- Tool-call 参数解析支持 dict、double-encoded JSON、fenced JSON、尾逗号 JSON、name/value list。
- Malformed tool args 不再静默变成 `{}` 后执行工具，而是作为 observation 回填给 LLM 继续修正。
- App/Agent runtime 在 TOOL_CALL 模型返回 JSON 文本而非原生 `tool_calls` 时，可 fallback 到 ReAct fenced JSON 解析。
- 新增 provider tool-call 兼容、malformed args observation、TOOL_CALL->ReAct fallback 单元测试。

验证：

- 已执行 `uv run ruff check app tests`，通过。
- 已执行 `uv run pytest -q`，75 个测试通过。

### 2026-05-13 M4 Workflow 图语义硬化记录

已完成：

- `validate_publish_graph` 增加边定义入口/出口校验：必须只有一个入度为 0 的 start 节点和一个出度为 0 的 end 节点。
- 增加变量引用校验：非 start 节点只能引用上游 predecessor，且引用变量名必须存在于 start inputs 或上游节点 outputs。
- Workflow debug runtime 改为 edge-driven execution batches，多个并行分支的下游 join 节点会等待全部前驱批次完成。
- App/Agent 调用 published workflow 的路径继续复用 `_ordered_nodes`，底层已改为批次计划的扁平化结果。

验证：

- 已执行 `uv run ruff check app tests`，通过。
- 已执行 `uv run pytest -q`，78 个测试通过。
- Docker backend rebuild 因外部网络超时未完成；当前只有 DB / Redis / Weaviate 容器运行，5011 未启动。

### 2026-05-13 M4 Workflow 异常图场景硬化记录

已完成：

- 新增循环图发布校验回归测试。
- 新增缺失变量引用发布校验回归测试。
- 新增 debug 运行时节点失败后不继续执行下游节点的回归测试。

验证：

- 已执行 `uv run pytest -q tests/test_workflow.py`，10 个测试通过。
- 已执行 `uv run ruff check app tests`，通过。
- 已执行 `uv run pytest -q`，85 个测试通过。
- Docker smoke 未执行：当前环境无法连接 Docker Desktop Linux engine。

### 2026-05-13 M5 Weaviate/vector 第一批迁移记录

已完成：

- 新增 `backend/app/infrastructure/vector_store.py`，使用 `httpx` 直接接 Weaviate REST/GraphQL，不新增 Python 依赖。
- 新增 offline/dev 可用的 deterministic hash embedding；配置 `EMBEDDING_PROVIDER=openai` 且提供 OpenAI key 时可切换 OpenAI embeddings。
- `IndexingService` 文档索引完成后 best-effort 写入 Weaviate，写入失败不破坏 PgSQL fallback。
- `DatasetService` semantic 检索优先走 Weaviate，失败或无命中自动回落到 lexical；hybrid 优先 keyword + vector，否则 keyword + lexical。
- Document / Segment / Dataset 的启停和删除路径增加 best-effort vector record 同步。
- 新增 vector store、vector hit 排序、best-effort indexing 单元测试。

验证：

- 已执行 `uv run ruff check app tests`，通过。
- 已执行 `uv run pytest -q`，82 个测试通过。
- Docker backend rebuild 已完成，`llmops-backend-api` / `llmops-backend-celery` 已启动，`GET http://127.0.0.1:5011/healthz` 返回 `{"status":"ok"}`。
- Dockerfile 已补 `entrypoint.sh` CRLF 归一化，避免 Windows 工作区构建出的镜像启动失败。

## 7. 近期 TODO

- [x] M1：迁移 `pkg/response`。
- [x] M1：迁移 `pkg/paginator`。
- [x] M1：迁移旧异常类型。
- [x] M1：对齐旧 SQLAlchemy helper 和新 session。
- [x] M1：补齐旧配置到 `pydantic-settings` 的映射。
- [x] M2：迁移 Account/Auth/API Key 第一批代码。
- [ ] M2：真实 PostgreSQL / 旧 UI 联调。
- [x] M3：迁移 Tool。
- [x] M3：迁移 API Tool 第一批。
- [x] M3：迁移 Builtin Tool runtime。
- [x] M4：迁移 Workflow 第一批 API。
- [x] M4：迁移 Workflow 轻量节点运行时。
- [x] M4：补齐 Workflow 图语义和并行分支 join 执行计划。
- [x] M4：补齐 Workflow 异常图场景第一批。
- [ ] M4：补齐 Workflow Docker smoke 和更复杂条件图场景。
- [x] M5：迁移 Dataset / Document / Segment 第一批 API。
- [x] M5：补齐 Dataset 文档索引链和 PgSQL retrieval fallback。
- [x] M5：补齐 Weaviate / embedding 向量检索第一批。
- [ ] M5：补齐 Weaviate Docker smoke / OpenAI embedding provider smoke。
- [x] M6：迁移 App / Conversation 第一批 API。
- [x] M6：迁移 Existing Agent Runtime 第一批。
- [x] M6：硬化 FunctionCall/ReAct tool-call 兼容和 malformed args observation。
- [ ] M6：真实 provider credentials / streaming chunk smoke。
- [x] M7：迁移 WebApp / OpenAPI / Assistant / Audio / WeChat / AI 第一批。
- [ ] M7：Audio / WeChat / AI 真实凭证端到端 smoke。
