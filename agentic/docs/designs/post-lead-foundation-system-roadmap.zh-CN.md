# Lead 基础完成后的系统优先级路线

## 文档状态

- 状态：`DESIGN_READY`
- 负责人：Codex
- 创建日期：2026-08-19
- 最近更新：2026-08-19
- 适用基线：统一 Lead、Token Delta、Ask-only WAITING、Lazy Sandbox、统一 Tool Plane、MCP/A2A Runtime、Failure UX 和 Provider 按需诊断均已落地
- 后续关联：`docs/plans/durable-solo-lead-runtime-plan.md`

## 背景

当前 Lead Agent 已经具备 Direct/ReAct/Plan 三种执行模式、最小工具选择、真实流式输出、自然多轮对话、仅业务输入等待、Sandbox 晚激活和外部 Provider 惰性接入。2026-08-19 的实际测试也确认普通多轮对话与 Provider 诊断工作正常。

继续立即建设 Durable Run、跨进程 Lease、Effect Ledger 和本地 Child Execution 可以进一步加固运行时，但它会提前固化 Profile、Knowledge、Memory、Tool Effect 和 Verification Snapshot 等系统契约。当前这些上层载荷尚未形成真实产品闭环，如果先把 Lead Runtime 做到很深，后续建设项目知识、平台治理和发布能力时可能再次改写快照、权限与恢复模型。

因此，本路线把 Durable Solo Lead 保留为已记录的后续加固项，当前先补齐 Lead 之外、但会决定未来 Lead 输入和约束的系统能力。

## 目标

- 建立可重复的质量评测和运行观测闭环，使后续改动能量化判断是否改善正确性、延迟、成本和工具选择。
- 把现有 Project、File、Skill 和 Session 从导航功能连接成可控的项目知识工作区，为 Lead 提供真实、带来源、可撤销的上下文。
- 在继续扩大外部 Provider、发布入口和用户规模前，建立平台级配额、凭据、执行策略、网络出口和审计边界。
- 延后但不丢失 Durable Lead、本地 Sub Agent、Project Memory 与 ContextCompiler 路线，并为它们定义明确恢复条件。

## 功能范围

本路线确定后续模块的优先级、依赖和进入条件：

1. 系统基线与质量反馈闭环。
2. Project Knowledge Workspace 与文档处理/检索基础。
3. 平台控制面与多用户治理。
4. 受控发布和外部消费入口。
5. 在上述契约稳定后恢复 Durable Lead、Sub Agent 和 ContextCompiler。

## 非功能范围

- 本文不直接实施数据库迁移、公共 API、页面或 Lead Prompt 改造。
- 不在一个 Stage 中同时建设评测、Knowledge、治理和 Durable Runtime。
- 不把文件全文、Project 全部历史、Trace 或 Provider 配置自动注入模型。
- 不建设终端用户逐工具审批；平台安全仍由确定性策略、隔离、配额、网络和审计负责。
- 不为了“主流功能齐全”优先实现低价值的对话导出、统一资源选择器或装饰性管理页面。

## 业务流程

1. 开发者通过稳定任务集和 Run/Trace 信号观察 Lead 的路由、工具、质量、延迟、Token 与错误。
2. 用户创建或选择 Project，显式绑定文件、Knowledge 和 Skill；后台处理文件并生成带版本、来源和质量状态的可检索内容。
3. Lead 只读取当前 Session/Project Scope 允许的上下文摘要，必要时检索具体证据并在答案中返回引用。
4. 平台在 Tool/Provider 执行前应用租户权限、配额、凭据引用、Execution Class 和网络出口规则，并记录脱敏审计。
5. 系统具备稳定的真实任务、上下文载荷和安全约束后，再把它们固化进 Durable Snapshot、Safe Point、Effect Ledger 和后续 Child Execution。

## 核心规则

1. 先稳定 Lead 的输入、权限和评价标准，再固化 Lead 的跨进程恢复协议。
2. Project 首先是显式 Scope，不等于把所有项目内容无条件注入 Prompt。
3. Knowledge、Tool、Memory 和外部 A2A 内容均属于带来源 Observation，不能覆盖系统策略或用户目标。
4. 评测必须同时覆盖正确性、路由、工具范围、延迟、成本和失败恢复，不能只看模型主观回答质量。
5. 平台治理不得依赖终端用户判断风险；不满足 Capability、配额、网络或幂等要求时确定性拒绝。
6. 发布入口必须建立在凭据、配额、审计和滥用防护之上，不能先开放匿名 Agent Endpoint 再补安全。
7. Durable Lead 不是取消，而是等待真实 Context Binding、Execution Policy 和质量门禁稳定后恢复。

## 现有实现分析

### 相关代码与文档

- `api/app/core/agent/lead.py`：统一 Lead 执行入口，现有 Direct/ReAct/Plan 行为基线。
- `api/app/services/trace_service.py`：已有 Run、Lead Decision、Model Call、Skill、Token、延迟和脱敏记录，可作为质量反馈底座。
- `api/app/models/run_trace.py`：已有 Run/Step/Tool/Model/Trace 持久化模型，但尚无评测任务集、质量标注和聚合看板。
- `api/app/models/project.py` 与 `api/app/models/session.py`：Project 已能组织 Session，但当前设计明确不向 Agent 注入 Project 上下文。
- `api/app/controllers/file.py`：已有用户隔离的文件上传、目录、预览、下载和管理能力。
- `api/app/models/skill.py` 与 Skills 页面：个人 Skill、版本、安装、Run 使用和 Marketplace 已落地，可直接成为 Project Context 的一种显式绑定类型。
- `docs/designs/knowledge-document-processing.zh-CN.md`：已定义文档 Revision、Block、Retrieval、引用和安全边界。
- `docs/plans/document-processing-foundation-plan.md`：TXT/Markdown 文档处理底座为 `PLAN_READY`，但尚未实施。
- `docs/tool-management.zh-CN.md`：已记录 Execution Class、Capability Grant、网络出口、工具审计和配置审计缺口。
- `docs/plans/durable-solo-lead-runtime-plan.md`：Durable 方案已经拆分，但其部分基线早于统一 Lead、通用审批移除和 Provider Runtime，需要恢复前重新设计。

### 可复用能力

- 现有 Trace 数据已包含 Lead mode、模型用量、延迟和 Tool/Skill 记录，可先做离线评测与聚合，不必重建追踪系统。
- Project、Session、File 和 Skill 均已按用户隔离，有现成 Repository、API 和前端入口。
- Lazy Sandbox、统一 Tool Scope、Provider Catalog 和 FailureInfo 可直接复用于 Knowledge Tool 与平台治理。
- 文档处理设计已覆盖异步 Job、租约、幂等、质量告警和引用，不需要重新发明完整方案。

### 当前约束

- `docs/current-state.zh-CN.md` 的部分结论已经滞后，例如仍将 Skill 和旧 Planner/ReAct 主线描述为未升级状态；开始下一实施批次前需刷新事实基线。
- Project 当前只是 Session 单层导航目录，不拥有 Knowledge、Skill、Agent 配置或 Memory Scope。
- 文件中心能保存和预览文件，但没有 Document Revision、结构化解析、检索索引和引用闭环。
- Trace 能查看单次 Run，但缺少稳定评测集、Run 对比、质量反馈、聚合指标和发布门禁。
- 组织、角色、API Token、用量配额、配置审计、Capability Grant 和网络出口策略仍未形成统一控制面。

## 可选方案

### 方案 A：继续 Lead/Durable 优先

- 实现方式：立即执行 Durable Solo Lead 的十个任务，再建设 Knowledge、治理和发布。
- 优点：最早获得进程重启、Redis 丢失、SSE 断开和长任务恢复能力。
- 缺点：会在 Knowledge、Project Context、Capability Grant 和发布形态未稳定前固化 Snapshot 与状态机。
- 风险：后续新增真实上下文载荷和外部副作用分类时，需要修改迁移、恢复和 Effect Ledger。

### 方案 B：系统闭环优先，之后恢复 Durable Lead

- 实现方式：先做质量反馈基线，再建设项目知识工作区和平台治理；发布边界稳定后恢复 Durable Lead。
- 优点：每一步都有直接产品价值，也能为 Durable Snapshot、Verification 和 Effect Ledger 提供真实输入。
- 缺点：在 Durable 实施前，进程崩溃和多实例接管仍保持当前限制。
- 风险：如果出现大量长任务或频繁重启，Durable 延后会放大运行中断影响。

### 方案 C：用户界面广度优先

- 实现方式：先实现对话导出、统一资源选择器、更多设置页和视觉功能，再处理 Knowledge、治理和 Durable。
- 优点：交付快、演示功能多、风险较低。
- 缺点：没有显著提高 Agent 完成复杂真实任务的能力，也不能解决平台规模化边界。
- 风险：形成“功能很多但上下文、质量和安全闭环不足”的产品。

## 方案对比

| 维度 | 方案 A：Durable 优先 | 方案 B：系统闭环优先 | 方案 C：UI 广度优先 |
| --- | --- | --- | --- |
| 实现复杂度 | 高 | 分阶段，中高 | 低中 |
| 用户近期价值 | 主要体现在异常场景 | 高，知识和项目任务直接可用 | 中，主要改善便利性 |
| 架构返工风险 | 中高 | 低中 | 中 |
| 维护成本 | 状态机和迁移先增重 | 随真实模块逐步增长 | UI 面增多但核心能力不变 |
| 兼容性 | 需要大规模运行时切流 | 各模块可独立 Feature Flag | 高 |
| 测试难度 | 很高，需故障演练 | 可逐模块建立评测和门禁 | 低中 |
| 主要风险 | 固化不完整契约 | Durable 被无限延期 | 产品表面化 |

## 推荐方案

采用方案 B。

Lead 框架已经足以承载当前任务，系统现在更缺少的是：知道 Lead 是否真的做对、让它能使用稳定的项目知识、以及确保所有用户和外部 Provider 在平台规则内运行。这三类能力会反过来定义 Durable Run 必须冻结什么、恢复什么、对账什么和验证什么。

不选择方案 A，是因为当前 Durable 计划中的 Profile、Knowledge Snapshot、Approval/Effect 和旧 PlannerReAct 基线已有部分过时，直接执行会把历史假设带入新状态机。不选择方案 C，是因为便利性功能可以后补，不能替代质量、上下文和治理闭环。

## 推荐实施顺序

### S0：系统事实基线与 Agent Quality Loop（P0）

- 首个子设计采用 `docs/designs/run-trace-execution-chain-ux.zh-CN.md`：先修正 Trace 安全、查询和执行链合同，再建设质量聚合与评测。
- 刷新 `current-state`，明确已完成和真实缺口。
- 建立版本化离线任务集，覆盖 Direct/ReAct/Plan、工具选择、Provider 失败、Ask、附件、Skill 和多轮上下文。
- 基于现有 Trace 输出成功率、模式分布、TTFT、总延迟、Token、Tool 次数、错误码和用户重试等指标。
- 增加 Run 级用户反馈和内部评测结果，但不保存隐藏思维链。
- 为后续 Stage 建立“不能让哪些指标退化”的发布门禁。

### S1：Project Knowledge Workspace（P0/P1）

- 先执行 Document Processing Foundation，用 TXT/Markdown 打通 Revision、Block、Job 和受控 Document Tool。
- 再增加 Project 对 File/Knowledge/Skill 的显式版本化绑定，不自动绑定全部用户文件。
- 建立 scoped retrieval、引用和质量告警；权限过滤必须发生在检索前。
- 最后补统一资源选择器，使用户能清晰选择本轮文件、Skill 和 Project Knowledge。

### S2：平台控制面与多用户治理（公开部署前 P0）

- 用户/组织/角色与管理员边界。
- 用量配额、并发上限、速率限制和资源回收。
- Secret Reference 与凭据轮换，前端不回传真实 Secret。
- Provider Execution Class、Capability Grant、网络出口与确定性拒绝。
- Tool/Provider 调用审计、配置变更审计和外部副作用幂等基础。

### S3：受控发布与外部消费（P1）

- 用户级 API Token、OpenAPI Chat 和可撤销发布版本。
- Web App/嵌入入口的域名、配额、鉴权和滥用防护。
- A2A Agent 发布、认证与 Task 生命周期；与当前外部 A2A Tool Adapter 保持方向区分。

### L2：恢复 Lead 深化路线

- 按最新 Project Context、Knowledge、Governance 和 Trace 事实重新设计 Durable Solo Lead。
- 完成 Safe Point、Lease、Outbox、Effect Ledger、Verification 和可重放 SSE。
- Durable Solo Lead 稳定后再引入本地 Child Execution、有界并行、Project Memory 和 ContextCompiler。

## Durable Lead 恢复条件

满足任一运行压力条件，并且全部契约条件成立时恢复 Durable 设计：

运行压力条件：

- 出现需要跨进程持续执行的长任务；
- 需要 API 多实例部署或滚动升级不停 Run；
- 真实数据表明进程重启、SSE 重连或 Redis 故障造成不可接受的任务丢失。

契约条件：

- Project/Knowledge/Skill 的 Run Scope 和版本引用已经稳定；
- Execution Class、Capability Grant 和外部副作用分类已经确定；
- Trace/Eval 能判断恢复前后结果是否一致；
- 现有 Durable 计划已删除旧 PlannerReAct 和终端 Tool Approval 假设，并重新通过设计审查。

## 数据结构

本文不直接新增数据结构。各阶段设计时至少评估以下概念对象，但不得据此跳过独立设计：

| 概念 | 主要字段 | 用途 |
| --- | --- | --- |
| `QualitySignal` | run_id、runtime_version、mode、outcome、latency、usage、failure_code | 质量和回归门禁 |
| `EvaluationCase/Result` | case_version、input_ref、expected_constraints、actual_summary、score | 版本化离线评测 |
| `ContextBinding` | user_id、scope_type/id、resource_type/id/version、enabled | Project/Session 显式上下文范围 |
| `AuditRecord` | actor、action、target、decision、reason_code、trace_id、created_at | 平台确定性策略和配置审计 |

## 接口设计

本文不直接新增公共接口。进入各阶段前分别设计：

- S0：离线评测命令、Run 反馈和聚合查询边界。
- S1：Document Job、Context Binding、Retrieval 和 Citation 接口。
- S2：管理员、配额、Secret Reference、Grant 和 Audit 接口。
- S3：Token、Publish Revision、External Run 和撤销接口。

所有接口必须按用户/组织隔离，错误使用稳定 FailureInfo 或对应平台错误结构；不得把原始凭据、完整 Prompt、隐藏思维链或外部响应正文写入响应和日志。

## 错误处理与可观测性

- 每个 Stage 必须先定义稳定错误码和可观察指标，再接入 Lead 自动行为。
- 质量指标区分模型失败、Provider 失败、平台策略拒绝、文档质量不足和用户取消。
- Knowledge 处理允许部分成功并携带质量告警；不能用空检索结果伪装成功。
- 平台拒绝记录安全 reason_code 和 trace_id，不记录 Secret、Header、文件正文或 Tool 参数全文。
- Durable 恢复前先具备跨版本评测，避免只证明“状态恢复了”却无法证明“语义没有漂移”。

## 迁移与回滚

- 本路线文档本身无数据库迁移。
- 每个 Stage 独立分支、独立设计、独立计划和独立提交，使用 Feature Flag 或可逆绑定逐步启用。
- S0 只读消费现有 Trace 时可直接关闭聚合/反馈入口回滚。
- S1 的原始 File 不可变，Document Revision 和 Index 可重建；取消 Context Binding 即可停止注入。
- S2 的安全策略回滚只能收紧或回到已知安全规则，不得回滚为终端用户逐次审批或默认放行。
- Durable 恢复时继续保留 Legacy Runtime Feature Flag，已开始的 Run 不跨 Runtime 迁移。

## 风险

| 风险 | 可能性 | 影响 | 缓解措施 | 验证方式 |
| --- | --- | --- | --- | --- |
| Durable 被长期延期 | 中 | 高 | 定义明确恢复条件，每个季度或出现压力信号时复审 | 路线复审记录、故障统计 |
| S0 变成重型监控平台 | 中 | 中 | 首期只做版本任务集、聚合查询和最小反馈 | 交付范围审查 |
| Project 自动注入导致上下文膨胀 | 高 | 高 | 显式 Binding、检索优先、Token Budget 和引用 | Context token 与检索评测 |
| 文档处理范围失控 | 中高 | 高 | 先 TXT/Markdown，再按真实需求扩 PDF/Office/OCR | 分格式验收门禁 |
| 平台治理阻碍普通用户 | 中 | 中 | 安全拒绝可解释、默认策略按执行类别而非逐工具配置 | 允许/拒绝任务集 |
| 发布入口早于治理 | 中 | 高 | S3 以 S2 关键门禁通过为前置 | 发布 API 权限与滥用测试 |
| current-state 文档继续漂移 | 高 | 中 | S0 将代码/API/迁移扫描纳入状态文档验收 | 文档事实检查 |

## 重要假设

- 当前主要目标仍是让一个统一 Lead Agent 优秀、好用，而不是立即建设多 Agent 管理平台。
- 当前部署和试用规模允许暂缓跨进程 Durable Run，但不能删除已有计划和风险记录。
- 用户价值更依赖真实文件/知识任务、可理解的质量反馈和稳定平台边界，而不是继续增加聊天页小功能。
- Skills 已经是已实现能力；后续重点是与 Project/Knowledge Scope 的显式组合，而不是重新建设 Skill 基础。
- 对话导出和统一资源选择器仍可保留，但只有在 S1 需要统一选择 Knowledge/File/Skill 时才重新排序资源选择器。

## 待决策项

无影响本路线排序的核心未决项。进入 S0 时需要单独确认首批真实评测任务集；进入 S1 时需要单独确认优先文档格式；进入 S2 时需要确认产品是单租户自部署还是多租户服务，这些属于对应阶段设计输入。

## 验收标准

- [x] Durable Solo Lead、Sub Agent、Project Memory 和 ContextCompiler 已被记录且有明确恢复条件。
- [x] 当前推荐路线不要求继续改造 Lead Prompt、路由或执行状态机。
- [x] 已比较 Durable 优先、系统闭环优先和 UI 广度优先三种方案，并明确推荐方案 B。
- [x] S0—S3 与后续 L2 的依赖、范围和非目标清晰，不把多个子系统混入一个 Stage。
- [x] Project/Knowledge、平台治理和发布入口均保持用户隔离、敏感信息和副作用安全边界。
- [x] 每个后续 Stage 都要求独立设计、计划、验证和回滚，不允许从本路线直接进入大规模编码。
