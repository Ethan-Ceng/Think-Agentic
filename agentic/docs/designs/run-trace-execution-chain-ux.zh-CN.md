# Run Trace 与页面执行链路优化

## 文档状态

- 状态：`DESIGN_FINAL`
- 负责人：Codex
- 创建日期：2026-08-19
- 最近更新：2026-08-19
- 上位路线：`docs/designs/post-lead-foundation-system-roadmap.zh-CN.md`
- 适用范围：现有统一 Lead、Session SSE、Run/Trace 表和聊天执行过程 UI

## 背景

当前系统已经建立最小 Run/Trace 闭环：后端保存 Run、Step、Tool Call、Model Call、Trace Event 和 Run Skill，前端会话页可打开 TracePanel 查看时间线、步骤、工具、模型和 Skills。聊天时间线也会把 Step 与 Tool 组合成 `ThinkingBlock`。

但“记录”和“展示”仍是两套松散投影：

- `GET /runs/{run_id}` 每次一次性读取全部 Step、Tool、Model、Event 和 Skill，单项子接口又通过完整详情间接读取所有表；大 Run 会重复加载和传输。
- Trace Event 只有 `created_at` 和随机 ID，没有稳定游标、父子关系和统一节点语义；页面只能按时间排序并展示原始 event type/payload。
- Lead Strategy、Plan、Step、Model、Tool、Interaction 和最终回答散落在不同表/事件中，用户看不到一条清晰的因果链。
- TracePanel 手动刷新，不随当前 Run 实时更新；聊天页只消费 Session Step/Tool，Direct/ReAct/Plan 的呈现不一致。
- `ThinkingBlock` 使用“思考过程”文案，但实际展示的是公开 Step 描述、进度消息和 Tool Call，容易让用户误以为系统在展示模型隐藏思维链。
- 当前 Model Trace 会保存 `request_preview.messages`、完整 `base_url` 和 `response_preview.reasoning_content`；Tool Trace 也有原始 arguments/result 字段。只按字段名脱敏不足以成为稳定的用户展示和长期存储策略。

因此必须同时优化两层：后端建立安全、稳定、可增量消费的执行链投影；前端用同一合同分别提供简洁的用户执行过程和详细 Trace，而不是继续在浏览器拼接几组原始表。

## 目标

- 将一次 Run 表达为从 Lead 决策到最终回复的有序执行节点链，覆盖 Direct、ReAct、Plan 和 Ask/Resume。
- 页面实时展示“当前在做什么、为什么选择这种模式、调用了什么、结果如何、耗时多少”，不展示隐藏思维链。
- TracePanel 与聊天内联执行过程使用同一后端投影，刷新后、SSE 重连后和历史查看时语义一致。
- 默认 Trace 不保存或返回系统 Prompt、完整消息正文、模型隐藏 reasoning、凭据、完整 URL、Header 或未经策略处理的 Tool 原始参数/结果。
- 大 Run 支持服务端稳定排序、游标增量和按需详情，避免一次性加载所有原始记录。
- Trace 失败继续是观测降级，不阻断 Agent 正常回答；但丢失、乱序和投影失败可被发现。

## 功能范围

### 1. Run Trace 优化

- 定义统一、版本化 `RunExecutionView / ExecutionNode` 合同。
- 为 Trace Event 增加可增量读取的稳定 cursor、节点身份、父节点和用户安全摘要。
- 建立 `ExecutionViewAssembler`，服务端组合 AgentRun、TraceEvent、Step、Tool、Model、Skill 和 Interaction。
- 修正 Trace 写入与读取的敏感信息边界，移除隐藏 reasoning 和原始 Prompt/响应展示。
- Run 详情提供模式、状态、耗时、TTFT、Token、Step/Tool/Model 数量和 FailureInfo 汇总。
- 现有 `/runs` 接口保持兼容，新增执行链接口；旧详情接口内部改为直接查询和分页，不再隐式加载全部数据。
- 新增仅用于实时传输的 `execution_update` SSE envelope；数据库 Trace 是刷新后的事实源，不把该 envelope 重复写进 `sessions.events`。

### 2. 页面执行链路优化

- 聊天主入口采用“正在思考与执行 / 已思考并执行 N 秒”，展开层使用“思考与执行详情”；这里的“思考”只表示公开的 Lead 决策摘要、Planner 计划和执行进度，不表示模型隐藏思维链。
- 每次用户输入对应一个 Run Execution Card，按 Run 隔离，不再仅按“最近一个 Step”猜测 Tool 归属。
- 简单 Direct Run 默认折叠为一行；复杂 ReAct/Plan Run 在运行中展开，完成后可折叠。
- 展示用户可理解的 Lead 模式摘要、计划、步骤、模型阶段、工具调用、等待用户、失败和最终完成。
- Tool 详情继续复用现有 ToolPreviewPanel；Model 节点只展示模型、TTFT、总耗时、Token、工具范围数量和结束原因，不展示请求/响应正文。
- TracePanel 改为“概览 + 执行链 + 工具 + 模型 + Skills + 技术事件”，技术事件默认收起并使用安全 payload。
- 历史 Session、页面刷新和 SSE 重连后能从执行链接口恢复相同展示。

## 非功能范围

- 不展示、推导或持久化模型隐藏 chain-of-thought/reasoning 内容。
- 不通过额外 LLM 调用生成“思考摘要”；首期摘要来自稳定 reason_code 映射、Plan/Step 描述和 Tool/Failure 元数据。
- 不把 Trace 升级为 Durable Run 的状态权威，也不从 Trace 恢复 Agent 执行。
- 不在本阶段接入 Langfuse、Jaeger、Tempo 或完整 OpenTelemetry Collector。
- 不建设跨用户管理员观测台、成本计费、告警系统或 Eval 数据集；本设计只提供后续 Quality Loop 需要的安全数据合同。
- Provider 设置页的手工连接诊断仍不是 Agent Run，不进入聊天执行链；后续可在独立诊断活动中通过 `debug_id` 关联失败 Run。
- 不实现本地 Sub Agent DAG；数据合同允许父子节点，但页面首期只渲染当前单 Lead 的纵向树。

## 业务流程

### Direct

1. 用户发送简单问题，后端创建 Run。
2. Lead 记录 `strategy` 节点，公开摘要为“直接回答，无需工具”。
3. Model 节点进入运行中，页面显示“正在组织回答”。
4. Assistant Message 完成后，Run 节点完成；执行卡折叠显示模式、耗时和 Token。

### ReAct

1. Lead 记录“需要逐步使用工具”的策略摘要。
2. 每一轮 Model Decision、Tool Call 和 Observation 形成有父子关系的节点。
3. 页面实时更新当前工具、结果摘要和失败状态；Tool 参数/结果详情由安全 Tool Preview 提供。
4. 最终模型生成回答，Run 汇总工具次数、模型次数、耗时和失败恢复。

### Plan

1. Lead 记录“复杂任务，先制定计划”的策略摘要。
2. Plan 节点包含公开目标和 Step 列表；Step 状态更新映射到同一节点。
3. Model、Tool 和 Interaction 节点归属具体 Step；Replan 作为 Plan 子节点记录原因码和次数。
4. 所有 Step 完成后生成最终回复，执行卡保留可折叠的完整过程。

### Ask/Resume

1. `ask_user` 产生 Interaction 节点，Run/Step 显示“等待你的输入”。
2. 用户回答后同一节点变为 resolved，原 Run Execution Card 继续更新。
3. 不显示“恢复对话”或 Tool Approval；回答是业务流程的一部分。

### 失败与取消

1. Model、Tool、Provider 或 Run 失败映射为对应节点 FailureInfo。
2. 页面展示稳定消息、错误码、可恢复动作和 `debug_id`，不展示原始异常。
3. 用户取消显示为明确终止节点；Trace 写入失败只显示“执行记录暂不可用”，不伪造 Agent 失败。

## 核心规则

1. **执行过程不等于隐藏思维链**：只展示结构化决策摘要、公开计划、动作、Observation、Evidence、状态和指标。
2. **一个用户输入对应一个 Run Card**：节点归属以 `run_id/node_id/parent_node_id` 为准，不依赖浏览器对相邻事件的猜测。
3. **Trace 是观测投影**：Session/Agent Runtime 仍是当前执行事实；Trace 丢失不得改变 Run 业务结果。
4. **先写事实再通知页面**：`execution_update` 只能在安全 Trace 投影写入成功后发送；重连以执行链 API 为准。
5. **公开摘要与技术详情分层**：聊天页只用 summary；TracePanel 可读取 detail，但两者都不能返回 hidden/internal 数据。
6. **不保存原始模型请求/响应**：Session 已保存用户可见消息；Trace 只保存消息角色/数量/长度/Hash、工具范围和模型指标。
7. **Tool 可见性由服务端策略决定**：公共 Trace 不返回原始 arguments/result，仅返回 Tool Descriptor 允许的字段和固定长度摘要。
8. **稳定顺序由服务端提供**：客户端不再自行用时间戳拼接因果顺序；cursor 支持增量和重连补拉。
9. **Direct 也有最小执行链**：至少包含 Run、Strategy、Model/Response 和 Completion，不能因为没有 Step 就完全不可观察。
10. **Provider 诊断单独建模**：不为展示方便创建假 Run 或写入会话 Trace。

## 现有实现分析

### 相关代码与文档

- `api/app/models/run_trace.py`：已有 `agent_runs/run_steps/tool_calls/model_calls/trace_events`，Tool/Model 可关联 `run_step_id`，但 TraceEvent 缺少 cursor 和父子节点。
- `api/app/services/trace_service.py`：已经记录 Lead Strategy/Fallback/Replan/Completion、Model TTFT/Token、Skill 和运行事件；同时仍保存模型消息预览、`reasoning_content` 和完整 `base_url`。
- `api/app/repositories/db_trace_repository.py`：列表按 `created_at` 排序，无游标；`get_run_detail` 读取全部子表。
- `api/app/controllers/runs.py`：已有 Run、Event、Tool、Model 和 Skill 查询接口，但返回未版本化 dict，子接口存在重复全量加载。
- `web/src/components/TracePanel.vue`：前端一次性拉取完整详情，在浏览器排序，并直接格式化原始 payload JSON；仅手动刷新。
- `web/src/lib/session-events.ts`：聊天时间线按最近 Step 把 Tool 归组，Plan/Wait/Done 不进入时间线，Direct Tool 和并发事件只能近似关联。
- `web/src/components/chat/ThinkingBlock.vue`：已具备折叠、Step 状态和 Tool Group，可复用视觉结构，但“思考过程”命名和数据来源需要替换。
- `web/src/components/chat/ToolPreviewPanel.vue`：已有不同 Tool 类型的详情展示，可以继续作为执行节点的详情面板。

### 可复用能力

- Lead 已输出稳定 `mode/reason_code/replan_count`，无需额外模型调用即可生成安全策略摘要。
- PlanEvent、StepEvent、ToolEvent、InteractionEvent、ErrorEvent 和 DoneEvent 已有稳定 ID 与状态。
- ToolDescriptor 已包含 provider、source、executor、execution_class、risk 和资源需求，可用于安全、友好的节点元数据。
- ModelCall 已有 provider、model、message/tool 数量、Token、TTFT、总延迟和 finish_reason。
- FailureInfo 已统一错误类型、稳定 code、recovery_actions 和 debug_id。
- Session SSE 已有增量消费、重复/乱序防护和重连加载，可增加向后兼容的 transport-only execution update。

### 当前约束

- 当前只有用户级鉴权，没有独立 operator/admin 角色；本阶段公共 Run API 只能返回当前用户自己的安全详情。
- 现有历史 Trace 可能包含 `reasoning_content`、消息内容和完整 base URL，不能只修前端隐藏。
- `created_at` 精度和并发提交顺序不足以作为稳定游标；随机 UUID 不能解决顺序。
- Trace 写入采用 best-effort，Agent 不应因观测数据库失败而中断。
- 未来 Durable Runtime 会引入规范 Event/Outbox；本阶段字段命名必须避免假装当前 Trace 已是可恢复事实源。

## 可选方案

### 方案 A：只优化现有 TracePanel 和 ThinkingBlock

- 实现方式：继续消费现有详情接口，在前端对 Event/Step/Tool/Model 排序、分组和翻译文案。
- 优点：开发快、后端改动少、无迁移。
- 缺点：因果关系仍靠猜测，Direct/ReAct/Plan 不一致，历史刷新和实时 SSE 使用两套数据，安全字段仍在 API 与数据库中。
- 风险：页面看起来更好，但 Trace 合同和敏感信息问题继续积累。

### 方案 B：统一服务端 Execution View，双层页面消费

- 实现方式：扩展现有 Trace Event，新增 ExecutionViewAssembler 和增量接口；聊天执行卡与 TracePanel 共用 ExecutionNode，只在展示密度上区分。
- 优点：语义统一、可增量、可重连、可测试；复用现有表，不把 Trace 变为另一套 Runtime；能先修安全边界。
- 缺点：需要迁移、Trace 写入调整、API 版本化和前端两处重构。
- 风险：如果节点合同过度贴合当前 Lead，未来 Durable/Sub Agent 仍需扩展。

### 方案 C：接入外部 Observability 平台并嵌入页面

- 实现方式：用 OpenTelemetry/Langfuse 风格 Span 替代或旁路现有 Trace，将外部查询嵌入管理页面。
- 优点：指标、搜索、Span、采样和告警生态完整，适合大规模运营。
- 缺点：新增部署和隐私边界，外部 Span 不天然对应当前 Session UX；聊天执行过程仍需单独合同。
- 风险：双写、供应商绑定和敏感数据外发，复杂度远超当前阶段。

## 方案对比

| 维度 | 方案 A：前端增强 | 方案 B：统一 Execution View | 方案 C：外部平台 |
| --- | --- | --- | --- |
| 实现复杂度 | 低中 | 中高 | 高 |
| 维护成本 | 前端规则持续膨胀 | 单一服务端合同，适中 | 内外两套观测与部署 |
| 数据正确性 | 低中 | 高 | 高，但需适配业务语义 |
| 安全边界 | 无法彻底解决存储问题 | 可在写入与接口双层收口 | 额外增加外发风险 |
| 实时/重连 | 两套近似逻辑 | 统一快照 + 增量 | 平台实时，聊天仍需桥接 |
| 兼容性 | 高 | 新接口兼容旧接口 | 高改造成本 |
| 测试难度 | 中 | 中高，可做合同测试 | 高，包含外部系统 |
| 交付价值 | 主要改善视觉 | 同时改善数据、UX 和质量底座 | 偏运维平台 |
| 主要风险 | 美化错误模型 | 合同设计过宽 | 过度建设与隐私风险 |

## 推荐方案

采用方案 B：统一服务端 Execution View，聊天页和 TracePanel 分层消费。

只改页面无法解决当前 Trace 的全量查询、顺序、父子关系、历史重连和敏感字段问题；先接外部平台又不能直接改善用户对执行过程的理解。方案 B 能复用已有 Trace 表和事件，只增加一个明确的安全投影层，并为后续 Agent Quality Loop 提供稳定数据。

首期只表达单 Lead 的纵向树，不设计通用任意 DAG 编辑器；`parent_node_id` 是当前 Step/Tool/Model 因果关系的必要字段，也能自然兼容后续扩展。

## 最终交互方案

最终页面采用“ChatGPT 式渐进展开 + Planner 一等节点 + mooc-manus 步骤工具树”，但不把模型隐藏 reasoning 当作产品数据。

### 1. 消息级布局

每次用户输入对应一个 `RunProcessBlock`，固定放在该用户消息与最终 Assistant 回复之间：

```text
用户消息

  ▸ 已思考并执行 18 秒 · 计划 3/4 · 调用 5 个工具

Assistant 最终回复
```

展开后：

```text
用户消息

  ▾ 思考与执行详情                         18 秒
     判断任务类型：任务较复杂，先制定计划

     任务计划                              3/4
     ✓ 1. 检查现有实现
        └─ 读取 6 个文件
     ✓ 2. 对比可选方案
        └─ 搜索相关资料
     ● 3. 形成最终设计                     进行中
        ├─ 更新设计文档
        └─ 校验文档结构
     ○ 4. 输出结论                         等待中

     计划已调整 1 次

Assistant 最终回复
```

`RunProcessBlock` 是消息的一部分，不是页面底部的全局任务面板。这样历史会话、多轮并发输入、Ask/Resume 和页面刷新后都不会把某个计划错误绑定到另一轮消息。

### 2. 折叠与展开规则

- 新 Run 默认显示一行紧凑状态，不用大卡片抢占聊天空间。
- Direct 在生成回复时显示“正在组织回答”，完成后如果没有工具、等待或错误，可折叠为“已思考 N 秒”，也允许短回答完全隐藏过程行。
- ReAct 显示“正在思考与执行 · 当前动作 · 工具数”，点击后展开逐步动作和 Tool。
- Plan 显示“正在执行计划 · 已完成 N/M”，点击后展开完整 Planner 与步骤工具树。
- 用户主动展开或收起后，本 Run 后续 SSE 更新不得重置该选择。
- `waiting`、`failed` 状态在紧凑行中必须明显可见；具体 Ask 表单和恢复动作仍放在对话正文中，不藏在详情面板里。
- 完成后默认收起；失败时保持最后状态可见，但不强制展开整条历史。

### 3. Planner 是一等展示节点

Planner 不能继续只作为输入框上方的 `PlanPanel`，也不能被当成普通 Step。它是 Plan 模式 Run 的一级节点，位于 Lead 决策之后、执行 Step 之前。

Planner 展示内容：

- 计划标题或公开目标。
- 当前进度 `completed_steps / total_steps`。
- 每个 Step 的编号、描述、状态和安全结果摘要。
- 当前 Step 及其 Tool 子节点。
- `revision` 和 `replan_count`；发生重规划时显示“计划已调整 N 次”。
- 最终计划状态：完成、部分完成、失败或停止。

Planner 更新规则：

- 首次 `PlanEvent.CREATED` 建立 Plan 节点和稳定 Step 节点。
- `PlanEvent.UPDATED` 按 `step_id` 原位更新，不重复插入整份计划。
- 已完成 Step 不允许因后续 Replan 被改写；新增、删除或替换的未完成步骤形成新 `revision`。
- 聊天页只显示当前 revision 和调整次数；TracePanel 才提供 revision 变更历史。
- Direct/ReAct 没有正式计划时不制造空 Planner；ReAct 的动作轮次作为执行节点展示。

### 4. 展开详情的信息层级

详情只包含四层公开信息：

1. **Lead 决策摘要**：由稳定的 `mode + reason_code` 映射，例如“任务较复杂，先制定计划”，不额外调用模型生成解释。
2. **Planner**：计划目标、Step、进度、调整次数和状态。
3. **执行动作**：Step 下的 Tool、公开进度消息、安全 Observation/结果摘要、耗时和 FailureInfo。
4. **完成摘要**：总耗时、Step/Tool 数量、是否发生重规划或降级。

Model Call 不作为聊天页的主节点反复出现。聊天页只在确有价值时显示“正在规划 / 正在判断下一步 / 正在组织回答”等阶段标签；provider、model、TTFT、token、finish reason 放在 TracePanel 的模型页签中。

### 5. 两个页面的职责

| 页面 | 面向对象 | 默认密度 | 展示重点 |
| --- | --- | --- | --- |
| 聊天页 `RunProcessBlock` | 终端用户 | 低，单行折叠 | 当前动作、Planner 进度、Step/Tool 结果、等待和失败 |
| `TracePanel` | 开发与诊断 | 高，按需展开 | 完整 ExecutionNode、时序、模型指标、Tool 安全详情、Skills、技术事件 |

两者必须读取同一个 `RunExecutionView`，不能分别重新解释 Session Event 和 Trace 表。

### 6. 与参考实现的关系

- 采用 ChatGPT 的渐进披露原则：默认一行状态，点击查看过程，最终答案保持视觉主体。
- 采用 mooc-manus 的 Step 行、状态图标、Tool 沿 Step 向下展开和紧凑时间提示。
- 保留当前 agentic 已增强的 Tool 分组、失败恢复、Ask/Resume、手动展开状态和 Trace 指标。
- 不沿用 mooc-manus 将最新 Plan 固定在 Composer 上方的方式；该位置无法可靠表达多轮 Run 归属。
- 不直接展示模型 `reasoning_content`；“思考与执行详情”来自结构化公开事件。

### 7. 组件收敛

- 新增 `RunProcessBlock.vue`：紧凑头部、展开状态和模式分派。
- 新增 `ExecutionTree.vue`：统一渲染 Strategy、Plan、Step、Tool、Interaction、Error 和 Completion。
- 将 `PlanPanel.vue` 收敛为 `PlannerNode.vue`，嵌入 ExecutionTree，不再挂在 Composer。
- 将 `ThinkingBlock.vue` 的视觉与 Tool 展开能力合并进 `ExecutionTree`，完成兼容期后移除旧组件。
- 继续复用 `ToolPreviewPanel.vue`；聊天页 Tool 行只传安全 detail reference，不接收原始 Trace payload。
- `TracePanel.vue` 复用 ExecutionTree 的节点行组件，但使用诊断密度和额外页签，不复制一套组装逻辑。

## 页面信息架构

### 聊天内联 Run Execution Card

卡片头部：

- 状态：运行中、等待输入、已完成、失败、已停止。
- 模式：直接回答、逐步执行、计划执行。
- 当前动作：正在判断、正在搜索、正在读取文件、正在生成回答等。
- 汇总：总耗时、Tool 次数；完成后可选显示 Token。

节点默认文案：

| 节点类型 | 用户文案示例 | 默认详情 |
| --- | --- | --- |
| strategy | `直接回答，无需工具` / `需要逐步使用工具` / `复杂任务，先制定计划` | mode、稳定 reason label、决策耗时 |
| plan | `已制定 4 个步骤` | Step 标题与状态 |
| step | Step 公开描述 | 状态、耗时、结果摘要 |
| model | `正在判断下一步` / `正在组织回答` | 模型名、TTFT、总耗时、Token |
| tool | `搜索网页：…` / `读取文件：…` | 安全参数摘要、结果状态、耗时 |
| interaction | `等待你的输入` | 问题和已选择答案摘要 |
| error | 稳定 FailureInfo.message | code、debug_id、恢复动作 |
| completion | `任务已完成` | 总耗时、Step/Tool/Model 数 |

交互规则：

- Direct 完成后默认折叠；运行中只显示当前节点和轻量动画。
- ReAct/Plan 运行中默认展开当前节点，已完成历史节点折叠为摘要。
- 用户手动展开/折叠后不被状态更新强制重置。
- 点击 Tool 节点打开 ToolPreviewPanel；点击失败打开对应设置或重试动作。
- Model 节点没有“查看思维”入口。

### TracePanel

- 概览：状态、模式、开始/结束、总耗时、TTFT、Token、Step/Tool/Model/Skill 数、错误码。
- 执行链：与聊天卡相同节点，但展示完整安全摘要、节点 ID 和父子关系。
- 工具：按 Step/Provider/执行后端过滤，详情复用 ToolPreview。
- 模型：按 Agent/阶段展示模型、消息数量、Tool Schema 数量/字节、TTFT、总耗时、Token、finish_reason。
- Skills：保留现有 RunSkillsPanel。
- 技术事件：默认收起，显示安全 event type、cursor、node_id、时间和白名单 payload；不直接 dump 任意 JSON。

## 数据结构

### TraceEvent 扩展

| 字段 | 类型 | 必填 | 说明 | 约束/默认值 |
| --- | --- | --- | --- | --- |
| `ingest_seq` | bigint identity | 是 | 全局稳定增量 cursor | 只增；用于 `after` 补拉，不宣称是 Runtime 规范序号 |
| `schema_version` | smallint | 是 | Trace payload 合同版本 | 首期 `2`；历史为 `1` |
| `node_id` | string | 是 | 归属执行节点 | Run 内稳定，由领域实体 ID 派生 |
| `parent_node_id` | string/null | 否 | 父节点 | Run 根节点为空 |
| `visibility` | `user/internal` | 是 | 是否允许公共 Run API 返回 | 默认 `user`；hidden reasoning 不得以 internal 形式保存 |
| `summary` | string | 是 | 固定长度用户安全摘要 | 最大 300 字符 |
| `payload` | jsonb | 是 | 白名单技术属性 | 不含原始 Prompt/响应/Secret |

`ingest_seq` 只描述观测写入顺序，不替代未来 Durable `run_seq`。历史数据按 `created_at + id` 生成只读顺序并标记 `schema_version=1`；新数据使用数据库 identity cursor。

### ExecutionNode

| 字段 | 类型 | 必填 | 说明 | 约束/默认值 |
| --- | --- | --- | --- | --- |
| `node_id` | string | 是 | Run 内稳定节点 ID | 不包含 URL、Prompt 或用户正文 |
| `parent_node_id` | string/null | 否 | 父节点 | 形成单 Lead 纵向树 |
| `kind` | enum | 是 | `run/strategy/plan/step/model/tool/skill/interaction/error/completion` | 固定枚举 |
| `phase` | enum | 是 | `decide/plan/execute/wait/respond/finalize` | 用于文案与分组 |
| `status` | enum | 是 | `pending/running/waiting/succeeded/failed/cancelled` | 统一旧状态 |
| `title` | string | 是 | 用户可见短标题 | 最大 120 字符 |
| `summary` | string | 是 | 用户安全摘要 | 最大 500 字符 |
| `cursor` | bigint | 是 | 最新投影 cursor | 支持增量覆盖同一节点 |
| `started_at` | datetime/null | 否 | 开始时间 | UTC |
| `finished_at` | datetime/null | 否 | 结束时间 | UTC |
| `latency_ms` | int/null | 否 | 节点耗时 | 非负 |
| `metrics` | object | 是 | token/ttft/schema/tool 等白名单指标 | 无价格则不计算 cost |
| `failure` | FailureInfo/null | 否 | 稳定失败 | 不含原始异常 |
| `detail_kind` | string/null | 否 | `tool/model/step/interaction` | 指向安全详情类型 |
| `detail_id` | string/null | 否 | 详情记录 ID | 仍需当前用户 Run 权限 |

### RunExecutionView

| 字段 | 类型 | 必填 | 说明 |
| --- | --- | --- | --- |
| `schema_version` | int | 是 | Execution View 版本 |
| `run` | object | 是 | 安全 Run 概览、mode、状态和聚合指标 |
| `nodes` | ExecutionNode[] | 是 | 服务端有序节点或增量变更 |
| `next_cursor` | bigint/null | 否 | 后续增量读取位置 |
| `has_more` | bool | 是 | 是否还有节点/更新 |
| `trace_complete` | bool | 是 | Trace 投影是否完整；不等同于 Run 是否成功 |

## Trace 安全策略

### 新写入禁止项

- `reasoning_content`、analysis、hidden chain-of-thought。
- System/Developer Prompt、完整 messages、Skill 正文和完整模型响应。
- 完整 `base_url`、userinfo、query、Header、Cookie、Token、API Key 和环境变量。
- 未经 Tool Trace Policy 白名单处理的原始 arguments/result。
- Shell 完整环境、主机路径、堆栈和上游响应正文。

### 允许项

- 模型 Provider 的安全 ID、model name、message/tool 数量、schema bytes、Token、TTFT、总耗时和 finish_reason。
- ToolDescriptor 标识、Provider ID、execution backend/class、资源需求、状态、耗时、arguments hash。
- 每类 Tool 明确允许的摘要，例如搜索 query 的截断文本、沙箱相对文件名、HTTP host 的安全 Provider ID；不默认允许任意字段。
- Plan/Step 的公开描述、状态和结果摘要；FailureInfo 的稳定字段。

### 历史数据处理

1. 公共 API 立即在投影层删除 `reasoning_content`、base_url、message content 和原始 arguments/result，即使数据库尚未清理。
2. 一次性迁移清除历史 `model_calls.response_preview.reasoning_content` 和 request message content，并把 base_url 归一化为安全 Provider ID 或空值。
3. Tool 原始 arguments/result 在确认没有审计依赖后清空；保留 hash、安全 preview 和结构化元数据。
4. 迁移只在备份和隔离验证后执行，记录清理行数，不在日志输出被清理内容。

## 接口设计

### `GET /runs/{run_id}/execution`

- 输入：`after?: bigint`、`limit=200`（1—500）、`detail=summary|detail`。
- 输出：`RunExecutionView`；`after` 存在时只返回 cursor 更大的节点更新，同一 `node_id` 由客户端按 cursor 覆盖。
- 权限：Run 必须属于当前用户；不存在和跨用户统一 404。
- 幂等/并发：只读；相同 cursor 可重复请求。运行中的晚提交节点在后续 cursor 补拉。
- 兼容性：新增接口，不修改旧客户端；schema_version 不识别时客户端降级到现有 Step/Tool 时间线。

### `execution_update` SSE envelope

- 输入：无独立客户端请求，复用当前 Chat SSE。
- 输出：`{run_id, schema_version, nodes, next_cursor}`，只包含本次安全节点更新。
- 权限：沿用当前 Session Chat SSE 鉴权。
- 幂等/并发：客户端按 `run_id + node_id + cursor` 去重/覆盖；断线后调用 execution API 补拉。
- 兼容性：旧客户端忽略未知事件；该 envelope 不持久化到 `sessions.events`。

### 旧 Run 子接口

- `/runs/{id}/events|tool-calls|model-calls` 增加 cursor/limit 并直接查询对应 Repository。
- `/runs/{id}` 保持当前响应一段兼容期，但默认子记录上限；响应增加 `truncated` 标识。
- TracePanel 切换到 execution 接口后，旧全量详情标记 deprecated，不立即删除。

## 错误处理与可观测性

- Trace 写入失败：记录低基数 `trace_projection_failed`，Agent 继续；RunExecutionView 返回 `trace_complete=false`。
- 节点投影失败：跳过单个损坏节点并返回安全 warning，不把原始 payload 返回页面。
- cursor 过期/非法：HTTP 422；不存在或跨用户 Run：404。
- SSE execution update 丢失：不视为 Agent 失败，前端按 cursor 补拉。
- 关键指标：Trace 写入失败率、projection lag、execution API p50/p95、返回节点数/字节数、SSE 补拉次数、被安全策略丢弃字段数。
- 不记录用户消息、隐藏 reasoning、Tool 原始参数或响应内容到指标标签。

## 迁移与回滚

### 迁移

1. 先实现安全 API 投影，阻止历史敏感字段继续返回。
2. 新增 TraceEvent v2 字段和索引；旧字段与旧接口继续可读。
3. 切换新写入到安全 payload，并执行历史敏感内容清理迁移。
4. 上线 execution API 和合同测试。
5. TracePanel 切换到新合同，再上线聊天 Run Execution Card 和 SSE update。
6. 观察稳定后才废弃前端 `ThinkingBlock` 的旧 Step 邻接归组和旧全量详情调用。

### 回滚

- 关闭 `RUN_EXECUTION_VIEW_ENABLED`：前端退回现有 Session Step/Tool 与 TracePanel。
- TraceEvent v2 新列向后兼容，回滚应用不读取；不回填已经安全清除的原始 reasoning/Prompt/Tool 数据。
- `execution_update` 是未知 SSE 事件，旧客户端自动忽略。
- 历史清理不可恢复到应用数据库；执行前只允许生成加密备份并按保留策略管理，不能为了回滚继续在线暴露敏感内容。

## 分阶段实施边界

### T1：Trace 安全与查询正确性

- 公共 API 屏蔽 reasoning、raw prompt/response、base_url 和 Tool 原始字段。
- 子接口直接查询、服务端分页和稳定排序。
- TraceEvent v2 migration、cursor 和安全写入。

### T2：Execution View 合同

- ExecutionViewAssembler、节点关系、状态归一、汇总指标和历史 v1 兼容。
- 新增 execution API、合同测试和性能门禁。

### T3：聊天思考与执行详情

- Run Execution Card、Direct/ReAct/Plan/Ask/Failure 状态和 SSE execution update。
- 上线 `RunProcessBlock + ExecutionTree + PlannerNode`，将旧“思考过程”和 Composer PlanPanel 收敛到对应 Run，复用 ToolPreview 和 RecoveryAction。

### T4：TracePanel 重构

- 概览、执行链、按需工具/模型/Skills、技术事件和增量刷新。
- 移除前端原始 JSON dump 与重复全量请求。

每个 T Stage 独立验证、独立提交；不得在 T1 尚未关闭敏感字段问题时先交付更丰富的页面展示。

## 风险

| 风险 | 可能性 | 影响 | 缓解措施 | 验证方式 |
| --- | --- | --- | --- | --- |
| 把执行摘要误称为思维链 | 高 | 高 | 统一“执行过程”文案，禁止 reasoning 字段和查看入口 | UI 文案与 API schema 测试 |
| 历史 Trace 已含敏感内容 | 高 | 高 | API 先过滤、再离线清理、记录行数不记录内容 | 敏感 fixture 与迁移验证 |
| 新旧投影顺序不一致 | 中 | 高 | 服务端 cursor、node_id 覆盖、历史 v1 明确降级 | 乱序/重复/晚提交测试 |
| Execution View 变成第二状态机 | 中 | 高 | 只读投影、trace_complete 独立、禁止驱动 Agent 状态 | 架构边界和故障注入测试 |
| 大 Run 查询仍过重 | 中 | 中高 | cursor、limit、按需详情、响应字节上限和索引 | 1k/10k 节点压测 |
| SSE 增量丢失造成页面卡住 | 中 | 中 | cursor 补拉、终态强制刷新、未知事件兼容 | 断线重连 E2E |
| Tool 摘要过度脱敏导致不可用 | 中 | 中 | 按 Tool 类型定义白名单摘要，详情与复制分离 | Shell/File/Search/API 用例 |
| Trace 失败影响正常回复 | 低中 | 高 | 保持 best-effort、降级提示、不抛入 Agent 主链 | 数据库故障测试 |
| T1 清理影响既有调试习惯 | 中 | 中 | 保留元数据、hash、FailureInfo 和受控安全 preview | 开发者验收 |
| 为未来 Sub Agent 过度设计 | 低中 | 中 | 首期只支持单 Lead 树，parent_node_id 不引入调度语义 | 范围审查 |

## 重要假设

- 用户说的“思考调用链路”是希望理解 Agent 的公开工作过程，而不是查看模型私有 chain-of-thought。
- 当前用户既是自己 Run 的所有者，但所有权不等于可以暴露系统 Prompt、Secret、隐藏 reasoning 或未经治理的外部内容。
- 现有 Agent Run 规模首期可通过 PostgreSQL cursor 分页满足；达到集中式大规模观测需求后再评估 OpenTelemetry 外送。
- Direct/ReAct/Plan 和现有 Ask/Resume 是首期必须覆盖的全部 Lead 模式。
- 页面优先提供纵向执行链而非复杂 DAG，因为当前没有本地并行 Sub Agent。
- Provider 诊断仍保持独立活动；若用户之后需要历史诊断，应进入 Stage 4C 或独立诊断审计设计。

## 待决策项

无影响方案选择的核心未决项。实施计划开始前需要确认历史 Trace 安全清理的保留周期和备份策略；该选择影响迁移操作，但不改变“公共 API 立即停止返回敏感字段”的设计结论。

## 验收标准

- [ ] Direct、ReAct、Plan 和 Ask/Resume 均生成有序、稳定且可重连恢复的 Run Execution View。
- [ ] 聊天页使用“思考与执行详情”，且不出现“查看思维链”或把 Tool/Step 冒充模型隐藏思维的文案。
- [ ] Plan 模式在对应 RunProcessBlock 内展示 Planner 进度、稳定 Step、Tool 子节点和 Replan 次数；不再把最新 Plan 作为 Composer 全局面板。
- [ ] 新 Trace 不保存或返回 `reasoning_content`、系统 Prompt、完整消息、完整 base_url、凭据、Header 或未经白名单处理的 Tool 原始数据。
- [ ] 历史敏感字段在公共 API 立即被过滤，并通过受控迁移清理；迁移日志不包含被清理内容。
- [ ] `GET /runs/{id}/execution` 支持 cursor、limit、稳定节点覆盖和当前用户隔离。
- [ ] 旧 Run 接口继续兼容；子接口不再为了返回一种记录读取全部 Trace 表。
- [ ] 聊天执行卡和 TracePanel 使用同一 ExecutionNode 合同，页面刷新、SSE 断线和历史加载结果一致。
- [ ] 简单 Direct 完成态默认折叠；ReAct/Plan 运行态展示当前节点；用户手动折叠状态不会被刷新覆盖。
- [ ] Model 节点只展示 provider/model、消息与工具数量、Token、TTFT、总耗时和 finish_reason，不展示请求/响应正文。
- [ ] Tool 节点按服务端 Tool Trace Policy 展示安全摘要，点击复用详情面板，失败使用 FailureInfo。
- [ ] Trace 写入或 projection 故障不会终止 Agent，页面明确显示记录不完整而不是伪造 Run 失败。
- [ ] 1,000 节点 Run 的首屏 summary 响应在约定字节和延迟预算内；10,000 节点可通过 cursor 完整遍历，不一次性返回全部数据。
- [ ] 后端迁移、合同、安全、乱序、分页和故障测试，以及前端状态、重连、可访问性和生产构建全部通过。
