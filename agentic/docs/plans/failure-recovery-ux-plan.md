# Agent Failure 语义与恢复 UX 实施计划

## 关联设计

- 设计文档：`docs/designs/failure-recovery-ux.zh-CN.md`
- 上位设计：`docs/designs/agent-runtime-hitl-provider-reliability.zh-CN.md`
- 开发分支：`refactor/unified-tool-plane`
- 实施范围：Stage 4A；不包含 form_input、Provider 健康管理或通用 Recovery Workflow
- 提交策略：Stage 4A 完整验证后形成一个提交；不自动推送

## 当前进度

- 整体状态：`COMPLETE`
- 当前阶段：complete
- 当前任务：无
- 已完成：4 / 4
- 阻塞问题：无
- 最近更新时间：2026-08-19（Asia/Shanghai）

## 全局约束

- 保持 `FailureInfo` 和 `/sessions/{id}/resume` 的向后兼容，不新增数据库迁移。
- 新用户可见 ErrorEvent 不得包含原始异常、URL、Header、凭据、响应体或堆栈。
- 前端只执行有真实处理器的 RecoveryAction；本阶段不实现或展示 `choose_provider`。
- `retryable` 只控制同操作重试，不作为是否显示全部恢复动作的总开关。
- 所有实现先补失败/回归测试，再做最小修改；每个 Task 完成后立即回写证据。
- Stage 4A 只提交一次，不推送、不创建 PR、不合并。

## 状态变更记录

| 日期时间 | 整体状态 | 当前任务 | 变更原因 |
| --- | --- | --- | --- |
| 2026-08-19（Asia/Shanghai） | `PLAN_READY` | 无 | 设计、四个任务、文件边界与验证命令确认完成 |
| 2026-08-19（Asia/Shanghai） | `IN_PROGRESS` | Task 1 | 普通开发分支与干净基线已确认，开始测试先行实施 |
| 2026-08-19（Asia/Shanghai） | `IN_PROGRESS` | Task 2 | Model Failure 18 项测试和 Ruff 通过，开始 Agent 重试与终止边界 |
| 2026-08-19（Asia/Shanghai） | `IN_PROGRESS` | Task 3 | Agent/Runner/Service 43 项测试、Ruff 与 ErrorEvent 扫描通过，开始前端恢复 UX |
| 2026-08-19（Asia/Shanghai） | `VERIFYING` | Task 4 | Recovery Registry/组件 33 项测试与类型检查通过，开始全量验证与审查 |
| 2026-08-19（Asia/Shanghai） | `COMPLETE` | 无 | 全量门禁通过，审查发现的两个 major 已修复且无剩余 blocking/major；Stage 4A 形成单一提交 |

## Task 1：建立 Model Failure 合同与 Adapter 映射

状态：completed

### 目标

让 OpenAI-compatible LLM 的常见 SDK 失败形成稳定、安全、可测试的 ModelRuntimeError，并覆盖块调用和流式调用。

### 涉及文件

- `api/app/core/llm/failure.py`（新增）
- `api/app/core/llm/openai_llm.py`
- `api/tests/app/core/llm/test_openai_llm_streaming.py`
- `api/tests/app/core/llm/test_model_failure.py`（新增）

### 依赖与接口

- 前置任务：无。
- 输入：OpenAI SDK 异常类型、HTTP 状态和现有 FailureInfo。
- 输出：ModelFailureCode、model_failure、ModelRuntimeError 与安全 SDK 映射。

### 实施步骤

1. 写参数化合同测试，覆盖鉴权、权限、限流、超时、连接、非法请求、5xx、未知错误和敏感字符串不外泄。
2. 定义 Model Failure 默认消息、retryable 和 recovery_actions。
3. 修改 invoke/stream 异常边界；保留 streaming unsupported 的现有安全块调用回退。
4. 更新既有流式异常测试，断言类型化错误码而非普通 ServerRequestsError。

### 验证方式

- 运行：`uv run pytest tests/app/core/llm/test_model_failure.py tests/app/core/llm/test_openai_llm_streaming.py -q`
- 运行：`uv run ruff check app/core/llm/failure.py app/core/llm/openai_llm.py tests/app/core/llm/test_model_failure.py tests/app/core/llm/test_openai_llm_streaming.py`
- 预期：退出码均为 0；异常分类、流式兼容与安全投影全部通过。

### 完成条件

- 块调用和流式调用使用同一 Model Failure 合同。
- 所有用户消息均为安全固定文案，原始异常只保留为 cause。
- streaming unsupported 回退行为无回归。

### 执行结果

新增 10 类 ModelFailureCode、安全默认消息、可重试性、恢复动作和 ModelRuntimeError；OpenAI-compatible 的块/流调用按 SDK 类型与 HTTP 状态分类，不解析或投影上游错误文本。streaming unsupported 继续由 Agent 安全回退块调用。

### 验证证据

```text
命令：uv run pytest tests/app/core/llm/test_model_failure.py tests/app/core/llm/test_openai_llm_streaming.py -q
退出状态：0
关键结果：18 passed；10 类错误映射、安全投影、块/流兼容和 streaming unsupported 回退通过。

命令：uv run ruff check app/core/llm/failure.py app/core/llm/openai_llm.py tests/app/core/llm/test_model_failure.py tests/app/core/llm/test_openai_llm_streaming.py
退出状态：0
关键结果：All checks passed。
执行时间：2026-08-19 14:38（Asia/Shanghai）
```

## Task 2：贯通 Agent 重试与安全终止边界

状态：completed

### 目标

让 Agent 保留最后一个 Model Failure、跳过不可重试请求，并消除应用源码中的不安全终止 ErrorEvent。

### 涉及文件

- `api/app/core/entities/failure.py`
- `api/app/core/agent/base.py`
- `api/app/core/agent/agent_task_runner.py`
- `api/app/services/agent_service.py`
- `api/tests/app/core/agent/test_base_agent_streaming.py`
- `api/tests/app/core/agent/test_agent_task_runner_completion.py`
- `api/tests/app/services/test_agent_service_recovery.py`
- `api/tests/app/core/test_failure_contract.py`

### 依赖与接口

- 前置任务：Task 1。
- 输入：ModelRuntimeError、Run Failure 和现有 Agent/Session 终止逻辑。
- 输出：类型化重试耗尽、不可重试短路和安全 ErrorEvent。

### 实施步骤

1. 先写可重试/不可重试调用次数、最后 Failure 保留和订阅异常脱敏测试。
2. 修改 BaseAgent 重试链，空/非法响应投影为 Model Failure，迭代上限投影为 Run Failure。
3. Runner 增加 ModelRuntimeError 分支；通用异常继续安全降级。
4. AgentService 的任务构造异常安全收敛；输出订阅异常只关闭当前 SSE，不写 ErrorEvent、不终止 Run。
5. 扫描应用源码所有 ErrorEvent 构造点，收口用户可见终止事件。

### 验证方式

- 运行：`uv run pytest tests/app/core/agent/test_base_agent_streaming.py tests/app/core/agent/test_agent_task_runner_completion.py tests/app/services/test_agent_service_recovery.py tests/app/core/test_failure_contract.py -q`
- 运行：`uv run ruff check app/core/entities/failure.py app/core/agent/base.py app/core/agent/agent_task_runner.py app/services/agent_service.py tests/app/core/agent/test_base_agent_streaming.py tests/app/core/agent/test_agent_task_runner_completion.py tests/app/services/test_agent_service_recovery.py tests/app/core/test_failure_contract.py`
- 运行：`rg -n "ErrorEvent\\(error=" api/app --glob '*.py'`
- 预期：测试和 Ruff 退出 0；扫描结果只剩明确兼容输入或无结果。

### 完成条件

- 不可重试失败只调用一次，可重试失败有界重试。
- Runner 输出真实 Model Failure；未知异常仍安全。
- 订阅边界不泄露原始异常。

### 执行结果

BaseAgent 现在保留最后一个 Model Failure，不可重试错误立即终止，可重试错误仍按配置有界重试；空响应、无效流和迭代上限拥有稳定错误码。Runner 单独投影 ModelRuntimeError；AgentService 的任务构造异常收敛为安全 RUN_INTERNAL_ERROR，而 SSE/Redis 输出订阅异常只关闭消费者连接，不改写运行状态或持久化伪终止事件。

### 验证证据

```text
命令：uv run pytest tests/app/core/agent/test_base_agent_streaming.py tests/app/core/agent/test_agent_task_runner_completion.py tests/app/services/test_agent_service_recovery.py tests/app/core/test_failure_contract.py -q
退出状态：0
关键结果：43 passed；retryable 短路、最后 Failure 保留、Runner Model 投影、订阅脱敏与状态收敛通过。

命令：uv run ruff check app/core/entities/failure.py app/core/agent/base.py app/core/agent/agent_task_runner.py app/services/agent_service.py tests/app/core/agent/test_base_agent_streaming.py tests/app/core/agent/test_agent_task_runner_completion.py tests/app/services/test_agent_service_recovery.py tests/app/core/test_failure_contract.py
退出状态：0
关键结果：All checks passed。

命令：rg -n "ErrorEvent\\(error=" api/app --glob '*.py'
退出状态：0（清理前仅剩携带 FailureInfo 的 orphan 兼容构造；随后已移除显式 error 参数）
关键结果：应用终止事件已统一从 FailureInfo 投影。
执行时间：2026-08-19 14:43（Asia/Shanghai）
```

## Task 3：实现 RecoveryAction 白名单与定向设置 UX

状态：completed

### 目标

让错误卡只展示真实可执行动作，正确打开恢复 Run 或目标设置面板，并显示调试参考编号。

### 涉及文件

- `web/src/lib/failure-recovery.ts`（新增）
- `web/src/lib/failure-recovery.spec.ts`（新增）
- `web/src/components/chat/ChatMessage.vue`
- `web/src/components/chat/ChatMessage.spec.ts`
- `web/src/components/SessionDetailView.vue`
- `web/src/components/SessionDetailView.spec.ts`
- `web/src/composables/useSettingsModal.ts`
- `web/src/components/SettingsModal.vue`
- `web/src/components/SettingsModal.spec.ts`（新增）
- `web/src/components/settings/types.ts`
- `web/src/lib/settings.ts`（新增）

### 依赖与接口

- 前置任务：Task 2。
- 输入：FailureInfo.recovery_actions、现有 resumeTask 和 Settings Modal。
- 输出：FailureRecoveryCommand、动作白名单和设置 Tab 路由。

### 实施步骤

1. 写动作矩阵测试：支持项、未知/choose_provider 过滤、retryable=false、legacy fallback、去重和来源到设置页映射。
2. 实现纯函数 Recovery Registry，避免组件内按错误文案分支。
3. ChatMessage 按 Registry 渲染按钮并显示 debug_id；历史错误不显示动作。
4. SessionDetailView 分发 resume/settings 两类命令，保留 restart 确认和归档/running 门禁。
5. 扩展 Settings Modal 无参兼容的定向 Tab 打开能力。

### 验证方式

- 运行：`pnpm test:run -- src/lib/failure-recovery.spec.ts src/components/chat/ChatMessage.spec.ts src/components/SessionDetailView.spec.ts`
- 运行：`pnpm type-check`
- 预期：退出码均为 0；动作矩阵、组件事件、设置路由和 legacy 兼容通过。

### 完成条件

- `choose_provider` 不显示；其他支持动作有真实执行器。
- retryable=false 不会隐藏 start_new_run/check_config。
- 错误卡显示安全消息与 debug_id，不显示内部错误。

### 执行结果

新增纯函数 Recovery Registry，按后端顺序过滤无真实执行器的动作，并按实际命令去重；legacy ErrorEvent 保持原两个恢复动作。错误卡显示 debug_id，SessionDetail 分发 resume/settings 命令，Settings Modal 支持无参兼容的定向 Tab 打开。`retryable=false` 不再隐藏配置修复或重新执行动作。

### 验证证据

```text
命令：pnpm test:run -- src/components/SettingsModal.spec.ts src/lib/failure-recovery.spec.ts src/components/chat/ChatMessage.spec.ts src/components/SessionDetailView.spec.ts
退出状态：0
关键结果：4 files、35 tests passed；动作白名单、去重、legacy、debug_id、组件命令、同目标重复定向和移动端设置路由通过。

命令：pnpm type-check
退出状态：0
关键结果：vue-tsc -b 无错误。
执行时间：2026-08-19 14:51（Asia/Shanghai）
```

## Task 4：完成全量验证、设计回写与代码审查

状态：completed

### 目标

证明 Stage 4A 无后端、前端、构建和兼容性回归，完成独立审查并形成一个可回滚提交。

### 涉及文件

- `docs/designs/failure-recovery-ux.zh-CN.md`
- `docs/plans/failure-recovery-ux-plan.md`
- `docs/designs/agent-runtime-hitl-provider-reliability.zh-CN.md`
- Task 1–3 的全部实现与测试文件

### 依赖与接口

- 前置任务：Task 1–3。
- 输入：完整 Stage 4A diff。
- 输出：最新验证证据、审查结论、状态回写和一个 Git 提交。

### 实施步骤

1. 运行后端全量测试、Ruff、compileall 和必要数据库初始化。
2. 运行前端全量测试、类型检查和生产构建。
3. 执行 `git diff --check`、敏感错误扫描和验收标准逐条核对。
4. 按 blocking/major/minor/suggestion 审查完整 diff；修复 blocking/major 后重跑受影响门禁。
5. 更新上位设计 Stage 4A 状态与本计划证据。
6. 精确暂存本 Stage 文件并创建一个提交；确认提交后工作区干净，不推送。

### 验证方式

- 后端：`uv run pytest -o addopts="" -q --tb=short --basetemp=.pytest_tmp`
- 后端静态：`uv run ruff check app tests`
- 后端编译：`uv run python -m compileall -q app tests`
- 前端测试：`pnpm test:run`
- 前端类型：`pnpm type-check`
- 前端构建：`pnpm build`
- 差异：`git diff --check`、`git status --short`
- 预期：全部退出 0；审查无 blocking/major；提交后工作区干净。

### 完成条件

- 全部设计验收标准有最新证据。
- 无未处理 blocking/major。
- Stage 4A 独立形成一个提交且未推送。

### 执行结果

Stage 4A 的后端、前端和文档门禁全部通过。代码审查发现并修复两个 major：输出订阅异常曾错误持久化 Agent ErrorEvent 并终止 Run；设置面板的重复定向与移动端直达语义不完整。复审后无剩余 blocking/major，Stage 4A 可作为一个提交交付。

### 验证证据

```text
命令：uv run pytest -o addopts="" -q --tb=short --basetemp=.pytest_tmp
退出状态：0
关键结果：580 passed，11 个既有 Pydantic deprecated warnings。

命令：uv run ruff check app tests
退出状态：0
关键结果：All checks passed。

命令：uv run python -m compileall -q app tests
退出状态：0
关键结果：无错误输出。

命令：pnpm test:run
退出状态：0
关键结果：46 files、196 tests passed。

命令：pnpm type-check
退出状态：0
关键结果：vue-tsc -b 无错误。

命令：pnpm build
退出状态：0
关键结果：vue-tsc 与 Vite production build 成功，3679 modules transformed。

测试环境：隔离 PostgreSQL 16 与 Redis 7 容器；init.sql 后执行 alembic upgrade head 成功；验证后容器已删除。
执行时间：2026-08-19 15:10（Asia/Shanghai）
```

## 计划变更

| 日期 | 变更内容 | 原因 | 影响任务 | 是否影响设计 |
| --- | --- | --- | --- | --- |
| 2026-08-19 | 将原 Stage 4 拆为 4A Failure UX 与后续独立批次 | form_input、Provider 管理与失败 UX 可独立交付，避免范围耦合 | 全部 | 否；是上位设计的细化 |

## 最终验证

### 执行命令

```bash
uv run pytest -o addopts="" -q --tb=short --basetemp=.pytest_tmp
uv run ruff check app tests
uv run python -m compileall -q app tests
pnpm test:run
pnpm type-check
pnpm build
git diff --check
rg -n "ErrorEvent\\(error=" api/app --glob "*.py"
```

### 执行结果

- 单元测试：通过；后端 580、前端 196
- 集成测试：通过；后端全量测试使用隔离 PostgreSQL/Redis 与最新迁移
- 静态检查：通过；Ruff、compileall、diff check 和 ErrorEvent 扫描无错误
- 类型检查：通过；vue-tsc
- 构建：通过；Vite production build
- 数据库迁移：不适用；本 Stage 无迁移
- 手工验证：恢复命令、定向设置和订阅边界由组件/服务回归测试覆盖；未修改线上服务
- 代码审查：通过；修复 2 个 major 后复审无 blocking/major

### 验收标准检查

- [x] 模型异常分类稳定、安全且覆盖块/流调用。
- [x] Agent 重试遵守 retryable 并保留最后 Failure。
- [x] 用户可见终止 ErrorEvent 均安全类型化。
- [x] RecoveryAction 只展示真实执行器且设置页映射正确。
- [x] debug_id 与历史兼容行为正确。
- [x] 全量自动化、类型和构建通过。

### 未通过项目

无。

### 最终状态

`READY_TO_MERGE`
