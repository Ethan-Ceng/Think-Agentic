# Agentic 自主 Agent 升级架构总图

## 文档状态

- 状态：`DESIGN_READY`
- 负责人：Agentic Runtime
- 创建日期：2026-08-17
- 最近更新：2026-08-17
- 设计优先级：当本文与 `roadmap.zh-CN.md` 中的 Agent Profile、Agent 发布或多 Agent 产品化描述冲突时，以本文为准

## 一句话结论

保留 `agentic` 现有“一个聊天入口、一个自主 Agent”的产品形态，在原有 `AgentService → AgentTaskRunner → PlannerReActFlow` 主线上增量升级耐久 Runtime；用户始终只面对一个 Agent，固定 Lead 在内部按需创建 General Worker、Researcher、Reviewer Execution，不建设 Agent 创建、发布、版本运营或多 Agent 管理平台。

## 一页架构总图

```text
┌────────────────────────────── 用户产品面 ──────────────────────────────┐
│  Chat / Workspace（唯一主入口）                                       │
│  ├─ Goal / 消息 / 文件 / Skill                                       │
│  ├─ Plan / Progress / Interaction / Artifact                          │
│  └─ Execution Tree / Verification / Usage（按需展开）                 │
│                                                                       │
│  Projects + Memory       Skills          Settings + Runtime Overview  │
│  项目、文件、受控记忆     现有 Skill 体系   模型/Tool/MCP/A2A + 只读配置 │
└─────────────────────────────────┬─────────────────────────────────────┘
                                  │ HTTP Command / Query / SSE
                                  ▼
┌──────────────────────────── 应用协调层 ────────────────────────────────┐
│ AgentService（兼容 API 门面）                                         │
│   └─ RunCoordinator（唯一运行裁决者）                                 │
│      ├─ Goal / Steering / Pause / Resume / Cancel                     │
│      ├─ ProfileResolver / SnapshotMaterializer                        │
│      ├─ ExecutionScheduler / Lease / Recovery                         │
│      ├─ Interaction / Approval / Side-effect Gate                     │
│      └─ Verification / Result Adoption / Budget                       │
└───────────────────────────────┬───────────────────────────────────────┘
                                │ durable command / observation
                                ▼
┌──────────────────────────── 统一 Runtime Core ─────────────────────────┐
│ BuiltinProfileRegistry                                                │
│   ├─ lead（固定一个 Root）                                            │
│   ├─ general_worker（固定 Profile，可产生多个 Execution）             │
│   ├─ researcher（按需 Specialist）                                    │
│   └─ reviewer（按需验证 Specialist）                                  │
│                                                                       │
│ AgentHarness：Observe → Decide → Command → Observe                    │
│   ├─ Direct / ReAct / Plan-ReAct                                      │
│   ├─ Delegate / Wait / Adopt                                          │
│   ├─ Verify / Repair / Replan / Finalize                              │
│   └─ ContextCompiler / PromptManifest / Working Memory                │
└───────────────────────┬─────────────────────────────┬─────────────────┘
                        │ ports                       │ durable facts
                        ▼                             ▼
┌────────────────── 执行适配层 ─────────────────┐  ┌─────────────────────┐
│ ModelGateway                                   │  │ PostgreSQL           │
│ ToolFactory / FilteredTool / Approval          │  │ Session / Goal / Run │
│ Skill Runtime / Knowledge                      │  │ Execution / Event    │
│ Lazy Sandbox / Browser / Shell / File          │  │ Tool/Model/Usage     │
│ MCP / API Tool                                 │  │ Interaction/Verify   │
│ External A2A Adapter（只连接外部 Agent）       │  │ Memory / Outbox      │
└────────────────────────────────────────────────┘  └──────────┬──────────┘
                                                               │ wake-up
                                                               ▼
                                                    Redis / Worker / SSE
                                                    只做通知，不做事实源
```

## 背景

`agentic` 已经具备聊天、Planner/ReAct、Tool、Sandbox、Browser、Shell、File、MCP、A2A、Skill、HITL、SSE、Run Trace 和用户配置，是更合适的升级基座。当前短板不在“缺少 Agent 发布平台”，而在运行生命周期仍依赖进程内对象：

- `RedisStreamTask._task_registry` 持有活跃 Task；服务重启后 Task 句柄丢失。
- `AgentService` 发现数据库仍为 running 但进程内 Task 不存在时，只能把 Run 标记为中断，再让用户选择继续或重启。
- `PlannerReActFlow` 直接创建 `PlannerAgent` 和 `ReActAgent`，规划、执行、委派、验证尚未统一为可恢复的 Harness 状态机。
- `agent_runs`、`run_steps`、`tool_calls`、`model_calls`、`trace_events` 已有良好基础，但当前由 `TraceService` 投影产生，还不是执行恢复的权威事实。
- 当前路线文档提出用户创建多个 Agent Profile 并发布为 Web/API/A2A，这会把产品推向 Agent Builder，与最终确认的单一 Agent 产品边界不符。

升级目标是把现有执行型 Agent 变得更耐久、更自主、更可验证，而不是把它改造成 LLMOps 或多 Agent 发布平台。

## 目标

- 用户继续通过一个对话入口完成简单问答、研究、文件处理和有界工具任务。
- 每个 Root Run 自动使用唯一内置 Lead，不要求用户创建、选择或发布 Agent。
- Lead 可按需创建多个独立 General Worker Execution，以及 Researcher、Reviewer Execution。
- 简单任务不强制规划或委派；复杂任务可 Plan、Delegate、Wait、Adopt、Verify 和有限修复。
- 进程重启、Worker 崩溃、Redis 短暂不可用或 SSE 断线后，Run 能从数据库 Safe Point 恢复。
- 每个 Run 固定实际模型、Profile、Tool、Skill、Knowledge、Sandbox、Memory 和 Verification 配置快照。
- Project Memory 只接受用户显式写入或审阅后发布的 Candidate，不做无审计的后台长期学习。
- 复用现有 Tool、Skill、Sandbox、HITL、Trace、文件和 Web UI，避免重建已经工作的能力。

## 功能范围

1. 代码内置 Profile Registry 与只读 Effective Profile Snapshot。
2. 统一 AgentHarness 与 Direct、ReAct、Plan、Delegate、Verify 策略。
3. Durable Goal、Run、Execution、Event、Lease、Recovery 和 Outbox。
4. 固定 Lead 与本地 General Worker、Researcher、Reviewer Child Execution。
5. Context Compiler、Prompt Manifest、Working/Run/Session/Project Memory。
6. Tool Side-effect Ledger、Approval、Sandbox 和 Artifact 证据。
7. Deterministic Check + Reviewer 的完成验证与有限 Repair/Replan。
8. SSE 可恢复事件流、Execution Tree、Usage 和只读 Runtime Overview。

## 非功能范围

- Agent Definition CRUD、Draft、Publish、Activate、Rollback、Marketplace。
- 用户创建第二个 Lead、第五种内部 Agent，或修改 Lead→Child 拓扑。
- 本地 Lead/Worker/Specialist 使用 A2A 通信。
- Team、DAG、Swarm、Handoff、Worker 递归委派和深度大于 1 的 Child Tree。
- 重型 LLMOps、Workflow 画布、组织级 RBAC、无人值守 Trigger 平台。
- 自动 User/Episodic 长期记忆、在线自修改 Prompt/Profile/Skill。
- 保存或展示模型隐藏思维链。

## 产品信息架构

不新增“Agent 定义”“Agent 发布”“Agent 版本”菜单。建议收敛为四个用户心智：

| 产品区域 | 用户心智 | 主要内容 |
| --- | --- | --- |
| Chat / Workspace | 和一个 Agent 协作 | Goal、消息、文件、计划、交互、结果、Execution Tree、Verification |
| Projects + Memory | 给 Agent 稳定项目上下文 | 项目、文件、用户发布的 Memory、Candidate 审阅、来源与纠正 |
| Skills | 扩展做事方法 | 复用现有 Skill 编辑、版本、选择、Marketplace 和运行 Trace |
| Settings + Runtime | 配置基础能力并查看实际状态 | Model、Tool、MCP、外部 A2A、Sandbox；内置 Profile 仅只读预览 |

Files 可以继续保留独立页面，但语义上属于 Workspace/Project 资产，不形成第五个 Agent 管理概念。

## 核心规则

1. 对外永远只有一个 Agent；每个 Root Run 自动创建一个 Lead Execution。
2. `lead`、`general_worker`、`researcher`、`reviewer` 由代码和随应用打包的只读 JSON/Markdown 注册。
3. 四个 Profile 共用同一个 AgentHarness，差异只来自有效模型、Instructions、Capability、Policy、Runtime Limit 和 Verification Snapshot。
4. General Worker 是一个 Profile、多份 Execution，不是动态生成多个 Agent 定义。
5. Lead 只能通过当前 Run 固定的 Child Catalog 委派；请求、模型和数据库都不能扩大拓扑。
6. 本地 Child 必须经 RunCoordinator 创建、调度、取消和采用；A2A 只代表外部远程能力。
7. PostgreSQL 是状态事实源；Redis Stream 只做唤醒和传输优化，丢失后不得丢失 Run。
8. HTTP/SSE 连接不拥有执行生命周期；客户端断开不取消 Run，除非收到显式 Cancel Command。
9. 所有外部动作先形成 Command，再由 Coordinator 检查权限、预算、Approval、幂等和 Side-effect Ledger。
10. `finalize` 只是模型建议；只有 Runtime Check 和任务 Verification 通过后 Run 才能成功。
11. Child 输出是低信任 Result Envelope；Lead 必须记录 adopt、reject 或 conflict resolution。
12. Run 运行中不热切模型、Prompt、Tool、Skill、Knowledge 或 Policy；配置变化只影响新 Run。
13. Prompt 中低信任内容只能作为带来源的数据，不得覆盖 Runtime、用户授权或 Profile Instructions。
14. 不持久化隐藏推理；持久化 Public Plan、Decision Summary、Command、Observation、Evidence 和 Verification。
15. Project Memory 必须有 owner、project、source、status、revision 和审阅轨迹；模型只能提议 Candidate。

## 现有实现分析

### 可直接复用

| 现有实现 | 继续承担的职责 |
| --- | --- |
| `api/app/services/agent_service.py` | 保留聊天、SSE、HITL、下一条消息和会话兼容门面；逐步把运行裁决移交 RunCoordinator |
| `api/app/core/agent/agent_task_runner.py` | 过渡期执行适配器；复用附件、Skill、Tool Event、文件同步和资源清理 |
| `api/app/core/flows/planner_react.py` | 作为首个 Harness 策略适配器，行为稳定后拆除其对 Planner/ReAct 实例的直接编排 |
| `api/app/core/tools/factory.py` | 继续统一构建内置、API、MCP、外部 A2A Tool，并应用 FilteredTool Policy |
| `api/app/core/sandbox/runtime.py` | 继续提供 Lazy Sandbox、附件物化和生命周期观测 |
| `api/app/services/skill_*` | 继续负责 Skill 选择、物化、隔离、版本和 Trace |
| `api/app/services/trace_service.py` | 逐步变为 Durable Event 的投影器和查询服务，不再反向决定运行状态 |
| `api/app/models/run_trace.py` | 升级 `agent_runs`，复用 run_steps/tool_calls/model_calls；增加 Execution、Event、Verification 等事实 |
| `web/src/components/chat/**` | 保留聊天、Plan、Interaction、Artifact 和消息交互 |
| `web/src/components/TracePanel.vue` | 演进为 Timeline + Execution Tree + Verification/Usage 的可折叠运行详情 |

### 必须改变

- 用数据库可领取的 Execution + Lease 替代进程内 `_task_registry` 作为运行所有者。
- 用 RunCoordinator 替代 Controller、AgentService、Flow 对状态的分散写入。
- 用统一 AgentHarness 替代 PlannerAgent/ReActAgent 作为两个长期角色类的结构。
- 把 Trace 写入方向改成“Durable Event → Trace/UI Projection”，而不是运行逻辑顺带投影。
- 把 `sessions.events` 降为聊天兼容投影，不再承载恢复所需的唯一事实。
- 把现有单一 `llm_config` 解析为每个内置 Profile 的 Effective Model Snapshot；第一版可全部回落到同一模型。

## 可选方案

### 方案 A：把 FastAPI-AI 的 Agent 模块整体移植进来

- 实现方式：复制多层 Runtime、Repository、控制面和数据模型，再让 `agentic` UI 对接。
- 优点：耐久状态、评测和多 Agent 契约较完整。
- 缺点：与 `agentic` 的 Service Layer、现有 Tool/Skill/Session/Trace 重复，迁移面过大。
- 风险：再次把内部 Profile 误做成对外发布平台，并产生双套运行事实。

### 方案 B：在 agentic 原地提升 Run 为耐久 Runtime（推荐）

- 实现方式：保留现有 API/UI/Tool/Skill/Sandbox，以 RunCoordinator、AgentHarness、BuiltinProfileRegistry 和 Execution/Event 表替换进程内生命周期。
- 优点：最大化复用，用户体验连续，可逐段切换和回滚。
- 缺点：过渡期需要维护 `sessions.events`、Trace 与新 Durable Event 的单向投影。
- 风险：如果边界守卫不足，AgentService 和 PlannerReActFlow 可能继续拥有状态，形成双写。

### 方案 C：只增强 Planner/ReAct Prompt 和流程

- 实现方式：增加角色 Prompt、并发 asyncio Task 和最终 Reviewer 调用，不改持久化。
- 优点：交付最快，代码变化少。
- 缺点：仍不能真正恢复、审计、隔离 Child、处理副作用或保证完成语义。
- 风险：Demo 看似多 Agent，生产故障时仍丢失上下文并重复动作。

## 方案对比

| 维度 | 方案 A 整体移植 | 方案 B 原地提升 | 方案 C Flow 增强 |
| --- | --- | --- | --- |
| 实现复杂度 | 极高 | 中高、可切片 | 低 |
| 现有能力复用 | 低 | 高 | 高 |
| 产品边界匹配 | 容易过度平台化 | 最匹配 | 外形匹配、能力不足 |
| 恢复与一致性 | 可实现但迁移风险高 | 可实现且渐进 | 不满足 |
| 测试难度 | 极高 | 中高 | 中 |
| 回滚成本 | 高 | 低到中 | 低 |
| 主要风险 | 双系统、长期迁移 | 过渡期双写 | 伪耐久、伪多 Agent |

## 推荐方案

采用方案 B。`agentic` 已经拥有真正有价值的执行面和产品交互，缺的是运行状态的权威性，而不是更多控制面。升级应围绕“谁拥有 Run 状态、如何恢复、如何固定配置、如何验证结果”展开。方案 A 会重建现有能力并引入不需要的发布语义；方案 C 不能解决本次升级最关键的可靠性问题。

## Runtime 组件职责

| 组件 | 唯一职责 | 明确禁止 |
| --- | --- | --- |
| AgentService | 认证后的 HTTP/SSE 兼容门面、DTO 映射 | 持有 Task 生命周期、直接推进状态机 |
| RunCoordinator | Command、状态转换、幂等、预算、权限、Approval、Recovery | 生成自然语言答案、持有 Provider SDK 对象 |
| BuiltinProfileRegistry | 定义固定角色、能力上限和 Child Catalog | 读取数据库创建新 Agent 类型 |
| ProfileResolver | 解析当前用户模型/策略为 Effective Snapshot | 在运行中热切配置 |
| AgentHarness | Observe/Decide/Command 循环和策略切换 | 写 ORM、绕过 Coordinator 执行动作 |
| ExecutionScheduler | Lease、Heartbeat、并发、取消、重领 | 判断业务目标是否完成 |
| ContextCompiler | 按信任、来源、相关性和 Token Budget 编译上下文 | 让 Tool/Memory 指令覆盖高信任约束 |
| VerificationService | 确定性检查、Reviewer、Repair/Replan 决策 | 仅凭模型自报成功 |
| EventStore/Outbox | 顺序事实和投影通知 | 把 Redis 当规范历史 |

## 内置 Profile 与模型配置

建议资源目录：

```text
api/app/core/agent/profiles/
├─ registry.json
├─ lead.json
├─ general-worker.json
├─ researcher.json
├─ reviewer.json
└─ instructions/
```

Profile 至少包含：

```text
key / version / role / description
instructions_ref / output_contract
capability_ceiling / tool_policy / skill_policy
delegation_policy / allowed_child_refs
context_policy / memory_policy
verification_policy / runtime_limits / eval_suite_ref
```

模型解析规则：

1. 第一阶段四个 Profile 均可使用现有用户 `llm_config`，但仍分别生成 Effective Snapshot。
2. 后续如确有需要，只在 Settings 增加 `lead/worker/researcher/reviewer` 的窄模型覆盖；没有覆盖时回落到默认模型。
3. 模型配置不创建 Agent Definition，也不改变 Profile Key、职责和拓扑。
4. Run 创建时保存实际 Provider、Model、参数、Fallback 和能力检查结果；Lead 不得在 Spawn 时覆盖 Child 模型。

## 统一 AgentHarness

```text
Observation
  ├─ Goal / Plan / Last Result / Pending Interaction
  ├─ Tool / Skill / Memory / Child / Verification
  └─ Budget / Policy / Cancellation / Deadline
        ↓
Policy selects one mode
  Direct | ReAct | Plan-ReAct | Delegate | Verify | Repair
        ↓
Model returns structured Decision
        ↓
CommandRegistry validates
        ↓
RunCoordinator commits state and dispatches adapter
        ↓
Durable Observation + Event
```

现有 `PlannerAgent` 和 `ReActAgent` 第一阶段可以作为 Harness 内部适配器，确保行为不回归；最终长期结构只保留一个 Harness 和若干纯策略，不再让 Lead、Worker、Planner、ReAct 形成不同运行类。

## 关键业务流程

### 简单任务

1. 用户在 Session 发送消息。
2. AgentService 调用 RunCoordinator 创建 Run，自动解析 `lead` Effective Snapshot。
3. Worker 领取 Root Execution；Harness 选择 Direct 或 ReAct。
4. Runtime Check 与必要的 Task Verification 通过。
5. 最终消息、Artifact、Usage 和 Verification 投影到现有聊天 UI。

### 复杂任务与本地 Child

1. Lead 形成公开 Plan，并从固定 Child Catalog 选择 Opaque Capability Ref。
2. Coordinator 根据 Run 固定 Snapshot Map 创建 Child Execution；同一 General Worker 可创建多份 Execution。
3. Child 使用独立 Context、模型快照、预算、Lease 和 Result Envelope。
4. Lead 等待或继续其他工作，不占用 HTTP/SSE 连接。
5. Lead 对 Child 结果执行 adopt、reject 或 conflict resolution，并记录 Provenance。
6. Reviewer 只在风险、价值或 Verification Policy 要求时启动。

### Steering、HITL 与恢复

1. 用户提交 Steering、Pause、Resume、Cancel 或 Interaction Resolution Command。
2. Coordinator 在 Safe Point 检查 Goal Revision、当前副作用和状态版本。
3. 已确认的外部副作用不回滚；未开始动作可取消或重建。
4. Worker 崩溃后 Lease 过期，新 Worker 从 Execution Snapshot、Event、Tool Ledger 和 Pending Interaction 恢复。
5. Redis 丢失只影响唤醒延迟；周期扫描仍能重新领取 Ready Execution。

## Context 与 Project Memory

上下文采用四层：

```text
Working Memory   当前 Turn/Step 的短期状态
Run Memory       当前 Goal 的计划、证据、Artifact、Child Result
Session Memory   会话摘要和用户已确认事实
Project Memory   用户发布或审阅批准的项目事实/约束
```

ContextCompiler 固定信任顺序：Runtime Policy > 用户当前 Goal/约束 > 内置 Profile/激活 Skill > Task 数据 > Memory/Knowledge/Tool/Child 内容。所有低信任内容带 `source_ref`、`content_hash`、`trust_level` 和 `sensitivity`，不能通过文本伪装升级为指令。

Project Memory 生命周期：

```text
candidate → published → corrected
          └──────────→ deleted
```

模型和 Child 只能创建 Candidate；用户显式新增可直接 Published，或由用户审阅 Candidate 后发布。纠正创建新 Revision，删除清理可检索内容但保留无明文墓碑和审计事件。

## 数据结构

### 需要升级或新增的耐久事实

| 实体 | 关键字段 | 说明 |
| --- | --- | --- |
| `agent_runs`（升级） | session、goal_revision、status、root_execution、profile_snapshot_map、budget、version | 一个用户 Goal Attempt；从 Trace 主记录提升为运行聚合 |
| `agent_goal_revisions` | run、revision、objective、success_criteria、constraints、verification_policy | Steering 只追加 Revision，不覆盖历史 |
| `agent_executions` | run、root、parent、profile_key/hash、role、state、lease、task_brief、result、adoption | Root/Child 独立调度与恢复单元 |
| `agent_run_events` | run、run_seq、execution、type、payload、created_at | append-only 规范事件；`run_id + run_seq` 唯一 |
| `agent_outbox` | event、topic、status、attempt、next_attempt_at | 可靠通知 SSE/Worker/Projection |
| `run_steps`（升级） | execution、plan_revision、status、result | 公开计划步骤投影/检查点 |
| `tool_calls`（升级） | execution、idempotency_key、effect_status、approval、arguments_hash、result_ref | Tool Attempt 与 Side-effect Ledger；unknown 不盲目重试 |
| `model_calls`（复用） | execution、profile/model snapshot、usage、latency、error | 模型调用和成本事实 |
| `agent_interactions` | run、execution、action、status、resolution、version | 从 Session JSONB 兼容层升级为可恢复 HITL |
| `agent_verification_attempts` | run、execution、goal_revision、checks、evidence、outcome | 完成验证、修复和 Reviewer 证据 |
| `project_memories` | user、project、subject、revision、status、source、content_ref/hash | 受控 Project Memory，不保存无来源模型结论 |

`sessions.events` 在迁移期继续由 `agent_run_events` 投影，保证 Web 聊天历史和现有测试兼容；不得再从 `sessions.events` 反向恢复状态机。

## 状态机

```text
Run:
pending → running ↔ waiting_user
                  ↔ paused
                  → verifying → completed
                  → failed | cancelled

Execution:
ready → leased → running ↔ waiting
                        → succeeded
                        → failed | cancelled
          lease_expired → ready
```

状态变化必须由 RunCoordinator 在数据库事务中追加规范 Event；Worker、Model、Tool、SSE 和 UI 都不能直接写终态。

## 接口设计

### 保留兼容入口

- `POST /api/sessions/{session_id}/chat`：继续返回 SSE；内部改为提交 Run Command 后订阅持久事件。
- `POST /api/sessions/{session_id}/resume`、Interaction Resolution、Next Message：保持用户行为兼容，语义落到 Run Command。
- `GET /api/runs` 及现有 Trace 查询：保持兼容并逐步增加 Execution/Verification/Usage 投影。

### 新增运行接口

| 接口 | 用途 |
| --- | --- |
| `GET /api/runs/{run_id}/executions` | Execution Tree、Profile、状态、模型与 Adoption |
| `GET /api/runs/{run_id}/events?after_seq=N` | 断线恢复和缺口补拉 |
| `GET /api/runs/{run_id}/verifications` | Runtime Check、Reviewer、Evidence |
| `POST /api/runs/{run_id}/steering` | 新增 Goal Revision |
| `POST /api/runs/{run_id}/pause|resume|cancel` | 显式控制 Command |
| `GET /api/runtime/profile` | 唯一 Agent 与四个内置 Profile 的脱敏只读 Overview |
| `/api/projects/{project_id}/memories` | Project Memory 查询、显式发布、Candidate 审阅、纠正和删除 |

所有写接口使用 Idempotency Key 或稳定 Command ID；错误返回稳定错误码和 Correlation ID，不返回 Prompt、Secret、隐藏推理或未脱敏 Tool 参数。

## 错误处理与可观测性

- 错误域：goal、context、model、tool、skill、sandbox、delegation、verification、policy、runtime。
- 规范 Event 至少覆盖 Run/Execution 状态、Plan、Model、Tool、Interaction、Child、Adoption、Verification、Recovery 和 Usage。
- SSE `id` 使用 `run_id:run_seq`，客户端用 cursor 重连；UI 去重并在发现序号缺口时查询补拉。
- 记录 Profile/Config Hash、Provider/Model、Token、Cost、Latency、Tool Risk、Child Usage 和 Verification Outcome。
- 告警：Lease Lost、Outbox Lag、Unknown Side Effect、重复无进展、预算接近耗尽、连续 Verification 失败。
- 敏感内容只保存 Hash、受控 Preview 或加密 Content Ref；Trace 不保存 API Key 和隐藏思维链。

## 迁移与回滚

### 渐进迁移顺序

1. 增加 BuiltinProfileRegistry、Effective Snapshot 和 AgentHarness 门面；底层先适配现有 PlannerReActFlow，保证行为不变。
2. 把 `agent_runs` 提升为 Root Run 事实，增加 Execution/Event/Outbox；新 Run 双投影到 `sessions.events` 和现有 Trace UI。
3. 引入数据库 Worker、Lease、Heartbeat 和 Safe Point，切断进程内 Task Registry 对生命周期的所有权。
4. 落地 Goal Revision、Steering、Verification、Tool Ledger 和可恢复 Interaction。
5. 在 Feature Flag 下启用本地 Child Execution；先 General Worker，再 Researcher/Reviewer。
6. 增加 Project Memory 和 ContextCompiler，最后把 Web Trace 面板升级为 Execution/Verification 视图。

### 回滚原则

- Feature Flag 只影响新 Run：`durable_runtime`、`local_child_execution`、`project_memory`。
- 关闭本地 Child 后，Lead 仍必须是完整 Solo Agent；不能退回普通 Chat。
- 已创建的 Run 按创建时 Snapshot 和 Runtime Version 恢复，不被配置或 Feature Flag 热切。
- 回滚应用代码不删除 Run/Event/Usage/Verification 历史；数据库迁移优先追加和兼容读取。
- 在 Durable Runtime 达到恢复 Gate 前保留 Legacy Flow；切换完成后不得长期双写两套状态机。

## 风险

| 风险 | 可能性 | 影响 | 缓解措施 | 验证方式 |
| --- | --- | --- | --- | --- |
| AgentService、Flow、Coordinator 同时写状态 | 高 | 高 | Coordinator 成为唯一状态写入口，增加架构测试 | AST/依赖守卫 + 状态转换测试 |
| Trace 与 Durable Event 双事实源 | 高 | 高 | Event 先提交，Trace/Session 只做 Outbox 投影 | 故障注入和重放一致性测试 |
| Worker 重试产生重复副作用 | 中 | 极高 | Tool Idempotency、Side-effect Ledger、unknown 对账 | Worker Kill + 网络超时测试 |
| 多 Agent 增加成本但无质量收益 | 高 | 中高 | 简单任务 Solo；委派策略和 Solo/Multi A/B Gate | 质量、Token、Latency 对照 |
| Profile Registry 与数据库配置漂移 | 中 | 高 | 代码拥有 Key/拓扑，Snapshot 保存 Hash，数据库只能窄覆盖 | 篡改和 Hash 漂移测试 |
| Project Memory 被注入或固化错误 | 中 | 高 | 来源、信任、Candidate 审阅、Revision/删除 | 注入、纠正、跨用户测试 |
| 迁移破坏现有聊天与 HITL | 中 | 高 | 保留 API 和 Session Event 单向投影，逐段切流 | Agentic 全量非回归 + E2E |
| Harness 过度抽象拖慢落地 | 中 | 中 | 先包裹现有 Flow，只抽取已验证的状态与 Command | 每阶段文件/复杂度审查 |

## 重要假设

- `agentic` 继续采用当前 FastAPI Service Layer，不照搬 FastAPI-AI 的五层业务模块。
- PostgreSQL 可作为规范状态源；Redis 允许短暂丢失并可由数据库扫描补偿。
- 第一阶段所有内置 Profile 可共用现有用户模型配置，角色专属模型 UI 后置。
- Skill、Tool、Sandbox、MCP、外部 A2A、File、Auth 和现有 Web 交互是升级基线，不重新实现。
- V1 委派深度固定为 1，Worker 不递归委派；General Worker 默认并发上限从小值开始。
- Reviewer 是按需执行角色，不要求每个简单 Run 都进行第二次模型生成。

## 待决策项

无影响核心架构的待决策项。角色专属模型 UI、默认 Child 并发数、Reviewer 启用阈值和 Project Memory 自动推荐阈值应在实施评测中确定，不改变本文边界。

## 验收标准

- [ ] UI/API 中不存在 Agent Definition、Agent Publish、Agent Version 或 Root Agent 选择入口。
- [ ] 所有新 Run 自动使用唯一 `lead`；Registry 只包含 `lead`、`general_worker`、`researcher`、`reviewer`。
- [ ] 四个 Profile 共用 AgentHarness；General Worker 可以产生多个独立 Execution。
- [ ] 本地 Child 只经 RunCoordinator，测试可证明未调用 A2A Adapter。
- [ ] Run 创建后固定 Profile、模型、Tool、Skill、Memory、Sandbox 和 Verification Snapshot。
- [ ] API/SSE 断开、进程重启、Worker Kill 和 Redis Loss 后，Run 能从 Safe Point 恢复且事件不重不漏。
- [ ] 高风险 Tool 经 Approval 和 Side-effect Ledger；未知副作用不会盲目重试。
- [ ] 模型自报完成不能直接结束 Run；确定性检查和规定的 Reviewer 验证通过后才能成功。
- [ ] Child Result 的 adopt/reject/conflict 和 Evidence 可从 Execution Tree 查询。
- [ ] Project Memory 只注入授权的 Published Revision，Candidate、纠正、删除和跨用户隔离可测试。
- [ ] 现有聊天、文件、Skill、Tool、Sandbox、MCP、外部 A2A、HITL、分支和 SSE 行为通过非回归测试。
- [ ] 全量代码审查无 blocking/major，真实 PostgreSQL 迁移往返、故障演练和前后端构建通过。

