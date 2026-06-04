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

V2 定稿后，外部 A2A Agent 不进入插件广场混管，而是同步为外部 WorkerAgent，继续通过 PlannerAgent 的 Worker 编排区域绑定和调度。

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

2026-06-04 最新联调结论：

- Docker Compose 最新服务已重启并可访问，UI `http://localhost:3100`、API `/docs`、UI 代理 `/api/docs` 均返回 200。
- `GAODE_API_KEY` 和 `SERPER_API_KEY` 已在运行环境中生效；内置工具正常路径可成功调用高德天气和 Serper 搜索。
- PlannerAgent 在绑定具备天气/搜索能力的 WorkerAgent 后，询问“今天广州天气怎么样”可以成功编排 Worker 并返回实时天气结果。
- 此前天气失败的根因是工具凭据未配置，不是 PlannerAgent 编排主链路问题。
- 最后一轮 Planner 调试 session `0e37f677-e29c-4b41-a533-299b4e821035` 已抽检：10 条消息、10 个任务、11 次 Worker 调用均能关联 plan、step、worker call 和 trace；多轮追问、多 step、多 Worker、Worker 失败路径均有真实记录。按 v1 基础闭环可以视为大体通过。
- 图片上传和图片识别输入链路已通过：图片可随对话进入任务输入并由支持视觉能力的 Worker 正常返回内容说明。
- 本轮未实际触发 `manager_rule_v1` fallback 和非空 Worker 产物 artifact，不作为 v1 主链路阻塞，后续作为专项边界验证继续补齐。

需要明确一点：PlannerAgent 负责理解目标、拆分步骤、选择 Worker 和汇总结果；它不直接提供天气、搜索、外部 API、文件处理等业务能力。如果绑定的 WorkerAgent 没有实时天气能力，Planner 能正确理解“广州”是上文天气问题的补充，但最终仍只能返回 Worker 能力范围内的结果。

## 4. 后续主线

短期主线是 PlannerAgent v1 收尾：

- 验收清单已固定，天气/搜索真实链路已联通。
- 已用真实任务记录确认任务页主链路能看清 plan、step、worker call 和 trace。
- fallback、Worker 产物 artifact、未绑定 Worker、停止调试等边界继续作为非阻塞专项验证。
- 增加 WorkerAgent 能力模板，例如天气查询 Worker、搜索 Worker、通用问答 Worker、数据分析 Worker。
- 明确“Planner 编排成功但 Worker 能力不足”的用户提示口径。
- V2 定稿已固定为“能力感知编排 + A2A 外部 Worker + 动态重规划”，优先从能力摘要和 preflight 地基开始。

下一步实施顺序：

1. v2.1-1 到 v2.1-2：后端 schema、错误码、提示映射和内部 Worker `capability_summary` 生成。
2. v2.1-3 到 v2.1-5：Planner descriptor 注入、Router preflight、前端能力摘要/编排规则/任务页展示和 v1 回归。
3. v2.2：A2A Agent 注册、Agent Card 同步、SSRF/凭据安全、外部 WorkerAgent 映射、text `message/send` executor。
4. v2.3：Worker 失败或能力不匹配后动态重规划，展示原计划、新计划和改派记录。

中长期路线集中在 Agent Runtime：

- v2：能力感知编排、A2A 外部 WorkerAgent、动态重规划。
- v3：等待用户输入和人工审批。
- v4：并行 DAG 与依赖执行。
- v5：在 `app / a2a_agent` 已具备的基础上，扩展 `workflow / mcp / sandbox / api` 等非 A2A executor。
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
