# External Provider Unified Tool Plane 代码审查

## 审查范围

- 目标分支：`develop`
- 变更分支：`refactor/unified-tool-plane`
- 变更范围：Stage 1B 外部 Provider 接入统一 Tool Plane
- 设计文档：`docs/designs/agent-runtime-hitl-provider-reliability.zh-CN.md`
- 计划文档：`docs/plans/external-provider-tool-plane-plan.md`
- 审查者：同一 Agent 自检
- 审查日期：2026-08-19

## 首轮问题列表

### [major] Provider 精确约束错误地作用于未被该 Provider 覆盖的其他能力组

位置：`api/app/core/tools/scope.py:141`

问题：当步骤同时请求 `shell + mcp` 且系统对唯一 MCP Provider 做确定性收窄时，RuntimeToolScope 会把该 MCP Provider ID 当作所有能力组的全局约束，导致 `shell_execute` 被拒绝。已通过本地最小复现确认：`resolve_scope_selection(["shell", "mcp"])` 返回 `mcp.github` 后，`allows("shell", "shell_execute")` 为 `False`。

影响：合法的混合能力 React/Plan Step 无法执行内置工具；历史 capability-only 数据在新增单 MCP Provider 后也可能出现行为退化。

建议：Provider/Tool 精确约束只约束其实际覆盖的 capability group；未知或与全部所选 capability 都不相交的精确约束仍必须 fail closed。

状态：已修复；Provider/Tool 约束按 capability group 生效，Resolver 与 Runtime 均对未知精确约束 fail closed，混合 `shell + mcp` 回归通过。

### [major] MCP Provider/函数命名空间可能碰撞或生成无效模型函数名

位置：`api/app/core/tools/provider_catalog.py:27`、`api/app/core/tools/mcp.py:282`、`api/app/core/tools/mcp.py:597`

问题：`github` 与 `GitHub` 当前都生成 `mcp.github`；超长但字符合法的服务名不受长度限制。真实 MCP Schema 又直接使用原始 server/tool 名拼接函数名，空格、Unicode、超长名称和 search-tools 保留名都可能形成无效或重复函数名。

影响：Provider Catalog 覆盖、错误路由、Registry 丢失描述符，或模型 API 因函数名不合法而在工具调用前失败。

建议：对非规范或超长 Provider 名加入稳定摘要；对真实 MCP Tool 和 search-tools 使用同一套有界、合法且防碰撞的函数命名规则，并用显式路由表恢复原始 server/tool 名。

状态：已修复；Provider ID 和模型函数名均使用稳定、有界、防碰撞命名，调用通过规范化路由表还原原始 Tool 名。

### [major] 外部 Schema 预算按 Provider 分别计算，无法保证单 Step 上限

位置：`api/app/core/tools/mcp.py:429`

问题：每个选中 Provider 都单独与 `max_external_tool_schemas/max_external_schema_chars` 比较；多个 Provider 各自低于上限但合计超过上限时，仍会把全部 Schema 注入同一次模型调用。

影响：明确配置的上下文预算可被多 Provider 选择绕过，造成 Prompt 膨胀、延迟增加，严重时模型请求失败。

建议：按当前 Step 的全部选中 MCP Provider 汇总计算；超限时统一进入 search-tools 模式，并确保检索后的活跃 Schema 集合仍受同一总预算约束。

状态：已修复；预算按当前 Step 全部选中 MCP Provider 汇总，检索后的活跃 Schema 也受同一上限裁剪。

### [major] Lead 精确选择 search-tools 后会阻止 Top-K Schema 进入下一轮

位置：`api/app/core/tools/scope.py:149`、`api/app/core/tools/mcp.py:554`

问题：真实 Lead 路径会把 Catalog 中唯一可见的 MCP search-tools 写入 `tool_ids`。检索调用虽然更新了 MCPTool 活跃 Schema，但 RuntimeToolScope 仍只允许原 search-tools ID，因此下一次模型调用会过滤掉刚检索出的 Top-K Tool。

影响：二阶段检索表面成功，实际 Agent 永远无法调用检索结果，是核心验收链路失效。

建议：把 search-tools 返回的真实 Tool ID 作为系统验证后的 Scope refinement；只允许加入当前 capability 和已选 Provider 内、已经注册的 Tool ID，并在下一次模型调用和 Trace 中使用更新后的 Snapshot。

状态：已修复；search-tools 结果经 Registry/Provider/Capability 校验后原子替换系统解析的 Tool ID，下一轮 Scope 与 Trace 使用更新快照。

### [minor] 二阶段检索切换 Top-K 后 Registry 保留旧动态描述符

位置：`api/app/core/tools/registry.py:149`、`api/app/core/tools/factory.py:86`

问题：MCP search-tools 每次只追加新描述符，不替换同一 Provider 上一次的活跃集合。

影响：后续 Planner Catalog 和 Trace 可能看到已经不在当前注入集合中的旧 Tool，造成目录与模型可见 Schema 不一致。

建议：刷新 MCP Provider 时原子替换该 Provider 的 runtime descriptors。

状态：已修复；同一 MCP Provider 的 runtime descriptors 改为替换，重复搜索不会保留旧 Top-K。

### [minor] 外部 Catalog 元数据没有显式信任标记和 Prompt Injection 边界

位置：`api/app/schemas/tool_config.py:227`、`api/app/core/prompts/lead.py:37`

问题：虽然外部 label/description/tag 已限长并去控制字符，但 Catalog 没有标识其来自可编辑配置，Lead/Planner Prompt 也未明确禁止把其中的文本当作指令。

影响：恶意或误配置描述可能影响 Provider 选择，偏离平台策略。

建议：目录输出携带低基数 `metadata_trust`，并在中英 Prompt 中明确目录字段仅是数据、不得覆盖规则或用户请求。

状态：已修复；Catalog 输出 `metadata_trust`，Lead 与中英 Planner Prompt 明确目录字段是不可信数据而非指令。

### [minor] 非 MCP FilteredTool 也安装了无效刷新回调

位置：`api/app/core/tools/factory.py:74`

问题：当前条件写在 lambda 内，导致所有工具都有 `_after_prepare`；每次普通工具调用都会执行一次空返回回调和 Scope refresh。

影响：增加无意义工作并模糊“只有 MCP 动态 Schema 会刷新 Registry”的生命周期边界。

建议：只在构造 MCP FilteredTool 时传入回调。

状态：已修复；只有 MCP FilteredTool 安装 Registry 刷新回调。

## 首轮门禁

| 门禁 | 结果 | 证据 |
| --- | --- | --- |
| 无 blocking | 通过 | 未发现 blocking |
| 无未处理 major | 失败 | 4 项 major 待修复 |
| 首轮相关测试 | 通过 | 核心定向 177 passed；后端全量 501 passed |
| 首轮静态/编译/差异检查 | 通过 | Ruff、compileall、`git diff --check` 均退出 0 |
| 数据迁移 | 不适用 | 本批无产品数据库迁移 |

## 首轮审查结论

- 结论：`CHANGES_REQUIRED`
- 理由：存在 4 项 correctness/compatibility/budget major，合并前必须修复。
- 审查限制：本次为同一 Agent 自检；最终结论需在修复、复审和最新全量验证后更新。

## 修复后复审

- 需求符合度：Stage 1B 的离线 Provider Catalog、MCP 按 Scope 惰性发现、单 Step Schema 预算/二阶段检索、A2A 真实调用时初始化、Runner 零预连接、Scope/恢复/Trace 贯通均已覆盖。
- 正确性：4 项 major 与 3 项 minor 均已修复；混合 capability、未知精确约束、Provider/函数名碰撞、跨 Provider 总预算、search-tools Scope refinement、重复检索替换均有回归测试。
- 安全性：Catalog 不含 URL/Header/Env/凭据/参数 Schema；外部配置元数据有信任标记并在双语 Prompt 中按不可信数据处理；未选/未知 Provider 不连接，Scope/Policy 在 Adapter 前再次校验。
- 可维护性：API/MCP/A2A 复用统一 Registry、Schema Resolver、FilteredTool、Executor Router 与 Trace；非 MCP Adapter 不再安装动态刷新回调。
- 测试质量：新增测试覆盖真实 search-tools 精确 tool_id 路径、重复搜索、混合 Scope、命名碰撞、实际 Manager 反向路由、跨 Provider 预算和目录信任标记。
- 复审结果：未发现新的 blocking 或未处理 major。

## 无法验证项与剩余边界

- 未连接真实第三方 MCP/A2A 服务；传输协议错误、Provider Actor/cancel scope 隔离、跨 Run Schema Snapshot 和 A2A Card TTL/共享 HTTP Client 明确保留在 Stage 2/3。
- 本次为同一 Agent 自检，独立 Reviewer 可进一步降低审查偏差。
- 前述剩余项不属于 Stage 1B 完成声明，不据此宣称多轮 Provider 可靠性问题已经全部解决。

## 最终合并门禁

| 门禁 | 结果 | 证据 |
| --- | --- | --- |
| 无 blocking | 通过 | 复审未发现 blocking |
| 无未处理 major | 通过 | 4 项 major 全部修复并回归 |
| Stage 1B 验收 | 通过 | Provider Catalog、惰性发现、预算检索、A2A lazy、Scope/恢复/Trace 测试通过 |
| 核心回归 | 通过 | `182 passed`，11 个既有 Pydantic deprecation warnings |
| 后端全量 | 通过 | 隔离 PostgreSQL/Redis + 全部迁移后 `506 passed` |
| 静态检查 | 通过 | `uv run ruff check app tests` 退出 0 |
| 编译检查 | 通过 | `uv run python -m compileall -q app tests` 退出 0 |
| 差异检查 | 通过 | `git diff --check` 退出 0；仅 Git 的 LF/CRLF 工作区提示 |
| 产品数据库迁移 | 不适用 | 本批没有新增/修改产品迁移；现有迁移链已在隔离库执行到 head |

## 最终审查结论

- 结论：`APPROVED`
- 合并判断：`READY_TO_MERGE`
- 理由：Stage 1B 范围内无未处理 blocking/major，最新定向、全量、静态、编译和差异门禁全部通过。
- 下一步：等待用户决定是否提交/推送；后续架构工作进入 Stage 2 MCP Provider Actor、类型化错误与 Schema Snapshot，不把该边界并入本次完成声明。
