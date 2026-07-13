# Agentic 内置能力与外部工具边界

整理日期：2026-07-13

## 1. 最终结论

当前不再为“系统能力”提供独立页面，也不允许用户注册、启停或重置内置能力。

能力边界收敛为两层：

- 内置能力：Agent 运行时的内部基础设施，由代码注册并默认装配，不进入用户工具管理。
- 外部能力：用户或管理员注入的 API Tools、MCP、A2A，分别在现有入口注册和管理。

其中，用户消息能力是 Agent 与用户对话的基础组件，必须始终可用。文件、Shell、浏览器、搜索等代码内置能力同样由系统运行时负责装配，不再暴露用户级开关。

## 2. 产品信息架构

Settings 只保留以下相关入口：

```text
API Tools  -> 注册和管理 HTTP API Provider 与 operations
MCP        -> 管理 MCP Server 连接
A2A        -> 管理远程 Agent 连接
```

不再提供：

- “系统能力”页面。
- 内置能力的新增、编辑、删除、启停和恢复默认。
- 将内置能力与 API Tools、MCP、A2A 混合展示的统一工具源列表。

## 3. 运行时边界

`ToolRegistry` 仍汇总 Agent 实际运行所需的全部能力，但区分内部装配与外部配置：

```text
ToolRegistry
  |- builtin.*  系统内部默认装配
  |- api.*      用户 API Tools 配置
  |- mcp.*      MCP 连接动态注入
  `- a2a.*      A2A 连接动态注入
```

对 `builtin.*` 的约束：

- 不生成用户默认 binding。
- 忽略历史用户配置中的 builtin binding。
- 不受用户级 executor allowlist 影响。
- 始终由运行时按系统代码和环境条件装配。

这解决的是配置所有权问题，不代表所有能力可以绕过沙箱、凭证、网络或资源条件。比如文件和 Shell 能力仍需要相应运行环境；这些属于系统运行条件，不是用户工具开关。

## 4. API 边界

现有 `/api/tools` 路由继续服务 API Tools 管理，但用户可见数据收窄为外部 API 工具：

- `GET /api/tools`：只返回 `executor_type=api` 的 operations。
- `/api/tools/registrations`：只返回和管理非 builtin 的 API Provider。
- `/api/tools/bindings`：只需要提交 API operation 的用户 binding。

能力摘要和 preflight 属于运行时诊断能力，可以在内部汇总实际有效能力；它们不是系统能力管理入口。

MCP 与 A2A 继续使用各自的配置和页面，不并入 API Tools 注册列表。

## 5. 兼容策略

不要求迁移或清理已有用户配置：

- 历史 `builtin.*` binding 可以继续存在于 JSONB 中，但 Registry 不再读取其启停和风险覆盖。
- 前端保存 API Tools 时只提交 API operation binding，不再写入新的 builtin binding。
- 重置默认配置不再生成 builtin binding。
- API Tools、MCP、A2A 的已有配置保持不变。

## 6. 已实施范围

本次已经完成：

- 移除 Settings 的“系统能力”入口及其用户控制。
- API Tools 页面只展示自定义 API Provider 和对应 operations。
- 工具列表与注册列表服务只向用户返回 API Tools。
- Registry 将所有 `builtin.*` 视为系统内部默认能力，忽略用户 binding 和 executor 策略。
- 默认 binding 排除 `builtin.*`。
- 更新后端测试和当前状态文档。

未在本次扩展：

- 内置能力管理员控制台。
- 内置能力数据库模型或迁移。
- API Tools 的审批、审计和密钥托管增强。
- MCP tool 级细粒度治理。

## 7. 验收标准

- Settings 中不存在“系统能力”页面。
- 用户不能查看或修改 builtin 工具 binding。
- 用户消息等基础能力不会因旧配置或 executor 策略被禁用。
- API Tools 的注册、编辑、删除、测试和 operation 启停继续可用。
- MCP、A2A 仍在独立入口管理。
- Registry 和 Agent 运行时仍能装配内置能力。
