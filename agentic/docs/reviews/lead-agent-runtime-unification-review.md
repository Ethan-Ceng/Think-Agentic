# Lead Agent Runtime Unification 代码审查

## 审查范围

- 目标分支：`develop`
- 变更分支：`feature/lead-agent-runtime-unification`
- 变更范围：当前未提交工作区相对 `develop` 的 Lead Agent Runtime 改造
- 设计文档：`agentic/docs/designs/lead-agent-runtime-unification.zh-CN.md`
- 计划文档：`agentic/docs/plans/lead-agent-runtime-unification-plan.md`
- 审查者：同一 Agent 自检
- 审查日期：2026-08-18

## 需求与正确性结论

- `AgentTaskRunner` 只面向一个 `LeadAgent` 顶层入口；`PlannerAgent`、`ReActAgent` 与 Legacy Flow 仅作为 Lead 内部策略和回滚实现。
- Direct 复用首轮结构化决策答案，不创建 Plan/Step、不调用 Tool 或 Summarizer；附件、URL、时效信息和显式外部动作由服务端硬约束拦截。
- React 以单一 Goal 执行 Tool Loop，不产生用户可见 Plan/Step；Plan 只在多步骤任务中出现，成功步骤使用确定性更新，失败或 `needs_replan` 才调用 Planner，重规划最多 2 次。
- Step 的 `success=false` 会落为 `FAILED`，不会继续伪装为成功；Plan、React 的 HITL 均能恢复到原 Tool Call。
- Feature Flag 默认关闭并完整回退 Legacy；已处于等待状态的 Lead Run 不受后续开关变化影响。
- Trace 仅记录受控的模式、原因码、耗时、重规划次数和完成状态，不记录模型隐藏推理或敏感 Tool 参数。
- Lead Decide 在语言尚未知时使用精简双语 Prompt；决策后的 Planner、React Goal/Step 与 Finalizer 通过 Runtime Prompt Catalog 选择 `zh/en` Pack。英文 Prompt 已有生产调用者，当前 Run 的 System Prompt 只覆盖 LLM messages 视图，不污染持久化 Memory。
- 未新增数据库字段或迁移；Interaction Event 新字段均有默认值，旧事件可以继续解析。

## 审查中发现并已修复的问题

### [major][已修复] 运行中关闭 Feature Flag 会错误切换恢复引擎

位置：`agentic/api/app/core/agent/lead.py:446`

问题：最初实现先检查当前 Feature Flag，再判断 `interaction_response`，导致已经由 Lead 暂停的 Run 在恢复时可能被交给 Legacy Flow。

影响：Legacy Memory 与 Lead 的 Plan/Goal 上下文不一致，可能无法恢复审批中的原 Tool Call。

处置：先按持久化的 `lead_mode` 恢复在途 Run，仅对新 Run 应用当前 Feature Flag；增加关闭开关后恢复 React 的回归测试。

### [major][已修复] HITL 恢复丢失原 Run 的 Skill 选择

位置：`agentic/api/app/core/entities/event.py:72`、`agentic/api/app/services/agent_service.py:286`、`agentic/api/app/core/agent/lead.py:198`

问题：暂停事件最初没有持久化本 Run 的 `SkillRef`，恢复 Task 因而会使用空 Skill 上下文。

影响：恢复后的提示上下文和可用 Tool 可能与暂停前不同，破坏同一个 Run 的执行连续性。

处置：在内部 Interaction Event/Resolution 中携带 Skill 引用，并在恢复 Task 中重新传入；React、Plan 和服务层均增加回归覆盖。

### [major][已修复] Plan 重规划上限在暂停恢复后重置

位置：`agentic/api/app/core/entities/event.py:91`、`agentic/api/app/core/agent/lead.py:278`、`agentic/api/app/core/agent/lead.py:415`

问题：最初只在 `_continue_plan` 的局部变量中保存重规划次数，HITL 恢复后从 0 重新计数。

影响：通过多次暂停恢复可以绕过最多 2 次的重规划上限，增加成本并可能形成长循环。

处置：把非负 `lead_replan_count` 写入 Interaction 上下文并在恢复时继续计数；增加达到上限后的恢复回归测试。

### [major][已修复] 英文 Prompt 资产未进入生产运行链路

位置：`agentic/api/app/core/prompts/catalog.py`、`agentic/api/app/core/agent/base.py`、`agentic/api/app/core/agent/planner.py`、`agentic/api/app/core/agent/react.py`

问题：升级保留了 `prompts/en`，但 Planner/ReAct 仍静态导入主目录中文 Prompt；System Prompt 又在 Memory 初始化时固定，英文文件实际上不可达。`mooc-manus/api` 参考实现也只有两套静态资产，没有提供 Runtime Locale 接线。

影响：英文会话仍以中文执行规则调用模型，中英文镜像继续漂移；同一 Agent 跨 Run 切换语言时无法可靠替换 System Prompt。

处置：新增 `zh/en` Prompt Catalog；Lead Decide 保持精简双语，语言确定后按 Run 选择 Planner/React Pack；BaseAgent 仅覆盖本次 LLM messages 副本。增加生产引用、Planner/React/Finalizer、跨 Run 与 HITL Resume 回归。

### [major][已修复] 非中文 CJK 语言标签误选中文 Prompt Pack

位置：`agentic/api/app/core/prompts/catalog.py`

问题：增量审查发现早期 Locale 解析把任意 CJK 字符视为中文，导致 `日语`、`日本語` 等明确非中文标签选择中文 Pack。

影响：用户虽指定非中文输出语言，执行阶段却收到中文指令模板，降低语言遵循的稳定性。

处置：只把明确中文标签和中文标记解析为 `zh`；明确英文及其他未知非中文语言使用 `en` 指令 Pack，且不修改原始输出语言字段。新增日语标签回归后重新执行完整验证。

## 剩余非阻塞问题

### [minor] Lead 迁移适配器依赖 Legacy Flow 私有成员

位置：`agentic/api/app/core/agent/lead.py:119`

问题：Lead 为复用同一套 Tool Registry 和 Runtime Scope，当前读取了 Legacy Flow 的 `_tools` 与 `_tool_factory`。

影响：后续单独调整 Legacy Flow 内部字段时，需要同步修改 Lead 构造逻辑。

建议：在删除 Legacy 回退前，为 Flow 提供显式 Runtime Components 接口，或由 Lead 直接持有 ToolFactory。本批保留该耦合以避免双份 Tool 实例和扩大迁移范围。

### [minor] Legacy 首轮混合语言只使用确定性规则选择指令 Pack

位置：`agentic/api/app/core/prompts/catalog.py`

问题：Feature Flag 关闭的 Legacy 首轮尚无 Lead 结构化 `language`，因此按首个有语言特征的字符选择 `zh/en` 指令 Pack。

影响：极少数中英混合且开头语言不代表主要意图的消息可能选择非最佳指令 Pack；它不覆盖输出语言要求，后续轮次会以 Plan `language` 为准。

建议：保留为 Legacy 兼容策略；Lead 路径启用后由模型决策与服务端约束提供工作语言。真实模型评测若显示该边界显著，再引入独立轻量语言检测，而不是扩展 Prompt Pack 数量。

## 无法验证项

- 当前没有目标生产模型凭据和线上延迟基线，未运行真实模型的路由准确率、TTFT 与总延迟评测；离线代表任务集只能验证契约和确定性边界。因此 `lead_agent_enabled` 默认保持 `false`。
- 未做真实外部 Tool/A2A 端到端调用；本批没有修改 A2A 协议，现有 A2A 仍作为 Capability/Tool Adapter 进入 React 或 Plan Step。
- 本批没有数据库迁移，迁移验证不适用。

## 合并门禁

| 门禁 | 结果 | 证据 |
| --- | --- | --- |
| 无 blocking | 通过 | 自审未发现 blocking |
| 无未处理 major | 通过 | 3 个恢复连续性 major 与 2 个 Prompt Locale major 均已修复并增加回归测试 |
| 验收标准满足 | 通过 | Direct/React/Plan、失败语义、HITL、Feature Flag、Trace、Prompt Locale 均有聚焦测试 |
| 相关测试通过 | 通过 | 增量修复后的最终聚焦回归 128/128 |
| 静态与编译检查 | 通过 | Ruff、`compileall`、`git diff --check` 均为 Exit 0 |
| 数据迁移已验证 | 不适用 | 未新增迁移 |

## 审查结论

- 结论：`APPROVED`
- 理由：没有未解决 blocking/major；3 个运行状态连续性问题、英文 Prompt 不可达问题和非中文 CJK 误路由问题均已修复，修复后 128 项回归与静态门禁全部通过。
- 剩余风险：真实目标模型路由/延迟和外部 Tool 端到端尚未验证，Feature Flag 因此默认关闭；同一 Agent 自审不如独立 Reviewer 可靠。
- 下一步：代码与离线验证范围可进入合并；之后在 Staging 用目标模型完成路由集与延迟评测，再考虑默认开启 Feature Flag。不自动提交、推送、创建 PR 或合并。
