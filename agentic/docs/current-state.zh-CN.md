# Agentic 当前状态

整理日期：2026-07-13

本文是 `agentic` 当前实现基线，用于替代旧的数据库与部署基线文档。结论以当前代码为准，不再沿用旧文档中“用户、工具配置未入库”的说法。

## 1. 当前结论

`agentic` 已经从单用户 Demo 形态推进到“带登录、用户隔离、用户级配置和工具治理的自部署 Agent 运行时”。

已经落地：

- 用户注册、密码登录、JWT 当前用户。
- `sessions`、`files` 按 `user_id` 隔离。
- 用户级配置表 `configs`，承载 LLM、Agent、MCP、A2A、Tool 等配置。
- API 工具源注册配置、operation 启停、能力摘要、preflight；Settings 只管理 API Tools，MCP/A2A 保持独立入口，系统内置能力由运行时内部默认装配。
- 工具执行链路通过 `ToolFactory` 和 `FilteredTool` 过滤可见 schema 与调用。
- Run / Trace 最小后端闭环：`agent_runs`、`run_steps`、`tool_calls`、`model_calls`、`trace_events`，并提供 `/api/runs` 查询接口。
- Run / Trace 前端入口：会话页头部可打开 Trace 侧边面板，查看 run 列表、事件时间线、step、tool call、model call。

仍未标准化入库：

- Agent Profile / 数字员工实例。
- Skill / Runbook。
- Knowledge base、documents、chunks、indexes。
- 发布入口、API token、Web App 发布记录。
- 组织、工作区、角色、审计日志。

## 2. 数据库

迁移目录：

```text
agentic/api/alembic/versions/
```

当前业务表：

| 表 | 当前用途 |
| --- | --- |
| `users` | 用户账号、密码哈希、状态、登录时间。 |
| `sessions` | 会话主记录、事件流、文件快照、状态，已带 `user_id`。 |
| `files` | 上传或生成文件元数据，已带 `user_id`。 |
| `configs` | 用户级 typed JSONB 配置，按 `user_id + config_type` 唯一。 |
| `alembic_version` | Alembic 迁移版本。 |

重要迁移：

```text
20260707_0001_user_isolation.py
20260708_0001_configs.py
```

注意：用户隔离迁移会删除旧的 `sessions` 和 `files` 数据，因为旧数据没有所有者，不能安全归属到真实用户。

## 3. 认证与用户隔离

当前认证入口：

```text
POST /api/auth/register
POST /api/auth/password-login
POST /api/auth/logout
GET  /api/auth/me
```

当前受保护边界：

- `/sessions`：创建、列表、详情、删除、停止、聊天、文件、Shell 输出、VNC 均按当前用户校验。
- `/files`：上传、查询、下载均按当前用户校验。
- `/app-config`：读取和更新当前用户配置。
- `/tools`：读取和更新当前用户工具配置。

## 4. 用户级配置

配置从全局 `config.yaml` 过渡到用户级 `configs` 表。`config.yaml` 仍作为默认配置来源，新用户或缺失配置会从默认配置创建 typed config。

当前配置类型：

```text
llm
agent
mcp
a2a
tool
ui
storage
```

当前实现重点：

- `configs.user_id` 外键到 `users.id`。
- `configs.config_type` 标记配置类型。
- `configs.config` 使用 JSONB 存储具体配置。
- `user_id + config_type` 唯一。
- LLM key 更新支持保留脱敏值，不会因为前端传回 `******` 覆盖真实值。

当前限制：

- 配置已按用户隔离，但不是组织/工作区级配置。
- 敏感字段有脱敏与保留逻辑；数据库层加密不应视为已完成能力。

## 5. 工具治理

当前工具治理已不只是规划，已经进入运行链路。

已实现：

- `ToolConfig`：`bindings`、`registrations`、`runtime_policy`。
- `ToolRegistry`：汇总代码内置工具和用户注册的 API 工具源元数据。
- `ToolCapabilityService`：生成能力摘要。
- `ToolPreflightService`：基于规则判断任务是否缺工具能力。
- `ToolFactory`：构建当前 Agent 的工具集合。
- `FilteredTool`：过滤 LLM 可见工具 schema，并阻止禁用工具调用。
- 自定义 API 工具源注册、测试和运行时加载。
- 前端 Settings“API Tools”页：只管理自定义 API Provider/operations；系统内置能力不展示、不提供用户开关，由 Registry 内部默认装配，用户通知和询问等基础能力始终可用。

当前没有实现：

- `approval=ask/deny` 这类确认审批字段。
- 高风险工具执行前的人类确认流。
- 工具调用审计表。
- MCP 动态工具的完整 tool 级缓存与细粒度治理。

## 6. 运行时主线

核心执行链路仍是：

```text
用户请求
  -> Session / AgentService
  -> AgentTaskRunner
  -> PlannerReActFlow
  -> PlannerAgent 规划
  -> ReActAgent 执行
  -> ToolFactory 构造工具
  -> FilteredTool 应用工具配置
  -> SSE / sessions.events 记录过程
```

当前 `sessions.events` 仍承担会话消息、计划、工具调用结果等事件记录。它可以继续作为兼容层，但不等同于可分析的标准 Trace 表。

Run / Trace 最小闭环已经开始落地：

- Alembic 迁移：`20260709_0001_run_trace.py`。
- ORM：`AgentRunModel`、`RunStepModel`、`ToolCallModel`、`ModelCallModel`、`TraceEventModel`。
- 投影入口：`AgentTaskRunner._put_and_add_event()`。
- 模型调用观测入口：`BaseAgent._invoke_llm()` 和 `OpenAILLM.invoke()`。
- 查询接口：`GET /api/runs`、`GET /api/runs/{run_id}`、`GET /api/runs/{run_id}/events`、`GET /api/runs/{run_id}/tool-calls`、`GET /api/runs/{run_id}/model-calls`。
- 前端入口：`SessionHeader` 的 Trace 图标按钮，打开 `TracePanel` 侧边面板。

仍待补齐：

- 更细的输入/输出保存策略。
- 配置变更审计。
- 高风险工具确认与审批状态关联。

## 7. API 边界

统一前缀：

```text
/api
```

当前主要控制器：

| 控制器 | 前缀 | 说明 |
| --- | --- | --- |
| `auth.py` | `/auth` | 注册、登录、退出、当前用户。 |
| `health.py` | `/status` | 健康检查。 |
| `session.py` | `/sessions` | 会话、聊天 SSE、会话文件、沙箱文件、Shell 输出、VNC。 |
| `file.py` | `/files` | 文件上传、查询、下载。 |
| `app_config.py` | `/app-config` | 当前用户 LLM、Agent、MCP、A2A 配置。 |
| `tools.py` | `/tools` | 工具列表、绑定、注册、测试、能力摘要、preflight。 |
| `runs.py` | `/runs` | Run / Trace 查询、事件、工具调用、模型调用。 |

## 8. 部署基线

Docker 文件仍位于：

```text
agentic/docker/
```

完整部署入口：

```powershell
cd agentic\docker
docker compose --env-file ../.env -f docker-compose.yml up -d --build
```

默认访问：

```text
http://localhost:8088
```

本地开发建议只用 Docker 启动 PostgreSQL 和 Redis，再本机启动 API 与 Web。更细说明仍看：

```text
agentic/docker/LOCAL_DEV.md
```

## 9. 当前主要缺口

近期不要再优先做“登录/用户隔离/工具可视化是否存在”的讨论，这些已经落地。下一轮真正需要补的是：

1. Run / Trace 审计增强：在最小账本和前端查看之上补脱敏策略、配置变更审计。
2. 高风险工具确认与审计：在现有启停过滤和 Trace 之上补确认、拒绝、审批记录。
3. Agent Profile：让会话绑定明确的 Agent 身份、提示词、模型、工具策略。
4. Skill / Runbook：把可复用能力沉淀成独立概念。
5. Knowledge：文档解析、切分、索引、检索和引用来源。
6. 发布入口：Web App、OpenAPI Chat、A2A Agent。
