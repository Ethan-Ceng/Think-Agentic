# 聊天统一资源选择器实施计划

## 关联设计

- 设计文档：`agentic/docs/designs/chat-resource-picker.zh-CN.md`
- 开发分支：`feature/chat-resource-picker`
- 实施基线：`c8ab3c4`（用户已提交并验收的 A1 附件体验）

## 当前进度

- 整体状态：`DEFERRED`
- 当前阶段：planning
- 当前任务：无
- 已完成：0 / 5
- 阻塞问题：无；因当前可见收益有限，按产品决策暂缓实施
- 最近更新时间：2026-07-26（Asia/Shanghai）

## 全局约束

- 本批只统一 Composer 中当前消息协议已经支持的已有文件与已启用 Skills。
- 本地上传是文件添加动作；继续使用现有 `uploadFiles`，不成为新的资源类型。
- 消息与下一条消息 payload 继续只使用 `attachmentIds: string[]` 和 `skills: SkillRef[]`。
- 不纳入 MCP、A2A、API Tool、Project、Prompt、Agent Profile、Knowledge、长期记忆或通用资源 Provider。
- 不新增数据库、迁移、后端接口、依赖、lockfile、shell、沙箱写入或工具批准。
- `ChatInput` 继续作为附件、Skills、Dialog 和 Session 边界的唯一状态所有者。
- 资源 Dialog 只提交本次新增项；已有资源仍通过 Composer 卡片或标签移除。
- 文件与 Skills 使用独立加载和错误状态；任一失败不得阻断另一标签页。
- Skills 总数按 Composer 已有项与 Dialog 待选项共同计算，最多 5 个。
- 保留 `$` Skill Picker，并与资源 Dialog 共享身份、可用性、搜索和数量规则。
- A1 的目录、搜索、筛选、分页、跨页选择、竞态、焦点和附件预览生命周期不得回归。
- Session 切换必须关闭 Dialog 并丢弃未确认选择；取消、Escape 和关闭不得修改 Composer。
- 运行中确认的资源继续进入现有下一条消息队列，不修改当前 Run。
- `agentic/web/src/components.d.ts` 与 `auto-imports.d.ts` 的生成扫描差异不得混入本批。
- 一次只推进一个 Task；状态变化、执行结果和验证证据必须立即写回本计划。

## 状态变更记录

| 日期时间 | 整体状态 | 当前任务 | 变更原因 |
| --- | --- | --- | --- |
| 2026-07-26 | `PLAN_READY` | 无 | 设计完成并拆分为五项可恢复、可独立验证的实施任务 |
| 2026-07-26 | `DEFERRED` | 无 | 统一资源选择当前可见收益有限，保留设计和计划但不进入编码 |

## Task 1：建立统一资源选择契约与共享 Skill 规则

状态：pending

### 目标

用纯类型和纯函数定义资源 Dialog 的确认结果、Skill 身份、可用性、搜索、容量与去重规则，使行内 `$` Picker、统一 Dialog 和 `ChatInput` 使用同一套业务约束。

### 涉及文件

- `agentic/web/src/lib/chat-resource-picker.ts`（新建）
- `agentic/web/src/lib/chat-resource-picker.spec.ts`（新建）
- `agentic/web/src/components/skills/SkillPicker.vue`
- `agentic/web/src/components/skills/SkillPicker.spec.ts`
- `agentic/web/src/types/skill.ts`（仅现有导出无法表达窄接口时最小调整）

### 依赖与接口

- 前置任务：无。
- 输入：`SkillSummary[]`、`SkillRef[]`、搜索文本、当前已选 Skill 和最大数量。
- 输出：
  - `ChatResourcePickerTab`
  - `ChatResourcePickerResult`
  - Skill summary/ref 的稳定 key 与转换函数
  - 可用 Skill 过滤、搜索、去重和剩余容量函数
- 兼容：`SendMessageInput` 与现有 `SkillRef` 结构不变。

### 实施步骤

1. 先增加失败测试，覆盖 personal/marketplace Skill key、summary → ref、active/enabled 过滤、名称/展示名/描述搜索、稳定顺序、重复项和 0/4/5 容量边界。
2. 定义 `ChatResourcePickerTab = 'files' | 'skills'` 和只包含新增文件、Skill 摘要的 `ChatResourcePickerResult`。
3. 抽取 Skill key、转换、可用性、搜索和容量函数，所有函数不得读 Store、DOM、网络或 Session。
4. 将 `SkillPicker.vue` 改为复用共享函数，保持 ArrowUp/ArrowDown/Enter/Escape、重复禁用、最大 5 个和现有文案。
5. 补充行内 Picker 回归，证明共享规则没有改变 `$` 快捷选择行为。
6. 检查输出类型不包含 Skill 私密配置、文件路径、URL、Provider 凭据或用户 ID。

### 验证方式

- 运行：`pnpm test:run -- src/lib/chat-resource-picker.spec.ts src/components/skills/SkillPicker.spec.ts`
- 运行：`pnpm type-check`
- 运行：`git diff --check`
- 预期：退出 0；共享规则、行内 Picker 键盘行为、容量、去重和类型检查通过。

### 完成条件

- 行内 `$` Picker、后续 Dialog 与 `ChatInput` 可依赖同一个 Skill 身份和容量契约，且消息 payload 类型未变化。

### 执行结果

待执行。

### 验证证据

```text
待执行。
```

## Task 2：将文件选择器升级为统一资源 Dialog

状态：pending

### 目标

在不回退 A1 文件浏览能力的前提下，用一个可访问 Dialog 完成文件与 Skills 的跨标签临时选择、独立错误处理和原子确认。

### 涉及文件

- `agentic/web/src/components/chat/ChatFilePickerDialog.vue`（迁移后删除）
- `agentic/web/src/components/chat/ChatFilePickerDialog.spec.ts`（迁移后删除）
- `agentic/web/src/components/chat/ChatResourcePickerDialog.vue`（新建）
- `agentic/web/src/components/chat/ChatResourcePickerDialog.spec.ts`（新建）
- `agentic/web/src/components/chat/attachment-experience.css`
- `agentic/web/src/lib/chat-resource-picker.ts`

### 依赖与接口

- 前置任务：Task 1。
- 输入：
  - `modelValue`
  - `initialTab`
  - `selectedFileIds`
  - `selectedSkillKeys`
  - `availableSkills`
  - `skillsLoading`
  - `skillsError`
  - `skillLimit`
- 输出：
  - `update:modelValue`
  - `confirm(ChatResourcePickerResult)`
  - `retrySkills`
- 复用：现有文件列表 API、`FilePickerSelection` 和 A1 请求版本保护。

### 实施步骤

1. 先把 A1 文件选择器测试迁移到新组件名，确保迁移前测试能证明缺少统一 Dialog。
2. 将现有文件 Dialog 的目录、面包屑、搜索、类型/来源筛选、分页、多选、跨页/目录选择、加载/空/失败/重试和请求竞态完整迁入。
3. 增加“文件”“Skills”标签，`initialTab` 决定每次打开的初始标签。
4. 使用相互独立的 `fileById` 与 `skillByKey` 临时 selection map，标签切换不销毁选择。
5. Skills 标签只展示 active + enabled 项，支持名称、展示名和描述搜索；已有项显示“已添加”并禁用。
6. 按“Composer 已有 + Dialog 待选”计算 5 个上限，达到上限时禁用其余项并显示原因。
7. 接入 `skillsLoading`、`skillsError` 和 `retrySkills`；Skills 失败不清空文件选择，文件失败不阻断 Skills。
8. 取消、遮罩、关闭、Escape 和重新打开都重置临时状态；确认只 emit 本次新增、已去重的文件与 Skill。
9. 确认期间锁定重复提交；确认按钮文案显示两类资源合计数量。
10. 保持打开焦点、Tab/Enter/Escape、关闭后稳定触发器回焦、暗色、长文本和 390px 无横向溢出。
11. 删除旧组件与旧测试，确保仓库中不保留两套文件选择逻辑。

### 验证方式

- 运行：`pnpm test:run -- src/components/chat/ChatResourcePickerDialog.spec.ts src/lib/chat-resource-picker.spec.ts src/lib/composer-attachments.spec.ts`
- 运行：`pnpm type-check`
- 运行：`git diff --check`
- 预期：退出 0；A1 文件能力、跨标签选择、Skills 搜索/容量、错误隔离、取消、原子确认和焦点行为通过。

### 完成条件

- 一个 Dialog 可以从任一初始标签进入并一次确认文件与 Skills；取消无副作用，两类错误互不污染，旧文件 Dialog 已被完整替代。

### 执行结果

待执行。

### 验证证据

```text
待执行。
```

## Task 3：将 Composer 附件菜单升级为统一资源入口

状态：pending

### 目标

让 Composer 从一个可发现、键盘可用的资源入口到达本地上传、已有文件和 Skills，同时保留拖拽、粘贴与 `$` 快捷选择。

### 涉及文件

- `agentic/web/src/components/chat/ChatComposer.vue`
- `agentic/web/src/components/chat/ChatComposer.attachments.spec.ts`
- `agentic/web/src/components/chat/ChatComposer.skills.spec.ts`
- `agentic/web/src/components/chat/ChatComposer.runtime.spec.ts`
- `agentic/web/src/components/chat/attachment-experience.css`

### 依赖与接口

- 前置任务：Task 1。
- 输入：现有附件、Skills、上传/发送/禁用/运行状态。
- 输出：
  - 保留 `attach`
  - 新增 `openResourcePicker(tab: 'files' | 'skills')`
  - 移除内部使用的 `openFileLibrary`
- 兼容：保留 `selectSkill`、`removeSkill`、拖拽、粘贴、发送和停止事件。

### 实施步骤

1. 先增加失败测试，断言菜单显示三个动作及正确事件参数。
2. 将 tooltip、ARIA label 和菜单 label 从“附件”调整为“资源”，保持图标紧凑且含义清晰。
3. 保留“上传本地文件”，继续 emit `attach` 并复用隐藏文件 input。
4. “从我的文件选择”emit `openResourcePicker('files')`。
5. 新增“选择 Skill”，emit `openResourcePicker('skills')`。
6. 保持菜单外点击关闭、Escape 关闭并回焦、首项打开聚焦、禁用状态和菜单层级。
7. 证明文件拖拽、粘贴、上传卡、图片缩略图和失败重试行为没有变化。
8. 证明 `$` 行内 Picker、Skill chip 移除、Enter/Shift+Enter、运行中发送和停止行为没有变化。
9. 检查 390px、暗色、长菜单文案和无横向溢出样式。

### 验证方式

- 运行：`pnpm test:run -- src/components/chat/ChatComposer.attachments.spec.ts src/components/chat/ChatComposer.skills.spec.ts src/components/chat/ChatComposer.runtime.spec.ts`
- 运行：`pnpm type-check`
- 运行：`git diff --check`
- 预期：退出 0；三入口、事件参数、菜单键盘行为以及附件/Skill/运行态回归通过。

### 完成条件

- 用户可从同一个 Composer 入口发现三种添加动作，已有附件与 `$` Skill 交互无回归。

### 执行结果

待执行。

### 验证证据

```text
待执行。
```

## Task 4：接入 ChatInput、Store 与 Session 边界

状态：pending

### 目标

由 `ChatInput` 统一控制资源 Dialog、Store 状态和确认合并，使首页、普通 Session、运行中队列、失败恢复与 Session 快速切换保持正确。

### 涉及文件

- `agentic/web/src/components/chat/ChatInput.vue`
- `agentic/web/src/components/chat/ChatInput.attachments.spec.ts`
- `agentic/web/src/components/chat/ChatInput.spec.ts`
- `agentic/web/src/components/chat/ChatComposer.skills.spec.ts`
- `agentic/web/src/components/SessionDetailView.spec.ts`
- `agentic/web/src/views/HomeView.spec.ts`
- `agentic/web/src/lib/session-init.spec.ts`
- `agentic/web/src/stores/skills.ts`（原则上只复用，不修改）

### 依赖与接口

- 前置任务：Task 1–3。
- 输入：Composer `openResourcePicker(tab)`、现有附件集合、已选 Skills、`skillsStore.activeSkills/loading/error` 和 Session ID。
- 输出：Dialog props、`retrySkills`、原子合并、现有 `attachmentIds` 与 `skills` payload。

### 实施步骤

1. 先增加集成失败测试，覆盖 files/skills 初始标签、确认两类资源、取消、重试、重复去重和 Session 切换。
2. 用 `resourcePickerOpen` 与 `resourcePickerInitialTab` 替换 `filePickerOpen` 和 `openFileLibrary`。
3. 传入当前持久化文件 ID、当前 Skill key、active Skills、Store loading/error 和最大数量。
4. `retrySkills` 只调用现有 `skillsStore.loadSkills()`，错误继续由 Store 暴露，不在 Dialog 复制 API 状态。
5. 确认时先对文件调用现有 `addLibraryFiles`，再使用共享转换和 `selectSkill` 逻辑合并 Skills；两层都按 ID/key 去重。
6. 确认后关闭 Dialog；取消和单标签加载失败不改变 Composer 已有资源。
7. Session ID 变化时关闭 Dialog、重置初始标签并丢弃未确认选择，同时保留现有附件/Skill 清理规则。
8. 验证 Dialog 打开期间 Store props 更新、Skill 被禁用、重复确认和达到上限时不会产生重复或超额项。
9. 验证首页创建 Session、普通 Session 消息和 running Session 下一条消息仍发送相同 `attachmentIds`/`skills`。
10. 验证发送成功清理、发送失败保留、旧 Session 异步完成和附件 Blob URL 生命周期无回归。

### 验证方式

- 运行：`pnpm test:run -- src/components/chat/ChatInput.attachments.spec.ts src/components/chat/ChatInput.spec.ts src/components/chat/ChatComposer.skills.spec.ts src/components/SessionDetailView.spec.ts src/views/HomeView.spec.ts src/lib/session-init.spec.ts`
- 运行：`pnpm type-check`
- 运行：`git diff --check`
- 预期：退出 0；Dialog/Store 集成、去重、Session 切换、首页、普通消息、运行中队列和失败恢复通过。

### 完成条件

- 文件与 Skills 能从统一 Dialog 安全合并到所有消息发送路径，Session 与异步边界不串资源，payload 和后端协议不变。

### 执行结果

待执行。

### 验证证据

```text
待执行。
```

## Task 5：完成全量验证、页面验收和代码审查

状态：pending

### 目标

用最新自动化、类型、构建、静态、页面与审查证据确认 A2 满足设计，且 A1 附件、Skills、聊天运行与下一条消息没有回归。

### 涉及文件

- 本计划涉及的全部代码与测试
- `agentic/docs/designs/chat-resource-picker.zh-CN.md`
- `agentic/docs/librechat-ui-redesign.zh-CN.md`
- `agentic/docs/reviews/chat-resource-picker-review.md`（新建）
- `agentic/docs/plans/chat-resource-picker-plan.md`

### 依赖与接口

- 前置任务：Task 1–4。
- 输入：相对基线 `c8ab3c4` 的完整变更集与设计验收标准。
- 输出：最终验证证据、用户页面验收清单、分级代码审查和 `READY_TO_MERGE / BLOCKED / FAILED`。

### 实施步骤

1. 运行资源契约、统一 Dialog、Composer、ChatInput、SkillPicker、Home 和 SessionDetail 定向测试。
2. 运行前端全量测试、类型检查和生产构建。
3. 运行静态检查并恢复 `components.d.ts`、`auto-imports.d.ts` 的生成扫描差异。
4. 确认相对 `c8ab3c4` 无后端、数据库、迁移、`package.json`、lockfile 或依赖变化。
5. 页面验收三个资源菜单动作、文件/Skills 初始标签、跨标签待选保持、确认、取消和重复去重。
6. 验收文件目录/搜索/筛选/分页/竞态/失败重试与 Skills 搜索/上限/loading/error/retry 的独立状态。
7. 验收本地上传、拖拽、粘贴、图片预览、失败重试、`$` Skill Picker、发送成功/失败和运行中下一条消息。
8. 验收首页、普通 Session、快速 Session 切换、桌面、390px、暗色、长文本和无横向溢出。
9. 验收 Tab/Enter/Escape、菜单/Dialog 焦点恢复、ARIA 状态与屏幕阅读器可理解文案。
10. 监测已有文件不调用上传 API，整个能力不产生新增 shell、沙箱写入或工具批准请求。
11. 按 blocking/major/minor/suggestion 完成代码审查；修复后重新运行受影响验证。
12. 将实际范围、偏差、证据、页面验收和最终状态写回设计、计划、审查与 LibreChat 学习路线。

### 验证方式

- 定向：`pnpm test:run -- src/lib/chat-resource-picker.spec.ts src/lib/composer-attachments.spec.ts src/components/skills/SkillPicker.spec.ts src/components/chat/ChatResourcePickerDialog.spec.ts src/components/chat/ChatComposer.attachments.spec.ts src/components/chat/ChatComposer.skills.spec.ts src/components/chat/ChatComposer.runtime.spec.ts src/components/chat/ChatInput.attachments.spec.ts src/components/chat/ChatInput.spec.ts src/components/SessionDetailView.spec.ts src/views/HomeView.spec.ts src/lib/session-init.spec.ts`
- 全量：`pnpm test:run`
- 类型：`pnpm type-check`
- 构建：`pnpm build`
- 静态：`git diff --check`
- 变更边界：`git diff c8ab3c4 --stat`
- 禁止范围：`git diff --exit-code c8ab3c4 -- agentic/api agentic/web/package.json agentic/web/pnpm-lock.yaml`
- 生成声明：`git diff --exit-code c8ab3c4 -- agentic/web/src/components.d.ts agentic/web/src/auto-imports.d.ts`
- 手工：真实浏览器桌面/390px/暗色/键盘/文件/Skills/网络请求检查。

### 完成条件

- 自动化、类型、构建、静态、范围边界、页面和代码审查通过；无未处理 blocking/major；全部设计验收标准有证据。

### 执行结果

待执行。

### 验证证据

```text
待执行。
```

## 计划变更

| 日期 | 变更内容 | 原因 | 影响任务 | 是否影响设计 |
| --- | --- | --- | --- | --- |
| 2026-07-26 | 初始计划 | 将共享资源契约、统一 Dialog、Composer 入口、ChatInput/Session 集成和最终门禁拆为五项 | Task 1–5 | 否 |

## 最终验证

### 执行命令

```powershell
# agentic/web
pnpm test:run
pnpm type-check
pnpm build

# D:\AI\Think-Agentic
git diff --check
git status --short
git diff c8ab3c4 --stat
git diff --exit-code c8ab3c4 -- agentic/api agentic/web/package.json agentic/web/pnpm-lock.yaml
git diff --exit-code c8ab3c4 -- agentic/web/src/components.d.ts agentic/web/src/auto-imports.d.ts
```

### 执行结果

- 单元测试：未执行。
- 集成测试：未执行。
- 静态检查：未执行。
- 类型检查：未执行。
- 构建：未执行。
- 数据库迁移：不适用；设计禁止数据库与后端变更。
- 手工验证：未执行。
- 代码审查：未执行。

### 验收标准检查

- [ ] 统一资源入口可到达本地上传、我的文件和选择 Skill。
- [ ] 本地上传、拖拽、粘贴与 A1 行为一致。
- [ ] 文件或 Skills 菜单动作打开同一 Dialog 并落在正确初始标签。
- [ ] 文件与 Skills 标签切换不丢失未确认选择。
- [ ] 文件标签保留目录、搜索、类型/来源筛选、分页、跨页/目录多选、竞态、错误和重试。
- [ ] Skills 标签只展示 active + enabled 项，并支持名称、展示名和描述搜索。
- [ ] Composer 已有文件和 Skill 显示已添加且不能重复选择。
- [ ] 已有与待选 Skill 合计最多 5 个，并有明确上限反馈。
- [ ] 确认原子添加两类资源，重复 ID/key 不会重复合并。
- [ ] 取消、Escape、关闭和 Session 切换均不改变 Composer。
- [ ] 文件与 Skills 加载错误互不影响，并分别可重试。
- [ ] `$` Skill Picker 继续工作并共享相同规则。
- [ ] 首页、普通 Session 和 running Session 下一条消息 payload 保持 `attachmentIds` 与 `skills`。
- [ ] 发送成功/失败、重试、Session 切换和 Blob URL 生命周期无回归。
- [ ] 桌面、390px、暗色、键盘、焦点和屏幕阅读器状态通过。
- [ ] 无后端、数据库、迁移、依赖、lockfile、shell、沙箱写入或工具批准变化。
- [ ] 全量测试、类型检查、生产构建、范围检查和代码审查通过。

### 未通过项目

尚未执行实施与验证。

### 最终状态

`READY_TO_MERGE / BLOCKED / FAILED`（尚未判定；完成实施与最终验证后填写）。
