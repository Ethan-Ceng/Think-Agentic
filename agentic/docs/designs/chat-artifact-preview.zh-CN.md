# Markdown 代码块与生成产物统一预览设计

## 文档状态

- 状态：`DESIGN_READY`
- 负责人：Codex
- 创建日期：2026-07-25
- 最近更新：2026-07-25

## 背景

前几批 LibreChat 学习已经完成会话运行可靠性、工具审批、HITL、消息编辑、重新生成、分支和版本导航。下一批仍有明显学习价值、又不要求先建设 Project、Prompt、Agent 或 Memory 数据模型的能力，是 LibreChat 的 Artifact 交互：

- Assistant 回复中的产物不是一大段普通代码，而是一个可识别、可再次打开的入口；
- 右侧面板在“源码”和“预览”之间切换，并集中提供复制、下载和关闭；
- 桌面端使用侧栏，窄屏使用覆盖层；
- 不同产物类型只展示有意义的标签，例如 Office 文件只预览、纯代码只看源码；
- 当前产物选择在会话变化时重置，多个产物之间有清晰、稳定的选择状态。

LibreChat 的相关实现集中在：

- `LibreChat/client/src/components/Artifacts/Artifact.tsx`
- `LibreChat/client/src/components/Artifacts/ArtifactButton.tsx`
- `LibreChat/client/src/components/Artifacts/Artifacts.tsx`
- `LibreChat/client/src/components/Artifacts/ArtifactTabs.tsx`
- `LibreChat/client/src/components/Artifacts/ArtifactPreview.tsx`
- `LibreChat/client/src/components/Artifacts/DownloadArtifact.tsx`
- `LibreChat/client/src/components/SidePanel/ArtifactsPanel.tsx`
- `LibreChat/client/src/hooks/Artifacts/useArtifacts.ts`
- `LibreChat/client/src/hooks/Artifacts/useArtifactProps.ts`
- `LibreChat/client/src/store/artifacts.ts`
- `LibreChat/client/src/utils/artifacts.ts`
- `LibreChat/api/app/clients/prompts/artifacts.js`

`LibreChat/AGENTS.md` 指向的 `CLAUDE.md` 在本地副本中不存在；本设计仅依据可读取的源码与测试，不假设缺失说明中的额外约束。

当前系统已经有三个可复用基础：

1. `MarkdownContent.vue` 能安全关闭原始 HTML，并展示 fenced code；
2. Assistant 附件可以打开 `FilePreviewPanel.vue`，支持文本、图片和下载；
3. 工具和 Trace 已使用同一 Session 详情右侧区域。

但当前代码块只有静态 `<pre>`，没有语言标题、复制、下载或侧栏入口；文件预览没有源码/渲染视图；文件、工具、Trace 和未来产物分别维护互斥状态，手工打开的内容还可能被新工具自动覆盖。继续直接增加第四套面板状态，会扩大 SessionDetail 的交互分叉。

## 目标

- 将 Assistant 回复中的 fenced code block 提升为带语言、复制、下载和“在侧栏打开”的产物块。
- 为代码块产物提供统一侧栏：源码视图始终可用，Markdown 和 HTML 额外支持安全预览。
- 将 Assistant 生成文件纳入一致的源码/预览/下载交互，而不是另建后端 Artifact。
- 手工打开的文件或代码产物保持选中，不被后续自动工具预览抢走；用户关闭后才恢复自动跟随。
- 桌面、平板、390px 移动端和暗色模式都能访问全部操作。
- 全部复制、临时预览和代码块下载在浏览器内完成，不调用 shell、不写沙箱文件，也不触发工具批准。

## 功能范围

- 仅处理 Assistant 正文中已经闭合且内容非空的 fenced code block。
- 每个代码块展示：
  - 语言或“纯文本”标签；
  - 复制；
  - 下载；
  - 在右侧面板打开。
- 代码块侧栏展示：
  - 标题和语言；
  - “源码”标签；
  - 对 Markdown、HTML 展示“预览”标签；
  - 复制、下载、关闭。
- Markdown 预览继续使用 `markdown-it` 且 `html: false`。
- HTML 预览使用无权限 iframe：
  - `sandbox=""`，不授予脚本、同源、表单、弹窗或下载能力；
  - 注入严格 CSP，禁止网络请求和外部资源；
  - 只允许内联样式以及 `data:` / `blob:` 图片。
- Assistant 附件预览按类型约束标签：
  - Markdown、HTML：源码 + 预览；
  - 普通文本和代码：仅源码；
  - 图片：仅预览；
  - 不支持类型：说明 + 下载。
- 使用单一预览选择状态协调 file、tool、artifact、trace；VNC 继续保持独立全屏覆盖层。
- 手工选择为 pinned；自动工具跟随只能更新未固定或原本为自动工具的预览。
- Session 切换时清空预览选择、临时内容和对象 URL。
- 补充组件、集成、键盘、窄屏和安全边界测试。

## 非功能范围

- 不注入 LibreChat 的 `:::artifact` 系统提示，不要求模型改变输出协议。
- 不新增 Artifact 数据库表、API、事件或会话持久化。
- 不在后端保存代码块下载出来的临时文件。
- 不提供代码块编辑、保存、版本历史或重新运行。
- 不执行 JavaScript、TypeScript、React、Vue、Python、Mermaid 或任意用户代码。
- 不加载 npm 包、CDN、远程图片、远程字体或第三方 iframe。
- 不支持 Office/PDF 转 HTML、在线协作、分享或发布。
- 不自动把所有长回答或表格识别成产物。
- 不重构文件管理页；仅增强聊天 Session 中的附件预览。
- 不改变现有文件下载权限、工具审批、Agent Run、Trace、Memory 或分支语义。

## 业务流程

### 从 Assistant 代码块打开产物

1. Assistant 回复包含一个已闭合 fenced code block。
2. Markdown 渲染器为该块生成语言标题和复制、下载、打开按钮；正文仍直接可读。
3. 用户点击复制时，浏览器复制原始代码文本并给出成功/失败反馈。
4. 用户点击下载时，浏览器根据语言生成安全文件名和 MIME，使用 Blob 下载，不请求后端。
5. 用户点击打开时，ChatMessage 上报一个只读 `InlineChatArtifact`。
6. SessionDetail 将预览选择切换为 pinned artifact，关闭 file、tool、trace 的当前展示。
7. 侧栏默认展示源码；Markdown/HTML 可切到预览。
8. 用户关闭侧栏，清空当前选择；之后新工具事件可以重新自动跟随。

### 预览 Markdown

1. 用户打开语言为 `markdown` 或 `md` 的代码块。
2. 面板展示源码和预览两个标签。
3. 预览使用现有 Markdown 安全配置，原始 HTML 不执行。
4. 预览内的 fenced code 只作为内容展示，不再次生成可打开 Artifact，避免递归入口。

### 预览 HTML

1. 用户打开语言为 `html` 或 `htm` 的代码块或附件。
2. 面板先构建带最前置 CSP 的 `srcdoc`。
3. iframe 不获得任何 sandbox token，脚本、表单、弹窗、顶层导航、同源读取和下载均不可用。
4. 远程脚本、样式、图片、字体和网络连接被 CSP 拒绝。
5. 用户仍可切回源码、复制或下载原始内容。

### 打开生成文件

1. 用户点击 Assistant 附件卡片。
2. SessionDetail 选择 pinned file。
3. FilePreviewPanel 下载现有授权文件 Blob，并按扩展名确定可用标签。
4. Markdown/HTML 可切换源码与安全预览；图片只显示预览；代码和文本只显示源码。
5. 下载继续调用既有鉴权接口，不改变文件权限和存储方式。

### 新工具事件到达

1. 没有 pinned 选择，或者当前展示本来就是自动工具时，新工具继续自动打开并实时更新。
2. 用户手工打开了文件、代码产物、Trace 或某个工具时，新工具事件不抢走当前面板。
3. 用户关闭 pinned 面板后，后续新工具事件恢复自动跟随。

## 核心规则

1. Inline Artifact 是 Assistant 消息的只读派生视图，不是新的业务实体。
2. Artifact ID 使用 `session/message scope + fence index`，同一已完成消息重复渲染时保持稳定。
3. 只为已闭合、非空 fenced code block 创建操作栏；流式过程中未闭合的 fence 不出现半成品入口。
4. 原始代码必须通过内存映射参与复制、下载和打开，不能从已高亮或转义后的 DOM 反解析。
5. 文件名只能包含安全基础名和白名单扩展，移除路径分隔符、控制字符及保留名称；重复块使用序号区分。
6. `html/htm` 和 `markdown/md` 支持预览；其他语言第一版均为 source-only。
7. HTML 永远不在主页面 `v-html` 执行，且 iframe 不授予任何 sandbox token。
8. Markdown 预览保持 `html: false` 并沿用 markdown-it 的 URL 校验，不允许 `javascript:` URL；若实现新增新窗口打开，则必须同时设置 `noopener noreferrer`。
9. 预览失败只影响当前面板，不替换聊天正文，也不阻断输入和 Session 运行。
10. 同一时刻最多展示一个 file/tool/artifact/trace 侧栏；VNC 可单独覆盖。
11. 用户点击产生 pinned 选择；自动工具事件不能覆盖 pinned 选择。
12. Session 变化、组件卸载或文件变化时必须撤销 Blob URL，避免内存泄漏和跨 Session 残留。
13. 浏览器内复制和 Blob 下载不属于高风险工具，不触发 shell 或文件写入批准。

## 现有实现分析

### 相关代码与文档

- `agentic/web/src/components/MarkdownContent.vue`：当前使用 `markdown-it`、`html: false`、`linkify: true`、`breaks: true`，但通过单个 `v-html` 输出，尚无代码块事件桥接。
- `agentic/web/src/components/chat/ChatMessage.vue`：Assistant 正文的消息级入口，可向 SessionDetail 上报 Artifact。
- `agentic/web/src/components/SessionDetailView.vue`：维护 `previewFile`、`previewTool`、`traceOpen` 和自动工具跟随，适合统一为可判别选择状态。
- `agentic/web/src/components/FilePreviewPanel.vue`：已有文件鉴权下载、文本/图片识别、Blob URL 清理、失败重试和下载。
- `agentic/web/src/components/chat/ToolPreviewPanel.vue`：已有右侧面板标题、复制、关闭和窄屏展示模式。
- `agentic/web/src/lib/session-events.ts`：已有 `AttachmentFile` 投影，但没有 Inline Artifact 类型。
- `agentic/web/src/lib/api/file.ts`：已有鉴权下载和预览接口；本批可继续使用 `downloadFile` 获取原始 Blob。
- `agentic/web/src/style.css`：桌面侧栏宽度为 `clamp(420px, 40vw, 640px)`，900px 以下已切换为全屏或底部覆盖层。
- `agentic/web/src/components/chat/chat.css`：已有 Assistant Markdown、移动端消息和操作按钮样式。
- `agentic/docs/librechat-ui-redesign.zh-CN.md`：已把 Artifact/产品预览列为中高适用但尚未落地的学习项。

### 可复用能力

- Markdown 原始 HTML 已关闭，可继续作为 Markdown 预览的安全基线。
- 既有文件下载 API 已处理用户鉴权，无需新增后端接口。
- `downloadBlob`、`useToast`、`UiIconButton`、`UiState` 可复用于复制、下载和错误反馈。
- 现有 side-preview 响应式布局可直接承载 Artifact Panel。
- ToolPreviewPanel 的标题和动作布局可作为统一视觉参考。
- SessionDetail 已确保 file、tool、trace 互斥，迁移为 union state 后可以减少布尔组合。

### 当前约束

- `MarkdownContent` 使用 `v-html`，Vue 不能直接绑定渲染字符串内按钮事件；需要事件委托或安全的 token-to-component 渲染。
- 当前项目没有 Monaco、Sandpack、DOMPurify、Mermaid 等依赖；第一版不应为只读体验引入大型运行时。
- 文件类型只有扩展名、大小和 ID，没有可信 MIME；类型判断必须保守。
- HTML 附件可能很大，生成 `srcdoc` 需设大小上限和明确降级。
- 现有自动工具预览会无条件覆盖 file 选择；统一状态时必须补回原有“运行时自动跟随”而不造成回归。
- `agentic/web/src/components.d.ts` 当前存在用户未提交修改，本批实施时必须保留并避免把无关生成差异混入变更。

## 可选方案

### 方案 A：只美化代码块

- 实现方式：为 fenced code 增加语言标题和复制，不增加侧栏或文件预览。
- 优点：改动小、无安全运行面、交付快。
- 缺点：不能学习 LibreChat 的核心 Artifact 选择、源码/预览、下载和响应式面板。
- 风险：形成另一套代码块工具栏，但文件与工具预览仍割裂，后续还要二次改造。

### 方案 B：只读 Inline Artifact + 统一预览

- 实现方式：从既有 Assistant Markdown 和附件派生只读产物；增加源码/安全预览；统一侧栏选择和 pinned/auto 规则。
- 优点：复用当前数据和文件 API；无后端、迁移或模型提示变化；能覆盖 Artifact 最有价值的交互。
- 缺点：代码块不持久化为独立实体，无法编辑、版本化或在其他会话复用。
- 风险：HTML 预览、事件委托、对象 URL 清理和自动跟随互斥需要严格测试。

### 方案 C：完整复制 LibreChat Artifact 协议

- 实现方式：注入 `:::artifact` 系统提示，引入 Artifact 状态、版本、编辑器、Sandpack/运行沙箱、Office/Mermaid/React 类型和持久化。
- 优点：最接近 LibreChat，支持模型持续更新同一产物和交互式应用预览。
- 缺点：新增输出协议、依赖、执行面和数据模型，且会与当前“文件是 Agent 输出”的模型重叠。
- 风险：任意代码执行、提示污染、流式解析、历史兼容、跨会话权限和版本一致性风险高。

## 方案对比

| 维度 | 方案 A：代码块美化 | 方案 B：只读统一预览 | 方案 C：完整 Artifact 协议 |
| --- | --- | --- | --- |
| 实现复杂度 | 低 | 中 | 高 |
| 用户可见价值 | 中低 | 高 | 高 |
| 后端/迁移 | 无 | 无 | 大 |
| 新运行依赖 | 无 | 无 | 多 |
| 安全风险 | 低 | 中，可封闭 | 高 |
| 与现有文件模型兼容 | 一般 | 高 | 低 |
| 测试难度 | 低 | 中 | 很高 |
| 后续扩展空间 | 低 | 高 | 高 |

## 推荐方案

选择方案 B：只读 Inline Artifact + 统一预览。

它学习 LibreChat 的“产物入口、源码/预览、复制、下载、侧栏选择、移动端覆盖”这些高价值交互，同时保持 Agentic 当前的安全和审计边界。Inline Artifact 只是已存在消息的派生视图，生成文件仍使用既有文件权限；浏览器内操作不会引入额外工具批准。

不选择方案 A，是因为它无法解决预览割裂和 Artifact 可发现性；不选择方案 C，是因为完整协议会同时引入模型提示、任意代码执行、版本持久化和大型依赖，风险与当前需求不成比例。方案 B 还能作为未来完整 Artifact 的 UI 基础，但不会预先承诺其数据模型。

## 数据结构

无数据库结构变化。

### `InlineChatArtifact`

| 字段 | 类型 | 必填 | 说明 | 约束/默认值 |
| --- | --- | --- | --- | --- |
| `id` | `string` | 是 | 当前 Session 内稳定选择 ID | `{scope}:fence:{index}` |
| `scope` | `string` | 是 | 消息事件或时间线作用域 | 优先使用 `sourceEventId` |
| `index` | `number` | 是 | 消息内 fenced block 序号 | 从 0 开始 |
| `title` | `string` | 是 | 面板标题和下载文件名 | 安全基础名 + 扩展 |
| `language` | `string` | 是 | 规范化语言 | 未声明时为 `text` |
| `content` | `string` | 是 | 未转义原始内容 | 空内容不生成 Artifact |
| `kind` | `code/markdown/html` | 是 | 安全视图类型 | 仅 markdown/html 有 preview |
| `availableViews` | `Array<'source' \| 'preview'>` | 是 | 可用标签 | 至少含 source |

### `ChatPreviewSelection`

| 字段 | 类型 | 必填 | 说明 | 约束/默认值 |
| --- | --- | --- | --- | --- |
| `kind` | `file/tool/artifact/trace` | 是 | 当前侧栏类型 | 可判别 union |
| `source` | `user/auto` | 是 | 选择来源 | user 选择为 pinned |
| `payload` | 按 kind 区分 | 是 | 文件、工具、Artifact 或 Trace 参数 | 不持久化 |

`trace` 只需要 Session ID，不复制 Trace 数据；file/tool/artifact 分别持有现有 `AttachmentFile`、`ToolEvent` 和 `InlineChatArtifact`。

## 接口设计

### `MarkdownContent` 组件

- 新增输入：
  - `artifactScope?: string`：生成稳定 block ID。
  - `enableArtifacts?: boolean`：默认 `false`，仅 Assistant 正文启用。
- 新增输出事件：
  - `artifactOpen(artifact: InlineChatArtifact)`。
- 内部动作：
  - 根节点事件委托识别 `data-artifact-action` 和 `data-artifact-id`；
  - 复制、下载直接消费当前 render 建立的原始内容映射；
  - 打开动作发出只读结构。
- 兼容性：未传新 props 的现有错误提示和其他 Markdown 输出保持当前 HTML。

### `ChatArtifactPreviewPanel` 组件

- 输入：
  - `artifact: InlineChatArtifact`。
- 输出：
  - `close()`。
- 行为：
  - 初始标签为 `preview`（若可用），否则 `source`；
  - artifact ID 改变时重置为该类型的默认标签；
  - 复制和下载成功/失败给出 toast；
  - HTML 使用 `SafeHtmlPreview`，Markdown 使用非交互 `MarkdownContent`。

### `SafeHtmlPreview` 组件

- 输入：
  - `content: string`。
  - `title: string`。
- 输出：无。
- 行为：
  - 在组件内构建 CSP-first `srcdoc`；
  - iframe 使用空 sandbox；
  - 超过设定上限时不渲染，显示“内容过大，请查看源码或下载”；
  - 不创建网络请求，不暴露父页面引用。

### `ChatMessage` 事件

- 新增 `artifactOpen(artifact)`，只从非空 Assistant 正文透传。
- 错误卡片和用户消息不启用 Artifact 动作。

### SessionDetail 预览选择

- `openArtifact(artifact)`、`openFile(file)`、`openTool(tool, source)`、`openTrace()` 写入单一 selection。
- 用户事件统一设置 `source: 'user'`。
- 自动工具事件只有在 selection 为空或 `kind === 'tool' && source === 'auto'` 时更新。
- `closePreview()` 清空 selection。
- Session ID 改变时清空 selection，避免跨会话展示旧内容。

### 后端接口

无新增或变更。文件预览和下载继续使用现有 `/files/{file_id}/download` 权限链路。

## 错误处理与可观测性

- Clipboard API 不可用时使用现有 textarea fallback；仍失败则 toast“复制失败”。
- Blob 下载失败或浏览器阻止时提示，不写后端、不重试 shell。
- 文件鉴权或网络失败沿用 FilePreviewPanel 的错误态和重试。
- HTML 内容过大、构建失败或浏览器不支持 `srcdoc` 时降级到源码，不执行内容。
- 无法识别语言时归类为 `text`，保留源码、复制和下载，不猜测可执行预览。
- 前端不记录产物正文；如增加埋点，只记录 kind、language、action 和成功/失败。
- 建议指标：
  - `chat_artifact_opened_total`
  - `chat_artifact_copied_total`
  - `chat_artifact_downloaded_total`
  - `chat_artifact_preview_failed_total`

## 迁移与回滚

- 迁移：无数据库、历史消息或文件迁移。
- 历史数据：已有 Assistant fenced code 和附件在新前端加载后自动获得新交互。
- 回滚：
  - 移除代码块操作栏和 Artifact Panel；
  - 恢复 SessionDetail 的 `previewFile`、`previewTool`、`traceOpen` 独立状态；
  - FilePreviewPanel 恢复当前文本/图片单视图；
  - 不需要清理服务端数据。

## 风险

| 风险 | 可能性 | 影响 | 缓解措施 | 验证方式 |
| --- | --- | --- | --- | --- |
| HTML 借预览执行脚本或联网 | 中 | 高 | 空 sandbox + CSP-first + 禁止远程资源，不在主 DOM 执行 | 恶意 HTML 组件测试和浏览器手测 |
| 事件委托取错代码块内容 | 中 | 中 | 原始内容按稳定 ID 存内存 Map，不从 DOM 反解析 | 多块、重复语言、特殊字符测试 |
| 代码块文件名造成路径或保留名问题 | 中 | 中 | 基础名和扩展白名单、移除分隔符/控制字符 | 文件名单元测试 |
| 流式增量导致 ID 抖动 | 中 | 中 | 只处理已闭合 fence；ID 基于消息 scope + index | 增量内容重渲染测试 |
| 手工预览仍被工具自动覆盖 | 中 | 中 | user/auto 来源显式建模 | SessionDetail 集成测试 |
| 统一 selection 迁移破坏工具实时更新 | 中 | 高 | 保留 auto-tool 更新分支和 resolved tool lookup | 运行中工具更新回归 |
| Blob URL 未释放 | 中 | 中 | props 变化和 unmount 均 revoke | URL create/revoke 测试 |
| 超大代码/HTML 卡顿 | 中 | 中 | 预览大小上限，源码使用滚动容器 | 大内容边界测试 |
| 移动端动作拥挤 | 中 | 中 | 工具栏可换行，面板复用全屏/底部样式 | 390px 手工验收 |
| 用户工作区无关改动被覆盖 | 低 | 中 | 实施前后单独核对 `components.d.ts`，只暂存本批文件 | git status/diff 检查 |

## 重要假设

- 下一批优先继续学习 LibreChat 的 Chat/Artifact 交互，而不是启动 Project、Prompt、Agent 市场或长期 Memory 的新数据模型。
- 当前用户更重视减少批准打断；本批浏览器内预览、复制和下载不应调用任何高风险工具。
- 第一版“预览”是安全只读渲染，不等于运行用户应用。
- fenced code 是可靠且向后兼容的发现来源；无需要求模型立即学习专用 Artifact 指令。
- Assistant 附件继续是生成文件的权威对象；Inline Artifact 不和文件库重复存储。
- 当前分支为 `master`；实施复杂功能前需要创建普通分支 `feature/chat-artifact-preview`。
- 用户本轮要求“准备下一批任务”，授权创建设计和计划，不授权自动提交、推送、合并或开始业务实现。

## 待决策项

无。推荐方案安全边界明确，可以进入实施计划。

## 验收标准

- [ ] Assistant 的已闭合 fenced code 显示语言、复制、下载和侧栏打开操作，普通段落和未闭合 fence 不受影响。
- [ ] 多个代码块的 ID、原始内容、复制和下载不会串块，特殊字符保持原样。
- [ ] Markdown/HTML 代码块侧栏可切换源码和预览，其他语言只显示源码。
- [ ] HTML 预览不能执行脚本、联网、提交表单、弹窗、顶层导航或读取父页面。
- [ ] Markdown 预览不执行原始 HTML，也不递归生成新的 Artifact 操作。
- [ ] 代码块复制和下载完全在浏览器内完成，不产生 API、shell 或批准请求。
- [ ] Assistant 的 Markdown/HTML 附件具有源码/预览，图片仅预览，代码/文本仅源码，不支持类型可下载。
- [ ] 文件下载继续遵守现有鉴权和错误处理，不暴露未经授权文件。
- [ ] 手工打开 file/tool/artifact/trace 后，新工具事件不会抢占；关闭后自动工具跟随恢复。
- [ ] Session 切换清空预览，Blob URL 被撤销，不显示上一 Session 内容。
- [ ] 桌面、平板、390px 移动端和暗色模式下标题、标签、操作和内容不溢出。
- [ ] 键盘可以聚焦和触发代码块操作、标签、下载和关闭，焦点样式可见。
- [ ] 现有聊天、工具实时预览、文件、Trace、输入、分支、审批和 HITL 回归通过。
- [ ] 自动化、类型检查、生产构建、静态检查、代码审查和页面验收均有最新证据。
