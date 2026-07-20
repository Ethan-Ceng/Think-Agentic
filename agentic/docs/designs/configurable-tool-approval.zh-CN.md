# 可配置工具审批设计

## 背景

Human-in-the-loop 已支持 `auto | allow | ask | deny`，但当前 UI 只暴露“高风险工具执行前确认”全局开关。`shell_execute` 等系统内置工具被整体标记为高风险，因此用户要么逐次批准，要么关闭全部高风险确认，无法表达“允许 Shell、继续确认浏览器脚本”这类常见偏好。

## 目标

- 用户可以在设置中逐项配置系统高风险工具的审批策略。
- `shell_execute=allow` 后不再为每次调用创建审批卡。
- 未配置项继续采用 `auto`，保持现有安全默认值。
- 显式 `ask`、`deny` 始终覆盖风险默认值。
- 不新增数据库迁移，不改变既有 pending interaction 的处理语义。

## 功能范围

- 在工具列表响应中返回经过筛选的系统审批配置，不返回工具参数或凭据。
- “设置 → 通用 → 高级运行策略”展示系统高风险工具的审批选择器。
- 支持 `auto`（按风险）、`allow`（始终允许）、`ask`（每次确认）、`deny`（禁止执行）。
- 保存时复用现有 `/api/tools/bindings` 与 `ToolBinding` 持久化能力。
- 第一批覆盖 `shell_execute`、`shell_write_input`、`shell_kill_process`、`browser_console_exec`；Sandbox 文件写入已是中风险自动执行。

## 非功能范围

- 不解析 Shell 命令文本来判断具体命令是否安全。
- 不实现“仅本会话允许”或有过期时间的临时授权。
- 不在审批卡中直接修改永久策略。
- 不改变 Sandbox、认证、权限提升或外部执行边界。

## 现有实现分析

- `ToolBinding.approval` 已支持四态策略，配置已存入用户级 ToolConfig。
- `ToolConfigService.update_bindings` 使用合并写入，可安全保存系统内置工具的审批覆盖。
- `FilteredTool.get_approval_policy` 已优先读取显式 binding，随后才应用全局高风险规则。
- 当前 `ToolConfigService.list_tools` 只返回 API descriptors 和 runtime policy，前端无法读取系统内置 binding。
- Settings General 已保存 runtime policy，但 `buildToolBindings` 只构造 API binding。

## 可选方案

### 方案 A：继续只使用全局开关

关闭后所有高风险 `auto` 工具直接执行。

- 优点：无需开发。
- 缺点：粒度过粗，Shell 与浏览器脚本、外部副作用一起放开；不能解决安全与流畅性的冲突。

### 方案 B：持久化的逐工具审批配置

后端仅返回系统高风险工具的安全审批摘要，Settings General 提供逐项选择器，保存到现有 bindings。

- 优点：复用现有模型与存储；无迁移；行为明确；一次配置后不再重复确认。
- 缺点：`shell_execute=allow` 会允许该用户后续所有沙箱 Shell 命令，不能区分只读与破坏性命令。

### 方案 C：命令感知与会话级临时授权

审批策略接收 function arguments，解析 Shell 命令，并将临时 grant 写入 Session。

- 优点：交互最细致，可实现“本会话允许安全命令”。
- 缺点：跨平台 Shell 语法难以可靠解析；转义、脚本和间接执行容易绕过分类；需要修改工具公共接口、Session 状态和恢复规则，安全验证成本高。

## 方案对比

| 方案 | 复杂度 | 安全风险 | 兼容性 | 测试成本 | 交互改善 |
| --- | --- | --- | --- | --- | --- |
| A 全局开关 | 低 | 高 | 高 | 低 | 低 |
| B 逐工具配置 | 中 | 可控 | 高 | 中 | 高 |
| C 命令/会话感知 | 高 | 命令误判风险高 | 中 | 高 | 最高 |

## 推荐方案

采用方案 B。它直接解决“每次都要批准”，同时不会迫使用户关闭全部高风险保护。方案 C 暂不采用：Shell 命令分类不是可靠安全边界，错误放行比重复确认风险更大；如果未来需要会话授权，应以 Sandbox 能力令牌或明确的命令白名单设计，而不是字符串黑名单。

## 业务流程

1. 设置页读取工具列表。
2. 后端返回 runtime policy，以及系统高风险工具的 `tool_id`、名称、风险和有效 approval。
3. 用户将 `shell_execute` 从 `auto` 改为 `allow` 并保存。
4. 后端合并写入 `builtin.shell.shell_execute` binding，保留其他配置。
5. 新 Task 构建 FilteredTool 时读取该 binding，Shell 调用直接执行；现有 pending 审批仍需由原卡片解决。

## 核心规则

- 返回给前端的系统审批摘要不得包含 `params`、凭据或注册配置。
- 只有 catalog 中的系统高风险工具进入配置列表。
- 未设置 binding 时响应为 `auto`，不为了展示而写入默认配置。
- 保存单项策略不得覆盖其他 bindings 或 runtime policy。
- 已经创建的 pending interaction 不受配置变更追溯影响，避免绕过已展示的审批。
- `allow` 是用户级持久化选择，UI 必须明确提示其作用范围。

## 数据结构与接口

扩展 `ToolListResponse`：

```text
approval_tools: [
  {
    tool_id,
    function_name,
    label,
    risk_level,
    approval
  }
]
```

更新仍复用：

```text
POST /api/tools/bindings
```

请求中的 `bindings` 只提交有变化的系统审批 binding 与现有 API bindings；服务端继续采用 merge 语义。

## 错误处理

- 未知或非系统工具 ID：沿用 binding 合并规则，但 UI 不生成该项。
- 非法 approval：Pydantic 返回 422。
- 保存失败：前端保留选择并显示错误，不把本地状态标记为已保存。

## 迁移与回滚

- 无数据库迁移；旧配置缺少系统 binding 时保持 `auto`。
- 回滚前端后，已保存 binding 仍由后端生效；可通过重置工具配置恢复默认。
- 回滚后端前应先移除系统 approval bindings，或确保旧版本忽略未知字段。

## 风险

- 用户把 Shell 永久设为 allow 后，沙箱内破坏性命令也不会再询问。缓解：UI 明确警告作用范围，默认仍为 auto，每项支持恢复默认。
- Settings 保存 API bindings 时可能覆盖系统 binding。缓解：服务端保持 merge；前端只发送实际变更，新增回归测试。
- 配置变更影响新调用但不影响 pending。此差异是刻意设计，需用文案说明。

## 验收标准

- 设置页能独立配置 `shell_execute` 为 `allow`，刷新后仍保持。
- `shell_execute=allow` 时不产生 pending interaction；`ask` 时仍产生；`deny` 时不执行。
- 修改 Shell 策略不改变 `browser_console_exec` 的默认策略。
- API 响应不包含系统 ToolBinding.params 或敏感配置。
- 旧 ToolConfig 与缺少 `approval_tools` 的旧前端继续工作。
- 相关后端测试、前端组件测试、类型检查和构建通过。

## 重要假设

- Sandbox 是 Shell 的实际执行边界；逐工具 `allow` 不等价于宿主机权限提升。
- 用户需要的是可持久化偏好，而不是一次性绕过当前 pending。
- 第一版宁可明确允许整个工具，也不通过不可靠的命令字符串判断提供虚假安全感。

## 待决策项

- 无。按逐工具持久化配置实施；会话级授权和命令感知分类留作后续独立设计。
