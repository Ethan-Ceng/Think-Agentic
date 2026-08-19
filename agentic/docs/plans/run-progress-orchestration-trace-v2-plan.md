# 长任务编排、进度投影与 Trace 修订实施计划

## 关联设计

- 设计文档：`docs/designs/run-progress-orchestration-trace-v2.zh-CN.md`
- 基础设计：`docs/designs/run-trace-execution-chain-ux.zh-CN.md`
- 开发分支：`feature/run-execution-view`
- 提交策略：完成全部验证与代码审查后，按用户授权提交到当前分支；不推送、不合并。

## 当前进度

- 整体状态：`READY_TO_MERGE`
- 当前阶段：commit-and-restart
- 当前任务：Task 4
- 已完成：3 / 4
- 阻塞问题：无
- 最近更新时间：2026-08-20（Asia/Shanghai）

## 全局约束

- Plan 执行保持严格串行；本轮不引入并行 Step 或 Sub Agent DAG。
- Step 生命周期只由 StepEvent 决定，Plan 快照不能覆盖真实 started_at/finished_at。
- 只有最终交付、必要 Ask/Resume 和用户输入属于可见对话消息；Plan 初始说明与 Step 中间结果继续保存但 `visible=false`。
- 聊天只展示总体 Plan Item 与一个当前活动；完整 Tool/Model 历史只在 Trace diagnostic density 展示。
- 不保存或展示隐藏 reasoning、原始 Prompt、凭据或未治理 Tool 内容。
- Token 合计必须来自合并后的 Execution Model Nodes，不依赖“模型”页签是否加载，也不能受 100 条分页限制。
- Memory 压缩必须保留 Assistant tool_call 与对应 Tool message 的协议配对，只替换已消费的大 content。
- Legacy Flow 保留为显式配置或 Lead 决策异常时的兼容回退。

## 状态变更记录

| 日期时间 | 整体状态 | 当前任务 | 变更原因 |
| --- | --- | --- | --- |
| 2026-08-20（Asia/Shanghai） | `PLAN_READY` | 无 | 修订设计完成，任务边界和验证命令已确定 |
| 2026-08-20（Asia/Shanghai） | `IN_PROGRESS` | Task 1 | 用户已授权落地与提交，开始修正 Runtime 编排、消息和上下文语义 |
| 2026-08-20（Asia/Shanghai） | `REVIEWING` | Task 4 | Task 1–3 实现和首次全量验证通过，进入代码审查 |
| 2026-08-20（Asia/Shanghai） | `READY_TO_MERGE` | Task 4 | 审查 major 已修复，审查后全量复验通过，允许按用户授权提交 |

## Task 1：修正 Runtime 编排、消息可见性与上下文增长

状态：completed

### 目标

让新 Run 默认进入统一 Lead，Plan 成功 Step 不再重复请求 Planner；中间 Plan/Step 消息不污染对话，并对已消费的大 Tool Result 做有界压缩。

### 涉及文件

- `api/app/core/config.py`
- `api/.env.example`
- `api/app/core/flows/planner_react.py`
- `api/app/core/agent/lead.py`
- `api/app/core/agent/react.py`
- `api/app/core/agent/base.py`
- `api/app/core/entities/memory.py`
- `api/app/core/prompts/react.py`
- `api/app/core/prompts/en/react.py`
- `api/tests/app/core/agent/test_lead_agent_plan.py`
- `api/tests/app/core/agent/test_react_streaming.py`
- `api/tests/app/core/agent/test_base_agent_streaming.py`
- 新增或就近补充 Legacy Flow、Settings 与 Memory 测试

### 依赖与接口

- 前置任务：无。
- 输入：现有 Lead/Planner/ReAct 事件合同和 `MessageEvent.visible`。
- 输出：默认 Lead、条件 Replan、隐藏中间消息、可测试的 Tool Result compact 行为。

### 实施步骤

1. 将 `lead_agent_enabled` 默认值改为 true，并在示例配置中写明 `LEAD_AGENT_ENABLED=true`；显式 false 仍可回退。
2. 修改 Legacy `PlannerReactFlow`：成功且不要求 Replan 时直接产生 `PlanEvent.UPDATED` 并进入下一 Step；只有失败或 `needs_replan` 才调用 `planner.update_plan`。
3. 将 Lead/Legacy 的 `plan.message` 和 ReAct 的 `step.result` 标记为 `visible=false`；最终 summarize/Direct/React 交付保持可见。
4. 修改中英文 ReAct Prompt，只允许在主要阶段变化、计划变化或重要阻塞时使用 `message_notify_user`，禁止播报例行工具调用。
5. 为 Memory 增加“保留最近 N 个、压缩更早且超过阈值的 Tool Result”方法；Tool Loop 在结果被后续模型消费后调用，Step 间 compact 覆盖 `search_web` 等大结果。
6. 增加测试：默认 Lead 配置、严格条件 Replan、消息 visible、Tool 协议配对和大结果压缩。

### 验证方式

- 运行：`uv run pytest -o addopts="" -q tests/app/core/agent/test_lead_agent_plan.py tests/app/core/agent/test_react_streaming.py tests/app/core/agent/test_base_agent_streaming.py tests/app/core/flows --basetemp=.pytest_tmp_progress_runtime`
- 运行：`uv run ruff check app/core tests/app/core`
- 预期：全部退出 0；成功 Step 不产生 Planner update；中间消息 visible=false；最新 Tool Result 保留且旧大结果被 compact。

### 完成条件

- 新 Run 默认不再出现 `lead.fallback: feature_disabled`。
- Lead 与 Legacy Plan 都只有失败/needs_replan 才重规划。
- 正常多 Step Run 只把最终交付作为可见 Assistant Message。
- 长 Tool Loop 的历史大 Tool Result 有界，且消息协议合法。

### 执行结果

已默认启用统一 Lead；Legacy 成功步骤直接推进；Plan/Step 中间消息隐藏；通知 Prompt 收敛；已消费的大 Tool Result 有界压缩并保留协议字段。

### 验证证据

定向回归 15 passed；后端全量 624 passed；Ruff 与 compileall 通过。

## Task 2：修复 Execution View 时序、顺序与 Token 合同

状态：completed

### 目标

让 Step 时间、Plan revision、节点排序和 Token 汇总都来自正确事实，并能检测非法“多 Step 同时运行”状态。

### 涉及文件

- `api/app/schemas/run_execution.py`
- `api/app/services/trace_service.py`
- `api/app/services/execution_view.py`
- `api/tests/app/services/test_trace_service.py`
- `api/tests/app/services/test_execution_view.py`
- `web/src/lib/api/types.ts`
- `web/src/lib/run-execution.ts`
- `web/src/lib/run-execution.spec.ts`

### 依赖与接口

- 前置任务：Task 1。
- 输入：PlanEvent/StepEvent/Model event v2。
- 输出：可选 `ExecutionNode.ordinal`、稳定生命周期、跨页可重算 metrics 和并行状态 warning。

### 实施步骤

1. 给后端 Schema 和前端类型增加可选 `ordinal`；Plan Step 节点写入 index，节点合并时保留，兄弟排序优先 ordinal。
2. Plan 快照投影不再给 Step 写 `finished_at`；StepEvent 成为开始/结束时间唯一来源，后续 Plan 快照合并不得覆盖。
3. Plan revision 固定为 `1 + replan_count`，普通进度 UPDATED 不增加 revision。
4. Model Node 在 summary/detail 都保留安全 usage metrics；Run overview 从节点聚合 prompt/completion/total token、model count 和最小 TTFT。
5. 检测同一 Plan 多个 running/waiting Step，返回 `plan_parallel_state` warning 并令 trace_complete=false。
6. 投影 `lead.fallback` 为诊断 Strategy 节点，保留稳定 reason_code 摘要。
7. 增加时间不被 Plan 覆盖、ordinal、Token、重复 cursor 和非法并行 fixture 测试。

### 验证方式

- 运行：`uv run pytest -o addopts="" -q tests/app/services/test_execution_view.py tests/app/services/test_trace_service.py --basetemp=.pytest_tmp_progress_trace`
- 运行：`uv run ruff check app/services app/schemas tests/app/services`
- 预期：全部退出 0；Step 完成时间等于 step.completed；Token 合计准确；ordinal 稳定；多 running Step 被标记。

### 完成条件

- 当前样本的四个 Step 不再在 Execution View 中共享 Plan 完成时间。
- 随机 Step ID 不影响页面序号。
- Execution View 直接提供可聚合 Token，不需要 Model Calls 页签。
- 正常串行计划不产生 `plan_parallel_state`。

### 执行结果

已增加 ordinal，修复 Plan 快照覆盖 Step 生命周期与普通 UPDATED 增加 revision；summary/detail 均保留模型 usage；检测非法多活动 Step；投影 Lead fallback。

### 验证证据

定向回归 19 passed；真实 Run 新投影四 Step 时间正确、无重叠，55 个 Model Node 合计 2,867,820 token。

## Task 3：实现 ChatGPT 式聊天进度与 Trace 统计展示

状态：completed

### 目标

聊天只保留总体 Plan Item 和当前小动作，完成动作自动隐藏；Trace 使用 Execution View 展示完整诊断和可靠 Token。

### 涉及文件

- `web/src/components/chat/ExecutionTree.vue`
- `web/src/components/chat/PlannerNode.vue`
- `web/src/components/chat/RunProcessBlock.vue`
- `web/src/composables/useRunExecutions.ts`
- `web/src/components/TracePanel.vue`
- `web/src/components/chat/ExecutionTree.spec.ts`
- `web/src/components/chat/RunProcessBlock.spec.ts`
- `web/src/composables/useRunExecutions.spec.ts`
- `web/src/components/TracePanel.spec.ts`

### 依赖与接口

- 前置任务：Task 2。
- 输入：带 ordinal 和 usage metrics 的 ExecutionNode。
- 输出：Chat density 临时活动投影、Diagnostic density 完整树、独立于页签的 Token 汇总。

### 实施步骤

1. Chat density 只保留 Plan、全部 Step、最新一个 running/waiting Model/Tool/Interaction 和失败节点；过滤已完成 Tool/Model、Skill、Strategy、Completion 与 `message_notify_user`。
2. Chat density 隐藏 Plan/Step result summary，只显示标题、序号和状态；Diagnostic density 保持摘要、ID、cursor、耗时和完整历史。
3. Run 运行中自动展开仍保持用户手动折叠偏好；完成后当前活动消失，Header 与总体 Plan 状态保留。
4. `useRunExecutions` 和 TracePanel 在按 node_id 合并后重算 prompt/completion/total token、TTFT 和数量，避免 cursor 重放重复累加。
5. Trace Summary 分别显示输入、输出和总 Token；Tab 数量优先使用 Execution Overview，不依赖懒加载数组长度。
6. 增加组件测试覆盖活动出现/完成隐藏、Step 摘要隐藏、失败保留、ordinal 排序和超过 100 Model Node 的 Token 合计。

### 验证方式

- 运行：`pnpm test:run -- src/lib/run-execution.spec.ts src/composables/useRunExecutions.spec.ts src/components/chat/ExecutionTree.spec.ts src/components/chat/RunProcessBlock.spec.ts src/components/TracePanel.spec.ts`
- 运行：`pnpm type-check`
- 预期：全部退出 0；Chat 只显示一个当前活动并在终态隐藏；Trace Token 无需切换页签即可准确显示。

### 完成条件

- 页面不再把所有 Tool 历史和平铺 Step summary 当作“思考过程”。
- Plan Item 顺序与 Planner 一致，视觉上明确串行。
- Trace diagnostic 仍能查看完成的 Tool/Model 和每步摘要。
- Token 汇总不受懒加载、分页或重复更新影响。

### 执行结果

Chat density 仅保留 Plan、全部 Step、一个当前活动与失败；Plan/Step summary 隐藏；Diagnostic density 保留完整历史；Trace token 与 Tab 数量基于 Execution View。

### 验证证据

定向前端 18 passed；前端全量 229 passed；type-check 与生产 build 通过。

## Task 4：全量验证、真实 Session 回归、审查、提交与重启

状态：in_progress

### 目标

完成全量门禁和独立代码审查，用真实新 Session 验证用户观察到的四个问题，提交当前分支并重启服务供用户测试。

### 涉及文件

- Task 1–3 的全部实现与测试
- `docs/designs/run-progress-orchestration-trace-v2.zh-CN.md`
- `docs/plans/run-progress-orchestration-trace-v2-plan.md`
- `docs/reviews/run-progress-orchestration-trace-v2-review.md`（新增）

### 依赖与接口

- 前置任务：Task 1、Task 2、Task 3。
- 输入：完整 diff、自动化门禁、本地 API/Web/数据库运行环境。
- 输出：`READY_TO_MERGE` 证据、当前分支提交、已重启可测试服务。

### 实施步骤

1. 运行后端全量测试、Ruff、compileall；运行前端全量测试、type-check 和 build。
2. 对当前样本重新调用 Execution API，核对历史事件投影中的真实 Step 时间、ordinal 和 Token 合计。
3. 启动或重启本地 API/Web，创建新 Plan 长任务，核对 Lead strategy、严格串行、单一最终消息、活动隐藏和 Trace Token。
4. 使用 `code-review` 审查相对 `4ca02d5` 的完整 diff，修复所有 blocking/major 并重跑受影响门禁。
5. 使用 `verification-before-completion` 写回最终证据；状态达到 READY_TO_MERGE 后创建当前分支提交。
6. 提交后重启 API/Web，检查 `/api/status` 和 Web 首页可访问；不推送、不合并。

### 验证方式

- 后端：`uv run pytest -o addopts="" -q --tb=short --basetemp=.pytest_tmp_progress_final`
- 后端静态：`uv run ruff check app tests`
- 后端编译：`uv run python -m compileall -q app tests`
- 前端：`pnpm test:run`
- 前端类型：`pnpm type-check`
- 前端构建：`pnpm build`
- Git：`git diff --check`、`git status --short --branch`、`git diff --stat 4ca02d5`
- 手工/API：新 Run 不出现 feature_disabled；Step 不重叠；可见 Assistant 仅最终交付；Trace Token 等于 Model Node usage 总和。

### 完成条件

- 全量门禁通过且审查无未解决 blocking/major。
- 新真实 Session 的四类问题均有可复核证据。
- 当前分支产生一个包含本轮设计、实现、测试、计划和审查证据的提交。
- API/Web 重启后健康，用户可以直接测试。

### 执行结果

实现、全量验证、真实历史 Run 投影和代码审查已完成；等待创建用户已授权的当前分支提交并重启服务。

### 验证证据

审查结论 `APPROVED`；审查后后端 624 passed、前端 230 passed，Ruff、compileall、type-check、Vite build 和 diff check 均退出 0。

## 计划变更

| 日期 | 变更内容 | 原因 | 影响任务 | 是否影响设计 |
| --- | --- | --- | --- | --- |
| 2026-08-20 | 初始计划按 Runtime、Trace 合同、页面投影、最终验证拆分 | 与修订设计和真实样本根因对齐 | 全部 | 否 |

## 最终验证

### 执行命令

```bash
uv run pytest -o addopts="" -q --tb=short --basetemp=.pytest_tmp_progress_final
uv run ruff check app tests
uv run python -m compileall -q app tests
pnpm test:run
pnpm type-check
pnpm build
git diff --check
git status --short --branch
git diff --stat 4ca02d5
```

### 执行结果

- 单元测试：后端 624 passed；前端 229 passed。
- 集成测试：后端全量使用迁移到 head 的隔离 PostgreSQL `manus_test_progress_v2`，624 passed；临时库已清理。
- 静态检查：`uv run ruff check app tests` 退出 0；`git diff --check` 退出 0（仅 Git CRLF 提示）。
- 类型检查：`pnpm type-check` 退出 0；`compileall` 退出 0。
- 构建：`pnpm build` 退出 0，Vite 生产构建成功。
- 数据库迁移：不适用；本轮不修改数据库结构。
- 手工验证：原 Run `c1510e7c-e968-4ff7-81ee-6468db35c41f` 经新 Execution View 投影为 4 个 ordinal 0–3 的严格串行 Step，`trace_complete=true`、warnings 为空；Token 为 2,842,163 + 25,657 = 2,867,820，共 55 个 Model Node。当前 host Settings 解析 `lead_agent_enabled=True`。
- 代码审查：`APPROVED`；发现的 Model phase major 已修复并完成全量复验。

### 验收标准检查

- [x] 默认 Lead 生效，不出现 `feature_disabled` fallback。
- [x] Plan 严格串行，成功 Step 不重复调用 Planner。
- [x] 聊天只显示总体 Plan Item、一个当前活动和最终交付。
- [x] Step 生命周期、ordinal 和 Plan revision 正确。
- [x] Trace Token 不依赖 Model 页签或单页上限。
- [x] 大 Tool Result 有界压缩且工具协议合法。
- [x] 自动化、手工回归和代码审查全部通过。

### 未通过项目

无自动化或审查未通过项目。新长任务的主观产品体验由用户在重启后继续验证，避免未经授权创建会话和消耗模型额度。

### 最终状态

`READY_TO_MERGE`
