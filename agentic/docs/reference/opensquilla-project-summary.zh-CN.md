# OpenSquilla 项目深度总结

> 参考说明：本文是 OpenSquilla 调研材料，不代表 `agentic` 当前实现。当前 `agentic` 状态见 `../current-state.zh-CN.md`。

> 基于本仓库源码在 2026-07-07 的本地审阅整理。本文关注项目定位、架构主线、核心子系统、运行部署、测试质量和后续阅读路线。

## 1. 项目定位

OpenSquilla 是一个以本地 Gateway 为中心的个人 Agent 运行时。它不是单纯的聊天前端，而是把模型供应商、工具调用、会话存储、长期记忆、技能、定时任务、多渠道消息和 Web/桌面控制台组合在一起的 Agent 平台。

项目在 `pyproject.toml` 中的定位是：

- Python 微内核运行时；
- MCP-native 工具接入；
- 多通道消息系统；
- 本地优先的 Web UI、CLI、桌面端和 Gateway RPC 表面。

可以把它理解为：

```text
用户入口
  Web UI / CLI / 桌面端 / Telegram、Slack、Feishu 等渠道 / Cron
        |
        v
Gateway + RouteEnvelope + TaskRuntime
        |
        v
TurnRunner 统一编排一次对话/任务
        |
        v
Pipeline: 路由、技能筛选、提示词增强、模式选择
        |
        v
Agent 状态机
        |
        +--> LLM Provider 流式输出
        +--> ToolRegistry / MCP / 内置工具 / 沙箱 / 权限审批
        |
        v
Session / Memory / Usage / Artifacts / Events 持久化
```

## 2. 技术栈

后端主要是 Python 3.12+：

- CLI：Typer、Rich；
- Web/Gateway：Starlette、Uvicorn、WebSocket/RPC；
- 配置与模型：Pydantic、TOML、环境变量；
- 数据：SQLite、aiosqlite、SQLModel/SQLAlchemy、FTS5、可选 sqlite-vec；
- 并发：asyncio/anyio，自研 TaskRuntime 队列与会话级锁；
- 调度：自研 SchedulerEngine、cron 解析、持久化 job store；
- 搜索和内容抽取：DuckDuckGo、Bocha、Brave、Tavily、Exa，readability/html2text/BeautifulSoup；
- 文档/媒体：docx、pptx、openpyxl、pypdf、reportlab、pdfplumber、Pillow；
- 路由与推荐：可选 LightGBM、ONNX Runtime、tokenizers、numpy、scikit-learn。

前端与桌面端：

- Web UI：Vue 3、Vite、Pinia、vue-router、vue-i18n、TypeScript；
- Web 测试：Vitest、Playwright；
- 桌面端：Electron、electron-builder、electron-updater；
- 桌面端会管理本地 Gateway 子进程、密钥存储、首启配置和自动更新。

## 3. 仓库结构

关键目录如下：

| 路径 | 作用 |
| --- | --- |
| `src/opensquilla` | Python 后端主包，包含 Gateway、Agent、工具、会话、记忆、渠道、调度、Provider 等核心逻辑。 |
| `opensquilla-webui` | Vue Web 控制台，覆盖聊天、会话、审批、渠道、Cron、技能、用量、日志等视图。 |
| `desktop/electron` | Electron 桌面壳，打包 Web UI 与 Gateway runtime。 |
| `docs` | 用户文档、功能说明、配置、Gateway、会话、技能、记忆等说明。 |
| `migrations` | Gateway/session/memory/router 等持久化 schema 的迁移脚本。 |
| `tests` | 后端单元、集成、功能、live、浏览器、桌面、沙箱、Provider、记忆等测试。 |
| `.github/workflows` | CI、live E2E、发布资产、桌面安装包和 release 流程。 |
| `service-units` | 服务化运行相关文件。 |
| `Formula` | Homebrew 发行相关文件。 |

## 4. 入口与运行方式

Python 包定义了两个主要 console script：

- `opensquilla = opensquilla.cli.main:app`
- `gateway = opensquilla.cli.main:gateway_app`

`src/opensquilla/cli/main.py` 是 CLI 聚合入口。它会先加载 `.env`，支持 `--profile`/`OPENSQUILLA_PROFILE`，再挂载大量子命令：

- `gateway`：启动、停止、重启、查询本地 Gateway；
- `chat` / `agent`：终端交互或一次性任务；
- `providers` / `models` / `router`：供应商和模型路由；
- `channels`：消息渠道配置；
- `sessions`：会话管理；
- `memory`：长期记忆管理；
- `skills`：技能管理；
- `cron`：定时任务；
- `sandbox`：权限和沙箱姿态；
- `mcp-server`、`search`、`diagnostics`、`swebench` 等。

推荐开发运行方式：

```sh
uv sync --extra recommended --extra dev
uv run opensquilla --help
uv run opensquilla gateway run
```

默认 Gateway 地址是：

```text
http://127.0.0.1:18791/control/
```

这个默认值很重要：Gateway 控制工具、会话、渠道、审批和配置，所以默认只绑定 loopback。

## 5. Gateway 与服务装配

Gateway 是整个系统的中心。主要文件：

- `src/opensquilla/gateway/boot.py`
- `src/opensquilla/gateway/app.py`
- `src/opensquilla/gateway/config.py`
- `src/opensquilla/gateway/task_runtime.py`
- `src/opensquilla/gateway/channel_dispatch.py`

`boot.py` 的 `build_services()` 负责把运行时拼起来，包括：

- 配置加载与迁移；
- AgentRegistry；
- SessionManager；
- Provider selector；
- 模型目录与价格缓存；
- ToolRegistry 与内置工具；
- MCP 工具发现；
- 技能加载器；
- 搜索供应商；
- 记忆管理器、索引和修复服务；
- Scheduler/Cron；
- Router 决策记录、校准和历史；
- flush、heartbeat、diagnostics、usage 等后台服务。

`app.py` 创建 Starlette 应用，提供：

- `/healthz`、`/readyz`；
- `/control/` Web UI；
- `/api/config`、`/api/sessions`、`/api/chat`、`/api/system/status`、`/api/usage` 等 HTTP 接口；
- WebSocket RPC；
- CORS、RateLimit、SecurityHeaders、Auth、错误处理中间件。

`TaskRuntime` 是 Gateway 内的任务执行层。它的职责是：

- 同一 session 的 turn 串行化；
- 不同 session 可以并发；
- 控制全局并发数、单 session pending 数、队列溢出策略；
- 支持 turn deadline、取消、heartbeat、in-flight 指标；
- 避免 Web、渠道、Cron 同时写同一会话导致状态错乱。

## 6. 一次任务的核心链路

OpenSquilla 的关键设计是：Web、CLI、渠道、Cron、子 Agent 尽量走同一条 TurnRunner 路径。

### 6.1 路由入口

`src/opensquilla/gateway/routing.py` 定义 `RouteEnvelope`，把不同入口统一成稳定结构：

- WEB；
- CLI；
- CHANNEL；
- CRON；
- SUBAGENT；
- SYSTEM。

同时它会转换出 `ToolContext`，把调用方、owner 状态、工作区、权限、渠道上下文、artifact 设置、coding mode、工具 allow/deny 等信息带入工具执行层。

### 6.2 TurnRunner 编排

`src/opensquilla/engine/runtime.py` 中的 `TurnRunner` 是核心编排器。它把一次 turn 拆成多个 stage：

- 输入解析；
- Provider 与工具构建；
- Prompt 组装；
- Agent bootstrap；
- compaction/history 处理；
- attachment 处理；
- 流式消费；
- turn finalizer。

它负责把以下信息汇入模型请求：

- 用户输入；
- 会话历史；
- 记忆检索结果；
- 技能注入内容；
- 平台/时间/子 Agent/coding mode 提示；
- 附件和 workspace 上下文；
- Router 控制块；
- 工具定义；
- Provider 配置和 fallback。

### 6.3 Pipeline

`src/opensquilla/engine/pipeline.py` 是 turn 前的可插拔流水线。现有 step 包括：

- 时间和平台提示；
- coding mode；
- meta command / meta resolution；
- provider/model 解析；
- SquillaRouter 决策记录；
- 技能筛选；
- prompt cache；
- vision follow-up gate；
- subagent grounding。

Pipeline 的策略偏保守：step 异常会被记录并 fail-open，避免单个增强步骤把整个 turn 打死。

### 6.4 Agent 状态机

`src/opensquilla/engine/agent.py` 是显式状态机，典型流转是：

```text
IDLE -> THINKING -> STREAMING -> TOOL_CALLING -> THINKING -> DONE/ERROR
```

Agent 做的事情很多：

- 清理历史、修复 tool pairing、压缩或投影旧工具结果；
- 调用 Provider 的流式 chat；
- 收集 text delta、reasoning delta、tool call delta；
- 并行或串行执行工具；
- 处理工具审批、沙箱拒绝、router_control replay；
- 处理 provider 错误、fallback、重试；
- 在上下文超限时触发 compaction；
- 汇总 usage、cost、cache token、artifact 和最终 DoneEvent。

这是项目复杂度最高的部分之一，也是理解系统行为的关键入口。

## 7. Provider 与模型路由

Provider 抽象在 `src/opensquilla/provider/protocol.py`：

```text
LLMProvider.chat(messages, tools, config) -> AsyncIterator[StreamEvent]
```

流事件包括：

- TextDelta；
- ToolUseStart/Delta/End；
- ReasoningDelta；
- Done；
- Error。

`src/opensquilla/provider/registry.py` 注册了多类供应商：

- OpenRouter；
- OpenAI Chat/Responses；
- Azure；
- Anthropic；
- Ollama；
- DeepSeek；
- Gemini；
- DashScope/Qwen；
- Moonshot；
- MiniMax；
- Mistral；
- Groq；
- Zhipu；
- Qianfan；
- SiliconFlow；
- AiHubMix；
- Volcengine/BytePlus；
- OpenAI-compatible custom endpoint；
- vLLM、LM Studio、OVMS、LiteLLM proxy；
- OpenAI Codex OAuth 等。

`ModelSelector` 负责：

- 根据配置实例化 provider；
- 解析 base URL、API key env、模型名；
- 支持 static fallback；
- 支持 router 给出的 fallback chain；
- 支持插件 failover hook；
- 支持 direct 模式和 router 模式。

SquillaRouter 位于 `src/opensquilla/engine/steps/squilla_router.py` 与 `src/opensquilla/squilla_router`。它把任务复杂度、历史、预算和策略转换成模型 tier 决策。项目中的 tier 形态包括 `c0`、`c1`、`c2`、`c3`，目标是把简单任务留给便宜模型，把复杂任务路由到更强模型。

## 8. 工具、MCP、权限和沙箱

工具系统由 `ToolRegistry`、`ToolSpec`、`ToolContext` 和 dispatch pipeline 组成。

主要文件：

- `src/opensquilla/tools/registry.py`
- `src/opensquilla/tools/types.py`
- `src/opensquilla/tools/dispatch.py`
- `src/opensquilla/tools/policy/chain.py`
- `src/opensquilla/tools/builtin/*`
- `src/opensquilla/sandbox/*`

内置工具覆盖：

- 文件读写、编辑、列表、glob、grep；
- shell、后台进程、代码执行；
- git status/diff/log/commit；
- web search、web discover、web fetch；
- memory search/save/get/delete；
- sessions spawn/send/history/status/search；
- artifact 发布；
- 图片、PDF、TTS、音频和媒体工作流；
- CSV/XLSX/PPTX/PDF 等文档生成；
- Feishu/Lark 平台能力；
- cron/gateway 管理；
- skill 创建、查看、安装、编辑、删除；
- meta skill 调用。

工具执行前会经过策略链：

```text
OwnerOnly -> DenyList -> PrivateMemoryScope -> AllowList -> Profile -> PermissionMatrix
```

`dispatch.py` 还负责：

- 注入攻击防护；
- 工具运行预算；
- 工具结果预算；
- 参数和结果压缩；
- hook before/after；
- 错误 envelope。

MCP 接入在 `src/opensquilla/mcp/discovery.py`。它支持 stdio 和 SSE client，连接外部 MCP server 后调用 `tools/list`，再把每个 MCP tool 注册成 `mcp_<tool_name>` 的 OpenSquilla 工具。active MCP client 会被模块级列表持有，确保工具调用时连接仍然存活。

沙箱默认开启，核心配置在 `src/opensquilla/sandbox/config.py`：

- 默认 sandbox=True；
- 默认安全等级 STANDARD；
- 后端 auto；
- 支持 standard/trusted/full run mode；
- 网络默认 proxy_allowlist；
- 资源限制包括 CPU、内存、wall time；
- Windows/macOS/Linux 使用不同后端或退化路径；
- 多次拒绝、审批、workspace lockdown 和 tool policy 一起控制风险。

## 9. 会话、持久化和记忆

会话系统主要在：

- `src/opensquilla/session/manager.py`
- `src/opensquilla/session/storage.py`

SessionManager 提供：

- 创建、读取、列出、追加；
- fork；
- compact；
- archive/prune；
- export；
- task runtime 状态绑定。

SessionStorage 使用 SQLite，schema version 当前为 8，覆盖：

- sessions；
- transcript_entries；
- compacted_transcript_entries；
- transcript FTS；
- session summaries；
- session context states；
- durable receipts；
- agent tasks；
- cost rollup 和 router decision 等迁移扩展。

`migrations` 目录包含 V001 到 V017 的迁移，说明项目把会话、调度、heartbeat、memory、agent tasks、usage、meta runs、clarify、manual command、router decisions 等功能持续落进持久化层。

记忆系统主要在：

- `src/opensquilla/memory/manager.py`
- `src/opensquilla/memory/store.py`

MemoryManager 是每个 agent 的门面，组合：

- LongTermMemoryStore；
- MemorySyncManager；
- MemoryRetriever；
- TurnCaptureService。

它支持：

- Markdown-backed 记忆源；
- SQLite FTS5 关键词搜索；
- 可选 sqlite-vec 语义检索；
- embedding cache；
- legacy memory 迁移；
- session source index；
- flush session；
- dream/repair 等后台流程。

设计意图是：长期偏好、项目事实、任务痕迹不必全部塞回 prompt，而是按需检索进入上下文。

## 10. Skills 与 Meta-Skills

Skills 是项目的重要扩展机制。核心文件：

- `src/opensquilla/skills/loader.py`
- `src/opensquilla/skills/types.py`
- `src/opensquilla/skills/filter.py`
- `src/opensquilla/skills/injector.py`
- `src/opensquilla/engine/steps/skills_filter.py`

SkillLoader 读取 `SKILL.md`，解析 YAML frontmatter 和正文。它支持多层目录，优先级从低到高是：

```text
extra -> bundled -> managed -> personal -> project -> workspace
```

SkillSpec 中包含：

- name、description、triggers；
- always；
- requires tools；
- OS/env/bin/config 要求；
- install spec；
- provenance；
- user_invocable；
- risk/capability 元数据；
- meta skill 的 composition、output contract、eval prompts、preference keys 等。

技能筛选是确定性的，支持：

- always skill；
- 显式请求；
- trigger 命中；
- lexical/semantic/hybrid relevance；
- 工具可用性 gating；
- coding mode / meta mode gating；
- 注入 system prompt、user context 或 user message。

Meta-Skills 在 `src/opensquilla/skills/meta`，它们把重复多步骤工作流表达成可审计、可复用、可回放的 DAG/计划。相关能力包括：

- `/meta` 手动启动；
- clarify/input schema；
- step events；
- progress throttle；
- run reports；
- SOP compiler；
- auto-propose cron；
- meta skill creator。

这让 OpenSquilla 不只是“每次靠模型自由发挥”，而是可以把成熟流程固化成可治理的工作流。

## 11. 渠道与消息系统

渠道系统在 `src/opensquilla/channels`，支持：

- Slack；
- Discord；
- Telegram；
- Feishu/Lark；
- DingTalk；
- WeCom；
- QQ；
- Matrix；
- Microsoft Teams；
- terminal；
- websocket。

`ChannelManager` 从配置构建 adapter，负责：

- 注册启用的 channel；
- 收集 webhook routes；
- 启动/停止 adapter；
- 分发入站消息；
- retry/restart；
- 每个 channel 的 in-flight cap；
- 把 Feishu 等平台工具注册到工具层。

`gateway/channel_dispatch.py` 把渠道事件接入统一 turn 链路：

- sender allowlist / mention 过滤；
- owner/admin 识别；
- typing keepalive；
- TaskRuntime enqueue/start_turn；
- streaming 或 batch 回复；
- artifact delivery；
- approval prompt/card；
- queue full 处理；
- 输出内容清理，避免内部 compaction marker 或 directive 泄漏给用户。

## 12. 定时任务与 Heartbeat

调度系统在 `src/opensquilla/scheduler`。核心是 `SchedulerEngine`，它是一个 facade，内部委托给：

- SchedulerOps：CRUD、校验、job 规范化；
- SchedulerTimer：tick loop、并发、catchup；
- SessionReaper：过期 session 清理；
- JobStore：持久化。

调度任务支持：

- cron；
- every；
- at；
- 手动 run now；
- pause/resume/delete；
- execution 记录；
- max retries；
- timeout；
- jitter；
- delivery 配置；
- tool policy。

payload contract 区分：

- `agent_turn`；
- `reminder`；
- `system_event`。

handler 层会构建 cron RouteEnvelope 和 ToolContext，使定时任务也走统一 TurnRunner。DeliveryChain 可把结果送回 session、channel、webhook 或 WebSocket topic。

Heartbeat 相关文件包括 `heartbeat.py`、`heartbeat_loop.py`、`heartbeat_service.py`，用于周期性系统事件、主会话更新和渠道投递。

## 13. Web UI 与桌面端

Web UI 入口：

- `opensquilla-webui/src/main.ts`
- `opensquilla-webui/src/router/index.ts`
- `opensquilla-webui/src/stores/rpc.ts`
- `opensquilla-webui/src/lib/rpc.ts`

主要视图包括：

- Chat；
- Sessions；
- Approvals；
- Agents；
- Channels；
- Cron；
- Skills；
- Overview；
- Usage；
- Logs；
- Changelog；
- Settings。

Web UI 使用 WebSocket RPC，协议层支持：

- connect.challenge/connect 握手；
- token；
- event seq gap detection；
- ping；
- tick-watch timeout；
- 指数退避重连；
- URL token 注入。

Chat 视图是最复杂的前端表面，覆盖：

- 拖拽附件；
- artifact/deliverable；
- tool group；
- meta run 历史；
- sandbox resume；
- clarify；
- fork/regenerate/edit；
- usage/context warning；
- agent 切换。

Electron 桌面端在 `desktop/electron`。`src/main.ts` 显示它负责：

- BrowserWindow 生命周期；
- Gateway 子进程启动和健康检查；
- 首启 onboarding；
- provider/search/router 设置；
- safeStorage 或 plain secret backend；
- 日志；
- single instance lock；
- macOS 安装位置/签名诊断；
- 自动更新。

桌面端的 `scripts/gateway-entry.py` 直接调用 `opensquilla.cli.main:app`，说明桌面包本质上是把 Python CLI/Gateway runtime 打进应用，再由 Electron 管理它。

## 14. 搜索、抓取与内容抽取

搜索抽象在 `src/opensquilla/search`，运行时支持：

- DuckDuckGo：无 key 默认路径；
- Bocha；
- Brave Search；
- Tavily；
- Exa。

`web_search` 和 `web_discover` 是内置工具。自动搜索时会根据 provider 可用性、查询类型、缺 key 错误、fallback policy 选择候选 provider。`web_fetch` 优先使用本地 readability/html 抽取路径，必要时再升级到外部抓取能力。

安全上，URL 工具会通过 SSRF guard，默认阻断 private、loopback、link-local、reserved 地址。`198.18.0.0/15` fake-IP 代理段需要显式配置，且不能绕过其他内部地址阻断。

## 15. 配置、状态目录与密钥

配置加载顺序在 `docs/configuration.md` 中定义：

1. `OPENSQUILLA_GATEWAY_CONFIG_PATH`
2. `./opensquilla.toml`
3. `~/.opensquilla/config.toml`
4. 内置默认值

日常推荐通过 CLI 或 Web UI 配置，不直接手写 TOML。密钥推荐用环境变量引用，例如 `OPENROUTER_API_KEY`、`OPENAI_API_KEY`、`TAVILY_API_KEY`，避免把原始 key 写入配置、shell history 或 issue。

Gateway bind 优先级：

1. `--listen`
2. `--bind`
3. `OPENSQUILLA_LISTEN`
4. `OPENSQUILLA_GATEWAY_HOST`
5. config host
6. `127.0.0.1`

容器中 `OPENSQUILLA_STATE_DIR=/var/lib/opensquilla`，用于持久化配置、状态、日志和 workspace。普通本地安装默认在用户 home 下的 OpenSquilla 状态目录。

## 16. 部署与发布

### 源码和 wheel

Quickstart 推荐：

```sh
uv tool install --python 3.12 "opensquilla[recommended] @ <release-wheel-url>"
opensquilla onboard
opensquilla gateway run
```

源码开发：

```sh
git lfs pull --include="src/opensquilla/squilla_router/models/**"
uv sync --extra recommended --extra dev
uv run opensquilla gateway run
```

Git LFS 是关键点：Dockerfile 会检查 SquillaRouter v4 模型资产是否是完整文件。如果还是 LFS pointer，构建会失败。

### Docker

`Dockerfile` 使用 `python:3.13-slim-bookworm`，安装 recommended extras，创建非 root 用户 `opensquilla`，暴露 18791，并以：

```text
ENTRYPOINT ["opensquilla"]
CMD ["gateway", "run"]
```

启动。

安全默认：

- 容器内 bind `0.0.0.0` 是为了 Docker port publishing；
- host 侧默认应使用 `127.0.0.1:18791:18791`；
- `compose.yaml` 也采用 loopback 发布；
- 状态通过 named volume `opensquilla-state:/var/lib/opensquilla` 持久化；
- healthcheck 调 `/healthz`。

### 桌面安装包

`desktop/electron/package.json` 通过 electron-builder 生成 macOS DMG 和 Windows NSIS。发布流程会打包 gateway runtime，并有 gateway smoke 验证。

## 17. 测试与 CI

测试目录覆盖面很广：

- unit；
- functional；
- integration；
- live；
- gateway；
- engine；
- provider；
- memory；
- session；
- tools；
- sandbox；
- security；
- channels；
- mcp；
- desktop；
- migration；
- scheduler；
- webui browser；
- packaging。

`pyproject.toml` 中定义了 pytest marker，例如：

- `llm`；
- `live_search`；
- `live_channel`；
- `webui_browser`；
- `tui_real_terminal`；
- `local_golden`；
- `agent_context_boundary`；
- `llm_router_acc`。

主 CI `.github/workflows/ci.yml` 包含：

- changed files 分类；
- GitHub Actions workflow lint；
- Web UI build/typecheck；
- OpenTUI package tests；
- Electron unit/build tests；
- Ubuntu ruff、mypy、pytest、wheel build；
- Windows compatibility smoke；
- 条件性 Windows full tests；
- release packaging contracts；
- README locale parity；
- 汇总 gate。

额外 workflow 包括：

- live release E2E：Gateway LLM、Web UI browser chat、可选 Telegram；
- live search E2E：search provider 和 agent 搜索；
- Web UI real browser smoke；
- release assets：Python wheel、macOS Electron installer、Windows Electron installer、checksums、GitHub Release；
- model snapshot 刷新；
- PR body/target branch 检查。

这说明项目维护策略偏工程化：普通 PR 尽量跑本地可重复的质量门，live/secret-heavy 测试拆成单独 workflow。

## 18. 项目优势

1. 统一 turn 路径清晰
   Web、CLI、Channel、Cron 最终都尽量进入 RouteEnvelope、TaskRuntime、TurnRunner、Agent 这条路径，减少多入口行为漂移。

2. 扩展点完整
   Provider、Tool、MCP、Skill、Channel、Search、Scheduler、Web UI view 都有相对明确的扩展位置。

3. 安全默认比较认真
   loopback gateway、auth/CORS/rate/security middleware、tool policy、sandbox、SSRF guard、workspace lockdown、approval flow 都在设计内。

4. 持久化能力强
   会话、转录、FTS、summary、context state、cost、router decision、memory、cron execution 都有持久化或迁移支撑。

5. 产品面很完整
   CLI、Web、桌面、渠道、Cron、技能、记忆、审批、用量、日志都已经进入同一个产品体系。

## 19. 主要复杂度与风险点

1. Agent 和 Gateway boot 很大
   `engine/agent.py` 与 `gateway/boot.py` 承载大量行为。后续改动要优先读测试和周边 stage，避免局部修改破坏跨入口行为。

2. 多表面一致性成本高
   同一能力可能同时影响 Web、CLI、渠道、Cron、桌面端。变更时要确认 RouteEnvelope、ToolContext、TaskRuntime 和最终回复链路是否一致。

3. Provider 兼容矩阵大
   不同供应商的 tool calling、reasoning、usage、cache token、stream delta 格式差异很大。Provider 层改动需要有针对性测试。

4. Router 依赖模型资产
   SquillaRouter 的本地模型资产通过 Git LFS 管理。构建、Docker、发布和新环境安装都要确保 LFS 文件完整。

5. 沙箱跨平台差异
   Linux/macOS/Windows 沙箱能力不同，某些测试和行为需要区分平台。

6. live 能力依赖 secrets
   搜索、渠道、真实 LLM E2E 不适合放进普通 CI，需要维护单独的 live workflow 和密钥配置。

## 20. 建议阅读路线

如果要快速理解项目，推荐按这个顺序读：

1. `README.md`、`docs/quickstart.md`、`docs/features.md`
   先建立产品和用户表面的全局概念。

2. `pyproject.toml`、`src/opensquilla/cli/main.py`
   看包入口、依赖、CLI 命令边界。

3. `src/opensquilla/gateway/boot.py`、`src/opensquilla/gateway/app.py`
   理解服务如何装配，HTTP/RPC surface 如何暴露。

4. `src/opensquilla/gateway/routing.py`、`src/opensquilla/gateway/task_runtime.py`
   理解多入口如何统一，以及并发/队列策略。

5. `src/opensquilla/engine/runtime.py`、`src/opensquilla/engine/agent.py`
   深入一次 turn 的生命周期。

6. `src/opensquilla/provider/registry.py`、`src/opensquilla/provider/selector.py`
   理解模型供应商和 fallback。

7. `src/opensquilla/tools/registry.py`、`src/opensquilla/tools/dispatch.py`、`src/opensquilla/tools/builtin`
   理解工具声明、权限策略和执行链。

8. `src/opensquilla/session/storage.py`、`src/opensquilla/memory/manager.py`
   理解长期状态与记忆。

9. `src/opensquilla/skills/loader.py`、`src/opensquilla/skills/meta/orchestrator.py`
   理解 Skills 和 Meta-Skills。

10. `opensquilla-webui/src`、`desktop/electron/src/main.ts`
    理解 Web 和桌面端如何消费 Gateway。

## 21. 适合切入贡献的方向

对新贡献者来说，比较稳的切入点：

- 文档补充：配置、部署、Provider 示例、渠道排障；
- Web UI 小交互：单个 view 或 component 的显示/状态修复；
- Provider 兼容性：新增或修复某个供应商的 payload/stream/usage；
- 工具增强：新增小型内置工具或改善工具结果压缩；
- 测试补强：为已有 bug 增加 unit/functional regression；
- 搜索 provider 或 web_fetch 抽取质量；
- 技能包：新增 `SKILL.md` 或 Meta-Skill 流程模板。

高风险切入点：

- `engine/agent.py` 状态机；
- `gateway/boot.py` 服务装配；
- Session schema/migration；
- Tool policy/sandbox；
- SquillaRouter 训练资产或路由决策；
- Channel dispatch 的 streaming/approval/artifact 逻辑。

这些区域不是不能改，而是改动前需要先定位对应测试，并考虑 Web/CLI/Channel/Cron 的共同影响。

## 22. 总结

OpenSquilla 的核心价值在于把“个人 Agent”做成一个本地运行、可持久化、可扩展、可治理的系统。它的架构重心不是某个模型调用，而是围绕一次 turn 建立完整闭环：

- 输入来自多种表面；
- Gateway 统一编排；
- Router 决定模型层级；
- Skills 提供任务特定操作知识；
- Agent 状态机处理流式输出、工具、审批、压缩和 fallback；
- Session/Memory 保存长期上下文；
- Web/CLI/Channels/Cron/Desktop 共享同一运行时能力。

因此，深入这个项目时要把它当成“Agent runtime + control plane + tool/memory/channel ecosystem”，而不是单一聊天应用。
