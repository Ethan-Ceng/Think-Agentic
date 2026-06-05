# LLMOps 文档入口

记录日期：2026-06-05。

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

2026-06-04 V2.1 落地进展：

- 已新增 `worker_capability_v2` 能力摘要、`routing_policy_v1` 默认策略、稳定错误码和中文提示映射。
- 内部 WorkerAgent 同步 AgentVersion 时会生成并保存 `worker_config.capability_summary`，且刷新时保留 `manual_overrides`。
- Planner worker descriptor 已注入能力摘要，Planner 可在 worker 描述中看到输入模态、语义标签、工具名和模型 features。
- `RouterRuntime` 已增加 capability preflight，图片输入和搜索/最新信息硬需求可被确定性阻断。
- Planner 调试和 manager run 已接入 preflight；失败时任务落库 plan/step/preflight/trace，不再进入 Worker 调用。
- 已新增能力摘要、routing policy 和 preflight 诊断 API。
- 前端已接入 Worker 能力摘要展示、Planner 绑定 Worker 能力摘要、routing policy JSON 编辑/校验/保存、preflight 诊断和任务页 preflight 展示。
- 自动化验证通过：`uv run ruff check app tests`、`uv run pytest -q`、`pnpm type-check`、`pnpm build`；后端测试结果为 `146 passed`。
- 手工验收已确认 Worker 能力摘要、人工修正、routing policy 和 preflight 诊断可用；真实 session/task id 可在后续 V2 回归记录中补充。

2026-06-05 实施口径确认：

- PlannerAgent + 内部 WorkerAgent 主流程已完成本轮落地，不把 A2A 作为本轮必做功能。
- 已完成主流程包含：WorkerAgent id 口径统一、Planner 绑定兼容、任务页/trace 可观测、preflight 主链路稳定、一次动态重规划。
- 执行日志已增强为可排查视图：TraceEvent 会展示 Agent 名称、Planner 调用的 Worker、每个 Worker 执行的 step/task、选择理由、选择信号、Step 输入输出摘要和 WorkerCall Invocation/Result 摘要。
- 任务详情已新增日志筛选和调度回放：可按 Agent、事件类型和关键字过滤；可查看 plan snapshot、replan previous/new plan、plan diff；支持 Planner dry-run 只规划不执行。
- PlannerAgent 页面已避免误请求 Worker `capability-summary`；Planner 不直接维护能力摘要，能力摘要在其绑定的 WorkerAgent 上展示和维护。
- A2A 在产品上可以表现为 Planner 添加外部子 Agent，但架构上只允许表达为外部 WorkerAgent；Planner 通过 `AgentBinding` 绑定它，不直接保存 A2A 协议字段，也不把 A2A 当插件或普通工具。
- 本轮主流程会保留 A2A 接入点：按 `worker_agent_id` 绑定、清理只接受 `worker_app_id` 或 `target_ref_type = "app"` 的调度限制、保留 `executor_type` / `target_ref_type` 派发边界。
- A2A 具体实现暂缓到主流程完成后：`a2a_agents`、Agent Card 同步、A2A executor、URL/SSRF、凭据脱敏和 A2A call trace 后续单独实施。
- V5 已调整并落地为“WorkerAgent Runtime 能力增强”：WorkerAgent 可以在自己的任务边界内具备局部 ReAct 能力，自主选择 RAG、工具、Workflow、API 等 executor，但不能调用其他 WorkerAgent，也不能修改 Planner 的全局计划。
- V5 已完成 5 个执行面经验的首轮落地：Worker 内部 ReAct 循环、工具调用生命周期事件、Planner step 与 Worker internal step 分离、执行状态机、短期记忆压缩与回滚。MCP/sandbox 仅预留 policy 和事件协议，后续独立接入。
- V5 Runtime JSON、WorkerCall 和 TraceEvent 属于登录后后台排障面，不暴露给发布后的 Web App 普通用户。发布端 Web App/OpenAPI 仍可能展示普通 App 的 `agent_thoughts` 运行流程，若面向外部终端用户，建议后续增加发布配置开关，默认隐藏运行流程，只展示最终 answer。
- 已按 `agentic` 精华迁移完成 4 个增强点：Planner/Worker 双层分工保持不变；成功 Worker 反馈可触发受控 plan update；动态更新只追加新计划并只改未执行步骤；等待语义已收敛为 Task `waiting` + `wait.*` trace，plan update trace、step 执行契约和 Worker memory compaction 均进入可回放数据。

本轮完成状态：

1. v2.2-0：主流程兼容清理，统一 Planner 绑定、候选 Worker、requested worker、任务页和 preflight 的 WorkerAgent id 口径。已完成。
2. v2.2-1：Planner Worker 绑定接口支持 `worker_agent_id`，同时保留 `worker_app_id` 兼容内部 App Worker。已完成。
3. v2.2-2：清理内部 Worker 主链路中的 `target_ref_type = "app"` 隐含限制，只有读取 App 展示信息时才依赖 app target。已完成。
4. v2.2-3：任务页、WorkerCall、TraceEvent 统一展示 WorkerAgent、`target_ref_type`、`executor_type` 和 capability snapshot。已完成。
5. v2.3-1：`RouterPlannerAgent.update_plan()`、replan input schema 和 prompt。已完成。
6. v2.3-2：失败触发、改派、最多一次重规划和新计划二次校验。已完成。
7. v2.3-3：任务页原计划/新计划/replan trace 展示。已完成。
8. v2.3-4：完整主流程回归，覆盖内部 Worker、能力缺失、Worker 失败、历史任务回放。已完成；自动化回归为后端 `148 passed`、前端 `pnpm build` 通过。
9. v2.3-5：Agent 选择排查增强，包含选择理由、日志筛选、Step 输入输出、调度回放和 dry-run。已完成；增量验证为后端目标测试 `17 passed`、前端 `pnpm type-check` / `pnpm build` 通过。
10. v2.4：A2A 外部 WorkerAgent 接入，复用前面保留的 WorkerAgent id、`AgentBinding` 和 executor 派发边界。待后续专项；当前暂不纳入主流程。
11. v2.5：执行反馈驱动动态计划更新、Step 执行契约、Task `waiting` 轻量等待和 Worker 记忆/反馈治理。已完成首轮后端落地；目标验证为 `29 passed`，目标 ruff 通过。后续已补状态收敛、任务页可读化展示和 v6-lite 运行分析接口；本轮最终验证为后端 `162 passed`、全量 ruff 通过、前端 `pnpm build` 通过。

中长期路线集中在 Agent Runtime：

- v2：能力感知编排、内部 WorkerAgent 主流程硬化、动态重规划；A2A 外部 WorkerAgent 作为已设计的后续扩展。
- v3：等待用户输入和人工审批。该方向当前暂缓，只在后续企业治理、高风险动作或合规场景中恢复。
- v4：并行 DAG 与依赖执行。该方向建议先做受控 fan-out/fan-in，不做任意 LLM 自由 DAG。
- v5：WorkerAgent Runtime 能力增强。在保持 Planner 协议稳定的前提下，已完成 Worker 内部局部 ReAct 控制、工具事件、状态机、短期记忆压缩、workflow/api trace 与错误归一化；MCP/sandbox 后续按同一协议接入。
- v6：评估、治理、回放和生产化。v6-lite 已基于现有 `AgentTask / AgentPlan / AgentStep / WorkerCall / TraceEvent` 增加只读运行分析，后续继续沉淀评测集和长期报表。

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
