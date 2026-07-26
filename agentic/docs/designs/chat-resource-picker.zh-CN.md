# 聊天统一资源选择器

## 文档状态

- 状态：`DESIGN_READY`
- 负责人：Codex
- 创建日期：2026-07-26
- 最近更新：2026-07-26
- 关联路线：LibreChat UI 学习 A2「统一资源选择」
- 前置能力：A1「聊天附件体验」

## 背景

Agentic 的 Composer 当前已经支持两类可随消息发送的资源：

- 文件：本地上传、拖拽、粘贴或从“我的文件”选择，最终通过 `attachmentIds` 发送；
- Skill：通过 `$` 快捷选择，最终通过 `skills` 发送。

两类资源已经能工作，但入口和选择体验彼此分离：

- 回形针菜单只面向文件；
- Skill 主要依赖用户知道 `$` 快捷方式；
- 文件使用 Dialog，Skill 使用行内浮层；
- 用户无法从一个可发现的入口浏览当前消息可用的全部资源。

LibreChat 的 `AttachFileMenu`、`ToolsDropdown`、`BadgeRow` 和 Skill 选择交互证明了“统一入口 + 明确已选状态”的价值。但 Agentic 当前的消息协议只支持文件和 Skill；MCP、A2A 与 API Tool 属于全局连接或运行配置，不是逐消息资源。此次只学习交互结构，不提前复制 LibreChat 的通用 Provider 或资源平台。

## 目标

- Composer 提供一个清晰的“添加资源”入口，可到达本地上传、已有文件和已启用 Skill。
- “从我的文件选择”和“选择 Skill”打开同一个资源 Dialog，并落在对应标签页。
- 用户可以在文件与 Skill 标签页之间切换，保留本次尚未确认的选择。
- 点击确认后，一次性把本次新增文件和 Skill 合并到 Composer。
- 点击取消、按 Escape、切换 Session 或关闭 Dialog 时，不改变 Composer。
- 保留 `$` Skill 快捷选择，兼顾可发现入口与熟练用户效率。
- 复用 A1 文件选择器的目录、搜索、筛选、分页、多选、竞态和错误处理能力。
- 保持现有消息 API、权限模型、附件生命周期和 Skill 发送协议不变。

## 功能范围

- 将 Composer 的资源入口表达为“添加资源”，保留紧凑图标样式。
- 资源菜单包含：
  - 上传本地文件；
  - 从我的文件选择；
  - 选择 Skill。
- 新建 `ChatResourcePickerDialog`，包含：
  - “文件”标签页；
  - “Skills”标签页；
  - 跨标签页保留的本次新增选择；
  - 统一的取消与确认动作；
  - 已在 Composer 中的资源状态；
  - 390px、桌面、暗色、键盘与焦点行为。
- 文件标签页继承当前 `ChatFilePickerDialog` 的完整能力。
- Skills 标签页支持：
  - 仅显示当前启用且可用的 Skill；
  - 按名称、展示名或描述搜索；
  - 多选；
  - 已添加状态；
  - 最多 5 个 Skill 的容量约束。
- 确认结果只包含本次新增项，由 `ChatInput` 使用现有逻辑合并和去重。
- Session 切换时关闭 Dialog 并清空未确认状态。

## 非功能范围

- 不新增或修改数据库表、后端接口、消息 payload 或队列协议。
- 不把 MCP Server、A2A Agent、API Tool、Project、Prompt、Agent Profile、Knowledge 或长期记忆纳入本批资源类型。
- 不建设通用资源注册中心、Provider SDK、插件资源协议或跨产品资源市场。
- 不在 Dialog 中删除、替换或重新排序 Composer 已有资源。
- 不持久化未确认的资源草稿。
- 不改变本地文件上传、图片 Blob URL、失败重试或发送成功后的清理规则。
- 不移除 `$` Skill 快捷选择。
- 不新增依赖、shell 执行、沙箱写入或工具批准行为。

## 业务流程

### 从统一入口上传本地文件

1. 用户打开 Composer 的“添加资源”菜单。
2. 用户选择“上传本地文件”。
3. 浏览器原生文件选择器打开。
4. 选中文件继续进入现有 `uploadFiles` 流程。
5. Composer 显示上传中、成功或失败状态，行为与 A1 保持一致。

### 从“我的文件”添加资源

1. 用户打开“添加资源”菜单并选择“从我的文件选择”。
2. `ChatResourcePickerDialog` 打开并默认进入“文件”标签页。
3. 用户浏览目录、搜索、筛选、翻页并选择文件。
4. 用户可切换到 Skills 标签页继续选择；返回文件标签页时原选择仍保留。
5. 用户点击“添加”，Dialog 返回本次新增文件和 Skill。
6. `ChatInput` 使用现有文件与 Skill 合并逻辑更新 Composer。

### 从 Skill 入口添加资源

1. 用户打开“添加资源”菜单并选择“选择 Skill”。
2. 同一个 Dialog 打开并默认进入“Skills”标签页。
3. 用户搜索并选择 Skill；已在 Composer 中的 Skill 显示“已添加”且不可重复选择。
4. 用户最多可使“Composer 已有 + 本次待添加”达到 5 个 Skill。
5. 点击确认后，所选 Skill 使用现有 `selectSkill` 逻辑转换为消息 Skill 引用。

### 取消与会话切换

1. Dialog 内的文件与 Skill 选择只保存在 Dialog 临时状态。
2. 点击取消、遮罩、关闭按钮或按 Escape，临时状态被丢弃。
3. Session ID 变化时，Dialog 关闭并丢弃临时状态。
4. 重新打开 Dialog 时，根据 Composer 当前资源重新初始化，不恢复上一次未确认选择。

## 核心规则

1. A2 中“资源”只指当前消息协议已支持的已有文件和已启用 Skill；本地上传是添加文件的动作，不是第三种资源类型。
2. 统一的是入口、浏览和确认体验，不抽象新的后端资源协议。
3. Dialog 只提交新增项；Composer 中已有项只能通过现有附件卡片或 Skill 标签移除。
4. 当前 Composer 已有文件 ID 和 Skill key 在 Dialog 中显示为已添加且不可重复选择。
5. 文件选择结果不得包含本地路径、下载 URL、存储密钥、Provider 凭据或用户 ID。
6. Skill 选择结果只使用已有公开摘要字段；发送时仍由 `ChatInput` 转换为当前 `SkillRef`。
7. 文件与 Skill 的确认必须是一次用户动作；取消不得产生部分提交。
8. 文件标签页的目录、筛选、分页请求彼此使用请求版本保护，旧响应不得覆盖新状态。
9. 文件标签页失败不得使 Skills 标签页不可用；Skills 加载失败也不得使文件标签页不可用。
10. Skill 上限按“Composer 已选 + Dialog 待选”计算，最多 5 个；达到上限后其余项不可继续选择并显示原因。
11. 标签页切换不得丢失本次选择；Dialog 关闭则必须清空本次选择。
12. Session 切换、发送成功和组件卸载继续遵守现有附件与 Skill 清理边界。
13. running Session 中确认的资源继续进入现有下一条消息队列，不修改或中断当前 Run。
14. `$` Skill Picker 与统一 Dialog 共享同一可用 Skill 数据和上限规则，不能产生两套业务约束。
15. 确认按钮需防止重复提交；同一文件 ID 或 Skill key 最多合并一次。

## 现有实现分析

### 相关代码

- `agentic/web/src/components/chat/ChatInput.vue`
  - 拥有附件、已选 Skill、Session 切换和消息发送状态；
  - 已有 `addLibraryFiles` 与 `selectSkill` 合并边界。
- `agentic/web/src/components/chat/ChatComposer.vue`
  - 展示附件菜单、附件卡片、Skill 标签和文本输入；
  - 已提供本地上传与“我的文件”菜单动作；
  - 已集成 `$` Skill Picker。
- `agentic/web/src/components/chat/ChatFilePickerDialog.vue`
  - 已实现目录、搜索、类型/来源筛选、分页、多选、竞态、错误与焦点处理；
  - 当前只返回文件。
- `agentic/web/src/components/chat/SkillPicker.vue`
  - 已实现 Skill 搜索、键盘导航、选择和 Escape；
  - 当前是 Composer 内的行内浮层。
- `agentic/web/src/stores/skills.ts`
  - 提供当前激活和启用的 Skills 列表。
- `agentic/web/src/types/skill.ts`
  - 消息侧现有资源字段为 `attachmentIds` 与 `skills`。

### 可复用能力

- A1 的文件选择行为和测试可直接迁移到资源 Dialog 的文件标签页。
- `ChatInput` 已是文件与 Skill 的共同状态所有者，适合持有 Dialog 打开状态和确认合并。
- `SkillPicker` 已定义搜索字段、可用性和键盘选择经验。
- 当前消息和下一条消息接口已经同时携带文件 ID 与 Skill 引用，无需后端变更。
- Composer 已有附件卡片与 Skill 标签，确认后无需新增第三套已选资源展示。

### 约束

- 当前没有统一的 `Resource` 后端实体，也没有逐消息工具连接字段。
- 文件需要服务端分页与鉴权，Skill 列表适合客户端过滤，两类数据不能强制共用同一个加载状态。
- A1 文件选择器已经通过验收，改造时必须保持其行为与回归测试。
- Skill 最大数量为 5，Dialog 必须把 Composer 已有 Skill 纳入容量计算。
- 文件可能包含本地上传中的临时 ID；Dialog 只把持久化文件 ID 作为“已添加”判断依据。

## 可选方案

### 方案 A：只扩展资源入口菜单

- 实现：在现有附件菜单增加“选择 Skill”，仍分别打开文件 Dialog 和独立 Skill Picker。
- 优点：
  - 改动最小；
  - A1 文件 Dialog 几乎不动；
  - 风险低。
- 缺点：
  - 只是统一入口，没有统一浏览和确认；
  - 文件与 Skill 的加载、取消和已选反馈仍不一致；
  - 用户无法在一次选择流程中同时添加两类资源。
- 结论：价值不足，不符合“统一资源选择”的核心目标。

### 方案 B：文件 + Skills 统一 Dialog

- 实现：
  - 以 `ChatResourcePickerDialog` 替换只面向文件的 Dialog；
  - 使用文件与 Skills 两个标签页；
  - 两类数据分别加载，共享临时选择、取消和确认边界；
  - Composer 继续使用现有附件卡片与 Skill 标签。
- 优点：
  - 用户心智统一；
  - 复用 A1 文件能力和现有 Skill 数据；
  - 不改变后端协议；
  - 为后续资源类型保留清晰但不过度抽象的 UI 扩展点。
- 缺点：
  - 需要迁移文件 Dialog 和测试；
  - 需谨慎处理跨标签临时状态、Skill 容量和焦点恢复。
- 结论：覆盖需求且边界清晰，推荐。

### 方案 C：通用资源注册框架

- 实现：建立资源 Provider/Registry，把文件、Skill、MCP、A2A、API Tool、Project、Knowledge 等统一为可插拔资源类型。
- 优点：
  - 理论扩展性最强；
  - 长期可形成统一资源平台。
- 缺点：
  - 当前大部分类型没有逐消息协议；
  - 会牵涉权限、运行时、数据模型和后端 API；
  - 与后续 Project、Agent、Knowledge、MCP UI Resource 专项任务重叠。
- 结论：当前属于过度设计，拒绝。

## 方案对比

| 维度 | 方案 A：仅菜单 | 方案 B：统一 Dialog | 方案 C：资源框架 |
| --- | --- | --- | --- |
| 用户价值 | 中 | 高 | 未知，依赖后端能力 |
| 实现复杂度 | 低 | 中 | 高 |
| 后端变更 | 无 | 无 | 大概率需要 |
| A1 回归风险 | 低 | 中，可测试控制 | 高 |
| Skill 可发现性 | 有 | 强 | 强 |
| 一次添加多类资源 | 否 | 是 | 是 |
| 当前范围匹配 | 不完整 | 最佳 | 范围膨胀 |

## 推荐方案

选择方案 B：文件 + Skills 统一 Dialog。

该方案只统一当前真实存在的逐消息资源，不虚构通用资源协议。用户可以从一个入口发现文件和 Skill，在一次 Dialog 中完成选择，同时现有消息 payload、鉴权、上传、队列和展示模型全部保持不变。

实现时应把现有 `ChatFilePickerDialog` 的文件浏览能力迁入或重命名为 `ChatResourcePickerDialog`，避免保留两份文件选择逻辑。`ChatInput` 继续作为唯一状态所有者，Dialog 只维护未确认的临时选择。

## 数据结构

无数据库结构变化。

### `ChatResourcePickerTab`

```ts
type ChatResourcePickerTab = 'files' | 'skills'
```

### `ChatResourcePickerResult`

```ts
type ChatResourcePickerResult = {
  files: FilePickerSelection[]
  skills: SkillSummary[]
}
```

约束：

- 结果只包含本次新增项；
- `files` 延用 A1 的安全文件摘要；
- `skills` 使用现有 Skill 列表摘要；
- Dialog 不创建消息 payload；
- `ChatInput` 负责去重、转换和最终合并。

### Dialog 临时状态

```ts
type PendingResourceSelection = {
  fileById: Map<string, FilePickerSelection>
  skillByKey: Map<string, SkillSummary>
}
```

该状态只存在于 Dialog 生命周期内，不进入 Store、URL、Session、localStorage 或消息事件。

## 接口设计

### `ChatResourcePickerDialog`

输入：

- `modelValue: boolean`
- `initialTab: ChatResourcePickerTab`
- `selectedFileIds: string[]`
- `selectedSkillKeys: string[]`
- `availableSkills: SkillSummary[]`
- `skillsLoading: boolean`
- `skillsError: string | null`
- `skillLimit: number`，默认 5

输出：

- `update:modelValue`
- `confirm(result: ChatResourcePickerResult)`
- `retrySkills`

行为：

- 每次从关闭变为打开时重建临时选择；
- `initialTab` 只决定本次打开的初始标签；
- 关闭后不保留未确认选择；
- 确认时按 ID/key 去重并一次 emit；
- 文件和 Skill 使用独立 loading/error 状态；
- Skills 失败状态由 Store 提供，重试事件交还 `ChatInput` 调用现有 `loadSkills`；
- 关闭后焦点返回触发本次动作的菜单入口或资源按钮。

### `ChatComposer`

保留：

- 本地上传动作；
- 文件拖拽与粘贴；
- `$` Skill 快捷选择；
- 附件卡片和 Skill 标签移除动作。

调整事件：

```ts
openResourcePicker(tab: ChatResourcePickerTab)
```

资源菜单映射：

- “上传本地文件”继续触发本地文件输入；
- “从我的文件选择”触发 `openResourcePicker('files')`；
- “选择 Skill”触发 `openResourcePicker('skills')`。

### `ChatInput`

- 拥有 `resourcePickerOpen` 和 `resourcePickerInitialTab`。
- 向 Dialog 传入 Composer 当前持久化文件 ID、已选 Skill key 与可用 Skill 列表。
- `confirm` 后：
  - 文件沿用 `addLibraryFiles`；
  - Skill 沿用 `selectSkill`；
  - 两者均再次去重。
- Session 变化时关闭 Dialog。
- 发送 payload 保持：
  - `attachmentIds: string[]`
  - `skills: SkillRef[]`

### 后端接口

无新增或变更。继续使用现有：

- 文件列表和预览 API；
- Skill 列表 API/Store；
- 消息发送和下一条消息队列 API。

## 错误处理与可观测性

- 文件列表失败：
  - 文件标签显示错误与重试；
  - 保留已选临时项；
  - Skills 标签仍可使用。
- Skills 加载失败：
  - Skills 标签显示错误与重试；
  - 文件标签仍可使用；
  - 不清空 Composer 已有 Skill。
- 文件请求乱序：
  - 延用请求版本保护；
  - 旧目录、搜索、筛选或分页响应不能覆盖新响应。
- Skill 达到上限：
  - 禁用其余未选项；
  - 显示“最多选择 5 个 Skill”；
  - 不关闭 Dialog。
- 重复确认：
  - 确认期间禁用按钮；
  - `ChatInput` 再次按 ID/key 幂等合并。
- 已选资源在确认前失效：
  - 文件仍由发送端按当前用户重新校验；
  - Skill 仍由现有发送/运行边界校验；
  - 错误沿用当前消息发送恢复机制。
- 日志不得记录文件路径、内容、Blob URL、鉴权信息或 Skill 私密配置；必要日志仅记录资源类型、数量和错误类别。

## 迁移与回滚

### 迁移

- 无数据库、后端或历史数据迁移。
- 将 `ChatFilePickerDialog` 的能力迁入 `ChatResourcePickerDialog`，同步迁移测试。
- Composer 的“从我的文件选择”仍保留原文案和入口，只改变承载 Dialog。
- `$` Skill 快捷方式保持兼容。

### 回滚

- 恢复原 `ChatFilePickerDialog` 和 `openFileLibrary` 事件；
- 移除资源 Dialog 的 Skills 标签与菜单项；
- 文件、Skill、消息和 Session 数据均无需恢复。

### 计划分支

- 实施阶段使用普通分支 `feature/chat-resource-picker`。
- 基线为用户已提交并验收的 A1 完成提交。

## 风险

| 风险 | 可能性 | 影响 | 缓解措施 | 验证方式 |
| --- | --- | --- | --- | --- |
| 迁移文件 Dialog 导致 A1 回归 | 中 | 高 | 复用原逻辑并迁移全部单测，不重写 API 层 | 原文件选择测试 + 完整回归 |
| 标签切换丢失临时选择 | 中 | 中 | selection map 独立于标签页列表状态 | 跨标签、目录和分页测试 |
| Skill 容量计算遗漏已有项 | 中 | 中 | 以 selected + pending 统一计算 | 0/4/5 个已有 Skill 边界测试 |
| Props 更新后出现重复项 | 低 | 中 | 打开时初始化、确认时双重去重 | 动态更新与重复确认测试 |
| Session 切换泄漏临时选择 | 低 | 高 | watcher 主动关闭并重置 Dialog | Session 快速切换测试 |
| 焦点恢复到已关闭菜单项 | 中 | 低 | 记录稳定资源按钮引用作为回退焦点 | 键盘与读屏手工验收 |
| 文件与 Skill 错误状态相互污染 | 低 | 中 | 两标签独立 loading/error/retry | 分别模拟加载失败 |
| 390px 下标签、筛选和底栏溢出 | 中 | 中 | 标签固定、内容区滚动、底栏固定 | 390px 页面验收 |
| 同时点击确认产生重复合并 | 低 | 中 | 提交锁 + ChatInput 幂等去重 | 双击确认测试 |

## 假设

- A2 的“统一资源选择”仅覆盖文件与 Skills，因为它们是当前消息 payload 唯一支持的逐消息资源。
- MCP、A2A 和 API Tool 保持全局配置身份，不在本批伪装成消息资源。
- Project、Prompt、Agent Profile、Knowledge 和长期记忆继续作为后续独立学习任务。
- MCP UI Resource 仍按路线在 A7 单独处理。
- 用户希望保留 A1 已验收的“上传本地文件”和“从我的文件选择”入口。
- 用户希望 `$` 快捷选择继续可用。
- 当前没有需要用户先决策的架构分歧。

## 决策记录

| 日期 | 决策 | 原因 |
| --- | --- | --- |
| 2026-07-26 | 采用文件 + Skills 统一 Dialog | 覆盖当前真实逐消息资源，且无需后端协议变更 |
| 2026-07-26 | Dialog 只添加，不管理已有资源删除 | 避免意外删除和附件生命周期复杂化，移除入口已存在于 Composer |
| 2026-07-26 | 保留 `$` Skill Picker | 统一入口解决可发现性，快捷方式继续服务高频用户 |
| 2026-07-26 | Skills loading/error 由 Store 输入，重试由 Dialog 发事件 | 文件与 Skill 保持独立错误边界，Dialog 不复制 Store 或 API 状态 |
| 2026-07-26 | 不建设通用资源注册框架 | 当前数据模型与后续专项尚未准备，避免过度设计 |

## 验收标准

1. Composer 的统一资源入口可到达“上传本地文件”“从我的文件选择”“选择 Skill”。
2. 本地上传、拖拽和粘贴行为与 A1 一致。
3. 从“我的文件”打开时默认进入文件标签；从“选择 Skill”打开时默认进入 Skills 标签。
4. 文件与 Skills 标签可互相切换，未确认选择不会丢失。
5. 文件标签保留目录、当前目录搜索、类型/来源筛选、分页、跨页/目录多选、竞态保护、错误和重试。
6. Skills 标签只展示当前启用且可用的 Skill，并支持名称、展示名和描述搜索。
7. Composer 已有文件和 Skill 显示为已添加，不能重复选择。
8. “已有 + 待选”Skill 最多 5 个；达到上限时有明确反馈。
9. 点击确认后，文件与 Skill 一次性加入 Composer；重复 ID/key 不会重复添加。
10. 点击取消、按 Escape、关闭或切换 Session 均不改变 Composer。
11. 文件标签加载失败不影响 Skills；Skills 加载失败不影响文件。
12. `$` Skill 快捷选择继续工作，并遵守相同可用性与数量上限。
13. 发送普通消息和 running Session 下一条消息时，payload 仍只使用现有 `attachmentIds` 与 `skills`。
14. 发送成功、发送失败、重试、Session 切换和附件 Blob URL 生命周期无回归。
15. 桌面、390px、暗色、Tab/Enter/Escape、焦点恢复和屏幕阅读器状态通过验收。
16. 不新增后端接口、数据库迁移、依赖、shell 执行、沙箱写入或工具批准。
17. 相关单元测试、类型检查、构建和人工页面验收通过后，才可标记 `READY_TO_MERGE`。
