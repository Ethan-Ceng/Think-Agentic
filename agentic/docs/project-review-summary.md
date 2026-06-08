# Agentic 项目评估摘要

本文档基于 2026-06-08 对 `agentic` 子项目的代码、配置、文档和基础构建结果的检查整理，用于记录项目现状、主要风险和建议的整改方向。

## 1. 总体判断

`agentic` 是一个具备完整雏形的私有化通用 Agent 系统，项目中也称为 `MoocManus`。它不是简单聊天应用，而是包含 Planner、ReAct 执行器、工具调用、沙箱、浏览器、VNC、MCP/A2A、SSE 事件流和文件同步能力的任务执行系统。

当前更适合作为内网原型、技术验证或二次开发基础。如果要进入生产或公网环境，必须先补齐安全、配置治理、测试和部署运维能力。

简要评分：

| 维度 | 评价 |
| --- | --- |
| 研发原型 | 7/10 |
| 内网二开基础 | 6/10 |
| 生产可用 | 4/10 |

## 2. 当前架构概览

项目采用前端、后端、沙箱和基础设施分离的方式：

```text
agentic/
├── api/       FastAPI 后端，负责会话、Agent 调度、配置、文件、SSE、VNC 代理
├── web/       Vue 3 + Vite 前端，负责会话 UI、事件流展示、工具预览和 VNC
├── sandbox/   Ubuntu 沙箱服务，提供 Shell、文件、Chrome、VNC 能力
├── nginx/     统一入口网关配置
├── docs/      项目文档
└── docker-compose*.yml
```

核心服务：

| 服务 | 作用 |
| --- | --- |
| `manus-nginx` | 对外统一入口，转发 Web 和 API |
| `manus-web` | Vue 前端静态站点 |
| `manus-api` | FastAPI 后端服务 |
| `manus-postgres` | 会话、事件、文件元数据、memory 等业务数据 |
| `manus-redis` | Redis Stream 任务输入/输出队列 |
| `manus-sandbox` | Shell、文件操作、Chrome、CDP、VNC 沙箱 |

## 3. 主要优点

- 后端分层较完整，包含 controllers、services、repositories、models、schemas、core、dependencies、extensions。
- Agent 执行链条较清楚：`PlannerAgent` 规划，`ReActAgent` 执行，`PlannerReActFlow` 编排，`AgentTaskRunner` 负责事件、沙箱、文件和工具资源。
- 工具体系覆盖文件、Shell、浏览器、搜索、MCP、A2A 和用户询问。
- 前端已经具备会话流式展示、计划步骤展示、工具调用预览、文件预览、VNC 远程桌面等完整交互雏形。
- Docker Compose 能解析完整部署配置，前端在补齐依赖后可以通过生产构建。

## 4. 重点风险

### 4.1 密钥和配置治理

当前 `api/config.yaml` 中包含真实 LLM/MCP 访问密钥，且 `agentic/.env`、`agentic/api/.env`、`agentic/api/config.yaml` 被 Git 跟踪。密钥一旦进入 Git 历史，即使后续删除，历史版本仍可能泄露，因此应按已泄露处理并轮换。

需要明确的是：

- `.env` 不等于安全。它的价值主要是本地注入和避免提交到 Git。
- 内网数据库不等于不安全。数据库是否安全取决于认证、授权、网络隔离、加密、审计、备份和轮换机制。
- 当前问题的核心不是“文件还是数据库”，而是密钥明文进入仓库、配置接口缺少认证、生产密钥缺少统一治理。

### 4.2 当前配置实际保存位置

项目当前的 LLM、Agent、MCP、A2A 配置不是保存到 PostgreSQL，而是保存到 YAML 文件。

代码路径：

- `api/app/dependencies/infrastructure.py` 中的 `get_app_config()` 使用 `FileAppConfigRepository` 加载配置。
- `api/app/repositories/file_app_config_repository.py` 读写本地 YAML 配置文件。
- `api/app/services/app_config_service.py` 的 `_load()` 和 `_save()` 也直接读写 `config.yaml`。
- `api/app/core/config.py` 默认 `app_config_filepath = "config.yaml"`。

因此当前关系是：

| 数据类型 | 当前保存位置 |
| --- | --- |
| LLM / Agent / MCP / A2A 配置 | `api/config.yaml` |
| 数据库、Redis、COS、沙箱运行参数 | `.env` |
| 会话、事件、文件元数据、memory | PostgreSQL |
| 任务输入/输出事件队列 | Redis Stream |

如果希望配置真正保存到数据库，需要新增配置表，例如 `app_configs`，并替换 `FileAppConfigRepository` 和 `AppConfigService` 的文件读写逻辑。

### 4.3 认证和权限

当前 API 没有看到完整认证/授权机制。会话、文件、配置、VNC 等接口基本依赖内网可信环境。

风险点：

- 设置接口可以修改 LLM、Agent、MCP、A2A 配置。
- 文件上传、下载接口没有用户级权限控制。
- VNC WebSocket 代理没有独立认证。
- CORS 允许所有来源，且允许凭证。

如果对公网开放，必须先增加认证、权限、CSRF/CORS 策略和操作审计。

### 4.4 沙箱安全边界

沙箱提供 Shell、文件读写、浏览器、VNC 和 CDP 能力，功能强但风险也高。

当前需要重点关注：

- `docker-compose.yml` 将 `/var/run/docker.sock` 挂载给 API，API 具备管理宿主机 Docker 的高权限。
- 沙箱内 VNC 使用无密码配置。
- Chrome 启动参数禁用了多项安全限制。
- Shell 工具允许执行命令、安装依赖和文件管理。

这些能力适合可信内网或受控实验环境，不适合未经加固直接暴露。

### 4.5 测试覆盖不足

当前测试覆盖较薄：

- 主要只有 `/api/status` 路由测试。
- `TestClient(app)` 会触发 FastAPI lifespan，进而初始化数据库、Redis、存储，使基础测试也依赖外部服务。
- Agent 状态机、WaitEvent、人机协作恢复、工具调用、文件同步、MCP/A2A、VNC 代理等核心路径缺少自动化测试。

建议将测试分层：

- 单元测试：Agent、Flow、JSON parser、Memory、Repository 行为。
- 集成测试：API + 数据库 + Redis。
- 端到端测试：Docker Compose + 沙箱 + Web UI。

### 4.6 前端构建副作用

前端在补齐依赖后 `pnpm build` 可以通过，但 `vue-tsc -b` 会在 `web/src` 下生成未跟踪 `.js` 文件。该类生成物不适合作为源码保留。

建议调整构建命令：

```json
{
  "build": "vue-tsc --noEmit -b && vite build"
}
```

或在 TypeScript 配置中显式禁止 emit。

## 5. 已做验证

已完成的检查：

- 读取 README、Docker Compose、前后端配置、核心 Agent 流程、沙箱配置和配置服务实现。
- `docker compose config` 可以正常解析部署配置。
- 前端依赖补齐后，`pnpm build` 通过。
- 构建产生的 `web/src/*.js` 未跟踪生成物已清理，仓库状态恢复干净。

未完成的验证：

- 后端测试未能运行，因为当前环境找不到 `uv`，系统 Python 也没有 `pytest`。
- 未执行完整 Docker Compose 端到端启动。
- 未验证真实 LLM、MCP、A2A、沙箱 Shell、浏览器和 VNC 的完整业务流程。

## 6. 建议优先级

### P0：立即处理

- 轮换所有已进入仓库的 LLM、MCP、COS 等密钥。
- 从 Git 跟踪中移除真实 `.env` 和包含密钥的 `config.yaml`。
- 增加 `.env.example`、`config.example.yaml`，只保留占位符。
- 在 `.gitignore` 中忽略真实环境文件和真实运行配置。
- 给配置接口、文件接口、会话接口、VNC 接口增加认证和权限控制。

### P1：生产前必须处理

- 决定配置保存方案：YAML、数据库、Secret Manager 或混合方案。
- 如果配置存数据库，密钥字段需要加密存储，接口只允许写入和脱敏读取。
- 如果配置仍存 YAML，生产环境应使用只读模板加环境变量或 Secret 注入。
- 移除或严格限制 Docker socket 挂载。
- 对沙箱增加网络、文件系统、进程和资源隔离策略。
- 增加核心 Agent 流程和配置服务测试。

### P2：工程质量提升

- 修复前端 `vue-tsc -b` 产生源码目录 `.js` 文件的问题。
- 增加 CI：前端构建、后端导入检查、单元测试、Compose 配置检查。
- 对 README、LOCAL_DEV、部署文档进行统一，明确本地、内网、生产三种运行方式。
- 增加日志脱敏，避免 LLM 响应、工具结果或配置内容泄露密钥。

## 7. 推荐配置方案

较稳妥的目标方案：

- `config.example.yaml`：保存非敏感默认配置和结构。
- `.env.example`：保存运行环境变量占位符。
- 本地开发：使用 `.env` 和本地 `config.yaml`，但二者不进 Git。
- 生产部署：通过 Secret Manager、Docker secrets、Kubernetes Secret、Vault 或 SOPS 注入密钥。
- Web 设置页：允许配置模型名、base_url、温度、开关等非敏感项；密钥字段只写入、不回显。
- 数据库存储密钥时：使用 KMS 或 envelope encryption 加密，配合认证、审计和轮换。

结论：项目的技术骨架有价值，但安全和配置治理需要优先补强。下一阶段应先处理密钥、认证、配置持久化和测试基础，再继续扩展功能。
