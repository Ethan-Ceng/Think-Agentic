# Agentic 工具管理调研与落地方案

> 归档说明：本文是历史落地方案，部分内容已经实现或过期。当前工具管理说明见 `../tool-management.zh-CN.md`。

生成时间：2026-06-08

## 目标

在不破坏 `agentic` 现有架构的前提下，借鉴 `llmops` 的工具注册、工具绑定、权限策略、UI 管理、能力摘要和 preflight，让工具可以在 UI 上管理，并逐步进入运行时治理。

这里的“不破坏现有架构”指：

- 保留现有 `BaseTool`、`@tool`、`PlannerReActFlow`、`ReActAgent`、`PlannerAgent` 的主体调用方式。
- 保留现有内置工具实现：文件、Shell、浏览器、搜索、消息、MCP、A2A。
- 保留当前 `config.yaml` 配置仓库作为第一阶段持久化入口，后续再评估是否迁移到数据库。
- 默认行为兼容旧版本：如果没有 `tool_config`，按现状启用所有当前工具，避免现有任务突然缺能力。

## 当前 agentic 工具现状

### 运行时链路

`agentic` 已经有工具能力，不是完全依赖 MCP。

关键位置：

- `agentic/api/app/core/tools/base.py`：通过 `@tool(...)` 给方法挂载 OpenAI function schema，`BaseTool.get_tools()` 反射收集 schema，`BaseTool.invoke()` 根据工具名调用方法。
- `agentic/api/app/core/flows/planner_react.py`：在 `PlannerReActFlow.__init__` 中硬编码装配工具列表：`FileTool`、`ShellTool`、`BrowserTool`、`SearchTool`、`MessageTool`、`MCPTool`、`A2ATool`。
- `agentic/api/app/core/agent/base.py`：`_get_available_tools()` 把所有工具 schema 提供给 LLM；`_invoke_tool()` 执行工具调用。
- `agentic/api/app/core/agent/planner.py`：Planner 默认 `_tool_choice = "none"`，主要做规划。
- `agentic/api/app/core/agent/react.py`：ReAct 负责执行，真正消费工具调用。
- `agentic/api/app/core/agent/agent_task_runner.py`：负责初始化 MCP/A2A、消费 Flow 事件并转换工具内容事件。

当前工具函数包括：

- 文件：`read_file`、`write_file`、`replace_in_file`、`search_in_file`、`find_files`
- Shell：`shell_execute`、`shell_read_output`、`shell_wait_process`、`shell_write_input`、`shell_kill_process`
- 浏览器：`browser_view`、`browser_navigate`、`browser_click`、`browser_input`、`browser_console_exec` 等
- 搜索：`search_web`
- 用户消息：`message_notify_user`、`message_ask_user`
- A2A：`get_remote_agent_cards`、`call_remote_agent`
- MCP：运行时从 MCP server 动态加载工具 schema

### 配置与 UI

关键位置：

- `agentic/api/app/core/config.py`：默认 `app_config_filepath = "config.yaml"`。
- `agentic/api/app/repositories/file_app_config_repository.py`：读取/写入 YAML 配置。
- `agentic/api/app/services/app_config_service.py`：管理 LLM、Agent、MCP、A2A 配置。
- `agentic/api/app/schemas/app_config.py` 和 `agentic/api/app/core/entities/app_config.py`：当前 `AppConfig` 只有 `llm_config`、`agent_config`、`mcp_config`、`a2a_config`，没有工具配置。
- `agentic/web/src/components/SettingsModal.vue`：当前设置页只有 `common`、`llm`、`a2a`、`mcp` 四个 tab。
- `agentic/web/src/lib/api/config.ts`：前端已有配置 API 封装，但没有 tools API。

现状判断：

- 工具运行能力强，尤其是沙箱、Shell、浏览器、文件操作。
- 工具管理能力弱，主要是代码硬编码，UI 只能管理 MCP/A2A provider，不能管理具体工具函数。
- 没有工具注册表、工具绑定、风险等级、审批策略、能力摘要、preflight。
- 没有认证系统，因此第一阶段的“权限”只能是运行时策略权限，不是真正用户/RBAC 权限。

## llmops 可借鉴点

### 1. 工具注册

`llmops` 把工具拆成 provider 和 tool entity：

- 内置工具：`llmops/api/app/api/routers/builtin_tool.py`
- 内置工具服务：`llmops/api/app/services/builtin_tool_service.py`
- 内置工具 runtime：`llmops/api/app/core/tools/builtin_tools/runtime.py`
- 自定义 API 工具：`llmops/api/app/api/routers/api_tool.py`
- 自定义 API 工具服务：`llmops/api/app/services/api_tool_service.py`
- OpenAPI 工具模型：`llmops/api/app/models/api_tool.py`
- API 工具 runtime：`llmops/api/app/core/tools/api_tools/providers/api_provider_manager.py`

可借鉴：

- 工具需要稳定 ID，不要只依赖 LLM function name。
- 工具需要 metadata：provider、名称、描述、参数、类别、图标、是否需要凭证。
- 内置工具和自定义 API 工具可以使用同一种绑定结构。

不建议直接照搬：

- `llmops` 的工具更偏平台插件和普通 HTTP API；`agentic` 的核心价值是沙箱、浏览器、Shell 等执行型工具。
- `agentic` 第一阶段不宜引入完整 OpenAPI 工具数据库，否则改动过大。

### 2. 工具绑定

`llmops` 的 App/Worker 会保存已绑定工具，运行时只给 Agent 注入绑定过的工具。

关键位置：

- `llmops/api/app/models/app.py`：App/AppVersion 保存 `tools` JSONB。
- `llmops/api/app/services/app_service.py`：校验工具、组装 runtime capability、执行配置过的工具。
- `llmops/ui/src/views/space/apps/components/abilities/ToolsAbilityItem.vue`：UI 中选择、删除、配置工具。

可借鉴：

- 工具管理不应该只展示工具列表，还要保存“当前 Agent/应用启用了哪些工具”。
- 绑定结构应包含：类型、provider、tool、参数、启用状态。
- UI 中应能查看工具详情、参数、风险和启用状态。

### 3. 运行时策略与权限

`llmops` 有 runtime policy，例如 `allowed_executor_types`、是否允许 builtin/api/workflow 等。

关键位置：

- `llmops/api/app/services/app_service.py`
- `llmops/api/app/domain/agent_runtime/react_worker_agent.py`
- `llmops/api/tests/test_worker_runtime.py`

可借鉴：

- 权限可以先从“运行时策略”做起：允许哪些 executor 类型、哪些工具、哪些高危工具需要确认。
- 策略要在执行前生效，不能只靠 UI 提醒。

对 `agentic` 的约束：

- 当前无登录/用户/租户边界，所以暂不做用户级 RBAC。
- 第一版权限定义为系统级工具策略：
  - `enabled`: 是否启用
  - `risk_level`: `low | medium | high`
  - `approval`: `none | ask | deny`
  - `allowed_executor_types`: `builtin | mcp | a2a | api`

### 4. 能力摘要

`llmops` 会从模型、工具绑定、能力绑定生成 `capability_summary`。

关键位置：

- `llmops/api/app/services/agent_capability_service.py`
- `llmops/ui/src/views/space/apps/components/CapabilitySummaryPanel.vue`
- `llmops/api/tests/test_agent_capability_service.py`

可借鉴字段：

- `tool_names`
- `semantic_tags`
- `input_modalities`
- `output_modalities`
- `model_features`
- `constraints`
- `generated_at`

对 `agentic` 的意义：

- 给 UI 一个清晰的“当前 Agent 能做什么”视图。
- 给 Planner/ReAct prompt 一个能力边界摘要。
- 给 preflight 提供判断依据。

### 5. Preflight

`llmops` 在任务执行前做能力校验，例如图片输入需要 vision worker、最新信息需要 search。

关键位置：

- `llmops/api/app/domain/agent_runtime/router_runtime.py`
- `llmops/api/app/api/routers/app.py` 中 `/{app_id}/planner/preflight`
- `llmops/ui/src/views/space/apps/components/PlannerAgentAbility.vue`
- `llmops/api/tests/test_router_agent_manager_service.py`

可借鉴：

- preflight 不必一开始就很聪明，可以先做规则校验。
- 输出要结构化：`status`、`checks`、`passed`、`error_code`、`user_message`、`capability_snapshot`。
- preflight 结果可以写入事件流或计划上下文，方便追踪为什么任务被阻断。

## 推荐目标架构

### 总体思路

不要重写工具系统，增加一个薄的管理层：

```text
UI Settings Tools Tab
        |
        v
Tools API / AppConfigService
        |
        v
ToolConfig in config.yaml
        |
        v
ToolRegistry + CapabilityService + PreflightService
        |
        v
ToolFactory builds current BaseTool list
        |
        v
FilteredTool wrapper
        |
        v
Existing PlannerReActFlow / ReActAgent / BaseTool.invoke
```

核心变化：

- 新增 `ToolRegistry`：收集工具元数据，不改变工具实现。
- 新增 `ToolConfig`：保存 UI 上的工具启停、审批策略和运行时策略。
- 新增 `FilteredTool`：包装现有 `BaseTool`，只暴露被启用的 function schema，调用未启用工具时返回失败。
- 新增 `CapabilityService`：根据启用工具生成能力摘要。
- 新增 `PreflightService`：根据用户请求和能力摘要做运行前检查。
- `PlannerReActFlow` 只把硬编码工具列表改为 `ToolFactory.build(...)`，下游 Agent 不感知变化。

### 工具 ID 规范

建议使用稳定 ID，避免和 LLM function name 混淆：

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

说明：

- 对 LLM 暴露的 function name 保持现状，例如 `shell_execute`，避免 prompt 和工具调用格式破坏。
- UI、配置、权限、审计使用稳定 `tool_id`。
- MCP 动态工具可以先 provider 级管理，后续再做 tool 级发现与缓存。

## 后端落地设计

### 新增数据结构

建议在 `agentic/api/app/schemas/app_config.py` 和 `agentic/api/app/core/entities/app_config.py` 中增加：

```python
class ToolBinding(BaseModel):
    enabled: bool = True
    approval: str = "none"  # none | ask | deny
    risk_level: str = "low"  # low | medium | high
    params: dict[str, Any] = Field(default_factory=dict)


class RuntimeToolPolicy(BaseModel):
    allowed_executor_types: list[str] = Field(default_factory=lambda: ["builtin", "mcp", "a2a"])
    max_tool_iterations: int = 100
    approval_mode: str = "warn_only"  # warn_only | enforce


class ToolConfig(BaseModel):
    schema_version: str = "tool_config_v1"
    mode: str = "allowlist"
    bindings: dict[str, ToolBinding] = Field(default_factory=dict)
    runtime_policy: RuntimeToolPolicy = Field(default_factory=RuntimeToolPolicy)
```

再在 `AppConfig` 增加：

```python
tool_config: ToolConfig = Field(default_factory=ToolConfig)
```

兼容性：

- 当前 `AppConfig` 已有 `ConfigDict(extra="allow")`，旧 YAML 不会因为新增字段失败。
- 如果旧配置没有 `tool_config`，服务端默认生成配置，并按“全部当前内置工具启用”解释。

### 推荐文件

新增：

- `agentic/api/app/core/tools/registry.py`
- `agentic/api/app/core/tools/filter.py`
- `agentic/api/app/core/tools/factory.py`
- `agentic/api/app/services/tool_config_service.py`
- `agentic/api/app/services/tool_capability_service.py`
- `agentic/api/app/services/tool_preflight_service.py`
- `agentic/api/app/controllers/tools.py`
- `agentic/api/app/schemas/tool_config.py`

修改：

- `agentic/api/app/core/entities/app_config.py`
- `agentic/api/app/schemas/app_config.py`
- `agentic/api/app/services/app_config_service.py`
- `agentic/api/app/controllers/__init__.py`
- `agentic/api/app/core/flows/planner_react.py`
- 后续如果需要审批，再修改 `agentic/api/app/core/agent/base.py`

### ToolRegistry

职责：

- 从现有工具实例反射 `get_tools()` schema。
- 给每个 function 补充 provider、group、category、risk、executor type。
- 输出 UI 可展示的 descriptor。

描述符建议：

```python
class ToolDescriptor(BaseModel):
    tool_id: str
    function_name: str
    provider_id: str
    provider_label: str
    group: str
    executor_type: str
    label: str
    description: str
    schema: dict[str, Any]
    category: str
    risk_level: str
    requires_sandbox: bool = False
    requires_browser: bool = False
    requires_credentials: bool = False
    enabled_by_default: bool = True
```

风险建议：

- `low`：`read_file`、`search_in_file`、`find_files`、`browser_view`、`search_web`、`message_notify_user`
- `medium`：`browser_navigate`、`browser_click`、`browser_input`、`message_ask_user`、`call_remote_agent`
- `high`：`write_file`、`replace_in_file`、`shell_execute`、`shell_write_input`、`shell_kill_process`、`browser_console_exec`、MCP/A2A 未知远程动作

### FilteredTool

`FilteredTool` 是非破坏式执行过滤的关键。

```python
class FilteredTool(BaseTool):
    def __init__(self, inner: BaseTool, allowed_names: set[str]):
        self.inner = inner
        self.allowed_names = allowed_names

    def get_tools(self):
        return [
            schema for schema in self.inner.get_tools()
            if schema["function"]["name"] in self.allowed_names
        ]

    def has_tool(self, tool_name: str) -> bool:
        return tool_name in self.allowed_names and self.inner.has_tool(tool_name)

    async def invoke(self, tool_name: str, **kwargs):
        if tool_name not in self.allowed_names:
            return ToolResult(success=False, message=f"Tool disabled: {tool_name}")
        return await self.inner.invoke(tool_name, **kwargs)
```

收益：

- 不需要改 `FileTool`、`ShellTool`、`BrowserTool` 等实现。
- 不需要改 `BaseAgent._get_available_tools()` 的主体逻辑。
- UI 配置可以影响 LLM 可见工具，也可以防止运行时绕过。

### ToolFactory

`PlannerReActFlow` 当前直接写：

```python
tools = [
    FileTool(...),
    ShellTool(...),
    BrowserTool(...),
    SearchTool(...),
    MessageTool(),
    mcp_tool,
    a2a_tool,
]
```

建议改成：

```python
tools = ToolFactory(
    tool_config=tool_config,
).build(
    sandbox=sandbox,
    browser=browser,
    search_engine=search_engine,
    mcp_tool=mcp_tool,
    a2a_tool=a2a_tool,
)
```

`ToolFactory` 内部仍然创建同一批工具，只是在返回前根据 `ToolConfig` 包装成 `FilteredTool`。

### API 设计

第一阶段建议挂在 `/api/tools`，不混入现有 `/api/app-config` 太多逻辑：

```text
GET  /api/tools
POST /api/tools/bindings
GET  /api/tools/capability-summary
POST /api/tools/capability-summary/refresh
POST /api/tools/preflight
POST /api/tools/reset-defaults
```

`GET /api/tools` 返回：

```json
{
  "tools": [
    {
      "tool_id": "builtin.shell.shell_execute",
      "function_name": "shell_execute",
      "provider_label": "Shell",
      "group": "shell",
      "executor_type": "builtin",
      "label": "执行 Shell 命令",
      "description": "...",
      "risk_level": "high",
      "enabled": true,
      "approval": "ask",
      "requires_sandbox": true
    }
  ],
  "runtime_policy": {
    "allowed_executor_types": ["builtin", "mcp", "a2a"],
    "approval_mode": "warn_only",
    "max_tool_iterations": 100
  }
}
```

`POST /api/tools/bindings` body：

```json
{
  "bindings": {
    "builtin.shell.shell_execute": {
      "enabled": true,
      "approval": "ask",
      "risk_level": "high",
      "params": {}
    }
  },
  "runtime_policy": {
    "allowed_executor_types": ["builtin", "mcp", "a2a"],
    "approval_mode": "warn_only",
    "max_tool_iterations": 100
  }
}
```

`POST /api/tools/preflight` body：

```json
{
  "message": "帮我安装依赖并运行测试",
  "input_modalities": ["text/plain"]
}
```

返回：

```json
{
  "status": "blocked",
  "checks": [
    {
      "rule_id": "shell_required",
      "passed": false,
      "error_code": "capability_missing:shell",
      "user_message": "当前 Shell 工具未启用，无法执行命令或安装依赖。"
    }
  ],
  "capability_snapshot": {
    "tool_names": ["read_file", "search_web"],
    "semantic_tags": ["file_read", "search"]
  }
}
```

### Capability Summary

建议字段：

```json
{
  "schema_version": "tool_capability_v1",
  "executor_types": ["builtin", "mcp", "a2a"],
  "input_modalities": ["text/plain"],
  "output_modalities": ["text/plain"],
  "semantic_tags": ["file_read", "file_write", "shell", "browser", "search", "user_interaction"],
  "tool_names": ["read_file", "write_file", "shell_execute", "search_web"],
  "constraints": {
    "requires_sandbox": true,
    "requires_browser": true,
    "requires_credentials": true,
    "requires_approval": true,
    "high_risk_tool_count": 4
  },
  "generated_at": 1780920000
}
```

生成规则：

- 从 `ToolRegistry` + `ToolConfig` 生成。
- 只统计 enabled 工具。
- MCP/A2A 初期可按 provider 级别生成摘要，动态工具发现后再补 tool 级别。
- 能力摘要可以展示在 UI，也可以在后续注入 Planner prompt。

### Preflight 规则

第一阶段使用规则判断，不调用 LLM。

建议规则：

- `shell_required`：用户输入包含“运行命令、安装、npm、pnpm、pip、pytest、docker、执行脚本”等，且 `shell_execute` 未启用时阻断。
- `browser_required`：用户输入包含“打开网页、点击、登录、浏览器、截图、控制台”等，且浏览器工具未启用时阻断。
- `search_required`：用户输入包含“最新、今天、新闻、实时、搜索、查一下、价格、天气”等，且 `search_web` 和可用搜索 MCP 都未启用时阻断或警告。
- `file_write_required`：用户输入包含“修改、写入、生成文件、保存到、替换”等，且写文件工具未启用时阻断。
- `remote_agent_required`：用户输入明确要求调用远程 Agent，但 A2A 未启用时阻断。
- `high_risk_requires_approval`：任务需要高危工具，但该工具 `approval=deny` 时阻断；`approval=ask` 时警告或进入确认流程。

第一阶段建议：

- `approval_mode = "warn_only"`：只显示 warning，不打断已有任务。
- 第二阶段改为 `enforce`：真正阻断不可用工具。

## 前端 UI 设计

### 入口

复用 `agentic/web/src/components/SettingsModal.vue`，新增 `tools` tab：

```ts
type SettingTab = 'common' | 'llm' | 'tools' | 'a2a' | 'mcp'
```

理由：

- 当前项目没有复杂空间/应用管理页，设置弹窗是最自然的全局配置入口。
- 避免新增路由和整体信息架构改造。

### 页面结构

`tools` tab 建议包含四块：

1. 能力摘要

- 已启用工具数
- 高危工具数
- 是否需要沙箱
- 是否需要浏览器
- 当前 executor types
- semantic tags

2. 工具列表

按 group 分组：

- 文件
- Shell
- 浏览器
- 搜索
- 用户消息
- MCP
- A2A

每行展示：

- 工具名称
- 描述
- 风险标签
- 启用开关
- 确认策略：无需确认 / 需要确认 / 禁用
- 详情按钮

3. 运行时策略

- 允许 executor types
- 审批模式：warn only / enforce
- 最大工具迭代次数

4. Preflight 测试

- 输入一段任务描述
- 点击“检测”
- 展示 blocked/warning/pass 和具体规则结果

### 前端新增文件

建议新增：

- `agentic/web/src/lib/api/tools.ts`
- `agentic/web/src/lib/api/tool-types.ts`
- `agentic/web/src/components/settings/ToolsSettingsPane.vue`
- `agentic/web/src/components/settings/CapabilitySummary.vue`
- `agentic/web/src/components/settings/ToolPreflightPanel.vue`

修改：

- `agentic/web/src/components/SettingsModal.vue`

### UI 交互原则

- 工具开关保存到 `tool_config.bindings`。
- 默认展示所有当前内置工具为 enabled。
- 高危工具默认展示醒目风险标签。
- MCP/A2A 第一阶段先管理 provider 启停，tool 级别发现后再扩展。
- 不在 UI 中直接保存密钥明文；需要凭证的工具显示“需要环境变量/服务端配置”。

## 分阶段落地计划

### Phase 0：方案文档

当前文档即 Phase 0。

产出：

- 梳理现状。
- 明确可借鉴点。
- 明确非破坏式落地方案。

### Phase 1：只读注册表 + UI 展示 + Preflight 诊断

目标：

- 不影响任何现有任务执行。
- UI 能看到工具清单、风险、能力摘要。
- preflight 先做诊断，不强制阻断。

后端：

- 新增 `ToolRegistry`。
- 新增 `GET /api/tools`。
- 新增 `GET /api/tools/capability-summary`。
- 新增 `POST /api/tools/preflight`。
- 生成默认 bindings，但不改执行链路。

前端：

- SettingsModal 新增 Tools tab。
- 展示工具列表、风险等级、能力摘要、preflight 结果。

测试：

- registry 能正确收集所有内置工具。
- 旧 config 没有 `tool_config` 时接口正常。
- preflight 对 shell/search/browser/file_write 场景返回预期结果。

### Phase 2：绑定配置持久化 + 执行过滤

目标：

- UI 开关真正影响 LLM 可见工具和运行时工具调用。
- 旧配置默认全部启用，不破坏现有行为。

后端：

- `AppConfig` 增加 `tool_config`。
- `AppConfigService` 增加读写工具配置方法。
- 新增 `FilteredTool`。
- 新增 `ToolFactory`。
- `PlannerReActFlow` 使用 `ToolFactory.build(...)`。
- `AgentService`/依赖注入把 `tool_config` 传入 Flow。

前端：

- 工具开关、approval 策略、runtime policy 可保存。

测试：

- 禁用 `search_web` 后，LLM tools schema 不包含 `search_web`。
- 调用被禁用工具时返回 `ToolResult(success=False)`。
- 无 `tool_config` 的旧配置仍包含全部工具。
- MCP/A2A 原有启停能力不回退。

### Phase 3：权限 enforcement + 用户确认

目标：

- 高危工具执行前可确认。
- `approval=deny` 的工具不能执行。
- preflight 可以真正阻断任务。

后端：

- 在 `BaseAgent._invoke_tool()` 或工具调用中间层加入 policy check。
- 高危工具 `approval=ask` 时复用 `MessageTool`/等待事件机制请求用户确认。
- 工具事件中增加 policy/preflight 信息，便于 UI 展示。

前端：

- 任务执行过程中展示确认弹窗或确认消息。
- preflight blocked 时提示缺失能力和推荐启用工具。

测试：

- `shell_execute` 设置 `deny` 时无法执行。
- `shell_execute` 设置 `ask` 时任务进入等待确认。
- 用户拒绝后任务安全失败并记录事件。

### Phase 4：自定义 API 工具

目标：

- 借鉴 `llmops` 的 OpenAPI 插件管理能力。
- 让用户在 UI 上传/填写 OpenAPI schema，生成可调用工具。

建议等 Phase 1-3 稳定后再做。

后端：

- 新建 `api_tool_provider`、`api_tool` 表，或先用 YAML 做轻量原型。
- 解析 OpenAPI JSON。
- 构造 API RuntimeTool。
- 凭证使用环境变量引用或加密存储，不在 YAML 明文保存。

前端：

- 新增“自定义 API 工具”管理页或 Tools tab 子面板。

注意：

- 这一步需要认真处理鉴权、密钥、网络访问范围、请求审计，不能只做“任意 URL 调用”。

### Phase 5：能力感知规划

目标：

- Planner 在规划时知道当前工具能力边界。
- preflight 失败可以提示用户打开工具，或者自动改计划。

后端：

- 把 capability summary 注入 Planner prompt。
- 对计划步骤做更细粒度 preflight。
- 根据 preflight 结果决定是否继续、改计划或询问用户。

## 风险与注意事项

### 1. UI 管理不是安全边界

在没有认证和权限系统前，UI 上的工具权限只是系统配置，不是用户级安全边界。

如果要做到真正权限，需要补：

- 登录认证
- 用户/角色/租户
- 配置变更审计
- 工具调用审计
- 高危操作确认

### 2. 密钥不能因为 UI 管理而回到 YAML 明文

工具管理 UI 不应该直接保存真实 API key。

建议：

- UI 只保存环境变量名或 secret reference。
- 服务端从环境变量、密钥管理系统或加密数据库读取。
- `config.yaml` 只保存非敏感绑定和策略。

### 3. MCP 动态工具需要分阶段处理

MCP 工具 schema 是运行时发现的。

第一阶段：

- 管理 MCP server/provider 启停。
- 能力摘要把 MCP 标记为 `mcp`、`remote_tool`、`requires_credentials`。

第二阶段：

- 增加 MCP 工具发现 API。
- 缓存 server -> tools 列表。
- 支持 tool 级启停。

### 4. Shell/文件/浏览器属于高危工具

这些工具本身就是 `agentic` 的核心能力，但也最需要策略治理。

建议默认：

- 旧配置兼容：全部 enabled。
- 新 UI 首次展示：高危工具标记 `ask`，但 `approval_mode=warn_only`。
- 当确认机制成熟后，再切到 `approval_mode=enforce`。

## 最小可行实现顺序

建议第一轮开发只做以下 8 个动作：

1. 增加 `ToolConfig` schema，旧配置默认全部启用。
2. 增加 `ToolRegistry`，能列出当前内置工具。
3. 增加 `ToolCapabilityService`，能生成能力摘要。
4. 增加 `ToolPreflightService`，能做 shell/search/browser/file_write 规则检测。
5. 增加 `/api/tools`、`/api/tools/capability-summary`、`/api/tools/preflight`。
6. SettingsModal 增加 Tools tab，只读展示工具、风险和摘要。
7. 加单元测试覆盖 registry、summary、preflight。
8. 确认不影响现有聊天、MCP、A2A、文件上传和会话流程。

第二轮再做：

1. `/api/tools/bindings` 保存工具配置。
2. `FilteredTool` 执行过滤。
3. `ToolFactory` 替换 `PlannerReActFlow` 内硬编码工具装配。
4. UI 开关真正生效。
5. 加执行链路测试。

## 推荐结论

`agentic` 不需要复制 `llmops` 的整套平台结构。更合适的路线是：

- 学 `llmops` 的管理面：注册表、绑定、能力摘要、preflight、UI。
- 保留 `agentic` 的执行面：沙箱、Shell、浏览器、文件、MCP、A2A。
- 用 `ToolRegistry + ToolConfig + FilteredTool + ToolFactory` 做薄封装，把现有硬编码工具列表变成可配置工具列表。
- 第一阶段先可视化和诊断，第二阶段再让配置真正影响执行，第三阶段做高危审批和强制阻断。

这样改动小、回滚容易、对现有 Agent 调用链路影响最小，也能逐步把工具治理能力补起来。
