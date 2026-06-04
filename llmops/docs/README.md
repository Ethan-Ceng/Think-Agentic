# LLMOps 文档入口

记录日期：2026-06-04。

本目录只保留 3 份长期维护文档，用于替代历史上分散的调研、计划、实施记录和待办清单。后续新增设计和落地记录，优先更新这 3 份文档，不再按每轮任务新增单独文档。

## 1. 文档地图

| 文档 | 作用 | 主要读者 |
| --- | --- | --- |
| [llmops-architecture.md](./llmops-architecture.md) | 当前平台架构、产品模块、运行链路、实现边界 | 开发、架构、产品 |
| [llmops-agent-runtime-roadmap.md](./llmops-agent-runtime-roadmap.md) | Agent Runtime、WorkerAgent、PlannerAgent 的协议、v1 状态和 v2-v6 路线 | 开发、产品、测试 |
| [README.md](./README.md) | 文档入口、当前结论、维护规则 | 所有人 |

## 2. 当前核心结论

`llmops` 的定位是企业级 Agent 平台控制面和运行治理面，而不是单个 Agent 的本地执行脚本集合。

当前产品口径已经固定为：

```text
AI 应用
  - PlannerAgent
  - WorkerAgent
```

PlannerAgent 和 WorkerAgent 是同级 AI 应用类型，不是上下级资源。两者都在 AI 应用页面创建、管理、调试和发布，通过 `agent_type` 区分：

- `worker`：执行具体能力的 WorkerAgent。
- `planner`：编排多个 WorkerAgent 的 PlannerAgent。

详情页主体复用现有 AI 应用体验。差异主要集中在“应用能力”区域：

- WorkerAgent 配置模型、工具、知识库、工作流等执行能力。
- PlannerAgent 绑定 WorkerAgent，维护可调用 Worker 列表、优先级和启停状态。

## 3. PlannerAgent v1 状态

PlannerAgent v1 目标是跑通基础编排闭环。当前可以按基础闭环通过处理：

- PlannerAgent / WorkerAgent 已作为 AI 应用同级类型管理。
- PlannerAgent 能绑定 WorkerAgent。
- PlannerAgent 调试复用 `/apps/{app_id}/debug-chat`。
- WorkerAgent 仍由 `WorkerRuntime -> ReActWorkerAgent -> AppService.run_app_worker()` 执行。
- Planner 使用 `RouterPlannerAgent.create_plan()` 生成 `RouterPlan`。
- `RouterPlan` 必须经过 Pydantic schema 校验和 `RouterRuntime.validate_plan()` 业务校验。
- Planner 调用失败、输出非法、使用未绑定 Worker、输出 async 或 approval 时，回退到 `manager_rule_v1`。
- Planner 调试已传递 `recent_history` 和 `conversation_id`，短追问可以继承上文意图。
- 任务记录能关联 `AgentTask / AgentPlan / AgentStep / WorkerCall / TraceEvent`。

需要明确一点：PlannerAgent 负责理解目标、拆分步骤、选择 Worker 和汇总结果；它不直接提供天气、搜索、外部 API、文件处理等业务能力。如果绑定的 WorkerAgent 没有实时天气能力，Planner 能正确理解“广州”是上文天气问题的补充，但最终仍只能返回 Worker 能力范围内的结果。

## 4. 后续主线

短期主线是 PlannerAgent v1 收尾：

- 固定验收清单。
- 用真实调试记录确认任务页能看清 plan、step、worker call、trace 和 fallback 原因。
- 增加 WorkerAgent 能力模板，例如天气查询 Worker、搜索 Worker、通用问答 Worker、数据分析 Worker。
- 明确“Planner 编排成功但 Worker 能力不足”的用户提示口径。

中长期路线集中在 Agent Runtime：

- v2：动态重规划。
- v3：等待用户输入和人工审批。
- v4：并行 DAG 与依赖执行。
- v5：Worker executor 扩展到 `app / workflow / mcp / a2a / sandbox / api`。
- v6：评估、治理、回放和生产化。

完整路线见 [llmops-agent-runtime-roadmap.md](./llmops-agent-runtime-roadmap.md)。

## 5. 历史文档处理

以下旧文档已合并进当前 3 份文档，并从目录中移除：

- `llmops-agentic-runtime-design.md`
- `llmops-architecture-and-implementation.md`
- `llmops-enterprise-autonomous-agent-platform-plan.md`
- `llmops-planner-agent-agentic-research-design.md`
- `llmops-platform-foundation-todo.md`
- `llmops-router-planner-agent-mainline-plan.md`

合并原则：

- 架构和实现总结进入 [llmops-architecture.md](./llmops-architecture.md)。
- Agent Runtime、WorkerRuntime、PlannerAgent、agentic 调研结论和 v1-v6 路线进入 [llmops-agent-runtime-roadmap.md](./llmops-agent-runtime-roadmap.md)。
- 过期假设只保留结论，不保留已经被实际产品口径覆盖的历史过程。

## 6. 文档维护规则

- 新增平台模块、运行链路或重要实现边界时，更新 `llmops-architecture.md`。
- 新增 Agent Runtime 协议、PlannerAgent/WorkerAgent 行为、阶段路线或验收清单时，更新 `llmops-agent-runtime-roadmap.md`。
- 文档目录结构变化、主线状态变化时，更新 `README.md`。
- 不再新增一次性计划文档，除非该文档会在完成后合并回这 3 份文档。
