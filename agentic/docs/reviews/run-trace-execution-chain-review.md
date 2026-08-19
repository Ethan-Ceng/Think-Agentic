# Run Trace 与页面思考执行链路代码审查

## 审查范围

- 目标基线：`develop@4ed4fe9`
- 变更分支：`feature/run-execution-view`
- 变更范围：`develop...working tree`；真实长任务整改复审范围为 `c3c4de6...working tree`
- 设计文档：`docs/designs/run-trace-execution-chain-ux.zh-CN.md`
- 计划文档：`docs/plans/run-trace-execution-chain-plan.md`
- 审查者：同一 Agent 自检
- 审查日期：2026-08-19

## 需求符合度

- [x] TraceEvent v2、稳定 cursor、安全白名单和非破坏性迁移已落地。
- [x] `RunExecutionView/ExecutionNode` 是聊天页与 TracePanel 的共同合同，Planner 是一等节点。
- [x] 聊天页按消息 Run 展示紧凑过程行，展开后突出 Planner、Step、Tool、Interaction、Error 与 Completion；Model/Skill 技术节点只保留在诊断视图。
- [x] TracePanel 首屏只读取 Run 列表与 Execution View，工具、模型、Skills、技术事件按页签加载。
- [x] `execution_update` 仅走 SSE，不写入 Session 历史；Trace/SSE 失败不终止 Agent。
- [x] 页面没有隐藏 chain-of-thought、完整 Prompt、原始 Tool payload 或原始 Trace JSON 的展示入口。

## 正确性

- [x] Direct、ReAct、Plan、Replan、Ask/Resume、Failure 和 Completion 均能投影为稳定节点。
- [x] 相同 `node_id` 按 cursor 幂等覆盖，并保留最早 `started_at`、最终 `finished_at` 和跨阶段指标。
- [x] 运行中 TracePanel 按 cursor 增量刷新，收到终态后停止并对当前诊断页签做最后补拉。
- [x] Run/会话切换会使旧请求失效，不会把旧 Run 的诊断记录写入当前面板。
- [x] Lead 的 `waiting/failed/completed` 状态不会被无条件投影成成功；失败后的 `done` 不覆盖失败终态。
- [x] 已注册但不在当前 Step Scope 的历史工具调用，以及完全未知的工具调用，都会生成失败 Observation 供模型纠正，不再升级为 Run 内部异常。
- [x] 生产端以 `events.value.push(...)` 写入的 `execution_update` 可被实时消费；运行态默认展开且不覆盖用户手动折叠选择。

## 安全性

- [x] 新 Trace 写入按事件类型白名单化；历史记录通过公共 API 再次安全投影。
- [x] 历史 `error.failure` 只返回结构化允许字段，嵌套 reasoning、messages 等未知字段被剥离。
- [x] Tool/Model 公共记录不返回参数、结果、请求响应预览或完整 Provider URL。
- [x] Run Skills 公共记录不返回内部选择 reason 或 sandbox path。
- [x] 所有 Run 子接口先验证当前用户对 Run 的所有权，越权统一为不存在。
- [x] 历史敏感数据只做公共面隔离；没有在未授权情况下执行不可逆物理清理。
- [x] 聊天 Tool 节点只通过有 Run 所有权校验的安全分页 API 读取公共投影，不读取 Trace 原始 payload。

## 可维护性

- [x] 后端 Assembler 是纯投影，不驱动 Agent Runtime 状态。
- [x] 前端聊天页与 TracePanel 共享 `ExecutionNode` 类型、`ExecutionTree` 和节点合并函数。
- [x] Execution、Tool、Model、Event 使用独立 cursor；Skills 是有界且按 Run 一次性按需加载。
- [x] T1、T2、T3、T4 均为独立提交，最终审查整改单独收尾。

## 问题列表

未发现未解决的 blocking、major 或 minor 问题。

### [major][已修复] 当前步骤外工具调用在 ToolEvent 前终止长任务

位置：`api/app/core/agent/base.py`、`api/app/core/tools/base.py`、`api/app/core/tools/filter.py`

问题：真实 Session `2d5831ca-4aea-469d-8103-ad0a5c1b4c0a` 的最后一次模型调用返回 `browser_navigate`，但当前 Step 只暴露 `search_web`。原实现用运行时可见性判断工具是否存在，并在生成失败 ToolEvent 前抛出 `ValueError`，使可恢复的模型偏差升级为 Run 失败。

处置：区分“工具已注册”和“当前可执行”；已注册但越权/禁用的调用进入统一执行策略并返回失败 Observation，完全未知工具生成等价失败结果，底层工具不会执行。参数化回归覆盖越权浏览器与未知工具，均能进入下一轮模型并正常结束。

### [major][已修复] 未知工具容错初版仍可能空引用

位置：`api/app/core/agent/base.py`、`api/tests/app/core/agent/test_base_agent_streaming.py`

问题：整改初版构造未知工具失败结果后，仍会继续读取空工具对象的执行策略；同时特殊交互工具需要继续尊重其有效可见性，避免未来配置变化后绕过路由。

处置：将未知、有效交互、策略拒绝和普通调用改为互斥分支；仅对当前有效的 `message_ask_user` 创建 Interaction，并增加完全未知工具回归。审查整改后受影响测试 45 项、后端全量 620 项通过。

### [major][已修复] 实时更新未触发且聊天执行节点重复平铺

位置：`web/src/composables/useRunExecutions.ts`、`web/src/components/chat/RunProcessBlock.vue`、`web/src/components/chat/ExecutionTree.vue`

问题：生产流使用数组 `push`，但监听器只观察 ref 身份，导致运行中的 `execution_update` 不被消费；RunProcessBlock 又同时渲染 current node 和完整树，聊天密度还平铺全部 Model Call，造成思考/工具重复且步骤关系不清。

处置：按事件数组长度增量消费；Plan/ReAct 运行态在用户未手动切换时默认展开；删除重复 current node，聊天密度隐藏 Model/Skill 技术节点，Step 展示序号和状态。回归覆盖 push、展开偏好、单次节点渲染和步骤层级。

### [minor][已修复] 消息级 Tool 节点缺少安全详情入口

位置：`web/src/components/SessionDetailView.vue`、`web/src/components/chat/ExecutionTree.vue`、`web/src/components/chat/ToolPreviewPanel.vue`

问题：聊天执行树的 Tool 节点不可点击，用户无法从步骤链查看参数摘要和结果摘要。

处置：Tool 节点发出 detail 引用，Session 页面按 cursor 分页查找当前 Run 的安全 ToolCallRecord，并复用 ToolPreviewPanel 展示公共投影；请求带版本失效保护，切换 Session 后旧响应不会回写。

### [major][已修复] 节点完成更新丢失生命周期字段

位置：`api/app/services/execution_view.py`、`web/src/lib/run-execution.ts`

问题：Tool、Model、Interaction 等节点从开始更新为完成时，最新节点会整体覆盖旧节点，导致 `started_at`、消息数和 Tool Schema 计数丢失。

处置：后端与前端均改为字段级合并；状态、结束时间和完成指标使用新值，开始时间与早期指标安全保留，并增加服务端和客户端回归测试。

### [major][已修复] 延迟诊断请求可污染新 Run

位置：`web/src/components/TracePanel.vue`

问题：工具、模型、Skills、技术事件请求没有绑定 `requestVersion + runId`。快速切换 Run 或会话后，旧请求可能回写当前面板。

处置：所有异步诊断请求在提交结果和错误前验证版本与 Run；切换时重置加载状态，并增加延迟响应回归测试。

### [major][已修复] TracePanel 缺少运行中增量与终态补拉

位置：`web/src/components/TracePanel.vue`

问题：面板只有手动刷新，未满足设计中的运行中 cursor 更新与终态最后同步。

处置：非终态 Run 每 2 秒增量读取 Execution View；终态后停止轮询，并仅对当前打开的诊断页签执行一次最终刷新，不重复全量加载其他页签。

### [major][已修复] Lead 失败完成被投影为成功

位置：`api/app/services/trace_service.py`、`api/app/services/execution_view.py`、`web/src/composables/useRunExecutions.ts`

问题：`lead.completed` 虽携带 `waiting/failed`，Assembler 仍固定生成成功 Completion；Plan 失败后出现 `done` 时还可能把 Run 改为 completed。

处置：Lead completion 现在更新 Trace Run 的 waiting/failed 终态；Assembler 按 payload 生成节点并拒绝失败 Run 的 `done` 覆盖；SSE 客户端识别失败 Completion。

### [major][已修复] 历史错误 payload 可返回未知嵌套字段

位置：`api/app/services/trace_service.py`

问题：`error.created` 顶层虽有 allowlist，但历史 `failure` 子对象曾整体透传，可能包含 reasoning 或消息正文。

处置：对 failure 子对象增加结构化 allowlist，并以包含历史 reasoning/messages 的 fixture 验证公共 Events API 不再返回这些字段。

### [minor][已修复] SSE 发送失败仍提前推进 cursor

位置：`api/app/core/agent/agent_task_runner.py`

问题：`execution_update` 写入输出流前已推进 cursor，瞬时传输失败会使当前连接跳过该批节点。

处置：有可见节点时只在发送成功后推进 cursor；无可见节点时仍正常推进，避免反复读取技术事件。回归测试验证失败后的下一次调用从原 cursor 重试。

## 剩余建议

- `listRuns` 当前仍受 200 条上限、TracePanel 受 30 条首屏上限约束；超长会话的 Run 列表分页可作为后续独立优化，不影响本设计约定的单 Run 执行链正确性。
- 全量后端测试仍输出 12 条 Pydantic v2 兼容性弃用警告，为既有技术债，不是本分支引入。
- 同一 Agent 自检不具备 Reviewer 视角隔离；合并前仍建议人工快速复核公共 Trace 字段和 UI 文案。

## 无法验证项

- 未原地重建当前 `http://localhost:8088` 服务；该实例仍用于用户已有测试，本次实现和门禁均在工作区与隔离依赖中完成。
- 尝试通过应用内浏览器复核当前 Session，但本机浏览器运行时未能启动；因此没有把真实页面重放计为通过，UI 证据来自 27 项定向组件/集成测试及 225 项前端全量测试。
- 未执行多小时压测、浏览器性能录制或真实生产历史数据物理清理；历史清理必须另行授权。

## 合并门禁

| 门禁 | 结果 | 证据 |
| --- | --- | --- |
| 无 blocking | 通过 | 自审未发现 blocking。 |
| 无未处理 major | 通过 | 五项 major 均已修复并补回归。 |
| 后端全量 | 通过 | 隔离 PostgreSQL/Redis 下 620 passed；Ruff 与 compileall 退出 0。 |
| 前端全量 | 通过 | 53 files / 225 tests passed；vue-tsc 与 Vite build 退出 0。 |
| 数据迁移 | 通过 | 隔离 PostgreSQL 从空库 upgrade，随后 downgrade 到 `20260818_0001` 并 re-upgrade 到 `20260819_0001 (head)`。 |
| 安全与 Git | 通过 | 敏感字段扫描与 `git diff --check` 通过。 |

## 审查结论

- 结论：`APPROVED`
- 理由：真实长任务暴露的 Run 中断、实时更新失效、节点重复和步骤层级问题均已修复，复审发现的未知工具空引用也已关闭；安全边界、分页与增量语义均有自动化证据，完整测试与构建通过。
- 合并判断：允许合并；远端推送和 upstream 核对完成后，计划可标记为 `READY_TO_MERGE`。
