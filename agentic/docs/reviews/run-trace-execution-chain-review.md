# Run Trace 与页面思考执行链路代码审查

## 审查范围

- 目标基线：`develop@4ed4fe9`
- 变更分支：`feature/run-execution-view`
- 变更范围：`develop...working tree`
- 设计文档：`docs/designs/run-trace-execution-chain-ux.zh-CN.md`
- 计划文档：`docs/plans/run-trace-execution-chain-plan.md`
- 审查者：同一 Agent 自检
- 审查日期：2026-08-19

## 需求符合度

- [x] TraceEvent v2、稳定 cursor、安全白名单和非破坏性迁移已落地。
- [x] `RunExecutionView/ExecutionNode` 是聊天页与 TracePanel 的共同合同，Planner 是一等节点。
- [x] 聊天页按消息 Run 展示紧凑过程行，展开后显示 Planner、Step、Tool、Model、Interaction、Error 与 Completion。
- [x] TracePanel 首屏只读取 Run 列表与 Execution View，工具、模型、Skills、技术事件按页签加载。
- [x] `execution_update` 仅走 SSE，不写入 Session 历史；Trace/SSE 失败不终止 Agent。
- [x] 页面没有隐藏 chain-of-thought、完整 Prompt、原始 Tool payload 或原始 Trace JSON 的展示入口。

## 正确性

- [x] Direct、ReAct、Plan、Replan、Ask/Resume、Failure 和 Completion 均能投影为稳定节点。
- [x] 相同 `node_id` 按 cursor 幂等覆盖，并保留最早 `started_at`、最终 `finished_at` 和跨阶段指标。
- [x] 运行中 TracePanel 按 cursor 增量刷新，收到终态后停止并对当前诊断页签做最后补拉。
- [x] Run/会话切换会使旧请求失效，不会把旧 Run 的诊断记录写入当前面板。
- [x] Lead 的 `waiting/failed/completed` 状态不会被无条件投影成成功；失败后的 `done` 不覆盖失败终态。

## 安全性

- [x] 新 Trace 写入按事件类型白名单化；历史记录通过公共 API 再次安全投影。
- [x] 历史 `error.failure` 只返回结构化允许字段，嵌套 reasoning、messages 等未知字段被剥离。
- [x] Tool/Model 公共记录不返回参数、结果、请求响应预览或完整 Provider URL。
- [x] Run Skills 公共记录不返回内部选择 reason 或 sandbox path。
- [x] 所有 Run 子接口先验证当前用户对 Run 的所有权，越权统一为不存在。
- [x] 历史敏感数据只做公共面隔离；没有在未授权情况下执行不可逆物理清理。

## 可维护性

- [x] 后端 Assembler 是纯投影，不驱动 Agent Runtime 状态。
- [x] 前端聊天页与 TracePanel 共享 `ExecutionNode` 类型、`ExecutionTree` 和节点合并函数。
- [x] Execution、Tool、Model、Event 使用独立 cursor；Skills 是有界且按 Run 一次性按需加载。
- [x] T1、T2、T3、T4 均为独立提交，最终审查整改单独收尾。

## 问题列表

未发现未解决的 blocking、major 或 minor 问题。

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
- 未执行多小时压测、浏览器性能录制或真实生产历史数据物理清理；历史清理必须另行授权。

## 合并门禁

| 门禁 | 结果 | 证据 |
| --- | --- | --- |
| 无 blocking | 通过 | 自审未发现 blocking。 |
| 无未处理 major | 通过 | 五项 major 均已修复并补回归。 |
| 后端全量 | 通过 | 618 passed；Ruff 与 compileall 退出 0。 |
| 前端全量 | 通过 | 53 files / 222 tests passed；vue-tsc 与 Vite build 退出 0。 |
| 数据迁移 | 通过 | 隔离 PostgreSQL 从空库 upgrade，随后 downgrade 到 `20260818_0001` 并 re-upgrade 到 `20260819_0001 (head)`。 |
| 安全与 Git | 通过 | 敏感字段扫描与 `git diff --check` 通过。 |

## 审查结论

- 结论：`APPROVED`
- 理由：设计范围已完整落地，所有 blocking/major 已关闭，安全边界、分页与增量语义均有自动化证据，完整测试与构建通过。
- 合并判断：允许合并；远端推送和 upstream 核对完成后，计划可标记为 `READY_TO_MERGE`。
