# 长任务编排、进度投影与 Trace 修订代码审查

## 审查范围

- 目标基线：`4ca02d5`
- 变更分支：`feature/run-execution-view`
- 变更范围：`4ca02d5..working-tree`
- 设计文档：`docs/designs/run-progress-orchestration-trace-v2.zh-CN.md`
- 计划文档：`docs/plans/run-progress-orchestration-trace-v2-plan.md`
- 调试文档：`docs/debug/run-progress-orchestration-trace-v2.md`
- 审查者：同一 Agent 自检
- 审查日期：2026-08-20

## 需求符合度

- [x] 符合设计文档和验收标准。
- [x] Runtime、Execution View、Chat density 和 Trace token 四条修复链均已落地。
- [x] 没有擅自引入并行 Step、事件平台重建或数据库迁移。
- [x] 新真实长任务留给用户在重启后验证，避免未经授权创建会话和消耗模型额度。

## 正确性

- [x] Lead 与 Legacy 均保持单 Step 串行，只有失败或 `needs_replan` 才调用 Planner 更新。
- [x] Step 生命周期由 StepEvent 决定，Plan 快照只更新状态、顺序和摘要。
- [x] 增量节点按 node_id/cursor 幂等合并，ordinal、phase、开始/结束时间和安全 metrics 均保留。
- [x] Token 从合并后的唯一 Model Node 求和，不依赖资源页签或 100 条分页。

## 安全性

- [x] Execution View 继续使用 Trace allowlist，不暴露 Prompt、reasoning、凭据或原始 Tool 结果。
- [x] Memory 只替换已消费 Tool message 的 content，保留 role、tool_call_id、function_name 和 Assistant tool_call 配对。
- [x] 本轮没有新增权限入口、命令执行路径或数据库结构。

## 可维护性

- [x] Chat 和 Diagnostic density 共用 ExecutionNode 合同，差异集中在前端投影函数。
- [x] 后端和前端各自只有一个节点合并入口，生命周期字段不会分散处理。
- [x] 删除了普通 Plan update 计数产生的伪 revision 与失去用途的 revision 缓存。

## 测试质量

- [x] RED 用例分别复现配置、消息、Replan、Memory、时序、顺序、Token 和 Chat 展示问题。
- [x] 覆盖真实 `model.succeeded` 不带 agent_name 的增量事件。
- [x] 覆盖 150 个 Model Node，证明 Token 合计不受单页 100 条限制。
- [x] 原始 Run 真实事件经新投影核对，得到正确时间线和 Token 总数。

## 问题列表

### [major] Model 完成事件覆盖调用阶段

位置：`api/app/services/execution_view.py`、`web/src/lib/run-execution.ts`

问题：真实 `model.succeeded` 事件不包含 `agent_name`，单事件投影会得到默认 `respond` phase，并在后端全量合并或前端 SSE 增量合并时覆盖 `model.started` 已确定的 `plan/decide` phase。

影响：Planner/Lead 模型调用在 Trace 中被错误归类为回答阶段，继续造成阶段链路混乱。

处置：已修复。后端和前端节点合并均保留首次生命周期 phase，并将成功事件 fixture 改为真实缺少 agent_name 的结构；定向和全量复验通过。

未发现其他 blocking、major 或需要延期处置的 minor。

## 无法验证项

- 新长任务的实际模型质量、模型自主选择 Plan 的稳定性和主观视觉感受需要用户在重启后的产品环境继续验证。
- 本次为同一 Agent 自检；若进入多人合并流程，独立 Reviewer 仍更可靠。

## 合并门禁

| 门禁 | 结果 | 证据 |
| --- | --- | --- |
| 无 blocking | 通过 | 完整 diff 自检未发现 blocking |
| 无未处理 major | 通过 | 唯一 major 已修复并复验 |
| 验收标准满足 | 通过 | 定向回归与原始 Run 实际投影 |
| 相关测试通过 | 通过 | 后端 624 passed；前端 230 passed |
| 构建通过 | 通过 | Ruff、compileall、type-check、Vite build、diff check 全部退出 0 |
| 数据迁移已验证 | 不适用 | 产品无 schema 变更；全量测试库迁移到 head 后通过 |

## 审查结论

- 结论：`APPROVED`
- 理由：已发现的问题完成修复，审查后全量复验通过，无未处理 blocking/major。
- 剩余风险：新长任务的产品主观体验需用户验证；同一 Agent 自检不等价于独立 Reviewer。
- 下一步：更新计划为 `READY_TO_MERGE`，按用户授权提交当前分支并重启 API/Web。
