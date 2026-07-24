# 对话编辑、重新生成与会话分支代码审查

## 审查范围

- 目标分支：`master`
- 变更分支：`feature/chat-conversation-branching`
- 变更范围：`a6e6917..working tree`
- 设计文档：`agentic/docs/designs/chat-conversation-branching.zh-CN.md`
- 计划文档：`agentic/docs/plans/chat-conversation-branching-plan.md`
- 审查者：同一 Agent 自检
- 审查日期：2026-07-24

## 需求符合度

- [x] 符合设计文档和服务端、前端验收标准。
- [x] fork、edit、regenerate、lineage、上下文继承和可靠启动均已实现。
- [x] 未擅自扩展为同 Session 消息树或 sibling 分支导航。
- [x] 审查中发现的可靠性偏差均已整改并重新验证。

## 正确性

- [x] 目标事件、角色、源会话状态、空值和异常路径均有校验。
- [x] 分支创建失败不会修改源 Session，也不会隐藏 queued 启动失败。
- [x] edit/regenerate 先持久化 queued next-message，再尝试一次性启动。
- [x] 唯一索引、行锁、嵌套事务和冲突后重读共同处理并发幂等。

## 安全性

- [x] 所有分支和来源详情均按当前用户归属校验。
- [x] 请求 schema 限制 operation、UUID、目标事件和编辑文本长度。
- [x] context seed 只包含可见 user/assistant 消息及附件文件名。
- [x] 日志不记录消息全文、附件路径、工具状态或隐藏事件。

## 可维护性

- [x] 领域实体、仓储、服务、API 和 UI 职责边界清晰。
- [x] 沿用现有 next-message、事件投影和 Session API 模式。
- [x] 新字段具备可逆迁移，旧 Session 的空 lineage 保持兼容。
- [x] 前端一次性导航令牌封装在 `session-init.ts`，存储不可用时安全降级。

## 测试质量

- [x] 核心 fork/edit/regenerate、上下文注入、幂等和权限路径有覆盖。
- [x] 审查中修复的 sessionStorage 降级有回归用例。
- [x] 异常、并发、附件失效和旧 Session 兼容路径有覆盖。
- [x] 后端集成测试使用真实 PostgreSQL，前端同时执行测试、类型检查与生产构建。

## 审查中已整改

### [major，已解决] 存储不可用时误报分支创建失败

位置：`agentic/web/src/lib/session-init.ts`

问题：服务端已经成功创建分支后，`sessionStorage.setItem` 抛错会进入外层失败处理，使页面误以为创建失败并停留在源会话。

整改：导航令牌创建和消费都捕获浏览器存储异常；令牌不可用时仍导航到新 Session，并保留 durable queued 卡片供手工发送。

验证：新增存储不可用回归测试；前端 58 个用例、类型检查和生产构建通过。

### [major，已解决] 网络响应丢失后的人工重试未复用 request_id

位置：`agentic/web/src/components/SessionDetailView.vue`

问题：首次请求在服务端成功但客户端未收到响应时，重新点击会生成新的 request_id，可能创建重复分支。

整改：按源 Session、事件、operation 和编辑内容保存待重试请求；仅在成功导航后清除 request_id。

验证：类型检查、生产构建及服务端唯一索引/并发重放测试通过。

## 当前问题列表

未发现未处理的 `blocking`、`major`、`minor` 或 `suggestion` 问题。

## 无法验证项

无。Codex Browser 运行时当时没有可用连接，随后由用户完成页面表面验收并确认无问题；异常恢复路径已有自动化覆盖。

## 合并门禁

| 门禁 | 结果 | 证据 |
| --- | --- | --- |
| 无 blocking | 通过 | 当前问题列表为空 |
| 无未处理 major | 通过 | 两项 major 已整改并重跑受影响验证 |
| 验收标准满足 | 通过 | 自动化验收通过；用户完成页面表面验收并确认无问题 |
| 相关测试通过 | 通过 | 后端 147 passed；前端 58 passed |
| 构建通过 | 通过 | `vue-tsc -b` 与 Vite production build 通过 |
| 数据迁移已验证 | 通过 | upgrade/downgrade/upgrade 通过，当前唯一 head 为 `20260724_0001` |

## 审查结论

- 结论：`APPROVED`
- 理由：实现与设计一致，审查中发现的两项可靠性问题已整改，当前无未处理代码问题，自动化和迁移门禁全绿。
- 剩余风险：本次为同一 Agent 自检，独立 Reviewer 更可靠。
- 下一步：实施计划已推进到 `READY_TO_MERGE`；等待用户明确授权后再提交或合并。
