# Agentic 当前状态

## 2026-08-18 增量：用户等待与工具执行解耦

当前 Chat 执行链路只在 Agent 缺少用户业务输入时进入 `waiting`。目前 `message_ask_user` 会产生持久化 Interaction/WaitEvent；用户回答后，系统从原 Tool Call 继续。它不是会话关闭，不要求保留活协程，也没有面向用户的“恢复对话”操作。

通用 `tool_approval` 已从新 Run、公共解决 API、设置页和输入阻塞逻辑中移除。工具能否执行由平台在调用前确定性判定：允许则直接执行，禁止则返回失败 Tool Result。`risk_level` 只用于分类和策略输入，不会触发用户等待。

历史 `tool_approval` 事件保持只读兼容，但没有批准/拒绝按钮，也不会阻塞新输入。用户继续输入时，服务端在事务领取边界把旧 pending 动作收敛为未执行，并补齐 Memory 中悬空的 Tool Result；旧 Tool Call 永远不会被执行。

整理日期：2026-08-18

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
- 文件中心：独立 `/files` 页面，支持目录、搜索、筛选、上传、预览、下载、重命名、移动和延迟删除，并区分用户上传与 AI 生成文件。
- 用户级文件存储：Local、腾讯 COS、阿里云 OSS 三种 Provider；凭据加密保存，切换默认 Provider 不改变历史文件读取位置。

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
| `files` | 用户上传或 AI 生成文件资产，包含目录、来源、实际存储 Provider、Run/Session 来源和延迟清理状态。 |
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
- `ToolConfig v2`：内部使用平台 `execution_policy=allow|deny`；旧审批字段仅在读取时迁移，终端用户写 API 不接受 `approval` 或 `execution_policy`。
- 自定义 API 工具源注册、测试和运行时加载。
- 前端 Settings“API Tools”页：只管理自定义 API Provider/operations；系统内置能力不展示、不提供用户开关，由 Registry 内部默认装配，用户通知和询问等基础能力始终可用。
- `ask_user` 持久化等待和回答；工具调用不会创建面向终端用户的安全审批。

当前有意不提供：

- `approval=ask` 或“高风险工具请用户确认”这类通用终端审批。

仍待实现：

- Provider Execution Class、Capability Grant、租户权限和网络出口策略。
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
- 平台执行策略、Capability Grant 与 Tool Trace 关联。

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
| `file.py` | `/files` | 文件中心列表、目录、上传、预览、下载、重命名、移动和删除。 |
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
2. 平台工具治理与审计：补 Execution Class、Capability Grant、外部副作用幂等/对账和确定性拒绝记录，不引入终端用户逐次审批。
3. Agent Profile：让会话绑定明确的 Agent 身份、提示词、模型、工具策略。
4. Skill / Runbook：把可复用能力沉淀成独立概念。
5. Knowledge：文档解析、切分、索引、检索和引用来源。
6. 发布入口：Web App、OpenAPI Chat、A2A Agent。
