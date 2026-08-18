# 移除通用 Tool Approval 代码审查

## 审查结论

- 结论：`APPROVED`
- 合并门禁：`READY_TO_MERGE`
- 审查基线：`develop@6cabc3d`
- 审查范围：`feature/remove-tool-approval` 工作区相对基线的全部实现与测试；用户已有的 `agentic/api/.env` 修改不在范围内
- 审查方式：当前会话同一 Agent 自审；受本次协作约束限制，未使用独立子 Agent，因此仍建议在正式合并流程中保留常规同伴审查

## 需求与设计符合性

- [x] 新 Run 不再创建 `tool_approval` Interaction。
- [x] `message_ask_user` 仍是唯一进入持久化 `WAITING` 的业务输入路径。
- [x] 普通工具按平台 `allow/deny` 策略确定性执行或失败，不由终端用户审批。
- [x] 历史待审批调用在下一条普通消息领取执行权时原子收敛为“未执行”，不会恢复或批准旧工具。
- [x] 历史审批事件仅只读展示，不阻塞输入且不泄露工具参数。
- [x] 设置 API 与前端不再暴露通用审批配置。
- [x] MCP/A2A 的 Provider 生命周期、能力筛选和外部写授权明确留待独立批次。

## 正确性与安全性审查

- Tool Loop 只有 `message_ask_user` 可创建 Interaction；其他工具读取 `get_execution_policy()` 后执行 `allow` 或返回 `deny` 失败结果。
- `Memory.close_pending_tool_calls()` 校验最后一条 Assistant 消息和预期 tool call，并为同一消息的所有悬空调用补齐失败 ToolResult，保持消息协议有效。
- `Session.retire_pending_tool_approval()` 只处理最新的历史 pending approval，追加拒绝/已解决事件并关闭悬空调用；重复调用幂等。
- Repository 在同一 Session 行锁内先收敛历史审批再领取新 Run，防止旧调用与新消息并发执行。
- `risk_level` 仅作为元数据保留，不再触发终端用户确认；显式平台 `deny` 仍然生效。
- 公共绑定更新模型不含内部 `execution_policy`，并以 `extra="forbid"` 拒绝隐藏字段；历史配置迁移仍由内部模型完成。

## 审查发现与整改

### 已整改：公共工具设置接口暴露平台执行策略

- 严重级别：`major`
- 原因：首轮实现复用了内部 `ToolBinding` 作为公共更新模型，使调用方可能提交 `execution_policy`；旧 `approval="ask"` 也可能被内部兼容逻辑静默映射为 `allow`。这会把平台安全策略重新交给终端用户，并产生危险的契约歧义。
- 整改：新增终端用户专用 `ToolBindingUpdate` 和 `RuntimeToolPolicyUpdate`；公共模型仅接受产品可配置字段并禁止额外字段。`ToolConfigService` 将公共更新合并到既有内部策略，公共请求不能覆盖 `execution_policy`。内部 `ToolBinding` 继续只负责读取历史 JSON，并将旧 `deny` 保持为 `deny`、旧 `ask/allow/auto` 收敛为 `allow`。
- 回归：新增对 `approval`、`execution_policy`、`approval_tools`、`require_approval_for_high_risk` 的拒绝测试；工具管理测试 19 项通过，后端全量 460 项通过。
- 状态：`resolved`

## 未发现的开放问题

- Blocking：无。
- Major：无。
- Minor：无已知未处理项。

## 验证门禁

| 门禁 | 结果 | 证据 |
| --- | --- | --- |
| 后端全量测试 | 通过 | `uv run pytest -q`：460 项全部通过 |
| 后端静态检查 | 通过 | `uv run ruff check app tests`：All checks passed |
| 前端全量测试 | 通过 | `pnpm test:run`：44 个文件、185 项全部通过 |
| 前端类型检查 | 通过 | `pnpm type-check` |
| 前端生产构建 | 通过 | `pnpm build`，3678 modules transformed |
| 数据库迁移 | 通过 | 隔离 PostgreSQL 上 `uv run alembic upgrade head` |
| Diff 健康检查 | 通过 | `git diff --check` 无空白错误，仅既有行尾转换提示 |

## 未覆盖与后续事项

- 本批次未在真实部署服务中执行浏览器端人工验收；自动化 API、组件、状态机和构建门禁均已覆盖。服务重新构建/重启后仍应做一次实际多轮对话冒烟测试。
- Sandbox 强化、Provider Execution Classes、Capability Grants、MCP/A2A 懒连接与错误分类属于后续架构批次，不作为本次通用审批移除的阻塞项。
- 未新增数据库 Schema；隔离数据库只验证当前 migration head 可正常应用。

## 最终判断

实现满足“WAITING 只等待用户业务输入、终端用户不审批平台工具”的目标。已整改唯一 `major` 问题，最新测试与构建门禁全部通过，因此代码状态为 `READY_TO_MERGE`；未经用户授权不提交、推送或合并。
