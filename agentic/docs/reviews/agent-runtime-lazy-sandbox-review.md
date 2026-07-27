# Agent Runtime Sandbox 懒启动与 Tool Token 优化代码审查

## 审查范围

- 目标分支：`master`
- 变更分支：`feature/agent-runtime-lazy-sandbox`
- 变更范围：`master...HEAD` 加 Task 6 当前工作区整改
- 设计文档：`agentic/docs/designs/knowledge-document-processing.zh-CN.md`
- 计划文档：`agentic/docs/plans/agent-runtime-lazy-sandbox-plan.md`
- 审查者：同一 Agent 自检
- 审查日期：2026-07-27

## 需求符合度

- [x] 普通文本和 Context 能力不创建或恢复 Sandbox。
- [x] Planner 不再接收完整 Tool Schema，ReAct 按 Step capability 裁剪。
- [x] Sandbox 首次能力调用才创建，并发、恢复、取消和失败路径有覆盖。
- [x] 附件只在 Sandbox Tool 实际使用时下载和同步。
- [x] ToolConfig、审批、waiting 恢复、next-message、Skill、MCP/A2A/API、Trace、VNC 和分支行为保持兼容。
- [x] 未增加数据库迁移，未修改 Sandbox 镜像和 Document Worker。

## 正确性

- [x] 未激活、固定地址、过期 handle、并发认领、取消创建和销毁均有明确行为。
- [x] 数据库通过 compare-and-set 原子认领 `sandbox_id`，竞争失败者销毁多余实例。
- [x] waiting 审批从持久化函数名恢复精确 Tool Scope，避免重复执行。
- [x] 服务关闭先快照任务注册表，Browser 客户端资源先清理再销毁 Sandbox。

## 安全性

- [x] 附件下载继续带 `user_id` 授权边界，并校验返回文件标识。
- [x] Sandbox 文件名去除路径、控制字符并限制长度。
- [x] Runtime Scope 只能缩小 ToolConfig 已允许能力，未知 capability 不授予工具。
- [x] Trace 只记录 Schema 数量/字节与资源摘要，不持久化完整动态 Schema 或附件内容。
- [x] 高风险工具审批、禁止策略和系统消息工具例外保持原协议。

## 可维护性

- [x] Lazy Runtime、Browser proxy、Tool Scope 和 Capability Registry 各自职责清晰。
- [x] 动态 MCP 初始化后的 Registry 刷新集中在 `ToolFactory`。
- [x] 历史 Step 缺少 capability 字段时保持可解析，waiting 恢复有精确兼容路径。
- [x] 无数据库 Schema 变化和隐式数据迁移。

## 测试质量

- [x] 核心行为、并发、取消、失败重试、审批恢复和跨 Run 复用有自动化覆盖。
- [x] PostgreSQL、Redis、真实 Docker Sandbox、Browser CDP 和 VNC TCP 均实际验证。
- [x] Tool Schema 数量与字节有确定性对比。
- [x] 后端全量、前端全量、类型检查和生产构建均通过。

## 问题列表

### [major][已整改] MCP 异步初始化后未刷新 Capability Registry

位置：`agentic/api/app/core/tools/factory.py`、`agentic/api/app/core/agent/agent_task_runner.py`

问题：Task 构造时 MCP 尚未初始化，初始 Registry 扫描不到动态 MCP Schema；初始化完成后没有再次注册，Planner 的 Capability Catalog 可能缺少 `mcp`。

影响：启用 MCP 的用户可能无法让新 Plan 选择 MCP 能力，违反 MCP 无回归验收条件。

整改：增加 `ToolFactory.refresh_mcp_tools()`，在 `MCPTool.initialize()` 完成后由 Flow 刷新共享 Registry；增加动态 MCP catalog 与 Runtime Scope 回归测试。

### [major][已整改] Browser 激活后 Runtime 销毁未清理 Playwright 客户端

位置：`agentic/api/app/core/sandbox/runtime.py`

问题：旧销毁路径直接清空 `_browser` 引用并删除容器，没有调用 `PlaywrightBrowser.cleanup()`；真实 Browser 验证出现未关闭 subprocess/pipe transport。

影响：Browser Run 在取消或服务关闭后可能泄漏 Playwright 客户端资源和事件循环 transport。

整改：在同一生命周期锁内先调用 Browser `cleanup()`，再销毁 Sandbox；即使 Browser 清理失败仍尝试销毁容器。增加清理顺序回归测试，并重新执行真实 CDP/VNC 验证，未再出现 transport 泄漏。

### [minor] 分支包含两处本批之前的非 Runtime 文件

位置：`readme.md`、`agentic/web/src/components.d.ts`

问题：Task 1 提交中带入了根目录个人恢复命令和前端自动组件声明；不属于 Sandbox/Tool Token 实现。

影响：不影响运行正确性，但增加合并噪声。

建议：用户提交 Task 6 时可决定是否保留；本轮按“保留用户既有改动”约束未擅自删除。

## 无法验证项

- 未调用真实外部 LLM Provider 验证自然语言规划质量；Planner 0 Schema、Capability Catalog、ReAct Scope 和 Trace 数据使用确定性自动化与本地度量验证。
- 未做 VNC 图形画面人工目视验收；已验证 Sandbox Supervisor 就绪、VNC TCP 可连接、Browser CDP 实际导航成功。

## 合并门禁

| 门禁 | 结果 | 证据 |
| --- | --- | --- |
| 无 blocking | 通过 | 审查未发现 blocking |
| 无未处理 major | 通过 | 2 个 major 已整改并回归 |
| 验收标准满足 | 通过 | 计划最终验收 9 项全部勾选 |
| 后端测试通过 | 通过 | 350 passed |
| 前端测试通过 | 通过 | 43 files / 172 tests passed |
| 静态与类型检查 | 通过 | Ruff、py_compile、vue-tsc、diff check |
| 构建通过 | 通过 | Vite production build |
| 数据迁移已验证 | 通过/不适用 | `alembic upgrade head` 通过；本批无新迁移 |
| 真实资源行为 | 通过 | Docker create=1、handle claim=1、清理回 0；File、CDP、VNC 成功 |

## 审查结论

- 结论：`APPROVED`
- 理由：验收条件、自动化、真实资源验证和构建均通过；没有遗留 blocking 或 major。
- 剩余风险：本次为同一 Agent 自检，独立 Reviewer 能进一步降低审查盲区；外部 LLM 规划质量与 VNC 画面未人工验收。
- 下一步：等待用户检查 Task 6 工作区并明确提交或合并。
