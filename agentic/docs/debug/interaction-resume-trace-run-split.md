# Interaction 回复后原执行仍显示等待

诊断状态：`READY_TO_MERGE`

真实 Session `2d5831ca-4aea-469d-8103-ad0a5c1b4c0a` 已完成并产生最终回复，但原可见输入对应的 Run `d8a0afc1-6a69-41e4-be12-48d3b8ab2d48` 保持 `waiting`；回答后的 `interaction.resolved` 与 `done.created` 被写入新 Run `d7ce056c-a802-4e72-8db8-be430f8d6436`。

调用链：Interaction 回复 → 新 Task → `AgentTaskRunner._prepare_skill_runtime` → 无条件 `TraceService.start_run` → pending/resolved 跨 Run → 原执行卡永久等待。

根因：进程内 Task 生命周期被错误地等同于逻辑 Trace Run 生命周期。恢复必须重建 Task，但必须复用 action_id 对应的原 waiting Run。

修复范围：Trace Repository 增加 waiting Run 查询；TraceService 恢复原 Run 的 plan/step/replan 上下文；AgentTaskRunner 对 `interaction_response` 优先 resume；Execution View 不再把 `wait.created` 投影成第二个 Interaction 节点。

回归门禁：新增三项测试在未修复代码上得到 3 failed；最小实现后 3 passed，既有 Interaction/Trace/Execution View 相关测试 58 passed，隔离 PostgreSQL 后端全量 627 passed，前端相关 14 passed，Ruff 与 compileall 通过。目标历史 Run 已在单事务内追加 resolved/done 并更新为 completed，continuation 历史保持不变。
