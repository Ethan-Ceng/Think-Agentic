# Dify 后端架构学习与 FastAPI 初始化参考

更新时间：2026-05-13

本文基于当前仓库 `api/`、`docker/`、后端配置和入口文件梳理。目标不是逐行复刻 Dify，而是提炼一个“类似 Dify 的智能体平台”在后端初始化时值得借鉴的架构边界、目录组织和技术栈选择。

## 0. 本项目技术选择声明

本项目目标后端技术栈明确采用 FastAPI，不采用 Flask。

以下 Dify 相关内容只用于理解成熟平台的边界设计、API 分面、Provider 抽象、异步任务、RAG 和 Workflow 思路，不作为本项目目标技术栈。

本项目不采用：

- Flask
- Flask-RESTX
- Flask-SQLAlchemy
- Flask-Migrate
- Flask-Login
- Flask Blueprint
- Flask app context

本项目采用：

- FastAPI
- APIRouter
- FastAPI dependency injection
- FastAPI lifespan
- SQLAlchemy 2.x
- Alembic
- Pydantic / Pydantic Settings
- ASGI Streaming / SSE
- Celery + Redis
- PostgreSQL

## 1. Dify 后端定位

Dify 后端是一个偏平台型的 LLM 应用运行时，核心职责包括：

- 管理租户、账号、工作区、应用、模型供应商、API Key、文件、数据集和插件。
- 对外提供多类 API：控制台管理 API、公开服务 API、Web 应用 API、文件 API、内部 API、触发器 API、MCP API。
- 执行 Chat、Completion、Agent Chat、Workflow、RAG Pipeline 等应用模式。
- 维护工作流编排、节点运行、变量池、事件流、暂停恢复、人机协同等运行时能力。
- 管理 RAG 文档抽取、切分、索引、向量检索、关键词检索和重排。
- 通过 Celery + Redis 承担异步任务、队列隔离、周期任务和耗时工作流。
- 通过插件守护进程、模型 Provider、工具 Provider、向量库 Provider 扩展外部能力。

它不是一个简单 CRUD API，而是一个“控制面 + 运行时 + 异步任务 + 插件生态 + RAG/Workflow 引擎”的组合。

## 2. Dify 原始后端技术栈（仅参考，不采用）

本节描述的是 Dify 原始后端栈，用于对照学习。它不是本项目的目标技术栈。本项目目标栈见第 0 节和第 9 节。

### 2.1 语言和运行时

- Python：`~=3.12.0`
- 包管理：`uv`
- Web 框架：Flask 3.x
- API 组织：Flask Blueprint + Flask-RESTX
- OpenAPI：Flask-RESTX + `fastopenapi[flask]`
- JSON 序列化：`flask-orjson`
- 生产运行：Gunicorn + gevent / gevent-websocket
- WebSocket / Socket.IO：`python-socketio`

### 2.2 数据与缓存

- ORM：SQLAlchemy / Flask-SQLAlchemy
- 迁移：Flask-Migrate / Alembic
- 主数据库：PostgreSQL 优先，同时保留 MySQL、OceanBase、SeekDB 等兼容配置
- 缓存与队列：Redis
- Celery Broker / Result Backend：默认 Redis，也支持数据库等配置
- 多租户隔离：业务层和查询层强依赖 `tenant_id`

### 2.3 异步任务

- Celery 5.x
- Celery Beat 周期任务
- Worker 默认 gevent pool
- 队列按业务拆分：dataset、mail、plugin、workflow、trigger、retention、workflow_based_app_execution 等

### 2.4 LLM、RAG、工作流

- 工作流/图运行时：`graphon`
- 模型运行时：通过插件 Provider 与 `graphon.model_runtime` 适配
- RAG：文档抽取、清洗、切分、embedding、向量索引、检索、rerank
- 向量库：通过 `api/providers/vdb/*` 工作区包扩展，支持 pgvector、qdrant、weaviate、milvus、elasticsearch、opensearch、chroma 等
- 关键词检索：默认 `jieba`
- HTTP 调用：`httpx`，并通过 SSRF Proxy 做外部访问边界

### 2.5 存储、插件和外部服务

- 文件存储抽象：local / OpenDAL / S3 / OSS / Azure Blob / COS / OBS / TOS / Supabase 等
- 插件守护进程：`plugin_daemon` 独立服务
- 代码执行：`dify-sandbox` 独立服务
- 邮件：SMTP、SendGrid、Resend
- 可观测性：OpenTelemetry、Sentry、日志上下文、请求日志

### 2.6 质量工具

- Ruff：格式化和 lint
- basedpyright / pyrefly / mypy：类型检查相关
- pytest：单元测试
- testcontainers：部分集成测试
- import-linter：包边界检查入口

## 3. Dify 后端目录职责（仅参考）

下面是 `api/` 的核心目录视角。

| 目录 | 主要职责 |
| --- | --- |
| `app.py` | Flask 入口。区分迁移命令和正常服务，创建 `flask_app`、`socketio_app`，暴露 Celery 实例。 |
| `app_factory.py` | 应用工厂。加载配置，注册 before/after request hook，按顺序初始化扩展。 |
| `dify_app.py` | Dify 自定义 Flask 类型，给扩展属性提供类型语义。 |
| `configs/` | Pydantic Settings 配置聚合，按部署、功能、中间件、观测、企业版等拆分。 |
| `controllers/` | HTTP 适配层。负责请求解析、鉴权装饰、调用 service、返回响应。 |
| `services/` | 应用服务层。编排业务用例、事务、异步任务、Provider、仓储和领域能力。 |
| `core/` | 核心领域和运行时。包含 app 运行、workflow、rag、tools、plugin、model_manager、trigger、mcp 等。 |
| `models/` | SQLAlchemy 数据模型和枚举。 |
| `repositories/` | 面向 API/service 的仓储抽象和实现，尤其是 workflow run / node execution 等大表或复杂查询。 |
| `core/repositories/` | 面向 core 运行时的仓储协议和实现。 |
| `extensions/` | Flask 扩展初始化层：db、redis、celery、blueprints、storage、otel、sentry、login、mail 等。 |
| `tasks/` | Celery 异步任务。文档索引、工作流执行、邮件、插件升级、清理、触发器等。 |
| `schedule/` | Celery Beat 周期任务。 |
| `commands/` | Flask CLI 命令。租户创建、密码重置、数据库升级、插件安装、向量迁移、清理任务等。 |
| `migrations/` | Alembic 数据库迁移。 |
| `providers/vdb/` | 向量库 Provider 工作区包。 |
| `providers/trace/` | Trace Provider 工作区包。 |
| `libs/` | 通用基础设施工具：token、oauth、加密、分页、时间、邮件、Flask-RESTX 兼容、模块加载等。 |
| `factories/` | 文件、变量、Agent 等对象构建工厂。 |
| `tests/` | 单元测试和 testcontainers 集成测试。 |

## 4. API 面划分

Dify 没有把所有接口塞进一个 API 命名空间，而是按调用方隔离：

| Blueprint | URL 前缀 | 说明 |
| --- | --- | --- |
| `console` | `/console/api` | 控制台管理端 API，面向平台管理员、工作区成员。 |
| `service_api` | `/v1` | 对外开放的应用服务 API，用户通过 API Key 调用应用、数据集等。 |
| `web` | `/api` | WebApp / 嵌入式应用端 API。 |
| `files` | `/files` | 文件上传、预览和工具文件。 |
| `inner_api` | `/inner/api` | 内部服务、插件、企业能力通信。 |
| `mcp` | `/mcp` | Model Context Protocol 相关接口。 |
| `trigger` | `/triggers` | Webhook、定时、插件触发器入口。 |

这个划分值得借鉴：不同调用方的鉴权、CORS、错误响应、限流和可见数据范围通常不同，早期就拆开会降低后续复杂度。

## 5. 应用启动流程

核心路径：

```text
app.py
  -> create_app()
    -> create_flask_app_with_configs()
      -> DifyApp(__name__)
      -> dify_config.model_dump()
      -> before_request / after_request hooks
    -> initialize_extensions(app)
      -> timezone / logging / warnings
      -> import modules / orjson / forward refs / compress
      -> database / migrate / redis / storage
      -> logstore / celery / login / mail
      -> sentry / proxy / blueprints / commands / fastopenapi
      -> otel / request logging / session factory
    -> socketio.WSGIApp(sio, app)
```

迁移命令会走轻量路径：

```text
create_migrations_app()
  -> init database
  -> init migrate
```

生产容器根据 `MODE` 启动不同进程：

- `MODE=api`：Gunicorn + gevent websocket worker 启动 HTTP 服务。
- `MODE=worker`：Celery worker 处理异步任务。
- `MODE=beat`：Celery Beat 调度周期任务。
- `MODE=job`：一次性执行 Flask CLI 命令。
- `MODE=migration`：只执行数据库迁移后退出。

## 6. 分层关系

Dify 后端大体遵循：

```text
controllers
  -> services
    -> core / repositories / models / extensions
      -> external providers / storage / redis / database / celery
```

### 6.1 Controllers

Controllers 负责：

- 绑定 URL 和 HTTP 方法。
- 做请求参数解析和 Pydantic 校验。
- 做鉴权、租户上下文、权限检查入口。
- 调用 service。
- 序列化响应。

Controllers 不应该承载复杂业务逻辑。

### 6.2 Services

Services 负责用例编排：

- 查模型和权限。
- 组织事务。
- 调用 core 运行时。
- 调用 repository。
- 分派 Celery 任务。
- 处理业务异常。

例如应用生成的核心入口在 `services/app_generate_service.py`，它根据 AppMode 选择 Completion、Chat、Agent Chat、Advanced Chat、Workflow 的不同生成器。

### 6.3 Core

`core/` 是真正的平台能力层：

- `core/app/`：应用运行模式、生成器、runner、响应转换、app config。
- `core/workflow/`：工作流入口、节点工厂、变量池、系统变量、人机输入、触发器节点。
- `core/rag/`：文档处理、索引、检索、embedding、rerank。
- `core/tools/`：工具 Provider、内置工具、MCP 工具、工作流作为工具。
- `core/plugin/`：插件调用、endpoint、runtime factory。
- `core/model_manager.py`：按租户、Provider、模型类型解析模型实例和凭据。
- `core/trigger/`：触发器 Provider、订阅刷新、debug 事件。
- `core/mcp/`：MCP client/server/auth。

### 6.4 Models 和 Repositories

`models/` 是 SQLAlchemy 数据模型，代表数据库结构。典型领域包括：

- 账号、租户、工作区成员。
- 应用、站点、会话、消息。
- 数据集、文档、分段、元数据。
- 模型 Provider、凭据、负载均衡。
- 工作流、工作流运行、节点执行、暂停、人机输入。
- 工具、OAuth、触发器、文件。

Repository 不是无处不在。Dify 主要在复杂、大表、可替换存储或运行时持久化场景使用 repository，例如 workflow execution、node execution、workflow run。

## 7. 核心运行链路

### 7.1 普通 HTTP 请求

```text
client
  -> blueprint route
  -> controller resource
  -> request validation / auth / tenant context
  -> service
  -> repository / model / core capability
  -> response model
  -> Flask-RESTX error handler / response
```

### 7.2 应用生成与工作流执行

简化链路：

```text
controller
  -> AppGenerateService.generate()
    -> quota reserve / rate limit
    -> resolve AppMode
    -> CompletionAppGenerator / ChatAppGenerator / AgentChatAppGenerator
       or WorkflowAppGenerator / AdvancedChatAppGenerator
    -> streaming:
       -> enqueue workflow_based_app_execution_task
       -> retrieve events by workflow_run_id
    -> blocking:
       -> run generator directly
```

Workflow 模式进一步进入：

```text
workflow_based_app_execution_task
  -> WorkflowAppRunner.run()
    -> build system variables
    -> build VariablePool
    -> GraphRuntimeState
    -> DifyNodeFactory
    -> Graph.init()
    -> WorkflowEntry
      -> GraphEngine
      -> layers:
         - execution limits
         - LLM quota
         - observability
         - persistence
      -> node.run()
      -> graph events
      -> queue / SSE response
```

这里有几个关键设计：

- 工作流配置以图结构持久化，执行时转成 Graph。
- 节点由 `DifyNodeFactory` 统一创建，注入 LLM、HTTP、工具、文件、沙箱、人机输入等运行时依赖。
- 执行状态放在 `GraphRuntimeState` 和 `VariablePool`，系统变量、用户输入、环境变量统一进入变量池。
- 持久化、限额、观测作为 GraphEngine Layer 插入，而不是散落在每个节点里。
- Streaming 请求和后台执行解耦，事件通过队列/Redis/流式响应传递。

### 7.3 RAG 链路

典型 RAG 写入链路：

```text
upload / import document
  -> dataset service
  -> Celery document indexing task
  -> extractor
  -> cleaner
  -> splitter
  -> embedding
  -> vector store provider
  -> document / segment status update
```

典型 RAG 查询链路：

```text
workflow node / app retrieval
  -> dataset retriever
  -> keyword / vector search
  -> rerank
  -> context assembly
  -> prompt / LLM node
```

### 7.4 插件和 Provider

Dify 把许多外部能力做成 Provider：

- 模型 Provider：LLM、embedding、rerank、TTS、ASR、moderation。
- 工具 Provider：内置工具、插件工具、MCP 工具。
- 数据源 Provider：Notion、网站爬取、在线文档等。
- 向量库 Provider：以 workspace package 方式拆分。
- Trace Provider：Langfuse、LangSmith、MLflow 等。

Provider 的价值是把外部系统差异挡在平台边界之外。业务层只关心“我要一个模型实例/工具实例/向量检索器”，不直接依赖某个供应商 SDK。

## 8. Dify 值得借鉴的设计点

1. API 面按调用方拆分，而不是只按资源名拆分。
2. App Factory + Extension 初始化顺序清晰，基础设施集中装载。
3. 配置统一由 Pydantic Settings 聚合，避免业务代码直接读环境变量。
4. 多租户 ID 从入口流到查询、缓存、任务、日志。
5. 控制器薄，service 负责编排，core 放运行时和领域能力。
6. 工作流节点通过工厂注入依赖，节点本身不负责到处找全局对象。
7. 长耗时执行默认异步化，前端通过 SSE/事件流拿结果。
8. 队列按业务隔离，避免文档索引拖垮对话或工作流。
9. 外部 HTTP 统一走 SSRF Proxy 边界。
10. 文件存储、向量库、模型、工具、Trace 都抽象成可替换 Provider。
11. 复杂持久化使用 repository，不为了形式主义给所有表都套 repository。
12. 可观测性、限额、持久化作为运行时 layer 注入工作流引擎。

## 9. 用 FastAPI 初始化时的推荐技术栈

如果你要做一个类似平台，但从 FastAPI 起步，可以先选一个更轻、更清晰的组合：

### 9.1 基础依赖建议

```bash
uv init agent-platform-api
uv add fastapi "uvicorn[standard]" gunicorn
uv add pydantic-settings pydantic
uv add sqlalchemy asyncpg alembic
uv add redis celery
uv add httpx httpx-sse sse-starlette
uv add orjson python-multipart python-jose passlib
uv add opentelemetry-api opentelemetry-sdk opentelemetry-instrumentation-fastapi
uv add structlog
uv add --dev pytest pytest-asyncio ruff basedpyright
```

注意：数据库可以选同步 SQLAlchemy 或异步 SQLAlchemy。FastAPI 常用 async SQLAlchemy，但 Celery worker 里同步代码更直接。早期建议只选一种主路径，不要 API async、worker sync、repository 两套实现同时上。

### 9.2 推荐目录骨架

```text
agent-platform-api/
  pyproject.toml
  alembic.ini
  app/
    main.py
    app_factory.py
    core/
      config.py
      logging.py
      security.py
      errors.py
      tenant.py
    api/
      deps.py
      routers/
        console/
        service_api/
        web/
        files/
        inner_api/
        triggers/
    services/
      app_generate_service.py
      workflow_service.py
      dataset_service.py
      model_provider_service.py
      plugin_service.py
    domain/
      app/
      workflow/
      rag/
      tools/
      model/
      trigger/
    models/
      base.py
      account.py
      app.py
      workflow.py
      dataset.py
      provider.py
      file.py
    repositories/
      workflow_run_repository.py
      document_repository.py
      provider_repository.py
    infrastructure/
      db.py
      redis.py
      celery.py
      storage/
      vectorstores/
      llm_providers/
      observability.py
    tasks/
      celery_app.py
      document_indexing.py
      workflow_execution.py
      mail.py
    migrations/
    tests/
      unit/
      integration/
```

如果想更贴近 Dify 命名，也可以用 `controllers/`、`extensions/`、`core/`。但在 FastAPI 项目里，`api/routers` + `infrastructure` 往往更直观。

## 10. FastAPI 版本的分层建议

### 10.1 `app_factory.py`

承担类似 Dify `app_factory.py` 的职责：

- 创建 FastAPI 实例。
- 注册中间件：CORS、请求日志、异常处理、GZip、TrustedHost。
- 注册 routers。
- 初始化观测、Redis、数据库连接池、对象存储客户端。
- 在 lifespan 里做启动/关闭资源管理。

### 10.2 `api/routers`

按调用方拆：

- `console`：控制台管理，cookie/session 或 JWT。
- `service_api`：外部 API Key 调用，面向开发者。
- `web`：用户分享应用、嵌入应用调用。
- `files`：上传、预览、签名 URL。
- `inner_api`：插件、沙箱、内部服务回调。
- `triggers`：webhook、定时器、第三方事件。

不要一开始就只做 `/api/v1/*` 一个大路由，否则后续鉴权和 CORS 会混在一起。

### 10.3 `services`

Service 是用例层，示例：

- `AppGenerateService.generate()`
- `WorkflowService.publish()`
- `DatasetService.create_document()`
- `DocumentIndexingService.enqueue()`
- `ModelProviderService.validate_credentials()`
- `PluginService.install()`

它可以依赖 repository、task dispatcher、domain runtime、provider client，但不要直接处理 HTTP 请求对象。

### 10.4 `domain` 或 `core`

放真正稳定的领域能力：

- Workflow DAG、节点协议、变量池、执行事件。
- RAG 抽取、切分、索引、检索协议。
- Tool 调用协议。
- LLM Provider 抽象。
- Trigger 抽象。
- 多租户上下文对象。

这层应该尽量不依赖 FastAPI。

### 10.5 `infrastructure`

放可替换实现：

- PostgreSQL / SQLAlchemy。
- Redis。
- Celery。
- S3 / local storage。
- Qdrant / pgvector / Milvus。
- OpenAI / Anthropic / Azure / 本地模型。
- OpenTelemetry / Sentry。

## 11. 初始化阶段的最小可用范围

不要一开始复刻完整 Dify。建议分三期。

### Phase 1：平台最小闭环

- 账号、租户、工作区。
- App 管理。
- 模型 Provider 凭据管理。
- Chat/Completion 调用。
- 对话、消息、运行日志。
- 文件上传。
- 基础 RAG：上传文档、切分、embedding、向量检索。
- Celery worker 处理文档索引。
- SSE 返回流式生成结果。

### Phase 2：工作流和工具

- Workflow DAG 数据结构。
- Start、LLM、Knowledge Retrieval、HTTP Request、Code、Tool、End 等基础节点。
- 变量池和节点输出引用。
- Workflow run / node execution 持久化。
- 工作流异步执行和事件流。
- API Key 调用工作流。
- Webhook trigger。
- Tool Provider 抽象。

### Phase 3：平台化能力

- 插件系统。
- 多队列隔离。
- 模型负载均衡。
- 配额、限流、计费。
- 人机协同、暂停恢复。
- 观测 Trace。
- 多向量库 Provider。
- MCP。
- 市场和插件安装。

## 12. 数据模型优先级

FastAPI 初始化时建议先建这些表：

| 模型 | 说明 |
| --- | --- |
| `accounts` | 用户账号。 |
| `tenants` | 工作区/租户。 |
| `tenant_members` | 成员和角色。 |
| `apps` | 应用基础信息和模式。 |
| `app_model_configs` | App 模型配置、参数、提示词。 |
| `provider_credentials` | 模型供应商凭据，按租户隔离。 |
| `conversations` | 会话。 |
| `messages` | 消息和 token/费用/状态。 |
| `files` | 上传文件和存储 key。 |
| `datasets` | 知识库。 |
| `documents` | 知识库文档。 |
| `segments` | 文档分段和索引状态。 |
| `workflows` | 工作流草稿/发布版本，存图结构 JSON。 |
| `workflow_runs` | 工作流运行实例。 |
| `workflow_node_executions` | 节点执行实例。 |
| `api_tokens` | 外部调用 API Key。 |
| `triggers` | Webhook / schedule / plugin 触发器配置。 |

先保证这些核心模型的 `tenant_id`、`created_at`、`updated_at`、软删除或状态字段设计稳定。

## 13. FastAPI 请求链路建议

```text
client
  -> APIRouter
  -> dependency:
       get_current_user
       get_tenant
       get_db_session
       check_permission
  -> request schema
  -> service
  -> domain runtime / repository / provider
  -> response schema
```

SSE 链路建议：

```text
POST /console/api/apps/{app_id}/chat-messages
  -> create run_id
  -> enqueue Celery task
  -> return EventSourceResponse(event_generator(run_id))

worker
  -> execute app / workflow
  -> publish events to Redis Stream

event_generator
  -> read Redis Stream
  -> yield SSE events
```

## 14. FastAPI 中替代 Dify Flask 机制的映射

本节的目的不是建议使用 Flask，而是明确如果 Dify 中某个机制来自 Flask，本项目应使用哪个 FastAPI 机制替代。

| Dify Flask 机制 | FastAPI 建议 |
| --- | --- |
| Flask Blueprint | `APIRouter` |
| Flask extension init | app factory + lifespan + dependency provider |
| Flask-RESTX Resource | path operation function 或 class-based router |
| Flask request hook | middleware / dependency |
| Flask errorhandler | exception handler |
| Flask-Migrate CLI | Alembic CLI |
| Flask-Login | JWT/session dependency |
| Flask app context | 显式依赖注入，避免隐式全局上下文 |
| gevent streaming | ASGI StreamingResponse / EventSourceResponse |
| Socket.IO | WebSocket 或保留 Socket.IO ASGI |

## 15. 架构边界建议

建议从第一天就遵守：

- Router 不写业务逻辑。
- Service 不直接读环境变量。
- Domain/core 不依赖 FastAPI。
- Repository 不依赖 HTTP 层。
- 所有共享资源查询都必须带 `tenant_id`。
- 外部 HTTP 访问统一封装，后续才能加 SSRF 防护、审计和重试。
- LLM 调用统一走 ModelProvider 抽象，不要散落 OpenAI SDK 调用。
- 文件统一走 Storage 抽象，不要业务层拼本地路径。
- 异步任务参数用 Pydantic schema 序列化，避免传 ORM 对象。
- 工作流事件要结构化，前端不要解析日志字符串。
- 长任务必须可重试、幂等、可观测。

## 16. 可以先实现的核心接口

控制台：

- `POST /console/api/setup`
- `POST /console/api/login`
- `GET /console/api/account/profile`
- `GET /console/api/workspaces/current`
- `POST /console/api/apps`
- `GET /console/api/apps`
- `POST /console/api/apps/{app_id}/model-config`
- `POST /console/api/apps/{app_id}/chat-messages`
- `POST /console/api/datasets`
- `POST /console/api/datasets/{dataset_id}/documents`

服务 API：

- `POST /v1/chat-messages`
- `POST /v1/completion-messages`
- `POST /v1/workflows/run`
- `GET /v1/messages`
- `POST /v1/files/upload`

内部和任务：

- `POST /inner/api/plugin/callback`
- `POST /triggers/webhook/{token}`
- Celery task：`document_indexing_task`
- Celery task：`workflow_execution_task`

## 17. 不建议过早复制的部分

Dify 的完整能力很强，但以下模块不适合初始化阶段直接复刻：

- 完整插件市场和插件沙箱。
- 十几种向量库 Provider。
- 企业 license、billing、quota 全链路。
- 复杂工作流暂停恢复和人机协同。
- 多 Trace Provider。
- 所有邮件和清理周期任务。
- 控制台全部管理接口。

初始化阶段要先跑通“模型调用 + RAG + 工作流事件流 + 多租户权限”这条主线。

## 18. 一个适合起步的目标架构

```text
FastAPI API service
  -> PostgreSQL
  -> Redis
  -> Celery worker
  -> Object Storage
  -> Vector DB
  -> LLM Provider

API service:
  - console routers
  - service API routers
  - web routers
  - SSE event endpoint

Worker:
  - document indexing
  - workflow execution
  - mail / cleanup later

Domain runtime:
  - app generator
  - workflow engine
  - rag retriever
  - tool dispatcher
```

这个结构已经能支撑一个 Dify-like 平台的早期版本，并且后续可以逐步扩展 Provider、插件、Trigger、MCP 和企业能力。

## 19. 推荐落地顺序

1. 初始化 FastAPI 项目、配置、日志、异常处理、健康检查。
2. 建账号、租户、App、ProviderCredential、Conversation、Message 表。
3. 做模型 Provider 抽象，先支持一个 LLM Provider。
4. 做 Chat App 的阻塞和流式输出。
5. 引入 Redis Stream 或 Pub/Sub 存生成事件。
6. 引入 Celery，生成任务可以后台执行。
7. 做文件上传和 Storage 抽象。
8. 做 Dataset、Document、Segment。
9. 做文档索引 Celery task。
10. 接入一个向量库，例如 pgvector 或 Qdrant。
11. 做 Knowledge Retrieval。
12. 做 Workflow DAG 的最小节点集合。
13. 持久化 workflow run 和 node execution。
14. 做 API Key 和 `/v1` 外部调用面。
15. 最后再做插件、触发器、MCP、配额和观测增强。

## 20. 总结

Dify 后端最值得学习的不是 Flask 代码本身。本项目不采用 Flask，只学习它的平台边界：

- 多 API 面隔离。
- 控制面和运行时分离。
- 同步 HTTP 与异步 Worker 分离。
- Provider 抽象外部能力。
- Workflow 引擎围绕事件、变量池、节点工厂和持久化 layer 组织。
- RAG 是独立 pipeline，而不是塞进 chat controller。
- 配置、存储、Redis、DB、外部 HTTP、观测都集中在基础设施层。

用 FastAPI 初始化时，可以保留这些架构思想，但实现上更适合用 `APIRouter`、依赖注入、lifespan、Pydantic schema 和 ASGI streaming 来落地。
