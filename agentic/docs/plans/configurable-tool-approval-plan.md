# 可配置工具审批实施计划

## 关联设计

- 设计文档：`docs/designs/configurable-tool-approval.zh-CN.md`
- 开发分支：`feature/chat-human-in-the-loop`

## 当前进度

- 整体状态：`BLOCKED`
- 当前阶段：verification
- 当前任务：无；等待真实浏览器与 PostgreSQL/Redis 环境补验
- 已完成：3 / 3
- 阻塞问题：当前无可用浏览器实例；PostgreSQL/Redis 未启动
- 最近更新时间：2026-07-20 17:06（Asia/Shanghai）

## 全局约束

- 不新增数据库迁移，复用用户 ToolConfig JSON。
- 不向前端返回 ToolBinding.params、凭据或注册配置。
- 不解析 Shell 命令字符串，不把字符串分类当作安全边界。
- 新配置只影响后续工具调用，不追溯改变已创建的 pending interaction。
- 保持旧 ToolConfig、旧前端和现有全局高风险确认开关兼容。
- 不提交、推送或合并，除非用户另行授权。

## Task 1：扩展安全的系统审批配置契约

状态：completed

### 目标

让工具列表 API 返回可配置的系统高风险工具审批摘要，并确保更新单项 binding 不覆盖其他配置。

### 涉及文件

- `api/app/schemas/tool_config.py`
- `api/app/services/tool_config_service.py`
- `api/tests/app/core/tools/test_tool_management.py`

### 实施步骤

1. 新增只包含 tool_id、function_name、label、risk_level、approval 的响应模型。
2. ToolConfigService 从 builtin catalog/registry 生成系统高风险工具摘要，缺省 approval 为 auto。
3. 保持 `/tools/bindings` 合并语义，增加系统 binding 保存、刷新读取、互不覆盖及脱敏测试。

### 验证方式

- `py -m pytest tests/app/core/tools/test_tool_management.py -q`
- 预期退出码 0；摘要只含安全字段，Shell 单项策略可持久化，其他配置不被覆盖。

### 完成条件

- API 契约向后兼容；前端能读取四个系统高风险工具的有效审批策略；响应无敏感参数。

### 执行结果

新增 `ToolApprovalSetting` 安全响应模型；工具列表按 builtin catalog 只返回四个系统高风险工具的 ID、名称、标签、风险和 approval，不返回 binding params。更新仍复用 bindings merge 语义，单项 Shell 修改不会覆盖浏览器策略。

### 验证证据

`py -m pytest tests/app/core/tools/test_tool_management.py -q` 退出码 0，15 passed。新增测试先确认缺少 `approval_tools` 时失败，实现后通过，并覆盖敏感 params 不出现在响应、默认 auto 和 binding 合并。

## Task 2：设置页提供逐工具审批策略

状态：completed

### 目标

用户可在通用设置中把 Shell 等系统高风险工具独立设为按风险、始终允许、每次确认或禁止。

### 涉及文件

- `web/src/lib/api/types.ts`
- `web/src/components/settings/SettingsGeneralPanel.vue`
- `web/src/components/settings/SettingsGeneralPanel.spec.ts`（新建）
- `web/src/style.css`
- `web/vitest.config.ts`

### 实施步骤

1. 增加 approval tool 和四态 approval 的前端类型。
2. Settings General 加载审批摘要、展示作用范围警告和逐项选择器。
3. 保存时仅提交系统审批变更，并保留当前 API bindings 与 runtime policy。
4. 覆盖加载、修改、保存 payload、保存失败和全局开关联动文案测试。

### 验证方式

- `pnpm test:run -- src/components/settings/SettingsGeneralPanel.spec.ts`
- `pnpm type-check`
- 预期均退出 0；`shell_execute=allow` 的 payload 正确且其他项不被覆盖。

### 完成条件

- 用户能完成逐项配置并刷新保持；UI 清楚说明 allow 的持久化和作用范围。

### 执行结果

ToolListData 新增 approval_tools；通用设置加载并展示逐工具四态策略，保存时将系统审批 bindings 与现有 API bindings 一并合并提交。UI 明确说明配置持久化、allow 跳过后续确认以及当前 pending 不受追溯影响，并补充移动端布局。Vitest 内联 Element Plus 依赖以支持设置组件测试。

### 验证证据

`pnpm test:run -- src/components/settings/SettingsGeneralPanel.spec.ts` 退出码 0，1 passed；测试覆盖 Shell 改为 allow、浏览器 ask 保持及保存 payload。`pnpm type-check` 与 `git diff --check` 均退出 0。

## Task 3：回归验证、文档与合并判断

状态：completed

### 目标

确认逐工具配置不破坏既有审批、Sandbox 文件自动执行、API Tools 设置和构建。

### 涉及文件

- `docs/tool-management.zh-CN.md`
- `docs/current-state.zh-CN.md`
- `docs/plans/configurable-tool-approval-plan.md`
- `docs/reviews/configurable-tool-approval-review.md`（新建）

### 实施步骤

1. 更新产品行为、默认值、风险和回滚文档。
2. 运行后端审批聚焦测试、前端完整测试、类型检查、构建和 diff 检查。
3. 审查安全边界、兼容性、配置合并和敏感字段暴露。
4. 写回实际证据并给出 READY_TO_MERGE/BLOCKED/FAILED。

### 验证方式

- `py -m pytest tests/app/core/test_interaction_events.py tests/app/core/tools/test_tool_management.py tests/app/core/agent/test_interaction_resume.py -q`
- `pnpm test:run`
- `pnpm type-check`
- `pnpm build`
- `git diff --check`

### 完成条件

- 适用命令退出 0；无 blocking/major；无法执行的环境验证被明确记录。

### 执行结果

工具治理与当前状态文档已同步逐工具审批行为。首次验证后审查发现前端过度回写和后端整条替换 binding 的 major；现已改为前端只提交变化项、后端只合并显式字段，并由测试锁定隐藏 params、其他工具策略和省略 approval 不被覆盖。复审无剩余 blocking/major。

### 验证证据

整改后重新验证：后端聚焦 23/23 通过；前端 14 个测试文件 35/35 通过；`pnpm build`（含 vue-tsc）、相关 `py_compile` 和 `git diff --check` 均退出 0。代码审查 `APPROVED`，详见 `docs/reviews/configurable-tool-approval-review.md`。

## 计划变更

| 日期 | 变更内容 | 原因 | 影响任务 | 是否影响设计 |
| --- | --- | --- | --- | --- |
| 2026-07-20 | 初始计划 | 将逐工具持久化审批拆分为契约、UI、验证三个独立任务 | Task 1–3 | 否 |
| 2026-07-20 | 前端改为只提交变化项，后端改为显式字段合并 | 审查发现过度回写可能造成并发旧值覆盖和隐藏字段丢失 | Task 3 | 否，落实既定约束 |

## 最终验证

### 执行命令

```powershell
py -m pytest tests/app/core/test_interaction_events.py tests/app/core/tools/test_tool_management.py tests/app/core/agent/test_interaction_resume.py -q
pnpm test:run
pnpm type-check
pnpm build
py -m py_compile app/schemas/tool_config.py app/services/tool_config_service.py
git diff --check
```

### 执行结果

- 后端测试：聚焦测试 23/23 通过。
- 前端测试：14 个测试文件 35/35 通过。
- 类型检查：`pnpm type-check` 通过。
- 构建：`pnpm build` 通过。
- 静态检查：相关 Python 文件 `py_compile` 与 `git diff --check` 通过。
- 数据库迁移：不适用。
- 手工验证：当前无可用浏览器实例，未执行真实设置页视觉和刷新操作；组件测试覆盖加载、修改与保存。
- 代码审查：`APPROVED`；发现的 1 个 major 已整改并重新验证。

### 验收标准检查

- [x] `shell_execute` 可独立配置并持久化（服务合并测试与组件保存测试）。
- [x] allow/ask/deny/auto 的运行时行为符合契约。
- [x] 修改 Shell 不影响其他系统高风险工具。
- [x] 响应不暴露 params、凭据或注册配置。
- [x] 旧配置和现有审批流程聚焦回归通过。

### 未通过项目

- 当前无可用浏览器实例，真实设置页视觉和刷新操作未验证。
- PostgreSQL/Redis 未启动，真实用户 ToolConfig 持久化未执行。

### 最终状态

`BLOCKED`
