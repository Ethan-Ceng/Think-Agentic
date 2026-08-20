# Interaction 恢复 Trace 连续性代码审查

## 审查范围

- 分支：`feature/run-execution-view`
- 基准：`ea3e4d1`
- 需求：用户回答 `message_ask_user` 后，原执行卡不得继续显示等待；Trace 不得把 continuation 拆成第二个逻辑 Run。
- 依据：`docs/debug/interaction-resume-trace-run-split.md`、`docs/plans/interaction-resume-trace-continuity-plan.md`、当前 diff 与最新验证结果。

## 问题列表

未发现 blocking 或 major 问题。

### [minor] 历史分裂 Run 不会自动迁移

位置：现有数据库历史记录

问题：修复只影响后续 Interaction continuation；修复前已经产生的 pending/resolved 跨 Run 数据仍保持原结构。

影响：旧 Session 的原 Run 仍可能显示 waiting，除非做一次性精确收敛；已完成 continuation Run 仍会保留在 Trace 历史中。

处置：不增加全库自动迁移，避免错误合并历史 Run。仅对用户指定的 Session/action_id 做显式、可审计的状态和 resolved 节点收敛，保留 continuation Run 作为历史证据。

## 正确性检查

- 新 Task 仅在 `interaction_response` 存在时尝试恢复 Run；普通新消息仍创建新 Run。
- waiting Run 查询同时限制 user_id、session_id、status 和 pending action_id，不会绑定其他用户或会话。
- 恢复后复用原 run_id/trace_id/input_event_id，并恢复 plan_id、step_id、run_step_id 和 replan_count。
- resolved、后续 Model/Tool/Step 与 done 均写入原 Run；DoneEvent 将 Run 终态更新为 completed。
- 找不到合法 waiting Run 时回退旧行为，兼容缺少 Trace 的历史会话。
- `wait.created` 只保留 Run 状态语义，不再制造第二个 Interaction 节点；实际 WaitEvent 均紧跟 InteractionEvent。

## 安全与一致性检查

- SQLAlchemy 参数表达式用于 action_id 查询，无字符串 SQL 拼接。
- Session 的回答所有权、状态、幂等与并发领取仍由既有行锁事务处理；Trace 查询不扩大回答权限。
- Trace payload 继续使用既有 allowlist，不新增回答正文或工具参数泄露。
- 不新增数据库 Schema 或迁移。

## 测试质量

- RED：新增三项回归在未修复代码上为 3 failed，分别锁定缺失 resume、Runner 错误 start_run、重复 wait 节点。
- GREEN：新增三项 3 passed；相关 Interaction/Trace/Execution View 58 passed。
- 全量：隔离 PostgreSQL 迁移到 head 后 627 passed。
- 前端相关：Run execution/chat 展示 14 passed。
- 静态：Ruff、compileall、git diff check 通过。
- 真实证据：目标数据库查询能按 user/session/action_id 唯一定位原 waiting Run。

## 无法验证项

- 未创建新的付费模型会话；真实新 Session 的主观交互由服务重启后用户复测。
- 修复前的 continuation Run 不做跨表搬迁，避免破坏历史 Token、Model 和 Tool 记录。

## 门禁检查

- 当前分支为普通功能分支：通过。
- 回归测试先 RED 后 GREEN：通过。
- 相关与后端全量测试：通过。
- 静态、编译、前端相关测试：通过。
- 数据库迁移：不适用；隔离库已迁移到现有 head 并完成全量测试。
- blocking/major：无。

## 结论

`APPROVED`。在完成目标 Session 的精确历史收敛、最终复验、提交、推送和重启后可交付。
