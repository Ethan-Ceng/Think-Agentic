# Interaction 恢复 Trace 连续性修复计划

## 关联信息

- 调试记录：`docs/debug/interaction-resume-trace-run-split.md`
- 关联设计：`docs/designs/run-progress-orchestration-trace-v2.zh-CN.md`
- 开发分支：`feature/run-execution-view`
- 提交策略：验证和审查通过后提交当前分支，并按用户授权推送远端。

## 当前进度

- 整体状态：`IN_PROGRESS`
- 当前阶段：verification-and-delivery
- 当前任务：Task 3
- 已完成：2 / 3
- 阻塞问题：无
- 最近更新时间：2026-08-20（Asia/Shanghai）

## 全局约束

- Interaction continuation 创建新进程内 Task，但复用原逻辑 Agent Run。
- 原 Run 只能由所属用户、Session 和同 action_id 的 pending Interaction 恢复。
- 找不到合法 waiting Run 时保留新 Run 兼容回退，不能错误绑定其他 Run。
- 不新增数据库 Schema，不改变公开 Interaction API。
- `wait.created` 不再生成与结构化 Interaction 重复的用户可见执行节点。

## Task 1：固定失败回归测试

状态：completed

### 目标

证明当前实现会把 pending/resolved 拆到两个 Run，并固定恢复后的投影契约。

### 涉及文件

- `api/tests/app/services/test_trace_service.py`
- `api/tests/app/core/agent/test_agent_task_runner_completion.py`
- `api/tests/app/services/test_execution_view.py`

### 实施步骤

1. 增加 TraceService 测试：新 TraceService 根据 resolution 恢复共享仓库中的原 waiting Run。
2. 增加 AgentTaskRunner 测试：携带 interaction_response 时调用 resume，且不调用 start_run。
3. 增加 Execution View 测试：pending Interaction 后的 wait.created 不产生第二个 Interaction 节点。
4. 在未修复代码上运行并记录预期失败。

### 验证方式

`uv run pytest -o addopts="" -q tests/app/services/test_trace_service.py tests/app/core/agent/test_agent_task_runner_completion.py tests/app/services/test_execution_view.py --basetemp=.pytest_tmp_interaction_trace_red`

### 完成条件

新增测试能稳定暴露 Run 分裂或冗余等待节点，失败原因与真实 Session 证据一致。

### 执行结果

新增三项回归分别覆盖 TraceService 恢复、AgentTaskRunner 分流和 Execution View 去重；未修复代码上三项全部稳定失败。

### 验证证据

RED：3 failed；失败分别为缺少 `resume_interaction_run`、Runner 未调用 resume、Interaction 节点数量为 2。修复后同一文件 3 passed。

## Task 2：复用原 waiting Run 并修正等待投影

状态：completed

### 目标

让问题卡与 Composer 的 continuation 在原 Run 内恢复、执行和完成。

### 涉及文件

- `api/app/repositories/trace_repository.py`
- `api/app/repositories/db_trace_repository.py`
- `api/app/services/trace_service.py`
- `api/app/core/agent/agent_task_runner.py`
- `api/app/services/execution_view.py`
- Task 1 测试文件

### 实施步骤

1. Repository 按 user/session/action_id 查询带 pending Interaction 的 waiting Run，并可查询其 Step 记录。
2. TraceService 绑定原 run_id/trace_id，恢复 plan、step、run_step 和 replan 上下文，将 Run 切回 running。
3. AgentTaskRunner 对 interaction_response 优先恢复；无合法原 Run 时回退 start_run。
4. Execution View 忽略独立 wait.created 节点，保留 Run waiting 状态和结构化 Interaction 节点。
5. 检查自然回复与结构化问题卡均进入相同内部恢复路径。

### 验证方式

运行 Task 1 聚焦测试、Interaction 恢复相关测试和 Ruff。

### 完成条件

- 同 action_id 的 pending/resolved/done 位于同一 run_id。
- 原 Run 从 waiting → running → completed。
- 不产生第二个 continuation AgentRun。
- pending/resolved Interaction 投影为一个收敛节点。

### 执行结果

Repository 已按 user/session/action_id 定位原 waiting Run；TraceService 恢复 run/plan/step/replan 上下文；Runner 对 Interaction continuation 复用原 Run；Execution View 忽略冗余 wait 节点。

### 验证证据

新增回归 3 passed；既有 Interaction/Trace/Execution View 相关测试 58 passed；真实 PostgreSQL 查询唯一命中目标 waiting Run；聚焦 Ruff 通过。

## Task 3：真实数据收敛、验证、审查、提交、推送与重启

状态：in_progress

### 目标

证明修复无回归，安全收敛当前样本的历史分裂 Run，并交付远端可测试版本。

### 涉及文件

- Task 1–2 全部文件
- `docs/debug/interaction-resume-trace-run-split.md`
- 本计划
- `docs/reviews/run-progress-orchestration-trace-v2-review.md`（如需补充）

### 实施步骤

1. 运行聚焦、相关恢复、后端全量测试及 Ruff/compileall。
2. 审查完整 diff，修复 blocking/major 后重跑受影响门禁。
3. 对目标 Session 做精确、可审计的一次性历史 Run 收敛，复核 Run/Trace 查询。
4. 更新调试和计划证据，提交当前分支并推送远端。
5. 重启 API/Web，检查状态接口和目标 Session 页面。

### 验证方式

- 聚焦：Task 1 命令。
- 相关：`uv run pytest -o addopts="" -q tests/app/services/test_agent_service_recovery.py tests/app/core/agent/test_interaction_resume.py --basetemp=.pytest_tmp_interaction_resume`
- 全量：`uv run pytest -o addopts="" -q --tb=short --basetemp=.pytest_tmp_interaction_full`
- 静态：`uv run ruff check app tests`、`uv run python -m compileall -q app tests`、`git diff --check`。
- 运行：`/api/status` 返回 ok，目标 Session 页面 HTTP 200，旧 Run 不再 waiting。

### 完成条件

- 最新验证通过且审查无 blocking/major。
- 当前样本和自动化均证明问题消失。
- 当前分支已提交并成功推送远端。
- 服务已重启可测试。

### 执行结果

待执行。

### 验证证据

待执行。

## 最终验证

- 单元与集成测试：待执行。
- 静态检查：待执行。
- 类型/编译：待执行。
- 数据库迁移：不适用。
- 手工/API：待执行。
- 审查：待执行。
- 最终状态：`IN_PROGRESS`。
