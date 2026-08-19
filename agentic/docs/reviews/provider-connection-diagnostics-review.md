# Provider 连接诊断与失败修复闭环代码审查

## 审查范围

- 基线提交：`14930fc`（Stage 4A）
- 变更分支：`refactor/unified-tool-plane`
- 变更范围：Stage 4B 的统一诊断契约、四类 Provider Adapter、设置页失败上下文、诊断 UX、测试与工程文档
- 设计文档：`docs/designs/provider-connection-diagnostics.zh-CN.md`
- 计划文档：`docs/plans/provider-connection-diagnostics-plan.md`
- 审查者：同一 Agent 自检
- 审查日期：2026-08-19

## 需求符合度

- [x] 诊断只读取当前用户已保存配置，客户端不能提交 URL、凭据、Header、命令或测试参数。
- [x] LLM/MCP/A2A/API 分别执行极小推理、Schema discovery、Agent Card discovery 和配置解析。
- [x] 诊断不创建 Run/Event/WAITING，不调用 MCP Tool、A2A 委派或 API Operation。
- [x] 业务失败使用统一安全结果，非法请求和越权目标保留 HTTP 4xx。
- [x] FailureInfo 仅作为设置弹窗瞬时上下文，普通打开、关闭和配置变化会使旧上下文或结果失效。

## 正确性

- [x] 同用户同目标诊断使用有界 single-flight，等待者取消不取消共享任务，容量耗尽安全失败。
- [x] 四类检查都有显式外层超时；LLM 无 SDK 重试且关闭临时客户端也有时间上界。
- [x] A2A 手工诊断禁用 stale fallback；API 缺少或无法解析 Schema 时不会误报健康。
- [x] 禁用 Provider 只通过内存副本测试，不写回启用状态。
- [x] 配置在请求期间变化时，旧的异步结果不会重新显示。

## 安全性

- [x] 请求与响应采用白名单模型，不返回原始 URL、凭据、Header、响应正文、异常正文或堆栈。
- [x] 日志只记录低基数 Provider 标识、状态、稳定错误码、debug_id 和耗时。
- [x] API 自定义标识和异步任务名均使用安全标识，不暴露用户输入的 URL/目标文本。
- [x] API 诊断只解析已保存 Schema；真实 Operation 测试仍是独立、显式且带副作用警告的动作。

## 可维护性

- [x] Controller、协调服务、Provider Adapter 和前端展示职责分离。
- [x] ProviderDiagnosticResult 与现有 FailureInfo 复用稳定错误语义。
- [x] A2A 的 `allow_stale` 与 LLM 的 `log_response` 都是向后兼容的可选参数。
- [x] Stage 4C 的健康历史、后台探活和路由反馈未混入本阶段。

## 测试质量

- [x] 后端覆盖契约、Controller、用户隔离、single-flight、容量、取消隔离、四类成功/失败/超时及 A2A fresh-only。
- [x] 前端覆盖恢复上下文生命周期、四面板接线、按钮门禁、配置变化失效和 API 配置语义。
- [x] 全量后端 605 项、前端 205 项测试通过；静态、类型、编译和生产构建门禁通过。

## 问题列表

### [major] LLM 诊断继承 SDK 默认重试并记录响应正文

影响：一次手工诊断可能产生多次付费请求，且诊断响应正文会进入日志，违反最小请求与安全日志边界。

处置：已修复。诊断专用 LLM 使用 `max_retries=0`，调用时设置 `log_response=false`，并增加生产装配回归测试。

### [major] 缺少 API Schema 时可能被校验为空 Operation 并报告健康

影响：用户会把“没有可验证 Schema”误解为远端连接或配置正常。

处置：已修复。新增只读 registration/OpenAPI 检查器，Schema 缺失或解析失败返回 `PROVIDER_CONFIGURATION_INVALID`；UI 固定显示“配置有效”，不声称远端连接正常。

### [minor] 配置在诊断请求期间变化后，旧结果可能异步回显

影响：结果与当前表单或已保存配置版本不一致。

处置：已修复。结果卡维护配置 generation，请求完成时只接受同代结果，并增加在途变更测试。

### [minor] API 目标标识和任务名可能包含用户输入

影响：自定义 registration id 或 URL 可能进入日志、任务调试信息。

处置：已修复。公开 provider_id 与任务名均使用固定前缀和摘要化安全标识。

### [minor] LLM 临时客户端关闭缺少时间上界

影响：异常连接的清理可能拖延诊断请求收尾。

处置：已修复。关闭动作增加 5 秒超时且不会覆盖原诊断结果。

### [suggestion] 并发总量需要显式回归

处置：已补充。服务的全局在途诊断上限为 128，容量耗尽返回安全、可重试结果，并有单元测试覆盖。

当前未发现未处理的 blocking、major、minor 或 suggestion。

## 无法验证项

- 未使用用户真实 LLM/MCP/A2A 凭据和外部端点执行联网诊断；自动测试使用受控 Adapter/Fake 验证协议、超时与错误投影，部署到 8088 后由用户手工验收真实连接。
- 本次为同一 Agent 自检；独立 Reviewer 可进一步降低盲区。

## 合并门禁

| 门禁 | 结果 | 证据 |
| --- | --- | --- |
| 无 blocking | 通过 | 未发现 blocking |
| 无未处理 major/minor | 通过 | 5 个 major/minor 均已修复并回归 |
| 验收标准满足 | 通过 | 设计验收项均有实现与自动测试证据 |
| 后端测试 | 通过 | 605 passed；11 个既有 Pydantic 弃用 warning |
| 前端测试 | 通过 | 48 files、205 tests passed |
| 静态与类型 | 通过 | Ruff、compileall、vue-tsc、`git diff --check` 通过 |
| 生产构建 | 通过 | Vite 构建通过，3683 modules transformed |
| 数据迁移 | 不适用 | 本阶段无迁移；空库 Alembic 到 head 验证通过 |

## 审查结论

- 结论：`APPROVED`
- 理由：功能满足 Stage 4B 设计，已关闭审查发现的所有问题，全量回归和构建门禁通过，未发现未处理 blocking、major 或 minor。
- 剩余风险：真实外部 Provider 的网络、凭据和协议差异需在 8088 环境手工验证；当前健康仅是按需瞬时结果，不用于 Lead 自动路由。
- 下一步：形成 Stage 4B 单一提交并部署到 8088；收集使用反馈后再决定是否设计 Stage 4C 健康历史与路由反馈。
