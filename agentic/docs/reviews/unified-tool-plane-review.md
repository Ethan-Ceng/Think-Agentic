# Unified Tool Plane Stage 1A 代码审查

## 审查结论

- 结论：`APPROVED`
- 合并判断：`READY_TO_MERGE`
- 范围：`refactor/unified-tool-plane` 相对 `develop` 的 Stage 1A 变更
- 审查时间：2026-08-18（Asia/Shanghai）
- 阻塞项：无
- 未解决 major：无

## 设计与范围符合性

- ToolDescriptor 已拆分 `source_type`、`execution_backend`、`resource_requirements`、`execution_class`、`generality` 与 `cost_class`，旧 `executor_type/requires_*` 仍可读。
- Lead/Planner 使用不含参数 Schema、URL、Header 或凭据的紧凑 Tool Catalog；React/Plan 使用同一个 Scope Snapshot 解析模型可见 Schema。
- ToolExecutorRouter 在进入现有运行时 Adapter 前重新执行 enabled、平台 allow/deny 与 Scope 校验；拒绝路径不会调用 Lazy Sandbox 代理。
- Lead -> React/Plan -> InteractionEvent -> InteractionResolution -> Resume 已传播 provider/tool scope；缺少新字段的历史事件继续按 capability-only 读取。
- Stage 1A 只声明内置工具平面迁移完成；MCP/A2A 惰性连接、Provider Actor、Schema Snapshot/预算、类型化 FailureInfo 与完整 Capability Grant 保留在 Stage 1B/2。

## 审查发现

### Major（已修复）

1. 未登记运行时函数在“只请求未知精确 ID”时可能退化到 capability 级允许。
   - 原因：`RuntimeToolScope.allows()` 的 `descriptor is None` 兼容分支只检查已成功解析的 provider/tool ID，没有检查 unknown ID，导致未知约束被误认为未请求精确约束。
   - 修复：只要请求过任何 provider/tool 精确约束（包括 unknown），未登记函数一律拒绝；标准注册函数继续按 Descriptor 关系判断。
   - 回归：`test_unknown_exact_constraints_reject_unregistered_runtime_functions` 覆盖未知 provider 与未知 tool 两种路径。

### Minor（已修复）

1. BaseAgent 保存了未使用的 `_tool_schema_resolver` 引用。
   - 修复：删除无效实例字段，继续通过统一 `ToolSchemaResolver.resolve_tools()` 聚合受治理 Schema。

### Suggestion（后续阶段）

1. Stage 1B 对外部 Provider Catalog 描述增加长度预算、可信来源标记和 Prompt Injection 防护；当前 Stage 1A 已排除参数 Schema、连接信息和凭据，但外部描述仍属于不可信元数据。
2. Stage 1B 明确新鲜 Lead 决策缺少 provider/tool 精确选择时的策略（确定性唯一候选、二阶段检索或拒绝），同时保留历史 capability-only 数据兼容。
3. Stage 2 为动态 MCP Schema 增加版本/配置指纹与删除失效工具的快照替换，避免长期运行进程保留已移除函数。

## 验证证据

- Lazy Sandbox 契约：34 passed。
- Agent/Tool/Sandbox 定向回归：171 passed（审查修复后最终复验）。
- 后端全量：486 passed（审查修复后最终复验）。
- 审查修复定向回归：39 passed。
- Ruff、Python compileall、`git diff --check`：审查修复后均通过。

最终复验未发现新的 blocking 或 major，Stage 1A 满足合并门禁；Stage 1B/2 的外部 Provider 与动态 Schema 工作不包含在本结论中。
