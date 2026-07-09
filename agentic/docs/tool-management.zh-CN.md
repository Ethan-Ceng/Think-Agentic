# Agentic 工具管理现状

整理日期：2026-07-09

本文替代旧的工具管理落地计划。旧文档中的 Phase 1/2 已经部分落地，当前应按“实现现状 + 未完成项 + 下一步”维护。

## 1. 当前结论

工具管理已经进入运行时，不再只是 UI 展示。

已完成：

- 工具列表 API。
- 工具绑定配置保存。
- API 工具源注册、更新、删除、测试。
- 能力摘要。
- preflight 规则诊断。
- Settings Tools tab。
- `ToolFactory` 构建当前工具集合。
- `FilteredTool` 过滤 LLM 可见工具 schema，并拦截禁用工具调用。
- 自定义 API 工具通过注册配置进入运行时。

需要澄清的是：当前没有类似 `llmops` 的通用工具注册管理中心。内置 Shell、File、Browser、Search、Message、MCP、A2A 等工具仍由代码中的 built-in catalog 定义；UI/API 管理的是这些内置工具的启停、风险等级和运行时策略。所谓“注册”主要指用户级自定义 API 工具源配置。

未完成：

- 高风险工具确认流。
- `approval=ask/deny` 策略字段。
- 工具调用审计表。
- 配置变更审计。
- MCP 动态工具 tool 级缓存和细粒度治理。
- Planner 基于 capability summary 自动改计划。

## 2. 当前架构

```text
Settings Tools tab
        |
        v
/api/tools
        |
        v
ToolConfigService
        |
        v
UserConfigService -> configs(config_type = "tool")
        |
        v
ToolRegistry + ToolCapabilityService + ToolPreflightService
        |
        v
ToolFactory
        |
        v
FilteredTool
        |
        v
PlannerReActFlow / ReActAgent
```

这个结构的优点是薄封装：不重写 File、Shell、Browser、Search、MCP、A2A 等工具实现，只在装配和调用边界做治理。

## 3. ToolConfig

当前结构：

```text
ToolConfig
  schema_version = "tool_config_v1"
  mode = "default_allow"
  bindings: dict[tool_id, ToolBinding]
  registrations: dict[registration_id, ToolRegistration]
  runtime_policy: RuntimeToolPolicy
```

`registrations` 当前不是独立数据库工具注册表，而是用户级 `configs(config_type = "tool")` 里的 JSONB 字段。它主要承载自定义 API 工具源；内置工具仍来自代码 catalog。

`ToolBinding` 当前字段：

```text
enabled
risk_level
params
```

`RuntimeToolPolicy` 当前字段：

```text
allowed_executor_types
max_tool_iterations
```

注意：旧方案里提到的 `approval`、`approval_mode` 当前没有在代码里落地。不要在新规划里把确认审批当成已有能力。

## 4. 工具 ID

当前治理应继续使用稳定 `tool_id`，而不是只依赖 LLM function name。

推荐规则：

```text
builtin.file.read_file
builtin.file.write_file
builtin.shell.shell_execute
builtin.browser.browser_console_exec
builtin.search.search_web
builtin.message.message_ask_user
mcp.<server_name>.<tool_name>
a2a.<agent_id>.call_remote_agent
api.<provider_id>.<tool_name>
```

对 LLM 暴露的 function name 可以继续保持现状，避免破坏工具调用格式。

## 5. API

当前工具 API：

```text
GET  /api/tools
POST /api/tools/bindings
GET  /api/tools/registrations
POST /api/tools/registrations
POST /api/tools/registrations/{registration_id}
POST /api/tools/registrations/{registration_id}/delete
POST /api/tools/registrations/{registration_id}/test
GET  /api/tools/capability-summary
POST /api/tools/capability-summary/refresh
POST /api/tools/preflight
POST /api/tools/reset-defaults
```

所有接口都依赖当前用户，工具配置保存在用户级 `configs` 表中。

## 6. 运行时过滤

运行时关键点：

- `PlannerReActFlow` 不再直接硬编码裸工具列表，而是通过 `ToolFactory(tool_config).build(...)` 构建。
- `ToolFactory` 仍装配内置工具、MCP、A2A、API 工具。
- 每个工具包外层包一层 `FilteredTool`。
- `FilteredTool.get_tools()` 只返回启用工具的 schema，模型看不到禁用工具。
- `FilteredTool.invoke()` 会阻止禁用工具调用，返回失败结果。

这已经覆盖“禁用工具后不应被模型看到”和“运行时不能绕过禁用配置”两个关键点。

## 7. 能力摘要

能力摘要由 `ToolCapabilityService` 从有效工具生成。

当前摘要包含：

- executor types。
- input/output modalities。
- semantic tags。
- tool names。
- constraints。
- generated_at。

当前 semantic tags 包括：

```text
file
file_read
file_write
shell
browser
browser_script
search
realtime
user_interaction
remote_agent
```

能力摘要目前主要服务 UI 和 preflight。后续可以注入 Planner prompt，让计划阶段知道当前工具边界。

## 8. Preflight

当前 preflight 是规则判断，不调用 LLM。

规则覆盖：

| rule_id | 检测能力 |
| --- | --- |
| `shell_required` | 命令、安装、脚本、pytest、docker 等。 |
| `browser_required` | 网页、点击、登录、浏览器、截图、控制台等。 |
| `search_required` | 最新、今天、新闻、实时、搜索、价格、天气等。 |
| `file_write_required` | 修改、写入、生成文件、替换、改代码等。 |
| `remote_agent_required` | A2A、远程 Agent、分派任务等。 |

返回状态：

```text
pass
warning
blocked
```

当前 preflight 是能力诊断，不等于完整安全审批。

## 9. 自定义 API 工具

当前已经有 API 工具源注册能力，并且 `APITool` 会从 `ToolConfig.registrations` 构建 API 工具定义。

仍需注意：

- 这不是 `llmops` 式 provider/tool 两级数据库注册管理。
- 不应在配置中保存明文密钥。
- 注册配置应继续支持脱敏。
- 需要进一步补请求审计、网络范围限制和错误可观测性。
- 自定义 API 工具属于高风险能力，后续应接入确认和审计。

## 10. 下一步

建议按这个顺序继续：

1. 补 Run / Trace 审计策略。
   最小账本和前端查看入口已经落地；下一步配置输入输出保存策略、脱敏策略和保留策略。
2. 补高风险工具确认策略。
   增加明确的策略字段，例如 `approval = none | ask | deny`，并在执行前生效。
3. 扩展工具调用审计策略。
   在最小 `tool_calls` 记录之上，补充更细的脱敏策略、完整输入输出保存开关、失败分类和导出能力。
4. 补配置变更审计。
   工具启停、自定义 API 工具源注册、密钥引用变化都应留痕。
5. 做 MCP tool 级发现缓存。
   当前可以先 provider 级治理，后续再支持 server -> tools 的细粒度启停。
6. 让 Planner 使用 capability summary。
   规划时知道工具边界，减少计划和实际执行能力不一致。

## 11. 风险

- UI 工具开关不是完整安全边界，真正安全还需要认证、授权、审计、确认和沙箱共同工作。
- Shell、文件写入、浏览器控制台、自定义 API、A2A 调用都应视为高风险。
- 默认兼容旧行为是合理的，但发布到外部入口前必须收紧高风险工具策略。
