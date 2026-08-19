# 长任务进度误并行、消息重复与 Trace 失真

## 文档状态

- 状态：`VERIFIED`
- 修复分支：`feature/run-execution-view`
- 创建日期：2026-08-20
- 最近更新：2026-08-20

## 问题描述

Session `2d5831ca-4aea-469d-8103-ad0a5c1b4c0a` 的真实长任务运行中，聊天页看起来像多个 Step 并行，Plan/Step/Tool 信息重复占据对话，Trace Step 时间和顺序错乱，Token 总数在未进入模型页签时不可见且存在分页少算风险。问题稳定出现在 Plan 长任务，不是偶发网络错误。

## 预期行为

- Plan Step 严格串行，一次最多一个 Step running/waiting。
- 聊天显示总体 Plan Item 和当前活动；活动完成后隐藏，正常 Run 只显示最终 Assistant 交付。
- Step started_at/finished_at 来自 StepEvent，Plan 快照不覆盖生命周期。
- Trace Token 来自全部 Model usage，不依赖页签或单页记录。
- 新 Run 默认使用统一 Lead；Legacy 只作为明确回退。

## 实际行为

- 目标 Run 实际串行，但 `_plan_nodes` 在每个 PlanEvent 中重复构造全部 Step，Chat density 又展示全部历史 Tool 和 Step summary，造成并行感。
- Trace 存在 `lead.fallback`，reason_code 为 `feature_disabled`，运行实际进入 Legacy `PlannerReactFlow`。
- 旧 Flow 每个成功 Step 后仍调用 `planner.update_plan`。
- Planner 初始消息和每个 Step result 都以可见 Assistant Message 保存；Prompt 还鼓励频繁 `message_notify_user`。
- 四个 `run_steps.finished_at` 都被最终 Plan 完成时间覆盖。
- TracePanel Token 从懒加载 `modelCalls` 数组求和，初始显示 `-`。

## 复现步骤

1. 启动当前分支 API/Web 与 PostgreSQL/Redis。
2. 打开 Session `2d5831ca-4aea-469d-8103-ad0a5c1b4c0a`，查看 Run `c1510e7c-e968-4ff7-81ee-6468db35c41f`。
3. 展开聊天执行块和 TracePanel，比较 Plan Step、Assistant Message、Tool/Model 节点、Step 时间和 Token。

- 复现频率：目标 Run 每次查看均可复现。
- 最小复现：ExecutionViewAssembler Plan/Step fixture、TracePanel 未加载 Models fixture、ReAct 多 Step 事件 fixture。

## 日志和证据

### 证据 1：实际执行严格串行

```text
Step 1 23:58:20 → 00:01:10
Step 2 00:01:23 → 00:02:54
Step 3 00:03:03 → 00:04:27
Step 4 00:04:34 → 00:05:17
```

- 获取命令：对 `trace_events` 的 `step.started/step.completed` 按 `ingest_seq` 查询。
- 说明：证明 Runtime 没有并行；不能证明页面投影正确。

### 证据 2：Lead 被关闭并回退

```text
lead.fallback {"reason_code":"feature_disabled","error_type":""}
```

- 获取命令：查询目标 Run 的 `lead.fallback` TraceEvent。
- 说明：证明本次不是统一 Lead 的 Plan 调度结果。

### 证据 3：Token 已完整保存

```text
model_calls=55
prompt_tokens=2,842,163
completion_tokens=25,657
total_tokens=2,867,820
missing_total_tokens=0
```

- 获取命令：对目标 Run 的 `model_calls` 汇总 count/sum/null count。
- 说明：证明 Token 数据未丢失，故障在聚合/展示链路。

### 证据 4：上下文膨胀

```text
step1 model_calls=25, total_tokens=1,031,906
step1 prompt: first=29,744, last=54,958
step1 search_web calls=20
Memory.compact only removes browser_view/browser_navigate
```

- 获取命令：按 step_id 汇总 Model/Tool Call，并检查 `Memory.compact`。
- 说明：证明搜索结果持续进入后续 Prompt；不能单独证明所有 Token 都可避免。

## 调用链

```text
Chat Request
→ AgentTaskRunner
→ LeadAgent(enabled=false)
→ PlannerReactFlow
→ PlanEvent/StepEvent/ToolEvent/MessageEvent
→ TraceService
→ ExecutionViewAssembler
→ useRunExecutions / ExecutionTree / TracePanel
→ 并行感、消息重复、时序和 Token 展示错误
```

- 正常路径：Lead strategy → 单个 Step started → 当前活动 → Step completed → 下一 Step → 最终 Message。
- 故障路径：feature_disabled fallback → 每 Step Planner update → Plan 快照反复覆盖 Step → 全历史节点平铺 → Token 依赖 Models 页签。
- 关键差异：Runtime 事实和两类 UI 投影没有明确区分 durable plan item 与 transient activity。

## 根因假设

### 假设 1：并行感来自投影，不来自调度

- 假设：所有 Step 都被 Plan 快照构造并以相同 cursor/随机 ID 排序，导致视觉误判。
- 依据：Step 事件时间无重叠；`_plan_nodes` 遍历整份 `steps`。
- 最小验证：为 Step 增加 ordinal，Chat density 只保留 Plan Item 和当前活动；构造两 Step 事件测试。
- 预期结果：Runtime 事件不变，但 Chat 中只出现一个 running activity，Step 顺序稳定。

### 假设 2：消息重复来自中间 MessageEvent 可见性与通知 Prompt

- 假设：`plan.message`、`step.result` 和 message notification 都被当作用户消息/动作展示。
- 依据：ReAct/Planner 代码显式 yield 可见 MessageEvent；Prompt 写有“必须通报进度”。
- 最小验证：断言中间事件 visible=false，并断言 Chat density 过滤通知工具。
- 预期结果：正常 Plan Run 只剩最终可见 Assistant Message。

### 假设 3：Trace 时间和 Token 是投影/聚合错误

- 假设：PlanEvent 时间写入终态 Step，Token 又从懒加载资源数组求和。
- 依据：`_project_plan_steps.finished_at=event.created_at`、`_plan_nodes` 同样赋值；TracePanel `totalTokens` reduce `modelCalls`。
- 最小验证：StepEvent 完成后再送 Plan.completed，断言 finish time不变；不加载 Model Calls 时直接从 Execution nodes 聚合 Token。
- 预期结果：Step 时间保持原值，Token 初始即准确。

### 假设 4：Token 成本增长来自旧 Flow 重规划和未压缩大 Tool Result

- 假设：成功 Step 的 Planner update 与历史 Search Tool Result 反复进入 Prompt。
- 依据：4 次 plan.updated、Planner 5 次调用；Memory 不处理 search_web。
- 最小验证：Mock Planner 断言成功 Step update_plan 未调用；Memory fixture 断言旧大 Tool content 被 compact 且最新结果保留。
- 预期结果：计划正常推进且模型调用/Prompt 上下文减少。

## 假设验证

| 假设 | 命令或实验 | 实际结果 | 结论 |
| --- | --- | --- | --- |
| 假设 1 | Trace SQL 时间线 + 代码路径检查 | 四 Step 无重叠；Assembler 平铺整份计划 | 成立 |
| 假设 2 | 统计 message.created / message_notify_user + 代码检查 | 6 个 MessageEvent、7 次 notify；中间消息默认 visible | 成立 |
| 假设 3 | 汇总 model_calls + 检查 TracePanel | 55 次 usage 完整，但初始 Token 取空数组 | 成立 |
| 假设 4 | 按 Step 汇总 token/search + 检查 compact | Step1 20 次 search、103 万 Token；search 不压缩 | 成立 |

## 最终根因

四项假设均由真实数据和调用链确认。根因是运行时事实、对话消息和执行活动被混用：配置让 Run 静默落到旧 Flow；旧 Flow 又无条件 Replan；Plan 快照被当作 Step 生命周期更新；中间结果和通知被当作对话内容；Trace Token 使用按需资源而非执行合同；Memory 没有对搜索等大结果做生命周期管理。

## 修复方案

- 修复位置：见 `docs/plans/run-progress-orchestration-trace-v2-plan.md` Task 1–3。
- 最小修改：启用已存在的 Lead；将 Legacy 与 Lead 收敛到相同条件 Replan；改 visible/Prompt；补有界 compact；修正现有 Execution View 字段与前端 density，不新建平台。
- 不采用的方案：只修 CSS/前端过滤，因为无法修复 fallback、重复 Planner、错误时间和上下文成本；不重建事件平台，因为超出本轮范围。
- 相同模式检查：已检查中英文 Prompt、Lead/Legacy 两条 Plan 路径、execute/resume 两条 Step 路径、后端与前端两处 node merge。

## 回归测试

- 测试文件：Task 1–3 所列后端/前端测试。
- 覆盖行为：默认 Lead、条件 Replan、visible、Memory compact、Step 时间、ordinal、Token、Chat transient activity。
- RED 命令：将在各 Task 开始时记录定向测试命令。
- RED 结果：Runtime 5 failed / 10 passed；Trace 4 failed / 15 passed；前端 5 failed / 13 passed，分别复现配置、可见性、重规划、Memory、时间/顺序/Token 和 Chat density 问题。
- GREEN 命令：与计划中每个 Task 的定向命令一致。
- GREEN 结果：Runtime 定向 15 passed；Trace 定向 19 passed；前端定向 18 passed。

## 验证结果

- 回归测试：全部定向回归通过。
- 相关测试：后端全量 624 passed；前端全量 229 passed。
- 构建或静态检查：Ruff、compileall、type-check、Vite build、git diff --check 全部通过。
- 手工复现：原始 Run 经新投影得到 4 个严格串行 Step、稳定 ordinal、无 warning；55 个模型节点合计 2,867,820 token。
- 未验证项：重启后的浏览器页面与用户新长任务回归。

## 审查与最终状态

- 审查文档：`docs/reviews/run-progress-orchestration-trace-v2-review.md`
- 审查结论：`APPROVED`；发现的 Model phase major 已修复并全量复验
- 最终状态：`READY_TO_MERGE`
