# 分支版本导航与气泡内编辑增强设计

## 文档状态

- 状态：`DESIGN_READY`
- 负责人：Codex
- 创建日期：2026-07-25
- 最近更新：2026-07-25

## 背景

当前系统已经完成第一阶段“消息编辑、重新生成与会话分支”：

- 用户消息支持“编辑并重新提交”；
- Assistant 消息支持“重新生成回复”；
- 任意可见用户/Assistant 消息支持“从这里分支”；
- 所有操作都创建独立 Session，原事件、Memory、Trace 和工具副作用保持不变；
- 分支详情展示来源提示并允许返回原对话。

因此本轮不能重复实现上述能力。与本地 LibreChat 源码比较后，真正仍有学习价值的差距是：

1. LibreChat 使用 `parentMessageId` 消息树和 `SiblingSwitch` 在同一对话里展示 `1 / N`，用户可以快速比较重新生成或编辑产生的多个版本；
2. LibreChat 在原消息位置进入编辑态，而当前系统使用独立 Dialog，编辑上下文与原消息的空间关系较弱；
3. 当前系统进入一个分支后只能返回直接来源，无法在同一来源节点产生的多个直接分支之间切换。

LibreChat 的相关实现集中在：

- `LibreChat/client/src/components/Chat/Messages/SiblingSwitch.tsx`
- `LibreChat/client/src/components/Chat/Messages/MultiMessage.tsx`
- `LibreChat/client/src/components/Chat/Messages/Content/EditMessage.tsx`
- `LibreChat/client/src/hooks/Messages/useBuildMessageTree.ts`
- `LibreChat/client/src/hooks/Chat/useChatFunctions.ts`

`LibreChat/AGENTS.md` 指向的 `CLAUDE.md` 在本地副本中不存在；本设计仅依据可读取的源码与测试，不假设缺失说明中的额外约束。

## 目标

- 在不改变 Session 快照分支模型的前提下，为同一来源消息产生的直接分支提供上一版、下一版和 `当前位置 / 总数` 导航。
- 用户从历史用户消息进入编辑时，编辑器在原消息位置展开，明确提示“原对话不变，将创建新分支”。
- 重新生成完成导航后，用户能在原始对话与同一节点的多个重新生成/编辑/fork 变体之间比较。
- 分支切换只改变当前路由和展示，不隐式运行 queued 输入、不恢复归档任务、不修改任何分支。
- 保持现有 Agent Run、Trace、审批、HITL、next-message 和工具副作用隔离语义。

## 功能范围

- 为分支 Session 提供直接分支族查询接口。
- 直接分支族定义为“一个直接来源 Session，加上该来源同一 `forked_from_event_id` 下的所有直接子 Session”。
- 分支详情来源提示升级为版本导航：
  - 上一版本；
  - 下一版本；
  - `1 / N`；
  - 当前版本名称、操作类型和归档状态；
  - 返回来源。
- 从分支返回来源时携带 `branchEvent` 查询参数，使来源页面刷新后仍能恢复同一分支族导航。
- 编辑用户消息时在消息气泡原位置显示 textarea、只读附件/Skills、取消和“创建分支并发送”。
- 支持 `Escape` 取消以及 `Ctrl/Cmd + Enter` 提交。
- 继续复用现有 `POST /sessions/{session_id}/branches`、request ID 幂等和 queued 自动启动机制。
- 桌面端、移动端、暗色模式和键盘焦点状态。

## 非功能范围

- 不把 Session 事件改造成 LibreChat 的 `parentMessageId` 消息树。
- 不在一个 Session 内保存 active leaf 或 sibling index。
- 不原地修改或保存历史用户/Assistant 消息。
- 不提供 LibreChat 的“仅保存历史消息文本”操作。
- 不允许编辑 Assistant 内容；Assistant 仍只支持重新生成。
- 不展示完整递归分支树；第一版只展示直接来源和同一锚点的直接子分支。
- 不合并不同来源事件、不同直接来源或不同层级的分支。
- 不改变分支上下文种子、附件权限、Skills 沿用和工具审批策略。
- 不实现分支重命名、合并、对比 diff、分享或导出。

## 业务流程

### 编辑历史用户消息

1. 用户在已完成、未归档且无 queued next-message 的 Session 中点击用户消息“编辑并重新提交”。
2. 原消息气泡切换成内联编辑器，预填原文本；附件和 Skills 只读展示。
3. 用户按 `Escape` 或点击取消，恢复原消息，不产生请求。
4. 用户按 `Ctrl/Cmd + Enter` 或点击“创建分支并发送”。
5. 前端复用现有 branches API 和稳定 request ID 创建 edit 分支。
6. 创建成功后导航至新 Session，并携带现有一次性 `runQueued` 意图以及 `branchEvent`。
7. 新分支正常启动；启动失败时 queued 输入仍可手工恢复。

### 重新生成 Assistant 回复

1. 用户点击 Assistant 消息“重新生成回复”。
2. 前端继续调用现有 regenerate 分支创建流程。
3. 新分支打开并启动 queued 输入。
4. 分支来源区域显示版本导航，原始来源为第 1 版，新创建分支按创建时间排列。
5. 用户可以切换到原始来源或同一锚点的其他变体进行比较。

### 浏览分支版本

1. 分支 Session 详情在没有显式本地锚点时，根据自身 `source_session_id + forked_from_event_id` 查询直接分支族。
2. 来源 Session 通过 URL 中的 `branchEvent` 查询同一直接分支族；一个本身也是分支的 Session，只要 `branchEvent` 是自身可见消息，也可以作为下一级直接分支族的来源。
3. 用户点击上一版、下一版或版本列表项。
4. 前端导航到目标 Session：
   - 目标为来源时保留 `branchEvent`；
   - 目标为子分支时由子分支自身 lineage 恢复分支族。
5. 导航只加载目标详情，不传递 `runQueued`，不触发新执行。

## 核心规则

1. 原 Session 和所有既有分支保持不可变；版本导航只是跨 Session 路由。
2. 直接分支族只包含当前用户拥有的 Session，不暴露其他用户的标题、状态或存在性。
3. 来源版本始终排在第一位；子分支按 `created_at ASC, id ASC` 稳定排序。
4. fork、edit 和 regenerate 可以出现在同一直接分支族，但必须展示清晰的操作类型。
5. 已归档子分支仍可出现在版本族中并带“已归档”标记；打开后继续遵守归档只读规则。
6. 来源已删除时不暴露来源信息；仍属于当前用户的直接兄弟分支可以继续互相导航。
7. 当前 Session 不在查询结果时，服务端返回冲突而不是让前端猜测位置。
8. `branchEvent` 只用于恢复来源页面的分支导航上下文，不参与权限判断，也不触发分支创建；若它属于当前 Session 的可见消息，则当前 Session 按来源模式解析，否则分支 Session 按自身 lineage 解析。
9. 版本切换永远不附带 `runQueued`；只有刚创建 edit/regenerate 分支的单次导航可以携带现有运行意图。
10. 同一时刻只能有一个消息进入内联编辑；切换 Session、开始运行或归档时自动取消未提交编辑。

## 现有实现分析

### 相关代码与文档

- `agentic/docs/designs/chat-conversation-branching.zh-CN.md`：第一阶段的不可变新 Session 分支设计。
- `agentic/api/app/models/session.py`：已有 `source_session_id` 索引、`forked_from_event_id`、`branch_operation` 和 `created_at`。
- `agentic/api/app/repositories/db_session_repository.py`：已有用户隔离、行锁和原子分支创建。
- `agentic/api/app/controllers/session.py`：已有分支创建接口和安全来源详情。
- `agentic/web/src/components/chat/MessageActions.vue`：已有 fork/edit/regenerate 操作。
- `agentic/web/src/components/chat/ChatEditBranchDialog.vue`：已有编辑内容、附件和 Skills 展示，可迁移为内联编辑器。
- `agentic/web/src/components/SessionDetailView.vue`：已有 request ID 恢复、queued 一次性启动和来源 banner。
- `agentic/web/src/lib/api/session.ts`：已有分支创建客户端。

### 可复用能力

- 现有 `source_session_id` 索引足以从直接来源筛选子分支。
- `forked_from_event_id` 可作为直接分支族锚点，无需新增数据库字段。
- `branch_operation` 可直接生成“原始、编辑、重新生成、手工分支”标签。
- 现有 Session 详情权限、归档只读和安全来源规则可复用。
- 现有 `pendingBranchRequest` 能保证内联编辑重复提交仍复用 request ID。
- 现有 `runQueued` 一次性意图可以保持创建后自动执行与刷新不重跑。

### 当前约束

- events 是 Session 内追加式 JSONB，不是消息树；不能直接移植 LibreChat 的 sibling index 状态。
- 分支复制后事件会获得新 ID，不能用事件 ID 在不同 Session 中逐条对齐。
- 当前只保存直接来源，不保存可快速查询的递归根；第一版只能可靠展示直接分支族。
- 来源删除后没有外键级联或根节点快照，UI 必须允许“来源不可用”。
- 当前编辑 Dialog 是页面级状态；改为内联后需避免与流式更新、路由切换和消息虚拟滚动冲突。

## 可选方案

### 方案 A：仅做交互外观优化

- 实现方式：把 Dialog 改成内联编辑，优化消息按钮和提示，但不增加分支族接口。
- 优点：改动小、无后端变化、交付快。
- 缺点：重新生成后仍只能返回来源，无法比较多个变体。
- 风险：解决了编辑的空间体验，却没有解决 LibreChat 最有价值的 sibling 导航差距。

### 方案 B：Session 级直接分支族导航

- 实现方式：基于现有 lineage 字段增加直接分支族查询；在来源 banner 中提供 `1 / N` 导航；编辑器改为气泡内展开。
- 优点：保留不可变、可审计的 Session 边界，同时获得接近 LibreChat 的版本比较体验；无需迁移。
- 缺点：切换版本会改变 Session URL，不能像同一消息树那样只替换一个气泡。
- 风险：来源删除、归档版本和路由查询状态必须有明确降级行为。

### 方案 C：完整迁移为同 Session 消息树

- 实现方式：为所有消息增加 parent/children，Session 保存 active leaf，事件投影、Memory、SSE、搜索和 Trace 全部感知当前分支路径。
- 优点：最接近 LibreChat，支持消息级 sibling 切换和递归分支树。
- 缺点：需要重构核心数据模型、运行状态、搜索和历史迁移。
- 风险：可能混淆不同 Agent Run/Trace 和工具副作用，破坏当前追加式审计与恢复语义。

## 方案对比

| 维度 | 方案 A：仅外观优化 | 方案 B：Session 级分支族 | 方案 C：同 Session 消息树 |
| --- | --- | --- | --- |
| 实现复杂度 | 低 | 中 | 高 |
| 维护成本 | 低 | 中 | 高 |
| 与现有 Agent 语义兼容 | 高 | 高 | 低 |
| 版本比较价值 | 低 | 高 | 高 |
| 测试难度 | 低 | 中 | 很高 |
| 数据迁移 | 无 | 无 | 大规模迁移 |
| 主要风险 | 价值不足 | 路由与 lineage 降级 | Run/Trace/工具语义混乱 |

## 推荐方案

选择方案 B：Session 级直接分支族导航。

它学习 LibreChat 的 sibling 可发现性和内联编辑体验，但不复制其消息树数据模型。当前系统以 Session 隔离 Agent Run、Trace、Memory、文件和工具副作用，这是比单页版本切换更重要的正确性边界。方案 B 无需迁移即可提供 `1 / N` 比较、来源返回和多个重新生成版本切换，收益明显高于仅做外观优化，风险又远低于完整消息树重构。

## 数据结构

无数据库结构变化。

新增只读响应结构：

### BranchFamilyVariant

| 字段 | 类型 | 必填 | 说明 | 约束/默认值 |
| --- | --- | --- | --- | --- |
| `session_id` | `string` | 是 | 来源或直接子分支 ID | 仅返回当前用户拥有的 Session |
| `title` | `string` | 是 | 当前标题 | 来源不可用时不返回来源项 |
| `operation` | `original/fork/edit/regenerate` | 是 | 版本类型 | 来源固定为 `original` |
| `status` | `string` | 是 | Session 运行状态 | 只读展示 |
| `archived_at` | `datetime/null` | 是 | 归档状态 | 归档版本可导航但只读 |
| `created_at` | `datetime` | 是 | 稳定排序时间 | 来源第一，其余升序 |
| `is_current` | `boolean` | 是 | 是否当前 Session | 仅一项为 true |

### BranchFamilyResponse

| 字段 | 类型 | 必填 | 说明 | 约束/默认值 |
| --- | --- | --- | --- | --- |
| `source_session_id` | `string/null` | 是 | 直接来源 ID | 来源删除或无权时为 null |
| `target_event_id` | `string` | 是 | 来源锚点事件 | 必须是可见 user/assistant 事件 |
| `current_session_id` | `string` | 是 | 当前 Session | 必须在 variants 中 |
| `variants` | `list[BranchFamilyVariant]` | 是 | 来源和直接子分支 | 来源第一，稳定排序 |

## 接口设计

### `GET /sessions/{session_id}/branch-family`

- 输入：
  - 路径 `session_id`：当前打开的 Session。
  - 查询 `target_event_id`：当前 Session 为来源时必填；当前 Session 为子分支时可省略并使用自身 `forked_from_event_id`；若一个分支 Session 继续作为下一级来源，则传入其自身可见消息 ID。
- 输出：`BranchFamilyResponse`。
- 权限：
  - 当前 Session 必须属于当前用户；
  - variants 只查询相同用户；
  - 来源已删除或不属于当前用户时不返回来源标题或 ID。
- 校验：
  - 来源模式下，`target_event_id` 必须指向当前 Session 内可见的 user/assistant MessageEvent；
  - 子分支模式下，省略 target_event_id 或传入自身 lineage 锚点；若显式值既不是自身 lineage 锚点、也不是当前 Session 的可见消息，则返回 409；
  - 普通 Session 未提供 target_event_id 时返回 422。
- 并发/幂等：只读查询，无幂等写入；结果按数据库当前提交状态返回。
- 兼容性：新增接口，不改变现有 Session 详情与 branches 创建响应。

### 前端路由查询 `branchEvent`

- 来源页格式：`/sessions/{source_session_id}?branchEvent={target_event_id}`。
- 子分支页可以保留或省略该查询；服务端以子分支自身 lineage 为准。
- 无效、不可见或不匹配的 branchEvent：
  - 页面本身继续正常加载；
  - 版本导航显示可恢复错误并允许重试或关闭；
  - 不影响聊天输入和现有消息操作。

## 错误处理与可观测性

- 404：当前 Session 不存在或无权访问；沿用统一资源隐藏规则。
- 409：子分支传入的 target_event_id 与自身 lineage 不一致，或当前 Session 不在计算出的分支族中。
- 422：普通来源 Session 缺少 target_event_id，或参数格式非法。
- 分支族加载失败不阻断会话详情；banner 保留来源返回能力并提供重试。
- 结构化日志只记录 user、current session、source session、target event 和 variant count，不记录消息正文。
- 建议指标：
  - `branch_family_loaded_total`
  - `branch_family_load_failed_total`
  - `branch_variant_navigated_total`
  - 按 operation 聚合，不记录标题或正文。

## 迁移与回滚

- 迁移：无。复用现有 `ix_sessions_source_session_id` 和 lineage 字段。
- 历史数据：普通 Session 不显示导航；已有第一阶段分支可以直接查询。
- 回滚：
  - 下线 `BranchVersionNavigator` 和 branch-family GET 接口；
  - 恢复现有来源 banner 与 `ChatEditBranchDialog`；
  - 不删除或修改任何 Session 数据。

## 风险

| 风险 | 可能性 | 影响 | 缓解措施 | 验证方式 |
| --- | --- | --- | --- | --- |
| 把不同锚点的分支错误合并 | 中 | 高 | 查询必须同时匹配 user、source_session_id、forked_from_event_id | 仓储组合条件测试 |
| 版本切换误触发 queued 运行 | 低 | 高 | 普通版本导航永不生成 runQueued；仅创建成功路径可生成 | 路由与 API 调用测试 |
| 来源删除后泄露标题或存在性 | 低 | 高 | 来源按当前用户重新查询；不可用时返回 null | 跨用户和删除来源测试 |
| 归档版本被隐式恢复 | 低 | 中 | 归档项只读标记，导航复用现有归档详情 | 归档导航测试 |
| 内联编辑被 SSE 或路由更新覆盖 | 中 | 中 | 只允许 completed Session；路由/状态变化自动取消草稿 | 组件状态与流式切换测试 |
| 分支数过多导致 banner 拥挤 | 中 | 低 | 默认只显示前后按钮和计数，完整列表放入弹出菜单 | 50 个变体组件测试 |
| 嵌套分支被误认为全局根族 | 中 | 中 | 明确只计算直接来源层级，UI 文案使用“此处版本” | 二级分支集成测试 |

## 重要假设

- 用户本轮希望继续学习 LibreChat 的交互价值，而不是重复开发已经完成的第一阶段。
- “版本”指来源 Session 与同一来源事件的直接子分支，不代表全局递归分支树。
- 用户接受版本切换改变 Session URL，以换取 Run/Trace/Memory 和工具副作用隔离。
- Assistant 内容不允许人工改写；需要不同回答时使用重新生成。
- 现有分支数量通常较小；首版不增加数据库复合索引，性能以实际查询基准决定。
- 用户回复“下一轮可以开始”授权产出设计，但不授权自动提交、推送、合并或直接实施。

## 待决策项

无。推荐方案保持现有不可变 Session 架构，范围足以进入实施计划拆分。

## 验收标准

- [ ] 已有分支 Session 打开后显示来源、操作类型和稳定的 `当前位置 / 总数`。
- [ ] 上一版、下一版和版本列表可以在来源及同锚点直接子分支之间切换。
- [ ] 从子分支切到来源时 URL 保存 branchEvent，刷新后导航仍存在且位置正确。
- [ ] 不同来源事件、不同直接来源和二级分支不会被合并为同一版本族。
- [ ] 版本导航不携带 runQueued、不启动新 Run、不恢复归档 Session。
- [ ] 来源删除或越权后不泄露来源信息，仍可展示当前用户拥有的直接兄弟分支。
- [ ] 用户消息可在原气泡位置进入编辑；Escape 取消，Ctrl/Cmd+Enter 创建 edit 分支。
- [ ] 内联编辑沿用只读附件和 Skills，不提供原地保存，不修改源事件。
- [ ] regenerate 新分支创建后出现在同一版本族，用户可以回看原始回复。
- [ ] running、waiting、queued、processing 和 archived 状态继续禁用编辑/重新生成/分支创建。
- [ ] branch-family API 的用户隔离、锚点校验、稳定排序和错误契约有自动化覆盖。
- [ ] 现有聊天、分支创建、next-message、HITL、审批、搜索、文件和 Trace 回归通过。
- [ ] 桌面、移动端、暗色模式和键盘焦点通过页面验收。
