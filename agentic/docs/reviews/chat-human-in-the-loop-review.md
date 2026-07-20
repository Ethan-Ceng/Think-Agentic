# Chat Human-in-the-loop 代码审查

## 审查范围

- 目标分支：`master`
- 变更分支：`feature/chat-human-in-the-loop`
- 变更范围：当前未提交工作区相对 `master` 的 Human-in-the-loop 实现
- 设计文档：`docs/designs/chat-human-in-the-loop.zh-CN.md`
- 计划文档：`docs/plans/chat-human-in-the-loop-plan.md`
- 审查者：同一 Agent 自检
- 审查日期：2026-07-20

## 需求与正确性结论

- 结构化 ask_user、高风险工具审批、拒绝无副作用、Memory 精确恢复、所有权、行锁幂等、SSE 卡片、策略设置和 Trace 脱敏均与设计一致。
- Sandbox 文件读取、普通写入和替换在 `auto` 策略下不触发审批；Shell、浏览器脚本等高风险操作继续确认，显式 `ask/deny` 覆盖不变。
- 审查中发现并整改了一个敏感信息问题：内部 `interaction_response.function_args` 现在只进入 Task input，不进入 Session 历史或 Message SSE；Interaction SSE 参数也在服务端递归脱敏。
- 未新增数据库列或迁移，旧 Session 事件与旧 ToolConfig 依靠默认值继续解析。

## 问题列表

### [minor] resolved 事务与恢复 Task 启动之间仍存在极小失败窗口

位置：`api/app/services/agent_service.py:214`、`api/app/controllers/session.py:258`

问题：resolved 事件在返回 EventSourceResponse 前提交，而恢复 Task 在 SSE 生成器开始迭代后创建。如果进程恰好在两者之间退出，交互已经是 resolved，但工具尚未继续。

影响：这种极端中断下不能通过再次点击同一审批动作自动恢复；需要使用现有任务恢复入口或人工重新发起。正常刷新、pending 阶段服务重启和并发双击不受影响。

建议：后续引入持久化 execution lease/outbox，或为 interaction 增加 `resuming` 状态与恢复扫描器；在没有工具级幂等键前，不应通过简单重放自动规避该窗口，以免重复副作用。

处置：记录为非阻塞已知限制，本期不扩大到持久化任务编排。

## 无法验证项

- PostgreSQL 与 Redis 未启动，依赖应用 lifespan/真实 Repository 的后端测试无法完成；全量套件 173 项中出现 11 个失败，均为连接拒绝。排除这些既有依赖型文件后 150 项通过，另有 1 个健康检查同样因 PostgreSQL 连接拒绝而无法执行。
- 当前会话没有可用浏览器实例，无法进行真实页面截图、暗色模式和触屏视觉检查。
- 没有新增数据库迁移，因此迁移验证不适用；DB 行锁 SQL 仅完成静态编译与领域/服务测试，未连接真实 PostgreSQL 执行。

## 合并门禁

| 门禁 | 结果 | 证据 |
| --- | --- | --- |
| 无 blocking | 通过 | 自审未发现 blocking |
| 无未处理 major | 通过 | 敏感载荷泄漏已整改并增加回归测试 |
| 验收标准满足 | 部分通过 | 功能聚焦 36 项全部通过；真实 DB/浏览器项未验证 |
| 相关测试通过 | 通过 | 后端聚焦 36/36；前端 34/34 |
| 构建通过 | 通过 | `pnpm build` 退出码 0 |
| 数据迁移已验证 | 不适用 | 本期不新增迁移 |

## 审查结论

- 结论：`APPROVED`
- 理由：未发现 blocking/major，审查发现的敏感参数外泄已整改并由测试锁定；剩余一个分布式启动窗口记录为 minor。
- 剩余风险：同一 Agent 自审不如独立 Reviewer；真实 PostgreSQL/Redis、浏览器视觉和真实行锁并发仍未验证。
- 下一步：补齐外部环境验证后将计划从 `BLOCKED` 更新为 `READY_TO_MERGE`；不自动提交、推送或合并。
