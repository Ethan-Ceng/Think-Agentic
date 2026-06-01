# Backend 目录功能设计（基于现有 api 迁移）

更新时间：2026-05-13

本文用于约束 `api` 迁移到 `backend` 时的目录边界。核心目标不是创造一套全新目录，而是把现有 `api` 的真实功能稳定迁入 FastAPI 工程，并明确少量新增目录的职责。

## 1. 结论

`shared` 和 `integrations` 不是旧 `api` 原有业务目录，也不是新的业务模块。

它们是迁移时为了承接旧 `api/pkg` 中混杂能力而补充的工程分层：

| 新目录 | 来源 | 定位 |
| --- | --- | --- |
| `backend/app/shared` | `api/pkg/response`、`api/pkg/paginator`、`api/pkg/password` 等 | 跨模块复用的轻量工具，不承载业务流程 |
| `backend/app/integrations` | `api/pkg/oauth`、后续第三方平台 SDK / 协议客户端 | 外部系统适配层，不承载业务编排 |
| `backend/app/infrastructure` | `api/app/extension`、`api/pkg/sqlalchemy` 的基础设施部分 | 数据库、Redis、Celery、对象存储、向量库等技术资源 |

如果某段代码包含业务规则，不能放进 `shared` 或 `integrations`，应放在 `services`、`core` 或对应业务模块中。

## 2. 目录准入规则

### 2.1 `shared`

允许放入：

- 响应格式：`success_json`、`fail_json`、`Response`。
- 分页结构：`PaginatorReq`、`Paginator`、`PageModel`。
- 密码哈希、密码强度正则等无业务归属工具。
- 通用时间、序列化、枚举辅助函数。

禁止放入：

- SQLAlchemy Model。
- 事务控制。
- 业务服务。
- 调用外部 HTTP / SDK。
- 读取具体业务配置并执行业务流程。

### 2.2 `integrations`

允许放入：

- GitHub OAuth、微信、OpenAI、通义、DeepSeek、COS、对象存储等外部协议客户端。
- 外部 API 请求封装。
- 第三方 SDK 的薄封装。
- provider metadata、图标、模型 yaml 等供应商资源。

禁止放入：

- 登录成功后创建账号、绑定租户等业务流程。
- App、Workflow、Tool、Dataset 的业务编排。
- 数据库事务。

示例：

```text
backend/app/integrations/oauth/github.py      # 只负责 GitHub OAuth 协议交互
backend/app/services/oauth_service.py         # 负责账号绑定、token 生成、登录流程
```

### 2.3 `infrastructure`

允许放入：

- DB engine/session。
- Redis client。
- Celery app。
- Weaviate / vector DB client。
- 对象存储底层 client。
- Alembic 集成。
- 应用生命周期初始化。

禁止放入：

- 直接实现 App / Agent / Workflow / Tool 的业务逻辑。
- 直接返回 API 响应结构。

## 3. backend 目标目录

短期目标是兼容迁移，不做大规模模块重排：

```text
backend/
  app/
    main.py                    # ASGI 入口
    app_factory.py             # FastAPI app factory / lifespan

    api/
      router.py                # 顶层路由注册
      deps.py                  # FastAPI Depends
      routers/
        system.py              # 健康检查和系统接口
        console.py             # 控制台 UI API，前缀 /console/api
        service_api.py         # 对外服务 API，前缀 /v1
        web.py                 # WebApp API，前缀 /api
        files.py               # 文件访问 API，前缀 /files
        inner.py               # 内部服务 API
        triggers.py            # webhook / trigger API

    schemas/                   # Pydantic request / response schema
    models/                    # SQLAlchemy ORM，优先保留旧表名和字段语义
    entities/                  # 非 ORM 的运行时实体和值对象
    services/                  # 应用服务层，编排业务流程和事务边界

    core/                      # 核心运行时，不直接依赖 HTTP
      agent/                   # 现有 FunctionCall / ReAct / queue runtime
      workflow/                # 现有 LangGraph workflow runtime
      tools/                   # builtin tool / api tool runtime
      retrievers/              # semantic / full-text retrieval
      memory/                  # conversation memory
      language_model/          # LLM provider manager and adapters
      file_extractor/          # document extraction
      builtin_apps/            # builtin app templates

    tasks/                     # Celery tasks
    infrastructure/            # DB / Redis / Celery / storage / vector DB
    integrations/              # third-party protocol / SDK adapters
    shared/                    # cross-module pure helpers
```

中期如果文件量过大，可以把 `api/routers/console.py` 拆为 `api/routers/console/*.py`，但迁移阶段优先保持路径稳定，避免目录重排和业务迁移混在一起。

## 4. 现有 api 目录到 backend 的映射

| 旧目录 / 文件 | 现有职责 | backend 目标 | 迁移方式 |
| --- | --- | --- | --- |
| `api/app/main.py` | 应用入口 | `backend/app/main.py` | 保留 ASGI 入口，生命周期移到 app factory |
| `api/app/server/http.py` | 旧应用创建和 HTTP server | `backend/app/app_factory.py` | 改为 FastAPI app factory / lifespan |
| `api/app/api/router.py` | 路由聚合 | `backend/app/api/router.py` | 按入口面聚合 routers |
| `api/app/api/routes/*` | 业务 HTTP 路由 | `backend/app/api/routers/*` | 先按 console / web / service_api / files 归类 |
| `api/app/api/dependencies.py` | 请求依赖 | `backend/app/api/deps.py` | 改成 FastAPI Depends |
| `api/app/api/middleware.py`、`api/app/middleware/*` | HTTP middleware | `backend/app/api/middleware.py` 或 `app_factory.py` | 只保留 HTTP 横切逻辑 |
| `api/app/model/*` | SQLAlchemy ORM | `backend/app/models/*` | 优先保留旧表名和字段 |
| `api/app/schema/*` | 请求/响应校验 | `backend/app/schemas/*` | 迁移为 Pydantic v2 |
| `api/app/entity/*` | 非 ORM 实体 | `backend/app/entities/*` | 保留运行时实体和值对象 |
| `api/app/service/*` | 应用服务层 | `backend/app/services/*` | 保留业务流程，改依赖注入和 session |
| `api/app/core/agent/*` | Agent runtime | `backend/app/core/agent/*` | 直接迁移，后续包装 Worker Runtime |
| `api/app/core/workflow/*` | Workflow runtime | `backend/app/core/workflow/*` | 直接迁移，后续包装 Workflow Capability |
| `api/app/core/tools/*` | Tool runtime | `backend/app/core/tools/*` | 直接迁移，后续包装 Tool Capability |
| `api/app/core/retrievers/*` | RAG 检索 | `backend/app/core/retrievers/*` | 直接迁移，后续包装 Knowledge Capability |
| `api/app/core/memory/*` | 会话记忆 | `backend/app/core/memory/*` | 直接迁移 |
| `api/app/core/language_model/*` | 模型供应商和调用 | `backend/app/core/language_model/*` | 短期保留，后续 provider client 可下沉到 integrations |
| `api/app/core/file_extractor/*` | 文件解析 | `backend/app/core/file_extractor/*` | 直接迁移 |
| `api/app/core/builtin_apps/*` | 内置应用模板 | `backend/app/core/builtin_apps/*` | 直接迁移 |
| `api/app/task/*` | Celery task | `backend/app/tasks/*` | 改用新 Celery app |
| `api/app/extension/database_extension.py` | DB 初始化 | `backend/app/infrastructure/db.py` | 合并到 SQLAlchemy 2.x session |
| `api/app/extension/redis_extension.py` | Redis 初始化 | `backend/app/infrastructure/redis.py` | 直接迁移配置和 client |
| `api/app/extension/celery_extension.py` | Celery 初始化 | `backend/app/infrastructure/celery.py` | 直接迁移队列配置 |
| `api/app/extension/weaviate_extension.py` | Weaviate 初始化 | `backend/app/infrastructure/vector_store.py` | 保留 Weaviate first |
| `api/app/extension/logging_extension.py` | 日志初始化 | `backend/app/core/logging.py` | 统一 structlog / logging |
| `api/app/extension/migrate_extension.py` | Flask migrate | `backend/app/alembic/*` | 使用 Alembic |
| `api/app/extension/login_extension.py` | 登录上下文 | `backend/app/api/deps.py` + `backend/app/core/security.py` | 改成依赖注入 |
| `api/app/storage/*` | 运行时文件和日志 | `backend/storage/*` 或外部存储 | 不放进 Python package |
| `api/app/lib/*` | 零散 helper | `backend/app/shared/*` 或归入具体模块 | 按依赖决定归属 |
| `api/pkg/response` | 响应格式 | `backend/app/shared/response` | 已迁移 |
| `api/pkg/paginator` | 分页 | `backend/app/shared/paginator` | 已迁移 |
| `api/pkg/password` | 密码工具 | `backend/app/shared/password` | 后续迁移 |
| `api/pkg/sqlalchemy` | DB facade / paginate | `backend/app/infrastructure/db.py` + `shared/paginator` | 拆分迁移 |
| `api/pkg/oauth` | OAuth 协议工具 | `backend/app/integrations/oauth` | 后续迁移 |

## 5. 按业务能力的目录落点

### 5.1 Account / Auth

```text
models/account.py
models/api_key.py
schemas/account.py
schemas/auth.py
services/account_service.py
services/jwt_service.py
services/oauth_service.py
api/routers/console/auth.py 或 api/routers/console.py
shared/password/
integrations/oauth/
```

### 5.2 App / Existing Agent Runtime

```text
models/app.py
models/conversation.py
schemas/app.py
schemas/conversation.py
services/app_service.py
services/app_config_service.py
services/conversation_service.py
services/assistant_agent_service.py
core/agent/
core/memory/
api/routers/console/app.py 或 api/routers/console.py
api/routers/web.py
tasks/app_task.py
```

### 5.3 Tool

```text
models/api_tool.py
schemas/api_tool.py
services/api_tool_service.py
services/builtin_tool_service.py
core/tools/api_tools/
core/tools/builtin_tools/
api/routers/console/api_tool.py 或 api/routers/console.py
api/routers/console/builtin_tool.py 或 api/routers/console.py
```

### 5.4 Workflow

```text
models/workflow.py
core/workflow/entities.py
schemas/workflow.py
services/workflow_service.py
core/workflow/
api/routers/workflow.py
```

### 5.5 Dataset / RAG

```text
models/dataset.py
schemas/dataset.py
schemas/document.py
schemas/segment.py
services/dataset_service.py
services/document_service.py
services/segment_service.py
services/indexing_service.py
services/retrieval_service.py
core/retrievers/
core/file_extractor/
infrastructure/vector_store.py
tasks/document_task.py
tasks/dataset_task.py
```

### 5.6 File / Audio / Channel / Publishing

```text
models/upload_file.py
models/platform.py
schemas/upload_file.py
schemas/audio.py
schemas/platform.py
services/upload_file_service.py
services/audio_service.py
services/platform_service.py
services/web_app_service.py
services/wechat_service.py
services/openapi_service.py
infrastructure/storage.py
integrations/wechat/
api/routers/files.py
api/routers/web.py
api/routers/service_api.py
```

## 6. 后续执行约束

迁移每个模块前先判断归属：

```text
HTTP 入参/出参       -> api / schemas
数据库表             -> models
业务编排             -> services
运行时引擎           -> core
异步任务             -> tasks
DB/Redis/Celery 等   -> infrastructure
纯工具               -> shared
第三方协议/SDK       -> integrations
非 ORM 实体          -> entities
```

新增目录必须满足两个条件：

1. 能明确映射到旧 `api` 的一类现有职责。
2. 目录职责不能和 `services`、`core`、`infrastructure` 重叠。

否则不新增目录，优先放入已有目录。
