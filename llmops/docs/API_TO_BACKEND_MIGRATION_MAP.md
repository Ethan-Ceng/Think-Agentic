# api 到 backend 迁移映射

目录边界以 `docs/BACKEND_API_DIRECTORY_DESIGN.md` 为准。后续不得随意新增未设计目录。

`shared` 只承接旧 `api/pkg` 中无业务归属的纯工具；`integrations` 只承接第三方协议/SDK 适配；`infrastructure` 承接 DB、Redis、Celery、对象存储、向量库等技术资源。

更新时间：2026-05-13

本文用于约束后续迁移：`backend` 不是重写项目，而是把 `api` 已有能力迁入新的 FastAPI 工程架构。

## 1. 迁移总原则

```text
旧 api 是功能来源。
backend 是新工程边界。
新架构是整理和治理外壳。
已有 worker agent / tool / workflow / dataset / app 不重写。
```

优先保留：

- 旧表名和字段语义。
- 旧 service 的业务规则。
- 旧 core runtime 的执行行为。
- 旧 UI 所需响应格式。
- 旧 Celery 任务的业务逻辑。

逐步替换：

- Flask 兼容命名和隐式全局依赖。
- 业务代码直接读环境变量。
- 混乱的 sync / async session。
- 路由按资源堆叠的注册方式。

## 2. 第一批迁移顺序

### 2.1 shared 基础包

| 来源 | 目标 | 说明 |
| --- | --- | --- |
| `api/pkg/response` | `backend/app/shared/response` | 兼容 UI 响应格式 |
| `api/pkg/paginator` | `backend/app/shared/paginator` | 兼容分页 |
| `api/pkg/password` | `backend/app/shared/password` | 账号密码迁移需要 |
| `api/pkg/oauth` | `backend/app/integrations/oauth` | GitHub OAuth |
| `api/app/exception` | `backend/app/core/errors.py` + exception package | 保留业务异常类型 |

### 2.2 auth/account

| 来源 | 目标 |
| --- | --- |
| `api/app/model/account.py` | `backend/app/models/account.py` |
| `api/app/service/account_service.py` | `backend/app/services/account_service.py` |
| `api/app/service/jwt_service.py` | `backend/app/services/jwt_service.py` |
| `api/app/service/oauth_service.py` | `backend/app/services/oauth_service.py` |
| `api/app/api/routes/auth.py` | `backend/app/api/routers/console/auth.py` |
| `api/app/api/routes/account.py` | `backend/app/api/routers/console/account.py` |

### 2.3 tool

| 来源 | 目标 |
| --- | --- |
| `api/app/model/api_tool.py` | `backend/app/models/api_tool.py` |
| `api/app/core/tools/builtin_tools` | `backend/app/core/tools/builtin_tools` |
| `api/app/core/tools/api_tools` | `backend/app/core/tools/api_tools` |
| `api/app/service/builtin_tool_service.py` | `backend/app/services/builtin_tool_service.py` |
| `api/app/service/api_tool_service.py` | `backend/app/services/api_tool_service.py` |
| `api/app/api/routes/builtin_tool.py` | `backend/app/api/routers/console/builtin_tool.py` |
| `api/app/api/routes/api_tool.py` | `backend/app/api/routers/console/api_tool.py` |

### 2.4 workflow

| 来源 | 目标 |
| --- | --- |
| `api/app/model/workflow.py` | `backend/app/models/workflow.py` |
| `api/app/entity/workflow_entity.py` | `backend/app/core/workflow/entities.py` |
| `api/app/core/workflow` | `backend/app/core/workflow` |
| `api/app/service/workflow_service.py` | `backend/app/services/workflow_service.py` |
| `api/app/api/routes/workflow.py` | `backend/app/api/routers/workflow.py` |

### 2.5 dataset/rag

| 来源 | 目标 |
| --- | --- |
| `api/app/model/dataset.py` | `backend/app/models/dataset.py` |
| `api/app/core/retrievers` | `backend/app/core/retrievers` |
| `api/app/core/file_extractor` | `backend/app/core/file_extractor` |
| `api/app/service/dataset_service.py` | `backend/app/services/dataset_service.py` |
| `api/app/service/document_service.py` | `backend/app/services/document_service.py` |
| `api/app/service/segment_service.py` | `backend/app/services/segment_service.py` |
| `api/app/service/indexing_service.py` | `backend/app/services/indexing_service.py` |
| `api/app/service/retrieval_service.py` | `backend/app/services/retrieval_service.py` |
| `api/app/task/document_task.py` | `backend/app/tasks/document_task.py` |
| `api/app/task/dataset_task.py` | `backend/app/tasks/dataset_task.py` |

### 2.6 existing agent/app

| 来源 | 目标 |
| --- | --- |
| `api/app/model/app.py` | `backend/app/models/app.py` |
| `api/app/model/conversation.py` | `backend/app/models/conversation.py` |
| `api/app/core/agent` | `backend/app/core/agent` |
| `api/app/core/memory` | `backend/app/core/memory` |
| `api/app/core/language_model` | `backend/app/core/language_model` |
| `api/app/service/app_service.py` | `backend/app/services/app_service.py` |
| `api/app/service/app_config_service.py` | `backend/app/services/app_config_service.py` |
| `api/app/service/conversation_service.py` | `backend/app/services/conversation_service.py` |
| `api/app/service/assistant_agent_service.py` | `backend/app/services/assistant_agent_service.py` |
| `api/app/task/app_task.py` | `backend/app/tasks/app_task.py` |

## 3. 新架构外壳接入点

旧能力迁移完成后，再做下面包装：

| 新架构概念 | 包装旧能力 |
| --- | --- |
| Worker Agent | 旧 App / Assistant Agent / core agent |
| Tool Capability | builtin tool / api tool |
| Workflow Capability | workflow |
| Knowledge Capability | dataset / retrieval |
| Task Engine | 旧 Celery 任务 + 新状态表 |
| Trace | conversation message thought + trace_events |
| Router Agent | 新增 manager 模式，调度已有 Worker/App |

## 4. 禁止事项

- 不在迁移 Tool 前重写 Tool Gateway。
- 不在迁移 Workflow 前重写 Workflow Engine。
- 不在迁移 Dataset 前切 pgvector。
- 不在迁移 App/Agent 前强制替换为新 Agent 表。
- 不同时改表名、改业务语义、改接口响应。
