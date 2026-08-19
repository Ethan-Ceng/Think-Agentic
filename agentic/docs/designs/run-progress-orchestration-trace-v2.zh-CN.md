# 长任务编排、进度投影与 Trace 修订设计

## 文档状态

- 状态：`DESIGN_READY`
- 负责人：Codex
- 创建日期：2026-08-20
- 最近更新：2026-08-20
- 基础设计：`docs/designs/run-trace-execution-chain-ux.zh-CN.md`
- 复盘样本：Session `2d5831ca-4aea-469d-8103-ad0a5c1b4c0a`，Run `c1510e7c-e968-4ff7-81ee-6468db35c41f`

## 背景

现有 Run Execution View 已经把 Run、Plan、Step、Tool、Model 和 Trace 事件连成统一合同，但真实长任务回归暴露出三类失配：

1. Runtime 实际串行，页面却把所有 Plan 快照和全部历史 Tool 同时展开，用户误以为步骤并行。
2. Planner 初始消息、每个 Step 结果和例行 `message_notify_user` 都进入对话或执行树，最终答案失去视觉主体。
3. Trace 的 Plan 快照覆盖 Step 生命周期时间，节点同游标后又按随机 ID 排序；Token 汇总依赖懒加载且只有前端当前页，导致时序和统计都不可信。

本次不是重新建设一套执行框架，而是把“Runtime 事实、聊天进度投影、诊断 Trace”重新分层，并修复真实样本已经证明的错误。

## 样本证据与根因

### 1. 步骤并未并行

目标 Run 的四个 Step 没有时间重叠：

| Step | 开始 | 完成 |
| --- | --- | --- |
| 1 | 23:58:20 | 00:01:10 |
| 2 | 00:01:23 | 00:02:54 |
| 3 | 00:03:03 | 00:04:27 |
| 4 | 00:04:34 | 00:05:17 |

旧 `PlannerReactFlow` 每次只通过 `plan.get_next_step()` 取一个 Step，统一 Lead 的 Plan 路径同样是串行循环。因此“并行感”是投影错误，不是调度并发。

### 2. 本次没有使用 Lead Agent

Trace 中存在：

```text
lead.fallback reason_code=feature_disabled
```

主因是 `Settings.lead_agent_enabled` 默认关闭，而本地主机 API 读取 `api/.env`，项目根 `.env` 中的 `LEAD_AGENT_ENABLED=true` 没有进入该进程。随后运行退回旧 `PlannerReactFlow`；旧流程在每个成功 Step 后都调用 Planner 更新计划，造成不必要的模型调用和 Plan 快照。

### 3. 对话信息重复

- `PlannerReactFlow` 和 `LeadAgent._run_plan` 会把 `plan.message` 作为可见 Assistant Message。
- `ReActAgent.execute_step/resume_step` 会把每个 `step.result` 再作为可见 Assistant Message。
- 中英文 ReAct Prompt 鼓励模型在工具调用前后使用 `message_notify_user`，样本中产生 7 次通知工具调用。
- 聊天执行树又展示相同 Step/Tool 事实，因此同一信息以消息、Step 摘要和 Tool 节点重复出现。

### 4. Trace 时序错误

- 每个 `PlanEvent` 都携带整份 Step 快照。
- `_project_plan_steps` 把该 Plan Event 的时间写到所有终态 Step 的 `finished_at`。
- `ExecutionViewAssembler._plan_nodes` 也用 Plan Event 时间构造终态 Step，并在节点合并时偏向后来的 `finished_at`。
- 结果是四个 Step 在 `run_steps` 中都显示为 Plan 最终完成时间，而不是各自的 `step.completed` 时间。
- 所有 Step 在最终 Plan 快照上获得相同 cursor，前端再按随机 `node_id` 排序，步骤顺序不稳定。

### 5. Token 数据存在，但汇总链路错误

样本 55 次 Model Call 均保存了 Token：

- Prompt Token：2,842,163
- Completion Token：25,657
- Total Token：2,867,820

当前 TracePanel 却从“模型”页签懒加载的 `modelCalls` 计算总量；未打开页签时显示 `-`，超过单页上限时还会少算。Execution View 的 Model 节点已有 usage 字段，但 summary 模式丢弃 metrics，Run Overview 也不聚合。

另一个成本根因是 Memory 只压缩 `browser_view/browser_navigate`，不会压缩 `search_web` 和其他大 Tool Result。样本第一步 20 次搜索使 Prompt 上下文从 29,744 增长到 54,958 Token，并被后续 Step 继续携带。

## 产品基准

### OpenAI ChatKit / ChatGPT 式进度

OpenAI ChatKit 把 `ChatKitTask` 定义为工作流的进度/状态对象，并用 `ChatKitTaskGroup` 组织多个任务；它与 Assistant Message 是不同的 Thread Item。这支持“计划项长期存在，活动状态独立更新”，而不是把每次动作追加成对话消息：[ChatKit thread items](https://developers.openai.com/api/reference/typescript/resources/beta/subresources/chatkit/subresources/threads/methods/list_items)。

OpenAI 的模型指导建议只在开始新的主要阶段或计划发生变化时发送简短更新，并避免播报例行工具调用；这与本项目 Prompt 当前要求工具前后通知的策略相反：[OpenAI model guidance](https://developers.openai.com/api/docs/guides/latest-model?model=gpt-5.2)。

### LangGraph 式事件投影

LangGraph 将原始执行事件先归一化，再通过 transformer 输出 messages、values、tasks、debug 等不同 typed projection；多个消费者读取同一底层事实，但不共享同一种展示密度：[LangGraph event streaming](https://docs.langchain.com/oss/python/langgraph/event-streaming)。本项目应沿用同样边界：一个事实流，聊天与 Trace 两种投影。

### Vercel AI SDK 式持久/临时数据分离

AI SDK 的 streaming data 区分持久 data part 与 transient data part；相同 ID 可原位更新，临时数据不写入消息历史：[AI SDK streaming data](https://ai-sdk.dev/docs/ai-sdk-ui/streaming-data)。本项目的“当前正在执行的小动作”应属于 transient projection，Plan/Step 状态和最终消息才是持久事实。

## 目标

- 保证 Plan 模式默认严格串行，并让页面能明确看出“一次只有一个 Step 运行”。
- 正常新 Run 默认进入统一 Lead；Legacy 只作为显式、可观测的兼容回退。
- 聊天区只持久展示总体 Plan Item；当前 Model/Tool 小动作运行时出现，完成即隐藏。
- Plan 初始说明和 Step 结果不再形成可见 Assistant 消息；一个 Run 正常只交付一个最终 Assistant 回复。
- Step 生命周期以 `StepEvent` 为准，Plan 快照不得覆盖真实开始/完成时间。
- Step 使用明确 ordinal 排序，不依赖随机 ID 或相同 cursor。
- Token 从 Execution View 的全部 Model Node 聚合，不依赖模型页签或分页加载状态。
- 压缩已经被模型消费的大 Tool Result，降低长任务跨轮上下文膨胀，同时保留最新观察和结构完整性。

## 功能范围

- Lead 默认开关及 Legacy fallback 可观测性。
- Legacy Plan 成功 Step 不再无条件调用 Planner 更新计划。
- Plan/Step 中间消息可见性规则。
- ReAct 进度 Prompt 和 `message_notify_user` 展示降噪。
- Memory 大 Tool Result 的阶段间和循环内有界压缩。
- ExecutionNode ordinal、Step 生命周期合并、Plan 快照写入语义。
- 聊天 ExecutionTree 的 Chat density 投影。
- TracePanel Token 汇总和诊断节点排序。
- 对应后端、前端和回归测试。

## 非功能范围

- 本阶段不引入并行 Step、Sub Agent DAG 或并行调度器。
- 不删除 Legacy Flow；它继续作为配置关闭和 Lead 决策失败时的回退。
- 不物理删除历史 Trace，也不重写旧 Session 消息；历史页面通过新投影降噪。
- 不展示隐藏 chain-of-thought/reasoning。
- 不引入新的外部 Observability 平台或 Token 计费价格表。
- 不用额外 LLM 调用生成进度摘要。

## 核心规则

1. **Runtime 单写事实**：Step 状态和时间只由 StepEvent 决定；PlanEvent 只描述计划结构、顺序、revision 和快照状态。
2. **串行不靠视觉猜测**：Plan 同一时刻最多一个 Step 为 `running/waiting`；测试直接验证事件序列无重叠。
3. **消息与活动分离**：只有用户输入、必要交互问题和最终交付是对话消息；计划、步骤和工具属于执行投影。
4. **活动是临时投影**：聊天只显示最新 `running/waiting` 的 Model/Tool；成功结束后移除，失败保留可恢复信息。
5. **Plan Item 是持久投影**：总体 Step 标题、顺序和状态保留；聊天不平铺每个 Step 的 result summary。
6. **Trace 保留完整诊断**：完成的 Model/Tool、Step result summary、Token 和技术事件仍可在 TracePanel 查看。
7. **Token 汇总不依赖 UI 页签**：Run total 等于所有 Model Node usage 之和，分页合并后幂等。
8. **压缩不破坏 Tool 协议**：保留 Assistant tool_call 与对应 Tool message，只把已消费的大 content 替换为稳定 compact marker。
9. **Lead 回退必须可见**：任何 fallback 都保留 reason_code；正常配置不得静默走 Legacy。

## 可选方案

### 方案 A：只修前端展示

- 实现方式：聊天过滤 Step summary 和已完成 Tool，TracePanel 改 Token 计算来源。
- 优点：改动小、上线快。
- 缺点：Lead 仍可能关闭，旧 Flow 仍无条件 Replan，Step 时间仍错误，Token 成本继续膨胀。
- 风险：页面更像正确，但底层事实仍不可信。

### 方案 B：修正 Runtime 事实并提供 Chat/Trace 双投影

- 实现方式：启用统一 Lead、保留显式回退；修正 Plan/Step 生命周期、ordinal、消息可见性和 Memory；聊天只投影总体计划与当前活动，Trace 保留完整历史。
- 优点：同时解决用户感知、调度语义、Trace 正确性和成本问题；沿用现有表与 Execution View。
- 缺点：涉及后端 Runtime、Trace 合同和前端组件，需要完整回归。
- 风险：Lead 切流或 Memory 压缩若缺少测试，可能改变长任务结果质量。

### 方案 C：重建独立 Event Stream/Span Runtime

- 实现方式：把现有 Session/Trace 全部替换为新的事件存储和投影器。
- 优点：长期模型最完整。
- 缺点：范围远超本次真实回归，迁移和兼容风险高。
- 风险：为修复现有产品体验引入第二次大规模平台改造。

## 方案对比

| 维度 | 方案 A | 方案 B | 方案 C |
| --- | --- | --- | --- |
| 实现复杂度 | 低 | 中 | 高 |
| 根因覆盖 | 低 | 高 | 高 |
| 数据正确性 | 不变 | 修复 | 重建 |
| 回归风险 | 低 | 中，可测试 | 高 |
| 长期维护 | 前端规则继续膨胀 | 单一事实、双投影 | 新旧系统迁移成本高 |
| 本轮适配度 | 不足 | 最佳 | 过度建设 |

## 推荐方案

采用方案 B。

这次样本已经证明问题不是单纯视觉瑕疵：运行时选错执行链、Plan 快照污染生命周期、Token 聚合与 Memory 策略都存在事实错误。方案 B 保留现有 Execution View 架构，只修清边界，能够在当前分支内通过确定性测试和真实 Session 回归验证。

## 业务流程

### Plan Run

1. Lead 选择 Plan 并生成 Plan/Step 列表。
2. 聊天显示总体 Plan Item；只有第一个 Step 标为运行中，其余等待。
3. Model/Tool 当前活动通过 Execution Update 出现于当前 Step 下。
4. Tool/Model 完成后，其临时活动行从聊天隐藏，但完整记录留在 Trace。
5. StepEvent 完成当前 Step，随后才允许下一 StepEvent started。
6. 中间 Step result 以 `visible=false` 保存，不形成聊天气泡。
7. 所有 Step 完成后只生成一条最终 Assistant Message。

### Fallback

1. 配置显式关闭或 Lead 决策失败时记录 `lead.fallback`。
2. Legacy Flow 仍严格串行；成功 Step 直接发 Plan UPDATED 快照，不再次请求 Planner。
3. 只有失败或 `needs_replan=true` 时才调用 Planner update。
4. TracePanel 显示 fallback reason；聊天不增加技术告警气泡。

## 数据结构

### ExecutionNode 扩展

| 字段 | 类型 | 必填 | 说明 | 默认值 |
| --- | --- | --- | --- | --- |
| `ordinal` | `int/null` | 否 | 同一父节点下的稳定业务顺序；Plan Step 使用 0-based index | `null` |

现有 `metrics.prompt_tokens/completion_tokens/total_tokens` 不新增字段，但 Model Node 在 summary/detail 两种投影中都保留安全数值。

### Chat Activity（前端派生，不持久化）

| 字段 | 来源 | 说明 |
| --- | --- | --- |
| `activeNode` | 最新 running/waiting Model、Tool 或 Interaction | 同时只显示一项 |
| `planItems` | Plan 下的 Step Node | 持久展示标题、ordinal、状态 |
| `failedActions` | failed Tool/Error | 保留到用户查看或 Run 结束 |

## 接口设计

### `GET /runs/{run_id}/execution`

- 保持现有路径和参数兼容。
- ExecutionNode 增加可选 `ordinal`，旧客户端忽略未知字段。
- Model Node 在 `detail=summary` 时也返回 Token/TTFT/count 等安全 metrics。
- Run Overview 对当前返回节点聚合 Token；前端跨 cursor 按 `node_id` 合并后重新计算全量，不从 Model Calls 页签取总数。

### Session MessageEvent

- 不改变公共 Schema。
- Plan 初始消息和 Step 中间结果仍可持久化，但设置 `visible=false`。
- 最终总结、Direct/React 最终交付保持 `visible=true`。

## 错误处理与可观测性

- Lead fallback 记录 reason_code，并在 Trace diagnostic density 展示。
- 检测同一 Plan 多个 Step 同时 running 时标记 `trace_complete=false` 和 `plan_parallel_state` warning；Runtime 测试应阻止新数据出现该状态。
- Token 缺失按“未知”而不是 0 处理；只有至少一个 Model Call 提供 usage 时才展示合计。
- Memory compact 只替换超过阈值且已被至少一次后续 Model Call 消费的 Tool Result；最新观察和待恢复 Tool Call 不压缩。
- 压缩次数、压缩字节数只记录低基数统计，不记录原始内容。

## 迁移与回滚

- 数据库无需新增表或迁移；`ordinal` 是 API 投影字段。
- 新的 Step 时间规则只影响新写入和 API 节点合并；不批量重写历史记录。
- Lead 仍可通过 `LEAD_AGENT_ENABLED=false` 回退 Legacy。
- 前端 Chat density 过滤可以独立回滚，不影响 Trace 数据。
- Memory compact 若出现质量回归，可关闭循环内压缩，仅保留 Step 间压缩。

## 风险

| 风险 | 可能性 | 影响 | 缓解措施 | 验证方式 |
| --- | --- | --- | --- | --- |
| Lead 默认切流后路由质量下降 | 中 | 高 | 保留配置回退；运行 Direct/ReAct/Plan 路由集和真实任务 | Lead 测试 + Session 回归 |
| 中间 Message 隐藏导致最终总结缺资料 | 低 | 高 | 只改 visible，不删除 Memory/Session 事实 | 多 Step 总结测试 |
| Tool Result 压缩过早 | 中 | 高 | 仅压缩已消费且非最近结果，保留协议配对 | Memory/Tool loop 单测 |
| Chat 过滤隐藏失败信息 | 中 | 高 | failed Tool/Error 始终保留 | 失败态组件测试 |
| Token 跨页重复累加 | 中 | 中 | 先按 node_id 合并，再从全量节点重算 | 重复 cursor/分页测试 |
| 历史 Trace 没有 StepEvent 时间 | 中 | 低 | 时间显示未知，不再用晚到 Plan 时间伪造 | 历史 fixture 测试 |

## 重要假设

- 用户要求的是 ChatGPT 式公开执行状态，不是模型隐藏 reasoning。
- 当前 Plan 的业务语义是严格串行；未来如果引入并行 Step，必须增加明确 dependency/group 合同，不能复用本次视觉暗示。
- 一个 Run 的最终 Assistant Message 是唯一交付；中间结果仍可在 Trace 和最终总结上下文中访问。
- 当前 Model Provider 返回的 usage 数据可作为 Token 统计事实；没有 usage 的调用显示未知。

## 待决策项

无。用户已授权按推荐方案落地并提交当前分支；Legacy 回退保留，因此不需要不可逆切换。

## 验收标准

- [ ] 新 Run 默认产生 `lead.strategy_selected`，不再因默认配置出现 `lead.fallback: feature_disabled`。
- [ ] Plan 四个 Step 的事件满足 `start(n+1) > finish(n)`，同一时刻最多一个 Step running/waiting。
- [ ] 成功 Step 不触发 Planner update；只有失败或 `needs_replan` 才调用。
- [ ] 聊天持久显示按 ordinal 排序的 Plan Item；只显示一个当前小动作，动作成功后隐藏。
- [ ] 聊天不显示 Plan 初始说明和每个 Step result 的 Assistant 气泡；正常 Plan Run 只显示最终交付消息。
- [ ] Chat density 不显示已完成 Tool/Model 和 Step result summary；Trace diagnostic 仍可查看完整历史。
- [ ] Step 的 `started_at/finished_at` 来自 StepEvent，后续 Plan UPDATED/COMPLETED 不得覆盖。
- [ ] TracePanel 打开后无需进入“模型”页签即可显示 Prompt、Completion 和 Total Token；超过 100 次调用仍统计完整。
- [ ] Memory 在长 Tool Loop 中对已消费的大结果有界压缩，且 Tool Call/Tool Result 协议配对保持有效。
- [ ] 后端定向与全量测试、Ruff/compileall、前端定向与全量测试、type-check/build 全部通过。
- [ ] 使用新 Session 完成一次真实 Plan 长任务回归，确认 Lead、生效的串行顺序、聊天降噪、Trace 时间和 Token 合计。
