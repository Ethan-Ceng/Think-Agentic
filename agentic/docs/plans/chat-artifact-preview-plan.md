# Markdown 代码块与生成产物统一预览实施计划

## 关联设计

- 设计文档：`agentic/docs/designs/chat-artifact-preview.zh-CN.md`
- 开发分支：`feature/chat-artifact-preview`

## 当前进度

- 整体状态：`READY_TO_MERGE`
- 当前阶段：completed
- 当前任务：Task 5：完成全量回归、安全验收和代码审查（completed）
- 已完成：5 / 5
- 阻塞问题：无
- 最近更新时间：2026-07-25 22:15（Asia/Shanghai）

## 全局约束

- Inline Artifact 只是 Assistant 消息的只读派生视图；不新增数据库、API、事件或模型输出协议。
- 不执行 JavaScript、React、Vue、Python、Mermaid 或其他用户代码。
- HTML 只能进入空 sandbox iframe，并注入禁止脚本、网络、表单、弹窗和顶层导航的 CSP。
- Markdown 继续使用 `html: false`，预览内不递归生成 Artifact 操作。
- 代码块复制和下载只使用浏览器 Clipboard/Blob，不调用 shell、不写沙箱文件、不触发工具批准。
- Assistant 附件继续使用既有文件鉴权和下载接口。
- 手工选择为 pinned；自动工具只能更新空 selection 或既有 auto-tool selection。
- Session 切换必须清空选择并撤销对象 URL。
- 保留 Agent Run、Trace、Memory、审批、HITL、分支和文件权限语义。
- 实施前创建普通 Git Branch，不自动提交、推送、创建 PR 或合并。
- `agentic/web/src/components.d.ts` 存在本批开始前的用户修改；除非用户确认属于本批，否则不得覆盖、还原或混入提交。

## 状态变更记录

| 日期时间 | 整体状态 | 当前任务 | 变更原因 |
| --- | --- | --- | --- |
| 2026-07-25 | `PLAN_READY` | 无 | 设计确认并完成五项实施拆分 |
| 2026-07-25 | `IN_PROGRESS` | Task 1 | 用户确认继续，已创建 `feature/chat-artifact-preview` 并开始实施 |
| 2026-07-25 18:43 | `IN_PROGRESS` | Task 2（pending） | Task 1 定向测试、回归和类型检查通过 |
| 2026-07-25 | `IN_PROGRESS` | Task 2 | 用户确认继续，开始实现安全预览侧栏 |
| 2026-07-25 20:09 | `IN_PROGRESS` | Task 3（pending） | Task 2 安全面板、定向回归和类型检查通过 |
| 2026-07-25 | `IN_PROGRESS` | Task 3 | 用户确认继续，开始统一 Session 预览选择 |
| 2026-07-25 20:22 | `IN_PROGRESS` | Task 4（pending） | Task 3 消息接入、固定选择、自动跟随和类型检查通过 |
| 2026-07-25 | `IN_PROGRESS` | Task 4 | 用户确认继续，开始升级聊天生成文件预览 |
| 2026-07-25 20:37 | `IN_PROGRESS` | Task 5（pending） | Task 4 文件分类、安全预览、竞态清理、键盘入口和类型检查通过 |
| 2026-07-25 | `IN_PROGRESS` | Task 5 | 用户确认继续，开始最终验证、安全验收和代码审查 |
| 2026-07-25 20:51 | `REVIEWING` | Task 5 | 定向测试、前端全量测试、类型检查和生产构建通过，进入完整 diff 与页面安全审查 |
| 2026-07-25 22:15 | `READY_TO_MERGE` | Task 5（completed） | 浏览器发现的 iframe 自身导航问题已整改；最终全量回归、安全验收、构建和代码审查通过 |

## Task 1：建立只读 Inline Artifact 模型与代码块动作

状态：completed

### 目标

让 Assistant 的已闭合 fenced code block 具有稳定、可测试的语言、复制、下载和打开动作，同时保持其他 Markdown 渲染兼容。

### 涉及文件

- `agentic/web/src/lib/chat-artifacts.ts`（新建）
- `agentic/web/src/lib/chat-artifacts.spec.ts`（新建）
- `agentic/web/src/components/MarkdownContent.vue`
- `agentic/web/src/components/MarkdownContent.spec.ts`（新建）
- `agentic/web/src/types/markdown-it.d.ts`
- `agentic/web/src/components/chat/chat.css`
- `agentic/web/src/style.css`（仅在通用 Markdown 规则必须调整时）

### 依赖与接口

- 前置任务：无。
- 输入：Assistant Markdown 字符串、消息 `artifactScope`、fenced block info/content。
- 输出：`InlineChatArtifact`、代码块工具栏、`artifactOpen` 事件。

### 实施步骤

1. 在 `chat-artifacts.ts` 定义 `InlineChatArtifact`、语言别名、kind、可用视图、MIME、扩展和安全文件名规则。
2. 实现从 scope、fence index、info string 和原始内容构建 Artifact 的纯函数；空内容和未闭合 fence 不生成。
3. 为 MarkdownContent 增加 `artifactScope`、`enableArtifacts` 和 `artifactOpen`；默认关闭，保持其他调用者兼容。
4. 使用 markdown-it fence renderer 输出语义化标题和三个按钮；代码正文继续正确转义。
5. 在 Markdown 根节点使用事件委托处理复制、下载、打开；复制/下载读取 render 时保存的原始内容 Map，不从 DOM 反解析。
6. 为 Clipboard fallback、Blob 生命周期、成功/失败 toast 和键盘按钮语义补齐处理。
7. 增加普通 Markdown、未闭合 fence、多代码块、特殊字符、语言别名、安全文件名和关闭模式的测试。

### 验证方式

- 运行：`pnpm test:run -- src/lib/chat-artifacts.spec.ts src/components/MarkdownContent.spec.ts`
- 运行：`pnpm type-check`
- 预期：退出 0；类型、派生 ID、原文复制/下载、事件透传和原 Markdown 兼容测试通过。

### 完成条件

- 只有启用 Artifact 的已闭合非空 fenced code 获得动作；多块不串内容，复制/下载无 API 或 shell 调用，其他 Markdown 行为无回归。

### 执行结果

新增 `InlineChatArtifact`、语言别名、kind/视图、MIME、扩展、安全文件名和闭合 fence 判断的纯函数。MarkdownContent 在默认关闭时保持原有安全渲染；启用后仅为已闭合、非空 fenced code 生成语言标题、复制、下载和打开按钮，并通过消息 scope 与原始 fence 序号生成稳定 ID。

代码块动作使用当前 render 建立的原始内容 Map，不从转义后的 DOM 反解析。复制优先 Clipboard API，并保留 textarea fallback；下载使用浏览器 Blob 和既有 `downloadBlob`，不调用后端、shell 或沙箱写入。CJK 链接规范化调整为跳过 fenced code，避免改变复制和下载的代码原文。

测试先行的首次运行按预期失败：缺少 `chat-artifacts.ts`，且 MarkdownContent 尚无动作。实现后定向测试由 8 项扩展到 10 项全部通过。类型检查暴露仓库既有 `markdown-it` 声明只有 `render(src)`；计划先记录偏差，再补充运行库已存在的 renderer、utils 和 env 最小类型，未新增依赖。

### 验证证据

```text
命令：pnpm test:run -- src/lib/chat-artifacts.spec.ts src/components/MarkdownContent.spec.ts
退出状态：0
关键结果：2 个测试文件、10 项测试全部通过；覆盖语言、稳定 ID、安全文件名、闭合 fence、多块原文、复制/失败、下载和 CJK 链接隔离
执行时间：2026-07-25 18:42（Asia/Shanghai）

命令：pnpm type-check
退出状态：0
关键结果：vue-tsc -b 通过
执行时间：2026-07-25 18:43（Asia/Shanghai）

命令：pnpm test:run -- src/components/chat/ChatMessage.spec.ts
退出状态：0
关键结果：1 个测试文件、5 项既有消息回归全部通过
执行时间：2026-07-25 18:43（Asia/Shanghai）

命令：git diff --check
退出状态：0
关键结果：无空白错误；仅显示仓库既有 LF/CRLF 转换提示
执行时间：2026-07-25 18:43（Asia/Shanghai）
```

## Task 2：实现源码/安全预览 Artifact 侧栏

状态：completed

### 目标

提供 LibreChat 式源码/预览、复制、下载、关闭面板，并把 HTML 预览限制在不可执行、不可联网的安全边界内。

### 涉及文件

- `agentic/web/src/components/chat/ChatArtifactPreviewPanel.vue`（新建）
- `agentic/web/src/components/chat/ChatArtifactPreviewPanel.spec.ts`（新建）
- `agentic/web/src/components/chat/SafeHtmlPreview.vue`（新建）
- `agentic/web/src/components/chat/SafeHtmlPreview.spec.ts`（新建）
- `agentic/web/src/lib/chat-artifacts.ts`
- `agentic/web/src/components/MarkdownContent.vue`
- `agentic/web/src/components/chat/artifact-preview.css`（新建）
- `agentic/web/src/main.ts`

### 依赖与接口

- 前置任务：Task 1。
- 输入：`InlineChatArtifact`。
- 输出：只读 source/preview panel 和 `close` 事件。

### 实施步骤

1. 新建 Artifact Panel，按 `availableViews` 显示源码和预览标签；单视图类型不显示无意义的标签。
2. artifact ID 变化时重置默认标签：可预览类型默认 preview，source-only 默认 source。
3. 源码视图使用可滚动 `<pre>`，保留空格和换行；标题和语言长文本安全截断。
4. Markdown 预览复用 MarkdownContent，但关闭 `enableArtifacts`，禁止递归入口和原始 HTML。
5. SafeHtmlPreview 在用户内容之前注入严格 CSP，以 `sandbox=""` iframe 渲染；设置内容大小上限和降级提示。
6. 面板复制和下载复用 Task 1 的原始内容、MIME 和安全文件名工具。
7. 增加 tab 约束、artifact 切换、复制、下载、关闭、超大内容、恶意脚本/网络/表单和 iframe 属性测试。

### 验证方式

- 运行：`pnpm test:run -- src/components/chat/ChatArtifactPreviewPanel.spec.ts src/components/chat/SafeHtmlPreview.spec.ts`
- 运行：`pnpm type-check`
- 预期：退出 0；Markdown/HTML 双视图、代码单视图和 HTML 安全属性全部通过。

### 完成条件

- 代码 Artifact 可可靠查看源码；Markdown/HTML 具有安全预览；HTML 无脚本、网络、表单、弹窗、导航或父页面权限。

### 执行结果

新增 `ChatArtifactPreviewPanel`：可预览 Artifact 默认进入预览，source-only 类型直接显示源码；双视图使用可访问 tablist，支持点击和左右方向键，Artifact ID 变化时重置到该类型默认视图。标题、语言、源码、复制、下载和关闭均有明确语义，Markdown 预览继续使用 `html: false` 且不会递归生成 Artifact。

新增 `SafeHtmlPreview`：把用户 HTML 包入独立 `srcdoc`，在用户内容之前写入严格 CSP；iframe 使用空 sandbox 和 `no-referrer`，禁止脚本、连接、Worker、子 frame、表单、base、object 和导航，并只允许 data/blob 图片、字体和媒体及内联样式。UTF-8 内容超过 500 KB 时不创建 iframe，提示查看源码或下载。

Task 1 的 Clipboard fallback、MIME 和 Blob 下载已提取到 `chat-artifacts.ts`，代码块与侧栏共用同一实现。新增样式已由 `main.ts` 引入。类型检查自动扫描生成的 `components.d.ts` 条目在验证后被移除，文件精确保持当前分支既有内容，本批组件继续使用显式 import。

测试先行首次运行按预期因两个组件尚不存在而失败；实现后曾出现一项超限提示文案断言和一项测试可空类型问题，均已修正并完成重跑。

### 验证证据

```text
命令：pnpm test:run -- src/components/chat/ChatArtifactPreviewPanel.spec.ts src/components/chat/SafeHtmlPreview.spec.ts src/lib/chat-artifacts.spec.ts src/components/MarkdownContent.spec.ts
退出状态：0
关键结果：4 个测试文件、17 项测试全部通过；覆盖 tab 约束/键盘、Artifact 切换、Markdown 非递归、复制下载关闭、sandbox、CSP 和超限降级
执行时间：2026-07-25 20:09（Asia/Shanghai）

命令：pnpm type-check
退出状态：0
关键结果：vue-tsc -b 通过
执行时间：2026-07-25 20:09（Asia/Shanghai）

命令：git diff --check
退出状态：0
关键结果：无空白错误；仅显示仓库既有 LF/CRLF 转换提示
执行时间：2026-07-25 20:08（Asia/Shanghai）
```

## Task 3：统一 Session 侧栏选择与手工固定规则

状态：completed

### 目标

把 file、tool、artifact、trace 迁移为单一可判别选择状态，并保证手工打开内容不会被自动工具跟随抢占。

### 涉及文件

- `agentic/web/src/lib/chat-preview.ts`（新建，若类型未放入现有模块）
- `agentic/web/src/lib/chat-preview.spec.ts`（新建）
- `agentic/web/src/components/chat/ChatMessage.vue`
- `agentic/web/src/components/chat/ChatMessage.spec.ts`
- `agentic/web/src/components/SessionDetailView.vue`
- `agentic/web/src/components/SessionDetailView.spec.ts`
- `agentic/web/src/components/chat/index.ts`（若继续维护统一导出）

### 依赖与接口

- 前置任务：Task 1–2。
- 输入：ChatMessage 的 `artifactOpen`、文件/工具/Trace 点击和运行时工具事件。
- 输出：单一 `ChatPreviewSelection`、pinned/auto 选择规则和 Artifact Panel 渲染。

### 实施步骤

1. 定义 file/tool/artifact/trace 可判别 selection 和 `source: user/auto`。
2. ChatMessage 只对 Assistant 正文启用 Artifact，并使用 `sourceEventId ?? item.id` 作为 scope；透传 `artifactOpen`。
3. SessionDetail 用 selection 替换 `previewFile`、`previewTool`、`traceOpen` 的互斥组合，保留 resolved tool 按 `tool_call_id` 获取最新状态。
4. 文件、Artifact、Trace 和用户点击工具写入 user selection；新工具自动跟随写入 auto selection。
5. 自动工具只在 selection 为空或当前为 auto tool 时更新；手工选择关闭后恢复自动跟随。
6. Session ID 变化和卸载时清空选择；VNC 打开/关闭保持既有行为且不错误恢复已固定选择。
7. 增加 Artifact 事件、互斥渲染、实时 tool 更新、pinned 防抢占、关闭恢复、Session 切换和 VNC 回归测试。

### 验证方式

- 运行：`pnpm test:run -- src/components/chat/ChatMessage.spec.ts src/components/SessionDetailView.spec.ts`
- 运行：`pnpm type-check`
- 预期：退出 0；四类侧栏互斥、手工固定、自动工具实时更新和 Session 清理通过。

### 完成条件

- Artifact 能从消息打开；任意时刻最多一个侧栏；用户选择不被新工具抢占，原有运行时工具跟随和 VNC 行为无回归。

### 执行结果

新增 `ChatPreviewSelection` 可判别 union，统一描述 file、tool、artifact、trace 及 `user/auto` 来源；`canAutoFollowTool` 明确规定只有空选择或既有 auto-tool 才能被新工具更新，file、手工 tool、artifact 和 trace 均保持固定。

Assistant 正文现在使用事件 ID（缺失时使用 timeline item ID）启用 Markdown Artifact，并把选中结构透传给 SessionDetail。SessionDetail 用单一 selection 替代 `previewFile`、`previewTool`、`traceOpen` 的互斥布尔组合，正式渲染 Artifact 侧栏；文件、工具、Artifact、Trace 点击均写入 user selection。

运行时新工具继续实时更新 auto-tool；用户固定内容不会被抢占。关闭固定面板后，后续新工具恢复自动跟随；工具面板的“跳转实时”显式进入 auto 模式。VNC 关闭只在允许自动跟随时恢复最新工具，Session ID 变化会清空预览、VNC 和工具计数，避免跨会话残留。

测试先行首次运行按预期因消息尚未启用 Artifact、Session 尚未处理事件而失败。实现后修正 shallowMount 的事件触发方式及两处测试可空/字面量类型，最终定向与相邻面板回归通过。类型检查自动生成的全局组件条目已再次移除，`components.d.ts` 无本批差异。

### 验证证据

```text
命令：pnpm test:run -- src/lib/chat-preview.spec.ts src/components/chat/ChatMessage.spec.ts src/components/SessionDetailView.spec.ts src/components/chat/ChatArtifactPreviewPanel.spec.ts
退出状态：0
关键结果：4 个测试文件、24 项测试全部通过；覆盖 Assistant 事件、scope fallback、四类 pinned 规则、Artifact 防抢占、关闭恢复自动工具、Session 清理和面板回归
执行时间：2026-07-25 20:21（Asia/Shanghai）

命令：pnpm type-check
退出状态：0
关键结果：vue-tsc -b 通过
执行时间：2026-07-25 20:21（Asia/Shanghai）

命令：git diff --check
退出状态：0
关键结果：无空白错误；仅显示仓库既有 LF/CRLF 转换提示
执行时间：2026-07-25 20:22（Asia/Shanghai）
```

## Task 4：将生成文件纳入源码/预览/下载体验

状态：completed

### 目标

增强聊天附件 FilePreviewPanel，使 Markdown、HTML、图片、代码/文本和不支持类型按各自有意义的视图展示，并复用同一安全预览边界。

### 涉及文件

- `agentic/web/src/lib/file-preview.ts`（新建）
- `agentic/web/src/lib/file-preview.spec.ts`（新建）
- `agentic/web/src/components/FilePreviewPanel.vue`
- `agentic/web/src/components/FilePreviewPanel.spec.ts`（新建）
- `agentic/web/src/components/chat/SafeHtmlPreview.vue`
- `agentic/web/src/components/MarkdownContent.vue`
- `agentic/web/src/components/chat/AttachmentsMessage.vue`
- `agentic/web/src/components/chat/AttachmentsMessage.spec.ts`（按需新建）
- `agentic/web/src/style.css`
- `agentic/web/src/components/chat/artifact-preview.css`

### 依赖与接口

- 前置任务：Task 2–3。
- 输入：既有 `AttachmentFile`、`fileApi.downloadFile` Blob 和扩展名。
- 输出：受类型约束的 source/preview/download 文件面板。

### 实施步骤

1. 将文件扩展名映射集中为 source-only、preview-only、source-preview、unsupported 四类；未知类型保守降级。
2. FilePreviewPanel 继续通过既有鉴权下载原始 Blob，一次加载后复用内容，不为切换标签重复请求。
3. Markdown 文件提供安全 Markdown 预览；HTML 文件复用 SafeHtmlPreview；图片继续使用 Blob URL；代码和文本只展示源码。
4. 不支持类型保持明确说明和下载；鉴权/网络失败保留错误态与重试。
5. file ID 变化和 unmount 时撤销旧 URL、清空内容和错误；并发响应不能覆盖更新后的文件。
6. 调整头部、标签、内容滚动、长文件名、390px 和暗色样式；附件卡保持现有点击与键盘语义。
7. 增加文件分类、单次请求、切换标签、竞态、URL 清理、失败重试、下载和安全预览测试。

### 验证方式

- 运行：`pnpm test:run -- src/components/FilePreviewPanel.spec.ts src/components/chat/AttachmentsMessage.spec.ts src/components/SessionDetailView.spec.ts`
- 运行：`pnpm type-check`
- 预期：退出 0；类型视图、鉴权下载、竞态清理、错误重试和键盘入口测试通过。

### 完成条件

- Assistant 生成文件与代码 Artifact 具有一致的标题、视图和动作语义，且未改变文件权限或引入额外后端接口。

### 执行结果

新增集中式文件预览描述器，按扩展名将 Markdown、HTML、SVG、栅格图片、代码/文本和未知文件保守映射为双视图、仅预览、仅源码或不支持。缺失扩展名时可从文件名回退推导；SVG 不再作为主页面图片直接加载，而是与 HTML 一样提供源码和空权限 sandbox 预览。

FilePreviewPanel 继续复用既有鉴权下载 API，但会缓存本次加载的 Blob：切换源码/预览以及加载后从头部下载都不会重复请求。Markdown 使用现有 `html: false` 渲染，HTML/SVG 复用 SafeHtmlPreview；普通代码和文本仅显示源码，栅格图片继续使用 Blob URL，未知类型不预取、只提供说明和按需下载。

文件 ID、文件名或扩展名变化时会重置视图、内容、错误、缓存 Blob 和对象 URL，并使用请求版本号丢弃旧响应、旧错误和延迟文本解析；卸载时使在途响应失效并撤销对象 URL。双视图标签支持点击和左右方向键，标题沿用 Artifact 面板的截断与响应式样式；附件卡既有点击、Enter、Space 和“查看全部”分离语义已用回归测试锁定，无需修改生产组件。

测试先行首次运行按预期失败：缺少文件分类模块，旧面板没有标签和安全 SVG 预览，且旧图片请求会覆盖新选择。实现后新增键盘焦点断言时，首次重跑先遇到 Windows 沙箱 `spawn EPERM`，在已批准的测试命令范围外层重跑后又发现测试组件未挂到文档导致焦点断言无效；改为真实 DOM 挂载并卸载后，定向测试及相邻面板回归全部通过。类型检查自动生成的两条全局组件声明已移除，`components.d.ts` 无本批差异。

### 验证证据

```text
命令：pnpm test:run -- src/lib/file-preview.spec.ts src/components/FilePreviewPanel.spec.ts src/components/chat/AttachmentsMessage.spec.ts
退出状态：0
关键结果：3 个测试文件、10 项测试全部通过；覆盖文件分类、Markdown/SVG 安全预览、单次请求与 Blob 复用、键盘标签、源码-only、竞态、URL 清理、未知类型按需下载、错误重试和附件键盘入口
执行时间：2026-07-25 20:36（Asia/Shanghai）

命令：pnpm test:run -- src/lib/file-preview.spec.ts src/components/FilePreviewPanel.spec.ts src/components/chat/AttachmentsMessage.spec.ts src/components/SessionDetailView.spec.ts src/components/chat/SafeHtmlPreview.spec.ts src/components/MarkdownContent.spec.ts src/components/chat/ChatArtifactPreviewPanel.spec.ts
退出状态：0
关键结果：7 个测试文件、34 项测试全部通过；文件预览与 Session 选择、HTML 沙箱、Markdown 和 Artifact 面板相邻回归通过
执行时间：2026-07-25 20:34（Asia/Shanghai）

命令：pnpm type-check
退出状态：0
关键结果：vue-tsc -b 通过；移除自动扫描条目后 components.d.ts 无本批差异
执行时间：2026-07-25 20:35（Asia/Shanghai）

命令：git diff --check
退出状态：0
关键结果：无空白错误；仅显示仓库既有 LF/CRLF 转换提示
执行时间：2026-07-25 20:35（Asia/Shanghai）
```

## Task 5：完成全量回归、安全验收和代码审查

状态：completed

### 目标

以最新证据确认 Artifact、文件预览和统一选择不会破坏聊天、工具实时预览、Trace、输入、分支、审批和 HITL，并完成安全与页面门禁。

### 涉及文件

- 本计划涉及的全部代码和测试
- `agentic/docs/librechat-ui-redesign.zh-CN.md`
- `agentic/docs/reviews/chat-artifact-preview-review.md`（新建）
- `agentic/docs/plans/chat-artifact-preview-plan.md`

### 依赖与接口

- 前置任务：Task 1–4。
- 输入：完整变更集和设计验收标准。
- 输出：最新验证证据、分级审查和 `READY_TO_MERGE / BLOCKED / FAILED`。

### 实施步骤

1. 运行新增 Artifact、Markdown、FilePreview、ChatMessage 和 SessionDetail 定向测试。
2. 运行前端全量测试、类型检查和生产构建。
3. 确认本批没有后端、数据库迁移、lockfile 或大型运行依赖变更。
4. 运行 `git diff --check`，审阅完整 diff，并确认没有覆盖本批开始前的 `components.d.ts` 用户修改。
5. 使用恶意 HTML 手工检查脚本、网络、表单、弹窗、顶层导航和父页面读取均被阻止。
6. 手工验证普通/多代码块、Markdown/HTML/图片/代码/未知文件、复制、下载、手工固定、自动工具恢复、Session 切换。
7. 验收桌面、平板、390px、暗色和键盘焦点；确认浏览器内操作不出现工具批准请求。
8. 按 blocking/major/minor/suggestion 代码审查；整改后重跑受影响验证。
9. 将实际证据、限制和最终状态写回计划、审查及 LibreChat 学习文档。

### 验证方式

- 定向：`pnpm test:run -- src/lib/chat-artifacts.spec.ts src/components/MarkdownContent.spec.ts src/components/chat/ChatArtifactPreviewPanel.spec.ts src/components/chat/SafeHtmlPreview.spec.ts src/components/FilePreviewPanel.spec.ts src/components/chat/ChatMessage.spec.ts src/components/SessionDetailView.spec.ts`
- 全量：`pnpm test:run`
- 类型：`pnpm type-check`
- 构建：`pnpm build`
- 静态：`git diff --check`
- 变更边界：`git status --short`、`git diff --stat`、`git diff -- agentic/api agentic/web/package.json agentic/web/pnpm-lock.yaml`
- 手工：安全 HTML、Markdown、文件分类、pinned/auto、桌面/平板/390px、暗色、键盘和无批准弹窗。

### 完成条件

- 自动化、类型、构建、静态、安全和页面验收通过；无意外后端/迁移/依赖变化；审查无未处理 blocking/major；全部设计验收项有证据。

### 执行结果

完成 Artifact、Markdown、文件预览、ChatMessage 和 SessionDetail 定向回归，并运行前端全量测试、类型检查和生产构建。变更边界确认没有后端、数据库迁移、`package.json`、lockfile 或新运行依赖变化；构建工具自动生成的 Artifact 组件声明已再次移除，`components.d.ts` 保持 Task 1 开始前已有的 `ChatEditBranchDialog` 用户条目，没有新增本批自动扫描差异。

代码审查首次进行真实 Chrome 安全验收时发现一项 `major`：空 sandbox 能阻止脚本和顶层越权，但普通链接点击仍可让 iframe 自身请求外部地址，远程资源 URL 也可能进入请求管线，不能只依赖浏览器对 `navigate-to` 和资源 CSP 的支持。新增失败回归测试后，SafeHtmlPreview 改为在生成 `srcdoc` 前使用惰性 `<template>` 解析，移除 refresh、导航、表单、嵌套文档和外部资源 URL；`src/poster` 仅保留 `data:`/`blob:`。空 sandbox 和严格 CSP 继续作为后续防线。

整改后本机 Chrome 实测恶意脚本未执行、父页面未被修改，远程图片、子 frame、表单、refresh、弹窗和点击链接产生的外部请求总数为 0。桌面 1440px 下侧栏宽 576px，390×844 下侧栏准确铺满视口且无横向溢出；暗色背景/文字可读，左右方向键能切换标签并移动焦点。内置浏览器插件因版本路径引用失效无法连接，页面验收按技能降级流程使用本机 Chrome + Playwright 完成。

最终代码审查结论为 `APPROVED`，未发现未处理的 blocking、major、minor 或 suggestion。审查记录已保存到 `agentic/docs/reviews/chat-artifact-preview-review.md`，LibreChat 学习文档已将只读 Artifact 与生成文件统一预览标记为已落地。剩余限制是本次为同一 Agent 自检，且没有重新生成一条登录态真实 SSE Agent 回复；相关消息、工具、Trace、输入、分支、审批和 HITL 由全量自动化与实际组件浏览器验收覆盖。

### 验证证据

```text
命令：pnpm test:run -- src/lib/chat-artifacts.spec.ts src/components/MarkdownContent.spec.ts src/components/chat/ChatArtifactPreviewPanel.spec.ts src/components/chat/SafeHtmlPreview.spec.ts src/lib/file-preview.spec.ts src/components/FilePreviewPanel.spec.ts src/components/chat/AttachmentsMessage.spec.ts src/lib/chat-preview.spec.ts src/components/chat/ChatMessage.spec.ts src/components/SessionDetailView.spec.ts
退出状态：0
关键结果：10 个测试文件、46 项定向测试全部通过
执行时间：2026-07-25 20:49（Asia/Shanghai）

命令：pnpm test:run
退出状态：0
关键结果：安全整改后 33 个测试文件、119 项前端全量测试全部通过
执行时间：2026-07-25 22:11（Asia/Shanghai）

命令：pnpm type-check
退出状态：0
关键结果：vue-tsc -b 通过
执行时间：2026-07-25 22:12（Asia/Shanghai）

命令：pnpm build
退出状态：0
关键结果：vue-tsc -b 与 Vite 生产构建通过，3665 个模块完成转换
执行时间：2026-07-25 22:12（Asia/Shanghai）

命令：本机 Chrome + Playwright 实际组件验收
退出状态：0
关键结果：sandbox/CSP/内容净化生效，恶意外部请求 0；1440px、390px、暗色和键盘焦点通过
执行时间：2026-07-25 22:10（Asia/Shanghai）

命令：git diff --check；git diff master -- agentic/api agentic/web/package.json agentic/web/pnpm-lock.yaml；git diff --exit-code HEAD -- agentic/web/src/components.d.ts
退出状态：0
关键结果：无空白错误、后端/依赖边界无差异、components.d.ts 无 Task 5 工作区差异；仅有仓库既有 LF/CRLF 提示
执行时间：2026-07-25 22:15（Asia/Shanghai）
```

## 计划变更

| 日期 | 变更内容 | 原因 | 影响任务 | 是否影响设计 |
| --- | --- | --- | --- | --- |
| 2026-07-25 | 初始计划 | 将只读 Artifact、面板、统一选择、生成文件和最终门禁拆为五个可独立验收任务 | Task 1–5 | 否 |
| 2026-07-25 | Task 1 补充 `markdown-it` 局部类型声明 | 现有声明只有 `render(src)`，无法表达本任务使用的 fence renderer、utils 和 render env；补充运行库现有 API，不新增依赖 | Task 1 | 否 |
| 2026-07-25 | Task 2 复用浏览器复制/下载函数 | Artifact 面板与 Markdown 代码块必须共享同一 Clipboard fallback、MIME 和 Blob 下载规则，避免两套行为漂移 | Task 2 | 否 |

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
git diff --stat
git diff -- agentic/api agentic/web/package.json agentic/web/pnpm-lock.yaml
```

### 执行结果

- 单元测试：通过；33 个测试文件、119 项测试。
- 集成测试：通过；ChatMessage、SessionDetail、文件/工具/Artifact/Trace 选择、自动跟随、分支、审批和 HITL 均包含在全量套件中。
- 静态检查：通过；`git diff --check` 无空白错误，仅有仓库既有 LF/CRLF 提示。
- 类型检查：通过；`vue-tsc -b` 退出 0。
- 构建：通过；Vite 生产构建完成 3665 个模块。
- 数据库迁移：不适用；无后端、数据库或迁移变化。
- 手工验证：通过；真实 Chrome 组件验收覆盖恶意 HTML、无外部请求、桌面、390px、暗色和键盘。
- 代码审查：`APPROVED`；审查发现的一项 iframe 自身导航 major 已整改并重新验证，无未处理 blocking/major。

### 验收标准检查

- [x] Assistant fenced code 的语言、复制、下载和侧栏入口正确。
- [x] 多代码块、特殊字符、未闭合 fence 和流式重渲染正确。
- [x] Markdown/HTML 双视图和其他代码 source-only 正确。
- [x] HTML 脚本、网络、表单、弹窗、导航和父页面访问被阻止。
- [x] Markdown 不执行 HTML、不递归生成 Artifact。
- [x] 浏览器内复制/下载不产生 API、shell 或批准请求。
- [x] 生成文件按 Markdown/HTML/图片/代码/未知类型正确展示。
- [x] 文件鉴权、失败重试、竞态和 Blob URL 清理正确。
- [x] file/tool/artifact/trace 互斥，手工 pinned 与自动工具恢复正确。
- [x] Session 切换和 VNC 无状态残留或回归。
- [x] 桌面、平板、390px、暗色和键盘焦点通过。
- [x] 现有聊天、工具、Trace、输入、分支、审批和 HITL 回归通过。
- [x] 无意外后端、迁移、依赖或用户工作区文件变化。
- [x] 自动化、类型、构建、静态、审查和页面验收有最新证据。

### 未通过项目

无未通过项目。

限制：内置浏览器插件连接不可用，已使用本机 Chrome 替代；未重新生成登录态真实 SSE Agent 回复。同一 Agent 完成实现与自审，独立安全复核仍更可靠。

### 最终状态

`READY_TO_MERGE`。自动化、类型、生产构建、静态、安全浏览器和代码审查门禁均通过，等待用户明确提交、推送或合并。
