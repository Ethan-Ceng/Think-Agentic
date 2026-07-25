# 聊天附件交互增强实施计划

## 关联设计

- 设计文档：`agentic/docs/designs/chat-attachment-experience.zh-CN.md`
- 开发分支：`feature/chat-attachment-experience`
- 堆叠基线：`16ccd1e`（已验收的 Artifact 批次；尚未合并到 `master`）

## 当前进度

- 整体状态：`IN_PROGRESS`
- 当前阶段：implementation
- 当前任务：无（等待开始 Task 3）
- 已完成：2 / 5
- 阻塞问题：无
- 最近更新时间：2026-07-25（Asia/Shanghai）

## 全局约束

- 本批只实现 Composer 文件拖拽、统一附件菜单、“我的文件”选择和图片缩略图。
- 现有本地选择、粘贴和拖拽必须共用同一个上传状态机。
- 已有文件直接复用当前用户的 available 文件 ID，不重新上传或复制对象。
- 发送 payload 继续只包含 `attachmentIds`；服务端继续按 `file_id + current_user` 校验。
- 不新增数据库、迁移、后端 API、依赖、lockfile、shell、沙箱写入或工具批准。
- 不实现外部云盘、Knowledge、Vector Store、OCR、文件搜索工具或通用资源中心。
- 未发送附件不持久化；Session 切换继续清空附件和临时预览。
- 运行中附件继续使用现有下一条消息队列，不改变当前 Run、SSE、审批或 HITL。
- `agentic/web/src/components.d.ts` 的组件扫描差异不得混入本批；类型/构建后恢复到本批开始状态。
- 一次只推进一个 Task；每个 Task 完成后立即记录实际验证证据。

## 状态变更记录

| 日期时间 | 整体状态 | 当前任务 | 变更原因 |
| --- | --- | --- | --- |
| 2026-07-25 | `PLAN_READY` | 无 | 完成现状核对、三方案比较和五项可恢复实施拆分 |
| 2026-07-25 | `IN_PROGRESS` | Task 1 | 开始统一 Composer 附件类型、归一化与安全字段边界 |
| 2026-07-25 23:30 | `IN_PROGRESS` | 无 | Task 1 定向测试、类型和静态检查通过，等待 Task 2 |
| 2026-07-26 | `IN_PROGRESS` | Task 2 | 开始实现目录、筛选、分页、跨页选择和请求竞态 |
| 2026-07-26 05:21 | `IN_PROGRESS` | 无 | Task 2 定向测试、类型和静态检查通过，等待 Task 3 |

## Task 1：建立统一 Composer 附件视图模型

状态：completed

### 目标

用纯函数和窄类型统一表达本地上传与“我的文件”附件，为拖拽、选择、去重、图片判断和 optimistic message 提供稳定边界。

### 涉及文件

- `agentic/web/src/lib/composer-attachments.ts`（新建）
- `agentic/web/src/lib/composer-attachments.spec.ts`（新建）
- `agentic/web/src/components/chat/ChatComposer.vue`（仅导入共享类型时最小调整）
- `agentic/web/src/components/chat/ChatInput.vue`（仅导入共享类型时最小调整）
- `agentic/web/src/components/SessionDetailView.vue`（附件参数收窄需要时调整）

### 依赖与接口

- 前置任务：无。
- 输入：本地 `File`、上传响应 `FileInfo`、文件列表项 `ManagedFile` 和当前附件集合。
- 输出：`ComposerAttachmentFile`、`FilePickerSelection`、图片判断、已有文件归一化和按持久化 ID 去重函数。

### 实施步骤

1. 定义仅包含 ID、文件名、扩展名、大小、MIME、来源、上传状态、错误、进度和临时预览 URL 的 Composer 附件类型。
2. 将本地文件归一化为 uploading 项，将上传响应补丁为 uploaded 项。
3. 将 `ManagedFile` 归一化为 library/uploaded 项，不携带路径、下载 URL、Provider 或未声明字段。
4. 对已有文件按持久化 ID 去重；本地临时项保持现有可重复上传行为。
5. 规范化 MIME/扩展名图片判断，未知或伪装扩展名默认不生成图片预览。
6. 将 `ChatInput.onSend` 的附件展示参数收窄为实际使用的公开元数据，保持发送协议不变。
7. 增加字段精确断言、去重、顺序、空值、图片识别和敏感字段排除测试。

### 验证方式

- 运行：`pnpm test:run -- src/lib/composer-attachments.spec.ts src/components/chat/ChatInput.spec.ts src/components/SessionDetailView.spec.ts`
- 预期：退出 0；归一化、去重、图片判断、字段边界和现有发送回归通过。

### 完成条件

- 本地上传与已有文件可以进入同一个 Composer 附件集合，发送仍只依赖持久化 ID，library 选择结果不包含路径、URL 或存储信息。

### 执行结果

- 新建 `composer-attachments.ts`，集中定义本地上传与文件库共用的附件视图模型、安全消息元数据和文件选择白名单。
- 新增本地文件、上传完成、已有文件、稳定去重和浏览器安全栅格图片识别纯函数。
- 上传完成后附件从临时 ID 切换到持久化文件 ID，为后续“我的文件”选择去重提供统一键。
- `ChatComposer` 改为复用共享附件类型；`ChatInput`、`HomeView` 和 `SessionDetailView` 的发送附件参数由完整 `FileInfo` 收窄为 ID、名称、扩展名、大小和 MIME。
- 未修改发送 payload、文件 API、后端、数据库、依赖或 lockfile。

### 验证证据

```text
命令：pnpm test:run -- src/lib/composer-attachments.spec.ts
退出状态：1（预期失败）
关键结果：composer-attachments 模块尚不存在，证明新增测试先于实现失败
执行时间：2026-07-25 23:25（Asia/Shanghai）

命令：pnpm test:run -- src/lib/composer-attachments.spec.ts src/components/chat/ChatInput.spec.ts src/components/SessionDetailView.spec.ts
退出状态：0
关键结果：3 个测试文件、22 项测试全部通过
执行时间：2026-07-25 23:29（Asia/Shanghai）

命令：pnpm type-check
退出状态：0
关键结果：vue-tsc -b 通过
执行时间：2026-07-25 23:29（Asia/Shanghai）

命令：git diff --check；git diff --exit-code HEAD -- agentic/web/src/components.d.ts agentic/web/src/auto-imports.d.ts
退出状态：0
关键结果：静态格式通过；自动组件和自动导入声明均无差异
执行时间：2026-07-25 23:30（Asia/Shanghai）
```

## Task 2：实现可访问的“我的文件”选择 Dialog

状态：completed

### 目标

提供只读、可恢复选择态的文件 Dialog，使用户能跨目录和分页选择已有文件并安全返回 Composer。

### 涉及文件

- `agentic/web/src/components/chat/ChatFilePickerDialog.vue`（新建）
- `agentic/web/src/components/chat/ChatFilePickerDialog.spec.ts`（新建）
- `agentic/web/src/components/chat/attachment-experience.css`（新建）
- `agentic/web/src/main.ts`
- `agentic/web/src/lib/api/file.ts`（原则上只复用，不修改）
- `agentic/web/src/lib/api/types.ts`（仅共享类型确实不足时最小调整）

### 依赖与接口

- 前置任务：Task 1。
- 输入：`modelValue`、Composer 已有持久化文件 ID。
- 输出：`confirm(FilePickerSelection[])` 和 `update:modelValue`。

### 实施步骤

1. 使用现有 `ElDialog`、`UiTextField`、`UiState` 和文件 API 实现根目录加载。
2. 增加目录面包屑与进入目录行为；目录只导航，文件才可选择。
3. 增加当前目录搜索、文件类型、来源筛选和分页，筛选变化回到第一页。
4. 用独立 selection map 保留跨目录/分页选择；当前 Composer 已有文件显示为已选择且不重复计数。
5. 使用请求版本或等价机制，防止快速导航、搜索和筛选时旧响应覆盖新列表。
6. 取消不提交，确认返回安全窄类型；打开时以 props 重建选择，不泄漏上次 Session 状态。
7. 完成 loading、empty、error、retry、无可选文件和确认中状态。
8. 补充 Tab、Enter、Escape、焦点恢复、390px、长文件名和暗色样式。
9. 增加目录、筛选、分页、跨页选择、取消、确认、失败重试和请求竞态测试。

### 验证方式

- 运行：`pnpm test:run -- src/components/chat/ChatFilePickerDialog.spec.ts src/lib/composer-attachments.spec.ts`
- 预期：退出 0；目录、查询、选择持久性、竞态、错误状态和安全输出通过。

### 完成条件

- 用户能在不修改文件中心数据的情况下选择当前账号的已有文件；选择结果稳定、去重且只包含允许字段。

### 执行结果

- 新建 `ChatFilePickerDialog.vue`，复用现有文件 API 实现根目录/子目录导航、当前目录搜索、类型与来源筛选、分页和多选。
- 选择集合独立于当前列表，跨目录和分页保持稳定顺序；Composer 已有 ID 显示“已添加”并禁止重复选择。
- 使用请求版本隔离快速搜索、筛选和目录切换，迟到响应不会覆盖最新列表。
- Dialog 打开时重置选择和筛选，取消不提交，确认只返回 `FilePickerSelection` 白名单字段并恢复触发器焦点。
- 完成加载、空、失败、重试、长文件名、暗色 Token 和 640px 以下响应式布局。
- 新增独立附件体验样式并在 `main.ts` 引入；未修改文件 API、后端、数据库或依赖。

### 验证证据

```text
命令：pnpm test:run -- src/components/chat/ChatFilePickerDialog.spec.ts
退出状态：1（预期失败）
关键结果：ChatFilePickerDialog.vue 尚不存在，证明新增测试先于实现失败
执行时间：2026-07-26 05:17（Asia/Shanghai）

命令：pnpm test:run -- src/components/chat/ChatFilePickerDialog.spec.ts src/lib/composer-attachments.spec.ts
退出状态：0
关键结果：2 个测试文件、12 项测试全部通过；覆盖目录、筛选、分页、跨页选择、失败重试、请求竞态、安全输出和焦点恢复
执行时间：2026-07-26 05:20（Asia/Shanghai）

命令：pnpm type-check
退出状态：0
关键结果：vue-tsc -b 通过
执行时间：2026-07-26 05:20（Asia/Shanghai）

命令：git diff --check；git diff --exit-code HEAD -- agentic/web/src/components.d.ts agentic/web/src/auto-imports.d.ts
退出状态：0
关键结果：静态格式通过；自动组件和自动导入声明均无差异
执行时间：2026-07-26 05:21（Asia/Shanghai）
```

## Task 3：实现附件菜单、拖拽覆盖和图片卡片

状态：pending

### 目标

让 Composer 提供清晰的两种附件来源、稳定文件拖拽投放和非阻塞图片缩略图展示。

### 涉及文件

- `agentic/web/src/components/chat/ChatComposer.vue`
- `agentic/web/src/components/chat/ChatComposer.attachments.spec.ts`（新建）
- `agentic/web/src/components/chat/attachment-experience.css`
- `agentic/web/src/components/chat/chat.css`（仅移除或调整冲突规则时）

### 依赖与接口

- 前置任务：Task 1。
- 输入：统一附件项、disabled/uploading/sending 状态和图片 `previewUrl`。
- 输出：本地文件、打开文件库、移除、重试等事件；不直接调用文件 API。

### 实施步骤

1. 将回形针按钮升级为键盘可用菜单，提供“上传本地文件”和“从我的文件选择”。
2. 保持隐藏文件 input 由 `ChatInput` 控制，菜单只发事件。
3. 在 Composer 根区域处理 dragenter/dragover/dragleave/drop，只接受实际 Files。
4. 用进入深度或稳定命中判断消除子元素拖动闪烁；disabled/sending 时不接收投放。
5. 显示覆盖提示和明确 live 状态；drop 后把 `File[]` 交给现有上传路径。
6. 保留粘贴文件行为，证明粘贴、点击和拖拽触发相同上层入口。
7. 图片卡使用 Blob URL 缩略图和文件元数据；无 URL、加载错误或非图片降级为通用图标。
8. 保持失败重试、移除、上传进度、发送/停止按钮和 `$Skill` Picker 的层级与键盘行为。
9. 增加文件/非文件拖动、嵌套 dragleave、drop、菜单、图片降级、运行态和键盘测试。

### 验证方式

- 运行：`pnpm test:run -- src/components/chat/ChatComposer.attachments.spec.ts src/components/chat/ChatComposer.runtime.spec.ts src/components/chat/ChatComposer.skills.spec.ts`
- 预期：退出 0；三种附件输入、覆盖层、菜单、缩略图和 Composer 回归通过。

### 完成条件

- 拖拽文件能稳定进入与点击/粘贴相同的上传路径，非文件拖动不被拦截，附件菜单和图片卡可访问。

### 执行结果

待执行。

### 验证证据

```text
命令：待执行
退出状态：待执行
关键结果：待执行
执行时间：待执行
```

## Task 4：接入已有文件、预览生命周期与 Session 边界

状态：pending

### 目标

把 Dialog、附件菜单、上传队列和 Blob 预览接入 `ChatInput`，并证明首页、Session、运行中队列和快速切换行为正确。

### 涉及文件

- `agentic/web/src/components/chat/ChatInput.vue`
- `agentic/web/src/components/chat/ChatInput.spec.ts`
- `agentic/web/src/components/chat/ChatFilePickerDialog.vue`
- `agentic/web/src/components/chat/ChatComposer.vue`
- `agentic/web/src/components/SessionDetailView.vue`
- `agentic/web/src/components/SessionDetailView.spec.ts`
- `agentic/web/src/views/HomeView.vue`
- `agentic/web/src/views/HomeView.spec.ts`（若当前无测试则新建）
- `agentic/web/src/lib/session-init.spec.ts`

### 依赖与接口

- 前置任务：Task 1–3。
- 输入：Dialog selection、本地 `File`、上传结果、当前 Session ID 和现有发送回调。
- 输出：单一附件队列、`attachmentIds`、optimistic 附件元数据和完整 URL 清理。

### 实施步骤

1. 在 `ChatInput` 控制 Dialog 开关，并将已有文件合并到统一附件集合。
2. 对 library 图片使用 `previewFile` 懒加载 Blob；对本地图片立即创建对象 URL。
3. 用附件 ID/请求版本阻止迟到预览写回已移除或已切换项。
4. 在移除、发送成功、Session 切换、组件卸载和 URL 替换时精确撤销对象 URL。
5. 保持上传失败与发送失败附件；发送成功只清理发起发送的同一 Session 状态。
6. 首页创建 Session 时继续序列化已有文件 ID；Session 页面 optimistic message 显示正确文件元数据。
7. running Session 选择已有文件后继续进入 next-message queue；失败和 409 恢复逻辑不变。
8. 验证 Dialog 取消、重复选择、已删除文件、缩略图失败和快速 Session 切换。
9. 补充 API 调用断言：library 文件不调用 `uploadFile`，拖拽/粘贴/本地选择调用相同上传函数。

### 验证方式

- 运行：`pnpm test:run -- src/components/chat/ChatInput.spec.ts src/components/SessionDetailView.spec.ts src/views/HomeView.spec.ts src/lib/session-init.spec.ts`
- 运行：`pnpm type-check`
- 预期：退出 0；首页、Session、queue、失败保留、竞态和 URL 生命周期通过。

### 完成条件

- 两类附件在所有发送路径中行为一致，已有文件不重复上传，预览资源无泄漏，Session 切换不串附件。

### 执行结果

待执行。

### 验证证据

```text
命令：待执行
退出状态：待执行
关键结果：待执行
执行时间：待执行
```

## Task 5：完成全量回归、页面验收和代码审查

状态：pending

### 目标

用最新自动化、类型、构建、静态、页面和审查证据确认附件体验满足设计且不破坏聊天执行工作台。

### 涉及文件

- 本计划涉及的全部代码与测试
- `agentic/docs/librechat-ui-redesign.zh-CN.md`
- `agentic/docs/reviews/chat-attachment-experience-review.md`（新建）
- `agentic/docs/plans/chat-attachment-experience-plan.md`

### 依赖与接口

- 前置任务：Task 1–4。
- 输入：相对堆叠基线 `16ccd1e` 的完整变更集和设计验收标准。
- 输出：最终验证证据、页面验收结果、分级代码审查和 `READY_TO_MERGE / BLOCKED / FAILED`。

### 实施步骤

1. 运行附件模型、Dialog、Composer、ChatInput、Home 和 SessionDetail 定向测试。
2. 运行前端全量测试、类型检查和生产构建。
3. 确认无后端、数据库、迁移、`package.json`、lockfile 或依赖变化。
4. 运行 `git diff --check`，检查相对 `16ccd1e` 的完整差异并恢复 `components.d.ts` 扫描差异。
5. 页面验收本地选择、粘贴、拖拽、我的文件、图片/非图片、上传失败、列表失败和发送失败。
6. 验收首页、普通 Session、running queue、Session 快速切换、桌面、平板、390px、暗色、长文件名和无横向溢出。
7. 验收 Tab/Enter/Escape、菜单/Dialog 焦点恢复、拖拽 live 提示和非文件拖动。
8. 监测 library 选择不调用上传 API，整个能力不产生 shell、沙箱写入或工具批准请求。
9. 按 blocking/major/minor/suggestion 完成代码审查；修复后重新运行受影响验证。
10. 将实际范围、证据、限制和状态写回计划、审查和 LibreChat 学习文档。

### 验证方式

- 定向：`pnpm test:run -- src/lib/composer-attachments.spec.ts src/components/chat/ChatFilePickerDialog.spec.ts src/components/chat/ChatComposer.attachments.spec.ts src/components/chat/ChatInput.spec.ts src/components/SessionDetailView.spec.ts src/views/HomeView.spec.ts src/lib/session-init.spec.ts`
- 全量：`pnpm test:run`
- 类型：`pnpm type-check`
- 构建：`pnpm build`
- 静态：`git diff --check`
- 变更边界：`git diff 16ccd1e --stat`、`git diff 16ccd1e -- agentic/api agentic/web/package.json agentic/web/pnpm-lock.yaml agentic/web/src/components.d.ts`
- 手工：真实浏览器桌面/平板/390px/暗色/键盘/拖拽/网络请求检查。

### 完成条件

- 自动化、类型、构建、静态、权限边界、页面和审查通过；无未处理 blocking/major；所有设计验收项有证据。

### 执行结果

待执行。

### 验证证据

```text
命令：待执行
退出状态：待执行
关键结果：待执行
执行时间：待执行
```

## 计划变更

| 日期 | 变更内容 | 原因 | 影响任务 | 是否影响设计 |
| --- | --- | --- | --- | --- |
| 2026-07-25 | 初始计划 | 将附件模型、文件库 Dialog、Composer 交互、Session 集成和最终门禁拆为五项 | Task 1–5 | 否 |

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
git diff 16ccd1e --stat
git diff 16ccd1e -- agentic/api agentic/web/package.json agentic/web/pnpm-lock.yaml agentic/web/src/components.d.ts
```

### 执行结果

- 单元测试：未执行。
- 集成测试：未执行。
- 静态检查：未执行。
- 类型检查：未执行。
- 构建：未执行。
- 数据库迁移：不适用；设计不允许后端或数据库变化，实施后需确认。
- 手工验证：未执行。
- 代码审查：未执行。

### 验收标准检查

- [ ] 文件拖入 Composer 显示稳定覆盖，释放后进入现有上传队列。
- [ ] 文本、链接和页面内部拖动不触发上传或阻断默认行为。
- [ ] 粘贴、点击和拖拽共用上传状态、失败重试和发送规则。
- [ ] 回形针菜单可上传本地文件或打开“我的文件”。
- [ ] 文件 Dialog 支持目录、搜索、筛选、分页、多选和完整状态。
- [ ] 取消不改附件，确认直接复用 ID且不调用上传 API。
- [ ] 已有文件去重，跨目录/分页选择不丢失。
- [ ] 图片缩略图正确，失败降级且不阻止发送。
- [ ] Blob URL 在所有退出路径撤销。
- [ ] 首页、普通 Session、running queue 和快速 Session 切换正确。
- [ ] 发送失败保留附件，成功清理不影响其他 Session。
- [ ] 桌面、390px、暗色、键盘、焦点和无横向溢出通过。
- [ ] 无数据库、后端 API、依赖、lockfile、shell、沙箱写入或工具批准变化。
- [ ] 现有聊天、文件、Artifact、Tool、Trace、分支、审批、HITL、Skill 和下一条消息回归通过。

### 未通过项目

当前尚未开始实施，所有验证等待 Task 1–5 执行。

### 最终状态

待评定。实施完成后只能填写 `READY_TO_MERGE / BLOCKED / FAILED`；当前为 `PLAN_READY`。
