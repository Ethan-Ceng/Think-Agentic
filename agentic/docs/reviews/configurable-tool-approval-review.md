# 可配置工具审批代码审查

## 审查范围

- 目标分支：`master`
- 变更分支：`feature/chat-human-in-the-loop`
- 设计：`docs/designs/configurable-tool-approval.zh-CN.md`
- 计划：`docs/plans/configurable-tool-approval-plan.md`
- 审查范围：系统高风险工具审批摘要、binding 合并、通用设置逐项配置、测试与文档
- 审查者：同一 Agent 自检
- 审查日期：2026-07-20

## 问题列表

### [major，已整改] 设置页过度回写与 binding 整条替换

位置：`web/src/components/settings/SettingsGeneralPanel.vue`、`api/app/services/tool_config_service.py`

问题：首次实现会回写所有系统审批项，并用传入 ToolBinding 整条替换已有 binding。多标签页可能用旧值覆盖另一个工具；未暴露给前端的 params 也可能被空默认值清除，省略的 approval 可能被重置为 auto。

影响：配置更新可能造成并发丢失或隐藏字段丢失，削弱审批策略的可靠性。

整改：前端只提交相对加载基线实际变化的系统审批项；后端依据 Pydantic `model_fields_set` 只合并显式字段。新增回归断言证明 Shell params、浏览器策略和 API 工具 approval/params 保持不变。

验证：后端工具策略测试 15/15、设置组件测试 1/1 通过；整改后完整相关回归和构建重新通过。

## 未发现问题

- 未发现剩余 blocking 或 major。
- 系统审批摘要只包含 tool_id、function_name、label、risk_level 和 approval，不包含 params、凭据或注册信息。
- 缺少系统 binding 时返回 auto；旧 ToolConfig 和旧前端可继续使用。
- 已存在的 pending interaction 不因设置变更被追溯放行。
- allow 仍受 Sandbox 实际执行边界约束，但会放行该工具的全部沙箱内调用，UI 已明确提示。

## 无法验证项

- 当前无可用浏览器实例，未进行真实设置页视觉、键盘操作、移动端布局和刷新保持检查。
- PostgreSQL/Redis 未启动，未通过真实用户配置表验证持久化；服务层合并使用 FakeAppConfigService 覆盖。
- 同一 Agent 自审不能替代独立 Reviewer。

## 门禁检查

| 门禁 | 结果 | 证据 |
| --- | --- | --- |
| 无 blocking | 通过 | 自审未发现 blocking |
| 无未处理 major | 通过 | 过度回写/字段覆盖 major 已整改并回归 |
| 后端相关测试 | 通过 | 23/23 |
| 前端完整测试 | 通过 | 14 个文件、35/35 |
| 类型与构建 | 通过 | `pnpm build` 包含 vue-tsc，退出码 0 |
| 静态检查 | 通过 | Python `py_compile`、`git diff --check` 退出码 0 |
| 数据库迁移 | 不适用 | 未新增迁移 |
| 真实页面/持久化 | 未验证 | 浏览器和 PostgreSQL/Redis 不可用 |

## 审查结论

- 代码结论：`APPROVED`
- 合并门禁：`BLOCKED`
- 理由：代码层无 blocking/major，审查发现的配置覆盖问题已整改且最新验证通过；真实浏览器和数据库持久化仍缺少环境证据。
- 不自动提交、推送或合并。
