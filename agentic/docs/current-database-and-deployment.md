# Agentic 当前数据库与部署基线

归档日期：2026-07-02

本文档用于在设计登录、用户隔离、Knowledge、Trace、发布能力之前，先固定当前 `agentic` 系统的数据库、配置、存储和 Docker 部署现状。

## 1. 当前结论

当前 `agentic` 已经具备 Agent 运行时基础，但数据库仍是单用户/单租户形态。

- 已入库：会话 `sessions`、文件元数据 `files`。
- 未入库：用户、组织、工作区、数字员工实例、Knowledge、模型配置、工具配置、标准化 Run/Trace、发布记录。
- 当前会话事件、计划、工具调用等运行过程主要压在 `sessions.events` JSONB 中，不是可分析的标准 Trace 表。
- 当前模型、Agent、MCP、A2A、Tool 配置主要保存在 YAML 配置文件，不在数据库中。
- 登录和用户隔离的第一步应从 `users`、`sessions.user_id`、`files.user_id` 开始。

## 2. 当前数据库来源

迁移目录：

```text
agentic/api/alembic/versions/
```

当前迁移文件：

```text
87ed1cbb1088_create_sessions_table.py
0e0d242438bc_create_files_table.py
```

ORM 模型：

```text
agentic/api/app/models/session.py
agentic/api/app/models/file.py
```

业务表：

- `sessions`
- `files`
- `alembic_version`，Alembic 自动维护。

## 3. `sessions` 表

用途：保存一次用户会话的主记录、消息摘要、事件流、文件引用、内存和执行状态。

| 字段 | 类型 | 说明 |
| --- | --- | --- |
| `id` | `varchar(255)` | 主键，默认 UUID 字符串。 |
| `sandbox_id` | `varchar(255)` | 沙箱容器或沙箱实例标识，无外键。 |
| `task_id` | `varchar(255)` | 后台任务标识，通常关联 Redis 中的任务流/状态，无数据库外键。 |
| `title` | `varchar(255)` | 会话标题，默认空字符串。 |
| `unread_message_count` | `integer` | 未读消息数，默认 `0`。 |
| `latest_message` | `text` | 最新消息摘要，默认空字符串。 |
| `latest_message_at` | `datetime` | 最新消息时间，可为空。 |
| `events` | `jsonb` | 会话事件数组，默认 `[]`。当前消息、计划、工具结果等主要写在这里。 |
| `files` | `jsonb` | 会话关联文件数组，默认 `[]`。保存的是文件引用快照。 |
| `memories` | `jsonb` | 会话记忆对象，默认 `{}`。 |
| `status` | `varchar(255)` | 会话状态，数据库默认空字符串。当前业务枚举包括 `pending/running/waiting/completed`。 |
| `updated_at` | `datetime` | 更新时间，默认 `CURRENT_TIMESTAMP(0)`。 |
| `created_at` | `datetime` | 创建时间，默认 `CURRENT_TIMESTAMP(0)`。 |

当前关系特点：

- 没有 `user_id`，所有用户会话在逻辑上共用一张表。
- 没有 `agent_id` 或 `employee_id`，无法区分不同数字员工实例。
- 没有标准化 `messages`、`runs`、`steps`、`tool_calls` 表。
- `files` 是 JSONB 快照，不是到 `files.id` 的强外键关系。

## 4. `files` 表

用途：保存上传文件或生成文件的元数据。

| 字段 | 类型 | 说明 |
| --- | --- | --- |
| `id` | `varchar(255)` | 主键，默认 UUID 字符串。 |
| `filename` | `varchar(255)` | 原始文件名。 |
| `filepath` | `varchar(255)` | 本地或对象存储路径。 |
| `key` | `varchar(255)` | 存储 key。 |
| `extension` | `varchar(255)` | 文件扩展名。 |
| `mime_type` | `varchar(255)` | MIME 类型。 |
| `size` | `integer` | 文件大小，默认 `0`。 |
| `updated_at` | `datetime` | 更新时间，默认 `CURRENT_TIMESTAMP(0)`。 |
| `created_at` | `datetime` | 创建时间，默认 `CURRENT_TIMESTAMP(0)`。 |

当前关系特点：

- 没有 `user_id`，文件没有所有者隔离。
- 没有 `session_id` 强外键，会话和文件主要通过 `sessions.files` JSONB 建立弱关联。
- 没有 Knowledge 文件、向量索引、数据集分组等概念。

## 5. 当前配置与非数据库持久化

模型、Agent、MCP、A2A、Tool 配置当前主要由 `AppConfigService` 读写 YAML：

```text
agentic/api/app/services/app_config_service.py
agentic/api/app/services/tool_config_service.py
```

默认配置文件：

```text
config.yaml
```

在 Docker API 容器中，当前 `agentic/docker/docker-compose.yml` 不再挂载整个 `../api` 源码目录。部署栈只将 `../api/config.yaml` 挂载到 `/app/config.yaml`，并用 `api_storage` volume 持久化 `/app/storage`。

这意味着：

- 当前配置是全局配置，不按用户隔离。
- LLM API Key、模型名、Agent 配置、MCP/A2A 服务器、Tool 注册都是全局维度。
- 后续做登录后，应决定这些配置是按用户、按数字员工实例，还是按 workspace 隔离。

## 6. 当前文件存储

文件服务优先使用 COS 配置；未配置 COS 时使用本地 fallback：

```text
/app/storage/files
```

相关文件：

```text
agentic/api/app/extensions/cos_file_storage.py
agentic/api/app/extensions/file_storage.py
```

部署影响：

- Docker 完整部署中，本地 fallback 文件落到 `api_storage` volume 下的 `/app/storage/files`。
- `api/config.yaml` 仍通过单文件 bind mount 暴露，便于部署后调整 LLM、MCP、A2A 和工具配置。
- 登录隔离后，文件路径或对象存储 key 应包含 `user_id`、`workspace_id` 或 `agent_id` 维度，避免不同用户文件混放。

## 7. 当前 Redis 角色

Redis 不是业务主库，当前主要承担：

- 后台任务/事件流。
- SSE 会话推送。
- Agent 运行过程中的短期状态。

PostgreSQL 保存会话最终状态和文件元数据；Redis 不应被当成长期审计或 Trace 存储。

## 8. 当前 API 边界

统一前缀：

```text
/api
```

当前控制器：

| 控制器 | 前缀 | 说明 |
| --- | --- | --- |
| `health.py` | `/status` | 健康检查。 |
| `session.py` | `/sessions` | 会话创建、列表、详情、删除、停止、聊天 SSE、会话文件、沙箱文件读取、Shell 输出、VNC。 |
| `file.py` | `/files` | 上传、查询、下载文件。 |
| `app_config.py` | `/app-config` | LLM、Agent、MCP、A2A 配置管理。 |
| `tools.py` | `/tools` | 工具列表、绑定、注册、预检、能力摘要。 |

后续做登录时，必须优先改造这些边界：

- `/sessions` 所有查询和写入必须按当前用户过滤。
- `/files` 上传、下载、查询必须校验文件所有者。
- `/sessions/{session_id}/vnc` 必须校验当前用户是否拥有该会话。
- `/app-config` 和 `/tools` 需要从全局配置切换为用户级、数字员工级或 workspace 级配置。

## 9. 当前 Docker 部署结构

Docker 文件目录：

```text
agentic/docker/docker-compose.yml
agentic/docker/docker-compose.dev.yml
agentic/docker/LOCAL_DEV.md
agentic/docker/init.sql
agentic/docker/nginx/
```

完整部署服务：

| 服务 | 说明 |
| --- | --- |
| `manus-redis` | Redis 7，持久化 volume 为 `redis_data`。 |
| `manus-postgres` | PostgreSQL 16，持久化 volume 为 `postgres_data`。 |
| `manus-sandbox` | Agent 执行沙箱镜像。 |
| `manus-api` | FastAPI 后端。 |
| `manus-web` | Vue/Vite 前端构建后的 Web 服务。 |
| `manus-nginx` | Nginx 网关，默认暴露 `8088:80`。 |

已修正的部署点：

- compose 文件位于 `agentic/docker`，构建上下文已改为 `../api`、`../web`、`../sandbox`。
- API 不再挂载整个 `../api` 源码目录；部署只挂载 `../api/config.yaml:/app/config.yaml` 和 `api_storage:/app/storage`。
- Nginx 配置挂载已改为 `./nginx/...`。
- PostgreSQL 首次初始化 SQL 已放到 `./init.sql`，并挂载到 `/docker-entrypoint-initdb.d/10-init.sql`。
- 完整 Docker 部署中 `manus-api` 默认设置 `RUN_MIGRATIONS_ON_STARTUP=true`，新库启动时会自动跑 Alembic 迁移。

## 10. 完整 Docker 启动

在 `agentic/docker` 目录运行：

```powershell
docker compose --env-file ../.env -f docker-compose.yml up -d --build
```

默认访问：

```text
http://localhost:8088
```

健康检查：

```text
http://localhost:8088/api/status
```

注意：`--env-file ../.env` 用于 compose 变量插值；`env_file: ../.env` 用于容器运行时环境变量。两者作用不同。

## 11. 本地开发启动

本地开发建议只用 Docker 启动 PostgreSQL 和 Redis：

```powershell
cd agentic\docker
docker compose --env-file ../.env -f docker-compose.dev.yml up -d
```

然后本机启动 API：

```powershell
cd ..\api
uv run alembic upgrade head
uv run uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload
```

新开一个终端，在仓库根目录启动 Web：

```powershell
cd agentic\web
pnpm dev
```

更完整的本地开发说明见：

```text
agentic/docker/LOCAL_DEV.md
```

## 12. 后续登录与用户隔离的最小改造面

在做 Skill、Knowledge、发布能力之前，建议先完成最小用户隔离：

1. 新增 `users` 表。
2. 新增认证机制，可以先采用邮箱/密码 + JWT。
3. `sessions` 新增 `user_id`，所有会话查询和写入按当前用户过滤。
4. `files` 新增 `user_id`，上传、下载、文件信息查询都校验所有者。
5. 会话文件 JSONB 中继续保留文件快照，但真实授权以 `files.user_id` 为准。
6. VNC、Shell、沙箱文件读取都先校验 `session.user_id`。
7. `app_config` 和 `tool_config` 暂时可继续全局，第二阶段再迁到用户级或数字员工级。

推荐先不引入组织/工作区，除非要立即支持企业多团队管理。当前更务实的顺序是：

```text
users -> sessions.user_id/files.user_id -> user-level config -> agent profile -> knowledge -> trace analytics
```

## 13. 后续数据库演进方向

登录隔离之后，可以分阶段补齐：

| 阶段 | 建议新增 |
| --- | --- |
| 用户隔离 | `users`、`sessions.user_id`、`files.user_id`。 |
| 数字员工实例 | `agents` 或 `agent_profiles`，保存名称、角色、系统提示词、模型、工具策略。 |
| Knowledge | `knowledge_bases`、`knowledge_documents`、`knowledge_chunks`、`knowledge_indexes`。 |
| Trace | `runs`、`run_steps`、`tool_calls`、`llm_calls`、`trace_events`。 |
| 发布 | `app_publications`、`api_tokens`、`web_apps`、`openapi_endpoints`。 |
| 企业化 | `organizations`、`workspaces`、`memberships`、`roles`、`audit_logs`。 |

关键原则：

- 不要一开始把 `llmops` 的全套表搬过来。
- 先保证当前 `agentic` 的会话、文件、配置可以被用户隔离。
- Trace 和 Knowledge 可以等登录隔离稳定后再标准化。
- Workflow 暂不作为核心表设计，企业业务编排优先通过 MCP、中间层、API Tool 或后续 Workflow-lite 承接。
