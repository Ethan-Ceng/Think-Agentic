# 对话安全导出实施计划

## 关联设计

- 设计文档：`agentic/docs/designs/chat-conversation-export.zh-CN.md`
- 预留开发分支：`feature/chat-conversation-export`（当前未激活）
- 堆叠基线：`16ccd1e`（已验收的 Artifact 批次；尚未合并到 `master`）

## 当前进度

- 整体状态：`DEFERRED`
- 当前阶段：deferred
- 当前任务：无
- 已完成：0 / 5
- 阻塞问题：无；因产品优先级调整主动延期
- 最近更新时间：2026-07-25（Asia/Shanghai）

## 全局约束

- 导出是当前 Session 的浏览器内只读快照，不是可恢复备份、公开分享或完整审计包。
- 数据源必须是服务端事件形成的 `baseTimeline`，不得包含本地草稿、pending/failed optimistic 消息或排队输入。
- 只允许 user/assistant message、相邻附件元数据和 visible error 进入快照。
- Tool、Step、Interaction、Plan、Trace、Memory、审批参数、系统提示、模型配置和文件正文不得进入任何导出格式。
- 附件只导出文件名、扩展名和大小；不导出 ID、路径、URL、鉴权信息或正文。
- Markdown 与 JSON 必须由同一个版本化白名单快照生成。
- 运行中导出只表示确认时刻的已持久化快照，不停止任务、不改变 SSE、Composer、排队消息或自动工具跟随。
- 下载只使用浏览器 Blob，不新增 API、数据库、迁移、后台任务、依赖或工具批准。
- 文件名必须安全化并由所选格式决定最终扩展名。
- 不自动提交、推送、创建 PR、合并或调整堆叠分支历史。
- `agentic/web/src/components.d.ts` 的组件扫描差异不得混入本批；类型/构建后必须恢复到本批开始状态。

## 状态变更记录

| 日期时间 | 整体状态 | 当前任务 | 变更原因 |
| --- | --- | --- | --- |
| 2026-07-25 | `PLAN_READY` | 无 | 完成导出方案比较、设计和五项可恢复实施拆分 |
| 2026-07-25 | `DEFERRED` | 无 | 用户确认导出当前可有可无，优先学习附件交互等高价值体验；未开始 Task 1 |

## Task 1：建立版本化安全导出快照

状态：pending

### 目标

用纯函数把当前 Session 的持久化 timeline 投影为严格白名单、稳定顺序和可版本化的 `ConversationExportSnapshot`。

### 涉及文件

- `agentic/web/src/lib/conversation-export.ts`（新建）
- `agentic/web/src/lib/conversation-export.spec.ts`（新建）
- `agentic/web/src/lib/session-events.ts`（仅在时间类型无法满足时最小调整）

### 依赖与接口

- 前置任务：无。
- 输入：Session ID、标题、状态、导出时间和 `TimelineItem[]`。
- 输出：`ConversationExportSnapshot`、`ConversationExportEntry`、`ExportAttachment` 及 `buildConversationExportSnapshot`。

### 实施步骤

1. 定义固定 `schema: agentic.session.transcript`、`version: 1`、Session 安全元数据和 message/error 白名单 entry。
2. 只接受 user/assistant message 和 visible error；忽略 tool、step、interaction 及其他 timeline kind。
3. 把紧邻 message 且 role 匹配的 attachments 折叠到该 message；只保留 filename、规范化 extension 和非负 size。
4. 将合法毫秒时间转为 ISO；缺失或非法时间输出 null；保持输入顺序。
5. 空白标题回退“未命名任务”，消息正文使用事件原文，不从 DOM 反解析。
6. 增加混合敏感 timeline 测试，精确断言 JSON 结构中不存在 Tool 参数、Interaction、file ID、URL、路径或未声明字段。
7. 增加 attachments 无前置 message、role 不匹配、多附件、错误、空 timeline 和确定性测试。

### 验证方式

- 运行：`pnpm test:run -- src/lib/conversation-export.spec.ts`
- 预期：退出 0；白名单、顺序、附件归属、时间、空值和敏感字段排除全部通过。

### 完成条件

- 任意混合 timeline 只能产生 schema v1 的 message/error entries，且附件严格限制为三个公开字段。

### 执行结果

待执行。

### 验证证据

```text
命令：待执行
退出状态：待执行
关键结果：待执行
执行时间：待执行
```

## Task 2：实现 Markdown/JSON 序列化与安全浏览器下载

状态：pending

### 目标

让同一个安全快照可确定性生成 Markdown 或 JSON，并使用安全文件名和浏览器 Blob 完成下载。

### 涉及文件

- `agentic/web/src/lib/conversation-export.ts`
- `agentic/web/src/lib/conversation-export.spec.ts`
- `agentic/web/src/lib/utils.ts`（仅复用既有 `downloadBlob`，原则上不修改）
- `agentic/web/src/lib/chat-artifacts.ts`（仅在确需提取通用文件名函数时调整）

### 依赖与接口

- 前置任务：Task 1。
- 输入：`ConversationExportSnapshot`、格式和用户文件名。
- 输出：`serializeConversationMarkdown`、`serializeConversationJson`、安全文件名和 `downloadConversationExport`。

### 实施步骤

1. Markdown 输出标题、Session 状态、导出时间、顺序消息、附件 manifest 和可见错误。
2. JSON 输出固定 schema/version、两个空格缩进和末尾换行，不读取原始 events。
3. 规范化用户文件名：移除路径/控制字符、Windows 保留名、尾部点/空格，限制长度并去掉伪扩展。
4. 根据格式固定添加 `.md` 或 `.json`，设置 UTF-8 MIME。
5. 下载复用 `downloadBlob`；不调用 file/session API、shell 或任何工具。
6. 增加多语言、代码块、特殊字符、空白标题、伪扩展、保留名、超长名、MIME 和 Blob 生命周期测试。
7. 验证 Markdown/JSON 都只消费 Task 1 快照，无法旁路加入隐藏字段。

### 验证方式

- 运行：`pnpm test:run -- src/lib/conversation-export.spec.ts src/lib/chat-artifacts.spec.ts`
- 预期：退出 0；两种格式、文件名、MIME、下载与既有 Artifact 工具回归通过。

### 完成条件

- 相同快照与时间产生稳定内容；最终文件名由格式控制，下载无网络、shell 或批准副作用。

### 执行结果

待执行。

### 验证证据

```text
命令：待执行
退出状态：待执行
关键结果：待执行
执行时间：待执行
```

## Task 3：实现导出 Dialog 与隐私/快照说明

状态：pending

### 目标

提供可访问、可恢复焦点且能保留失败编辑态的文件名/格式 Dialog，并明确安全导出范围。

### 涉及文件

- `agentic/web/src/components/chat/SessionExportDialog.vue`（新建）
- `agentic/web/src/components/chat/SessionExportDialog.spec.ts`（新建）
- `agentic/web/src/components/chat/conversation-export.css`（新建）
- `agentic/web/src/main.ts`
- `agentic/web/src/lib/conversation-export.ts`

### 依赖与接口

- 前置任务：Task 1–2。
- 输入：`modelValue`、Session ID/标题/状态和 `baseTimeline`。
- 输出：关闭事件及可选的不含正文的 `exported(format, filename)` 事件。

### 实施步骤

1. 使用 Element Plus Dialog 和现有 UI 组件实现文件名、Markdown/JSON 选择、范围说明及取消/导出动作。
2. 打开或 Session ID 变化时重置为标题派生文件名和 Markdown；关闭后由 Dialog 恢复触发器焦点。
3. running/waiting 显示“当前已保存快照”提示；completed 保持简洁说明。
4. 确认时重新从当前 props 构建快照，避免打开 Dialog 后 Session 更新却导出旧内容。
5. 成功下载后关闭并 toast 最终文件名；失败保持打开、文件名和格式不丢失。
6. 没有 exportable message/error 时禁用导出并提供说明。
7. 增加打开重置、格式选择、Session 快速切换、运行中提示、空状态、成功、失败保留和 Escape/焦点测试。

### 验证方式

- 运行：`pnpm test:run -- src/components/chat/SessionExportDialog.spec.ts src/lib/conversation-export.spec.ts`
- 预期：退出 0；Dialog 状态、当前快照、错误恢复、格式和可访问交互通过。

### 完成条件

- Dialog 始终导出当前 Session 的最新安全快照，失败不丢编辑态，运行中与隐私边界对用户清晰可见。

### 执行结果

待执行。

### 验证证据

```text
命令：待执行
退出状态：待执行
关键结果：待执行
执行时间：待执行
```

## Task 4：接入 SessionHeader 与持久化事件边界

状态：pending

### 目标

把导出入口接入 Session 页面，并用集成测试证明它只消费 `baseTimeline`、不影响运行中交互和现有 Header 动作。

### 涉及文件

- `agentic/web/src/components/SessionHeader.vue`
- `agentic/web/src/components/SessionHeader.spec.ts`（新建或补充）
- `agentic/web/src/components/SessionDetailView.vue`
- `agentic/web/src/components/SessionDetailView.spec.ts`
- `agentic/web/src/components/chat/SessionExportDialog.vue`
- `agentic/web/src/components/chat/conversation-export.css`
- `agentic/web/src/style.css`（仅在现有 Header 响应式规则需要调整时）

### 依赖与接口

- 前置任务：Task 1–3。
- 输入：SessionDetail 的 `detail.session`、`baseTimeline`、运行状态和 Header 事件。
- 输出：标题栏导出入口、Dialog 生命周期和基于持久化 timeline 的快照。

### 实施步骤

1. SessionHeader 增加 `exportable` 输入和 `openExport` 事件；按钮具有明确 `aria-label/title`，不直接访问 events。
2. SessionDetail 根据 `baseTimeline` 是否含 message/error 决定入口状态，并控制 Dialog。
3. 只把 `baseTimeline` 传给 Dialog；构造同时存在 pending/failed optimistic message 的集成测试，证明其不会导出。
4. Session ID 变化时关闭/重置 Dialog；运行中打开/导出不改变 preview selection、VNC、SSE、Composer 或 queue。
5. 保持 Trace、文件、侧栏和移动 Header 操作顺序及可访问名称。
6. 调整桌面、平板、390px、长标题和暗色样式，确保 Header 动作不溢出。
7. 增加空 Session、已有消息、pending 隔离、Session 切换、Trace/文件回归和 Header 键盘测试。

### 验证方式

- 运行：`pnpm test:run -- src/components/SessionHeader.spec.ts src/components/SessionDetailView.spec.ts src/components/chat/SessionExportDialog.spec.ts`
- 运行：`pnpm type-check`
- 预期：退出 0；入口、baseTimeline 边界、运行中隔离、Session 重置、Header 回归和类型检查通过。

### 完成条件

- 用户能从当前 Session 导出持久化对话，且本地 pending 内容和现有运行/预览动作不受影响。

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

以最新证据确认安全投影、浏览器下载和 Session 接入满足设计，且不会破坏聊天、队列、文件、Artifact、Tool、Trace、分支、审批和 HITL。

### 涉及文件

- 本计划涉及的全部代码和测试
- `agentic/docs/librechat-ui-redesign.zh-CN.md`
- `agentic/docs/reviews/chat-conversation-export-review.md`（新建）
- `agentic/docs/plans/chat-conversation-export-plan.md`

### 依赖与接口

- 前置任务：Task 1–4。
- 输入：相对堆叠基线 `16ccd1e` 的完整变更集和设计验收标准。
- 输出：最新验证证据、页面结果、分级审查和 `READY_TO_MERGE / BLOCKED / FAILED`。

### 实施步骤

1. 运行导出 snapshot、序列化、Dialog、Header 和 SessionDetail 定向测试。
2. 运行前端全量测试、类型检查和生产构建。
3. 确认没有后端、数据库迁移、`package.json`、lockfile 或大型依赖变化。
4. 运行 `git diff --check`，审阅相对 `16ccd1e` 的完整 diff，并清理自动生成的 `components.d.ts` 差异。
5. 页面验证 Markdown/JSON、文件名、空/完成/运行中、失败保留、Session 切换和 pending 隔离。
6. 验收桌面、平板、390px、长标题、暗色、Tab/Enter/Escape、焦点恢复和 Header 不溢出。
7. 监测导出操作不产生 session/file API、shell、沙箱写入或工具批准请求。
8. 按 blocking/major/minor/suggestion 完成代码审查；整改后重新运行受影响验证。
9. 将实际范围、证据、限制和状态写回计划、审查及 LibreChat 学习文档。

### 验证方式

- 定向：`pnpm test:run -- src/lib/conversation-export.spec.ts src/components/chat/SessionExportDialog.spec.ts src/components/SessionHeader.spec.ts src/components/SessionDetailView.spec.ts`
- 全量：`pnpm test:run`
- 类型：`pnpm type-check`
- 构建：`pnpm build`
- 静态：`git diff --check`
- 变更边界：`git diff 16ccd1e --stat`、`git diff 16ccd1e -- agentic/api agentic/web/package.json agentic/web/pnpm-lock.yaml agentic/web/src/components.d.ts`
- 手工：真实组件 Markdown/JSON 下载、网络请求监测、桌面/平板/390px、暗色、键盘和焦点恢复。

### 完成条件

- 自动化、类型、构建、静态、隐私边界、无工具批准和页面验收通过；审查无未处理 blocking/major；所有设计验收项有证据。

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
| 2026-07-25 | 初始计划 | 将安全快照、格式下载、Dialog、Session 接入和最终门禁拆为五个可独立验证任务 | Task 1–5 | 否 |

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

- [ ] 有持久化 message/error 的 Session 显示导出入口；空 Session 不可导出。
- [ ] Dialog 文件名、Markdown/JSON、打开重置和 Session 切换正确。
- [ ] Markdown/JSON 共用 schema v1 安全快照并保持服务端事件顺序。
- [ ] Tool、Step、Interaction、Plan、Trace、Memory、系统配置和审批参数不进入导出。
- [ ] 附件只有文件名、扩展名和大小，没有 ID、路径、URL 或正文。
- [ ] pending/failed optimistic 消息、本地草稿和排队输入不进入导出。
- [ ] running/waiting 快照提示正确，不影响任务、SSE、Composer 或 queue。
- [ ] 文件名对路径、控制字符、保留名、伪扩展和长度安全。
- [ ] 成功/失败反馈及失败保留编辑态正确。
- [ ] 浏览器 Blob 下载无后端、shell、沙箱写入或工具批准。
- [ ] 桌面、平板、390px、长标题、暗色、键盘和焦点恢复通过。
- [ ] 现有聊天、文件、Artifact、Tool、Trace、分支、审批、HITL 和下一条消息队列回归通过。
- [ ] 无数据库、后端 API、依赖、lockfile 或自动组件声明变化。
- [ ] 自动化、类型、构建、静态、页面和审查有最新证据。

### 未通过项目

当前尚未开始实施，所有验证待 Task 1–5 执行。

### 最终状态

待评定。实施完成后只能填写 `READY_TO_MERGE / BLOCKED / FAILED`；当前为 `PLAN_READY`。
