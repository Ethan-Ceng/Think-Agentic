# Provider 连接诊断实施计划

## 关联设计

- 设计文档：`docs/designs/provider-connection-diagnostics.zh-CN.md`
- 上位设计：`docs/designs/agent-runtime-hitl-provider-reliability.zh-CN.md`
- 开发分支：`refactor/unified-tool-plane`
- 实施范围：Stage 4B；不包含健康历史、后台轮询、自动路由或 Provider 自动切换
- 提交策略：Stage 4B 完整验证后形成一个提交；不自动推送

## 当前进度

- 整体状态：`COMPLETE`
- 当前阶段：complete
- 当前任务：无
- 已完成：4 / 4
- 阻塞问题：无
- 最近更新时间：2026-08-19（Asia/Shanghai）

## 全局约束

- 诊断只读取当前登录用户已经保存的权威配置，客户端不得提交 URL、Header、凭据、命令或测试参数。
- LLM 最多发起一次极小生成；MCP 只刷新 Tool Schema；A2A 只刷新 Agent Card 且禁用 stale fallback；API 只校验注册与 OpenAPI Schema。
- 诊断不创建 Agent Run、Session Event、Trace Plan 或 WAITING，不调用 MCP Tool、A2A 委派或 API Operation。
- 同一用户和 Provider 的并发诊断共享一个有界在途任务；等待者取消不得取消底层检查。
- 业务诊断失败以 HTTP 200 返回统一结果；请求非法、未认证或目标不属于当前用户时使用 HTTP 4xx。
- 不新增数据库迁移、健康持久化、后台探活、自动重试、自动切换或运行时路由反馈。
- 配置变化后前端立即清除旧诊断；普通设置入口和关闭弹窗会清除瞬时 FailureInfo 上下文。
- 每个 Task 完成后立即回写结果和验证证据；整个 Stage 4B 只提交一次且不推送。

## 状态变更记录

| 日期时间 | 整体状态 | 当前任务 | 变更原因 |
| --- | --- | --- | --- |
| 2026-08-19（Asia/Shanghai） | `IN_PROGRESS` | Task 1 | Stage 4B 设计已确认，任务边界、接口和验证命令已确定 |
| 2026-08-19（Asia/Shanghai） | `IN_PROGRESS` | Task 2 | 统一契约、路由和 single-flight 的 8 项测试及 Ruff 已通过 |
| 2026-08-19（Asia/Shanghai） | `IN_PROGRESS` | Task 3 | 四类最小诊断及 A2A fresh-only 回归共 53 项测试、Ruff 已通过 |
| 2026-08-19（Asia/Shanghai） | `VERIFYING` | Task 4 | 修复上下文和四面板诊断 UX 的 32 项测试、类型检查已通过 |
| 2026-08-19（Asia/Shanghai） | `REVIEWING` | Task 4 | 隔离 PostgreSQL/Redis 下 599 项后端、203 项前端及全部静态/类型/构建门禁通过 |
| 2026-08-19（Asia/Shanghai） | `COMPLETE` | 无 | 审查整改后 605 项后端、205 项前端及全部静态/类型/构建门禁通过，结论 `APPROVED` |

## Task 1：建立统一诊断契约与并发协调器

状态：completed

### 目标

新增严格的请求/结果模型、稳定诊断错误码和用户隔离的 single-flight 服务入口，使四类 Provider 共用同一安全语义。

### 涉及文件

- `api/app/schemas/provider_diagnostic.py`（新增）
- `api/app/services/provider_diagnostic_service.py`（新增）
- `api/app/controllers/provider_diagnostics.py`（新增）
- `api/app/dependencies/services.py`
- `api/app/controllers/__init__.py`
- `api/tests/app/services/test_provider_diagnostic_service.py`（新增）
- `api/tests/app/controllers/test_provider_diagnostics.py`（新增）

### 依赖与接口

- 前置任务：无。
- 输入：当前用户 ID、`ProviderDiagnosticRequest(provider_type, target_id)`、UserConfigService 和现有 Provider runtime。
- 输出：`POST /provider-diagnostics/test` 与 `ProviderDiagnosticResult`，供设置页统一消费。

### 实施步骤

1. 先写模型校验、用户隔离、业务失败 HTTP 200、非法目标 HTTP 4xx 和 single-flight 取消隔离测试。
2. 定义 provider/check/status/snapshot 枚举、请求目标约束、结果模型与新增稳定 FailureInfo 构造器。
3. 实现有界 single-flight 协调器，按 `user_id + provider_type + target_id` 复用在途任务并用 shield 隔离等待者取消。
4. 增加认证 Controller 和依赖装配；确保请求体无法携带敏感配置。

### 验证方式

- 运行：`uv run pytest tests/app/services/test_provider_diagnostic_service.py tests/app/controllers/test_provider_diagnostics.py -q`
- 运行：`uv run ruff check app/schemas/provider_diagnostic.py app/services/provider_diagnostic_service.py app/controllers/provider_diagnostics.py tests/app/services/test_provider_diagnostic_service.py tests/app/controllers/test_provider_diagnostics.py`
- 预期：命令退出码均为 0；契约、HTTP 语义、用户隔离和 single-flight 行为全部通过。

### 完成条件

- 请求只包含 Provider 类型和不透明目标 ID，目标约束由后端严格校验。
- 结果不会包含 URL、Header、凭据、命令、响应正文或原始异常。
- 相同用户/目标共享在途检查，不同用户或不同目标互不共享。

### 执行结果

新增严格请求/结果模型、两个诊断专用稳定错误码、认证 Controller 和有界 single-flight 协调器。相同用户/目标复用在途任务，等待者取消由 `asyncio.shield` 隔离；不同用户不共享。未知 Adapter 异常只记录低基数类型信息并投影为固定安全结果，不向响应或日志写入原始 URL、Token 或异常正文。

### 验证证据

```text
命令：`uv run pytest tests/app/services/test_provider_diagnostic_service.py tests/app/controllers/test_provider_diagnostics.py -q`
退出状态：0
关键结果：8 passed；请求目标约束、extra forbid、业务失败 HTTP 200 包装、用户隔离、single-flight 和取消隔离通过。
命令：`uv run ruff check app/core/provider_diagnostics.py app/schemas/provider_diagnostic.py app/services/provider_diagnostic_service.py app/controllers/provider_diagnostics.py app/dependencies/services.py app/dependencies/__init__.py app/controllers/__init__.py tests/app/services/test_provider_diagnostic_service.py tests/app/controllers/test_provider_diagnostics.py`
退出状态：0
关键结果：All checks passed。
执行时间：2026-08-19 17:02（Asia/Shanghai）
```

## Task 2：适配 LLM、MCP、A2A 与 API 的最小只读检查

状态：completed

### 目标

复用现有 Provider runtime 完成四类最小诊断，保证超时、错误分类、能力计数和副作用边界符合设计。

### 涉及文件

- `api/app/services/provider_diagnostic_service.py`
- `api/app/core/llm/openai_llm.py`
- `api/app/core/tools/a2a_runtime.py`
- `api/app/core/tools/provider_runtime.py`
- `api/app/services/tool_config_service.py`
- `api/tests/app/services/test_provider_diagnostic_service.py`
- `api/tests/app/core/llm/test_openai_llm_streaming.py`
- `api/tests/app/core/tools/test_mcp_lazy_provider.py`
- `api/tests/app/core/tools/test_a2a_provider_runtime.py`

### 依赖与接口

- 前置任务：Task 1。
- 输入：当前用户权威配置、现有 OpenAILLM、MCPProviderPool、A2AProviderRuntime 与 API registration 解析能力。
- 输出：四类 Adapter 的统一诊断结果；MCP/A2A 可安全刷新内存快照。

### 实施步骤

1. 写四类成功、超时、鉴权/配置错误、禁用 Provider、目标不存在和能力计数测试。
2. LLM 使用临时客户端执行一次极小 Chat Completion，外层 15 秒超时、无 Agent 重试，并可靠关闭客户端。
3. MCP 通过共享 Pool 强制刷新选定 server schema，不调用 Tool；A2A 强制刷新选定 Agent Card，手工诊断禁用 stale fallback 且不委派任务。
4. API 复用 registration/OpenAPI 解析，只返回 configuration 检查和 Operation 数量，不调用任何 Operation。
5. 将已知 runtime 异常复用为现有 FailureInfo，未知异常投影为安全诊断失败并记录低基数结构化日志。

### 验证方式

- 运行：`uv run pytest tests/app/services/test_provider_diagnostic_service.py tests/app/core/llm/test_openai_llm_streaming.py tests/app/core/tools/test_mcp_lazy_provider.py tests/app/core/tools/test_a2a_provider_runtime.py -q`
- 运行：`uv run ruff check app/services/provider_diagnostic_service.py app/core/llm/openai_llm.py app/core/tools/a2a_runtime.py app/core/tools/provider_runtime.py app/services/tool_config_service.py tests/app/services/test_provider_diagnostic_service.py tests/app/core/llm/test_openai_llm_streaming.py tests/app/core/tools/test_mcp_lazy_provider.py tests/app/core/tools/test_a2a_provider_runtime.py`
- 预期：命令退出码均为 0；四类检查的网络/副作用边界与 FailureInfo 分类全部通过。

### 完成条件

- LLM 单次最小请求；MCP/A2A 只发现能力；API 只做配置解析。
- A2A 手工失败不会被 stale 快照伪装为成功。
- 每类检查均有明确超时和安全的 healthy/degraded/unhealthy 结果。

### 执行结果

实现四个 Adapter 并接入应用级诊断服务：LLM 使用 `temperature=0/max_tokens=1` 发起一次最小请求并关闭临时客户端；MCP 只对选定 server 强制刷新共享 Pool Schema；A2A 强制刷新选定 Agent Card，并为 runtime 新增默认兼容的 `allow_stale` 参数，手工诊断显式设为 false；API 复用 registration 测试的空 Operation 分支，只解析配置和 Schema。禁用 Provider 通过内存副本测试，不写回启停状态。已知 runtime failure 保持原稳定码，外层超时按具体 Provider 投影；低基数日志只记录类型、稳定 provider_id、状态、code、debug_id 和耗时。

### 验证证据

```text
命令：`uv run pytest tests/app/services/test_provider_diagnostic_service.py tests/app/core/tools/test_a2a_provider_runtime.py tests/app/core/llm/test_openai_llm_streaming.py tests/app/core/tools/test_mcp_lazy_provider.py tests/app/controllers/test_provider_diagnostics.py -q`
退出状态：0
关键结果：53 passed；四类成功/失败、能力计数、禁用 Provider、目标不存在、LLM 客户端关闭与 A2A fresh-only 通过。
命令：`uv run ruff check app/services/provider_diagnostic_service.py app/core/llm/openai_llm.py app/core/tools/a2a_runtime.py app/dependencies/services.py tests/app/services/test_provider_diagnostic_service.py tests/app/core/tools/test_a2a_provider_runtime.py`
退出状态：0
关键结果：All checks passed。
执行时间：2026-08-19 17:08（Asia/Shanghai）
```

## Task 3：完成设置页修复上下文与统一诊断 UX

状态：completed

### 目标

让错误卡带着安全 FailureInfo 打开正确设置页，并在 LLM、MCP、A2A、API 面板提供语义一致的“测试已保存配置”入口和结果卡。

### 涉及文件

- `web/src/api/provider-diagnostics.ts`（新增）
- `web/src/lib/failure-recovery.ts`
- `web/src/composables/useSettingsModal.ts`
- `web/src/components/SessionDetailView.vue`
- `web/src/components/SettingsModal.vue`
- `web/src/components/settings/ProviderDiagnosticCard.vue`（新增）
- `web/src/components/settings/SettingsModelPanel.vue`
- `web/src/components/settings/SettingsMcpPanel.vue`
- `web/src/components/settings/SettingsA2aPanel.vue`
- `web/src/components/settings/SettingsApiToolsPanel.vue`
- 对应 `*.spec.ts` 测试文件

### 依赖与接口

- 前置任务：Task 1、Task 2。
- 输入：Recovery settings command 的 FailureInfo、统一诊断 API、各设置面板的已保存配置状态。
- 输出：瞬时修复上下文、统一测试按钮、加载/成功/降级/失败结果和安全提示。

### 实施步骤

1. 先写 Recovery command 上下文传递、普通打开/关闭清理、重复点击防抖、配置变化清理结果和 API Operation 测试语义分离测试。
2. 扩展设置弹窗状态，使 FailureInfo 仅在错误卡定向打开时存在并由弹窗统一展示 code/message/debug_id。
3. 新增统一诊断客户端和结果卡，展示检查层级、耗时、能力数、快照状态及可选 FailureInfo。
4. 在四类面板接入测试入口；未保存的 LLM 表单禁用测试，MCP/A2A/API 配置变化后立即清除旧结果。
5. 明确 API 的“校验配置”不代表远程 Operation 正常，保留并区分现有显式 Operation 调用测试。

### 验证方式

- 运行：`pnpm test:run -- src/lib/failure-recovery.spec.ts src/components/SettingsModal.spec.ts src/components/SessionDetailView.spec.ts src/components/settings/ProviderDiagnosticCard.spec.ts src/components/settings/SettingsModelPanel.spec.ts src/components/settings/SettingsMcpPanel.spec.ts src/components/settings/SettingsA2aPanel.spec.ts src/components/settings/SettingsApiToolsPanel.spec.ts`
- 运行：`pnpm type-check`
- 预期：命令退出码均为 0；上下文生命周期、按钮门禁、结果失效和四面板语义全部通过。

### 完成条件

- 错误卡进入设置时显示安全失败上下文；普通进入和关闭后不残留。
- 四个面板使用同一诊断结果语义，不发送未保存配置。
- API Schema 校验与真实 Operation 调用在界面上清晰分离。

### 执行结果

Recovery settings command 现在携带完整安全 FailureInfo；设置弹窗仅在目标页显示 code/message/debug_id，普通入口与关闭都会清除瞬时上下文。新增统一诊断客户端和可复用结果卡，展示检查层级、耗时、能力数、快照与失败参考。LLM 有未保存修改时禁用诊断；MCP/A2A/API 行状态或配置变化会清除旧结果。API 设置页将无副作用的“校验已保存配置”和真实“调用 Operation 测试”明确分离，真实调用必须选择 Operation 并提示外部副作用。

### 验证证据

```text
命令：`pnpm test:run -- src/lib/failure-recovery.spec.ts src/components/SettingsModal.spec.ts src/components/SessionDetailView.spec.ts src/components/settings/ProviderDiagnosticCard.spec.ts src/components/settings/ProviderDiagnosticPanels.spec.ts`
退出状态：0
关键结果：5 files、32 tests passed；上下文生命周期、统一结果卡、旧结果失效、禁用 Provider 与四面板接线通过。
命令：`pnpm type-check`
退出状态：0
关键结果：`vue-tsc -b` 无错误。
执行时间：2026-08-19 17:21（Asia/Shanghai）
```

## Task 4：完成全量验证、设计回写与代码审查

状态：completed

### 目标

证明 Stage 4B 没有后端、前端、构建、安全和兼容性回归，完成独立审查并形成一个可回滚提交。

### 涉及文件

- `docs/designs/provider-connection-diagnostics.zh-CN.md`
- `docs/designs/agent-runtime-hitl-provider-reliability.zh-CN.md`
- `docs/plans/provider-connection-diagnostics-plan.md`
- `docs/reviews/provider-connection-diagnostics-review.md`（新增）
- Task 1—3 的全部实现与测试文件

### 依赖与接口

- 前置任务：Task 1—3。
- 输入：完整 Stage 4B diff。
- 输出：最新验证证据、审查结论、状态回写和一个 Git 提交。

### 实施步骤

1. 运行后端全量测试、Ruff 和 compileall；运行前端全量测试、类型检查和生产构建。
2. 执行 `git diff --check`、敏感字段扫描、接口路由检查和验收标准逐项核对。
3. 按 blocking/major/minor/suggestion 审查完整 diff；修复 blocking/major 后重跑受影响门禁。
4. 回写设计、上位路线图和本计划的实际证据与最终状态。
5. 精确暂存 Stage 4B 文件并创建一个提交；确认提交后工作区干净，不推送。

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

- 全部设计验收标准都有最新证据。
- 无未处理 blocking/major。
- Stage 4B 独立形成一个提交且未推送。

### 执行结果

完成后端、前端、接口、安全边界和兼容性全量门禁。首次后端全量执行因本机测试端口缺少 PostgreSQL/Redis，出现 24 项失败、1 项错误；启动仅供本阶段验证的隔离 PostgreSQL/Redis 后，从空库执行 Alembic 到 head 成功，随后全量回归通过。自审发现并修复 LLM 诊断继承 SDK 默认重试及记录响应正文、API 缺少 Schema 时可能误报健康、配置变更期间的旧结果回显、API 目标标识泄漏和 LLM 客户端关闭缺少上界等问题；整改后重跑全部门禁，无未处理 blocking、major 或 minor。

Stage 4B 的实现、测试、设计、计划与审查记录统一纳入一个 Git 提交，不推送。真实用户凭据对应的 LLM/MCP/A2A 远端连接留给 8088 手工验收，不作为自动门禁伪造。

### 验证证据

```text
后端全量：uv run pytest -o addopts="" -q --tb=short --basetemp=.pytest_tmp
退出状态：0；605 passed，11 个既有 Pydantic 弃用 warning。
后端静态：uv run ruff check app tests
退出状态：0；All checks passed。
后端编译：uv run python -m compileall -q app tests
退出状态：0。
前端全量：pnpm test:run
退出状态：0；48 files、205 tests passed。
前端类型：pnpm type-check
退出状态：0。
前端构建：pnpm build
退出状态：0；3683 modules transformed。
差异：git diff --check
退出状态：0；仅 Git 的 LF/CRLF 提示，无 whitespace error。
接口：应用路由中存在 POST /api/provider-diagnostics/test。
安全边界：诊断实现扫描未发现响应正文、原始异常、凭据、命令或 Agent/Session 写入路径；命中项仅为读取已保存 base_url、一次 llm.invoke 和低基数日志。
代码审查：docs/reviews/provider-connection-diagnostics-review.md，APPROVED。
执行时间：2026-08-19（Asia/Shanghai）
```

## 计划变更

| 日期 | 变更内容 | 原因 | 影响任务 | 是否影响设计 |
| --- | --- | --- | --- | --- |
| 2026-08-19 | 初始计划拆分为契约协调、Provider 适配、前端 UX、最终门禁四个任务 | 与已确认 Stage 4B 设计和单提交策略对齐 | 全部 | 否 |

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
git status --short
```

### 执行结果

- 单元测试：后端 605 项、前端 205 项全部通过。
- 集成测试：Controller、四类 Adapter、single-flight、A2A fresh-only、设置页恢复上下文和四面板接线均通过。
- 静态检查：Ruff、compileall、`git diff --check` 全部通过。
- 类型检查：`vue-tsc -b` 通过。
- 构建：Vite 生产构建通过，3683 个模块完成转换。
- 数据库迁移：不适用；本 Stage 不新增迁移。
- 手工验证：应用路由确认 `POST /api/provider-diagnostics/test` 已注册；真实 Provider 凭据连接待 8088 用户验收。
- 代码审查：`APPROVED`，无未处理 blocking、major 或 minor。

### 验收标准检查

- [x] 失败卡携带安全 FailureInfo 进入正确设置页，且上下文生命周期不泄漏。
- [x] LLM 仅一次极小调用并有 15 秒外层超时。
- [x] MCP/A2A 仅刷新发现数据，A2A 手工检查不使用 stale fallback。
- [x] API 只校验配置且与显式 Operation 调用清晰分离。
- [x] 同用户同目标 single-flight 生效，取消等待者不取消共享检查。
- [x] 不创建 Run/Event/WAITING，不持久化健康、不改变 Provider enabled 或路由状态。
- [x] 后端与前端全量门禁通过。

### 未通过项目

无。真实外部 Provider 连接和浏览器人工点击不在自动测试环境中执行，作为部署后的手工验收项保留。

### 最终状态

`READY_TO_MERGE`
