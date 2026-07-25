# 聊天附件交互增强

## 文档状态

- 状态：`DESIGN_READY`
- 负责人：Codex
- 创建日期：2026-07-25
- 最近更新：2026-07-25

## 背景

Agentic 的 Composer 已支持本地文件选择、剪贴板粘贴、上传状态、失败重试、移除附件和发送后的消息附件展示，但仍有三个明显断点：

- 用户必须精确点击回形针，不能把桌面文件直接拖入 Composer；
- 已经存在于“文件”中心的用户上传或 Agent 生成文件，不能直接复用，只能重复下载再上传；
- Composer 中所有附件都使用通用文件图标，图片缺少快速识别能力。

LibreChat 在 `DragDropWrapper`、`DragDropOverlay`、`AttachFileMenu`、`MyFilesModal` 和 `ImagePreview` 中提供了可借鉴的交互。Agentic 已有独立的文件目录、来源、鉴权、预览和软删除模型，因此只学习拖拽投放、来源菜单、已有文件选择和图片缩略图，不复制 LibreChat 的 Provider、SharePoint、Vector Store 或 Endpoint 文件能力。

## 目标

- 桌面用户可以把一个或多个操作系统文件拖到 Composer，看到明确投放状态并沿用现有上传流程。
- 回形针入口升级为菜单，支持“上传本地文件”和“从我的文件选择”。
- “从我的文件选择”支持目录导航、当前目录搜索、来源/类型筛选、分页、多选和已选状态。
- 已有文件被选择后直接复用其 ID，不重新上传或复制存储对象。
- 新上传和已有图片在 Composer 中显示安全缩略图；预览失败时退化为普通文件卡。
- 首页新建任务、已有 Session、运行中下一条消息均保持相同附件行为。
- 不新增数据库、后端接口、依赖、shell、沙箱写入或工具批准。

## 功能范围

- Composer 区域的文件拖拽检测、覆盖提示和投放。
- 回形针附件菜单：
  - 上传本地文件；
  - 从我的文件选择。
- 新建 `ChatFilePickerDialog`：
  - 目录面包屑；
  - 当前目录搜索；
  - 文件类型与来源筛选；
  - 分页；
  - 文件多选；
  - 保持跨分页/目录的已选文件；
  - 加载、空、失败、重试状态。
- 统一 Composer 附件视图模型，区分本地上传项和已存在文件。
- 图片缩略图 Blob URL 生命周期管理。
- 重复已有文件去重、Session 切换清理、发送成功清理和失败保留。
- 桌面、390px、暗色、键盘和屏幕阅读器状态。

## 非功能范围

- 不新增或改变文件上传、预览、下载、列表和发送 API。
- 不实现 SharePoint、Google Drive、OneDrive、外部 URL 或第三方云盘选择器。
- 不实现 Knowledge/Vector Store、OCR、文件搜索工具或代码执行资源绑定。
- 不新增文件大小、类型、数量业务限制；继续以后端和当前上传行为为准。
- 不在 Composer 中编辑、重命名、移动、删除或下载“我的文件”。
- 不把文件正文、Blob URL 或本地路径写入草稿、Session、事件或日志。
- 不持久化未发送的附件草稿；Session 切换仍清空附件。
- 不改变消息附件预览面板和生成文件管理。
- 不在移动端伪造系统拖拽；移动端通过附件菜单选择。

## 业务流程

### 拖入本地文件

1. 用户将包含 `Files` 的系统拖拽移入 Composer。
2. Composer 显示覆盖提示“释放以上传文件”，不响应普通文本、链接或页面内部拖拽。
3. 用户释放文件后，覆盖提示关闭，文件进入现有上传队列。
4. 每个文件继续显示上传中、成功或失败状态；失败项可重试或移除。
5. 用户发送后，附件 ID 随消息发送；成功清空，发送失败保留。

### 从“我的文件”选择

1. 用户打开附件菜单并选择“从我的文件选择”。
2. Dialog 加载当前用户根目录，可进入目录、搜索当前目录、筛选类型/来源和翻页。
3. 目录只能导航，只有状态为 available 的文件可选择。
4. 用户可跨目录和分页选择多个文件；已经在 Composer 中的文件显示为已选择且不会重复加入。
5. 点击“添加”后，Dialog 返回选中的安全文件元数据，Composer 直接创建 uploaded 状态附件项，不上传文件。
6. 发送时仍只提交文件 ID；服务端按当前用户重新查询文件。

### 图片缩略图

1. 新上传的图片优先使用本地 `File` 创建临时对象 URL。
2. 已有图片通过现有鉴权 `previewFile` 接口懒加载 Blob 后创建对象 URL。
3. 预览加载失败只隐藏缩略图，不影响附件发送。
4. 移除、发送成功、Session 切换或组件卸载时撤销对象 URL。

## 核心规则

1. 拖拽、粘贴和文件选择必须共用 `uploadFiles`，不能形成三套上传状态机。
2. 只有 `DataTransfer.types` 包含 `Files` 且存在实际文件时才拦截浏览器默认行为。
3. 拖拽覆盖层使用进入深度或等价稳定状态，子元素 `dragleave` 不得导致闪烁。
4. 已有文件只提交当前用户文件 ID；不能信任前端路径、URL、用户 ID 或存储 Provider。
5. 文件选择 Dialog 只消费现有用户隔离 API，不能读取其他用户、已删除或不可见文件。
6. 同一个已有文件 ID 在 Composer 中最多出现一次；本地重复上传沿用现有行为。
7. 文件夹不能作为附件；进入文件夹不得改变已选择的其他目录文件。
8. 加载新目录、搜索、筛选和分页时，旧请求不能覆盖新的列表状态。
9. Dialog 取消不修改 Composer；点击添加才提交选择。
10. 图片 Blob URL 只存在内存，不进入消息、localStorage、API payload 或日志。
11. 上传失败、已有文件预览失败和文件列表加载失败彼此隔离。
12. running Session 中添加附件继续进入现有下一条消息队列，不停止或修改当前 Run。

## 现有实现分析

### 相关代码与文档

- `agentic/web/src/components/chat/ChatInput.vue`：持有文本草稿、上传队列、附件 ID、Session 切换和发送状态。
- `agentic/web/src/components/chat/ChatComposer.vue`：展示附件卡、Skill、文本框和发送/停止动作；已处理粘贴文件。
- `agentic/web/src/views/FilesView.vue`：已有目录、搜索、类型/来源筛选、分页和文件预览模式。
- `agentic/web/src/lib/api/file.ts`：已有 `uploadFile`、`listFiles`、`getFileInfo` 和 `previewFile`。
- `agentic/web/src/components/FilePreviewPanel.vue`：已有 Blob URL 创建、竞态保护和撤销经验。
- `agentic/api/app/controllers/file.py`、`services/file_service.py`：列表和读取均绑定当前认证用户，只返回 available/visible 文件。
- `agentic/api/app/services/agent_service.py`：发送时按 `file_id + user_id` 重新读取附件，不信任前端文件正文。
- `LibreChat/client/src/components/Chat/Input/Files/*`：拖拽覆盖、附件菜单、文件列表和图片预览参考。

### 可复用能力

- 本地选择和剪贴板已共用 `uploadFiles(File[])`。
- `ComposerFileItem` 已表达 uploading/uploaded/failed、进度和错误。
- 文件中心 API 已支持目录、搜索、类型、来源和分页。
- `FilePreviewPanel` 已覆盖异步 Blob 竞态和 URL 回收。
- `ChatInput` 同时用于首页和 Session，完成一次接入即可覆盖两处。
- 当前消息发送只需要附件 ID；已有文件无需复制。

### 当前约束

- `ManagedFile` 与旧 `FileInfo` 类型字段集合不同，但 Composer 和 optimistic message 实际只需要 ID、名称、扩展名、大小和 MIME。
- `listFiles` 的搜索范围是当前目录，不是跨目录全局搜索。
- 文件预览接口需要 Bearer 鉴权，不能直接把相对 URL写入 `<img>`。
- 当前附件列表在 Session 切换时主动清空，本设计保持该隐私边界。
- 首页在上传后创建 Session 并通过 URL 传递附件 ID；已有文件必须兼容同一路径。

## 可选方案

### 方案 A：仅增加 Composer 拖拽

- 实现方式：在 `ChatComposer` 增加 drag/drop 覆盖层，继续使用现有隐藏文件输入和上传卡片。
- 优点：改动小、无新 Dialog、交付快。
- 缺点：无法复用文件中心内容，用户仍需重复上传；附件入口仍是单一动作。
- 风险：只解决最表面的交互问题，后续做“我的文件”时还会再次调整附件状态。

### 方案 B：统一附件入口 + 我的文件 + 缩略图

- 实现方式：保留 `ChatInput` 作为附件状态所有者；`ChatComposer` 负责拖拽和菜单；新增只读 `ChatFilePickerDialog`；用统一窄类型表达上传和已有附件。
- 优点：完整解决三处断点；复用现有 API；首页、Session、队列共享；不产生重复存储。
- 缺点：涉及 Dialog、竞态、跨页选择、对象 URL 生命周期和较完整测试。
- 风险：若把选择态与列表态耦合，目录切换可能丢选择；异步缩略图可能覆盖已切换附件。

### 方案 C：抽象全局文件资源中心

- 实现方式：建设统一资源 Store，把文件中心、Composer、Knowledge、Agent 和 Tool 的选择全部接入同一套 Picker。
- 优点：未来扩展能力最强，可作为 A2/C2/C1 的公共基础。
- 缺点：当前没有 Knowledge/Agent 数据模型，会提前设计大量未使用抽象并重构 FilesView。
- 风险：范围膨胀，附件体验被平台化工作拖慢。

## 方案对比

| 维度 | 方案 A：仅拖拽 | 方案 B：统一附件体验 | 方案 C：资源中心 |
| --- | --- | --- | --- |
| 实现复杂度 | 低 | 中 | 高 |
| 维护成本 | 低但后续重复改造 | 中，边界清晰 | 高，需维护通用协议 |
| 兼容性 | 最好 | 复用现有 API，兼容性好 | 涉及现有文件页重构 |
| 测试难度 | 低 | 中 | 高 |
| 主要风险 | 价值不完整 | 选择态与 Blob 生命周期 | 过度设计和范围膨胀 |

## 推荐方案

选择方案 B：统一附件入口 + 我的文件 + 缩略图。

它完整覆盖用户最常见的附件来源，同时保持后端协议和权限模型不变。方案 A 无法解决重复上传，后续仍需重做附件入口；方案 C 会把尚未开始的 Knowledge、Agent 和 Project 需求提前带入本批，不符合当前逐项学习策略。

## 数据结构

无数据库结构变化。

### `ComposerAttachmentFile`

| 字段 | 类型 | 必填 | 说明 | 约束/默认值 |
| --- | --- | --- | --- | --- |
| `id` | `string` | 是 | 本地临时 ID 或持久化文件 ID | 发送只使用持久化 ID |
| `filename` | `string` | 是 | 展示名称 | 不作为权限依据 |
| `extension` | `string` | 否 | 文件扩展名 | 小写展示 |
| `size` | `number` | 是 | 文件大小 | 非负 |
| `contentType` | `string` | 否 | MIME | 仅用于决定缩略图 |
| `origin` | `'upload' \| 'library'` | 是 | 附件来源 | 内存状态 |
| `uploadStatus` | `'uploading' \| 'uploaded' \| 'failed'` | 是 | 可发送状态 | library 直接为 uploaded |
| `uploadError` | `string` | 否 | 上传失败信息 | 不持久化 |
| `progress` | `number` | 否 | 上传进度 | 0–100 |
| `previewUrl` | `string` | 否 | 临时 Blob URL | 不序列化，离开时撤销 |

### `FilePickerSelection`

仅包含 `id`、`filename`、`extension`、`size`、`mime_type` 和 `source_type`。目录、路径、下载 URL、存储密钥和用户 ID不进入选择结果。

## 接口设计

### `ChatFilePickerDialog`

- 输入：
  - `modelValue: boolean`
  - `selectedIds: string[]`
- 输出：
  - `update:modelValue`
  - `confirm(files: FilePickerSelection[])`
- 权限：只调用带当前登录凭证的现有文件 API。
- 幂等/并发：相同 ID 去重；目录/筛选请求使用请求版本避免乱序覆盖。
- 兼容性：新增前端组件，不改变文件中心。

### `ChatComposer`

- 新增输入：附件菜单与拖拽所需状态。
- 新增事件：
  - `uploadLocalFiles(files: File[])`
  - `openFileLibrary()`
- 保留现有 `pasteFiles`、`removeFile`、`retryFile`、`send` 和 `stop`。
- 兼容性：现有点击上传路径仍可访问，只是由菜单选择。

### `ChatInput`

- 继续拥有附件队列。
- 新增已有文件合并、去重、缩略图加载和 URL 清理。
- `onSend` 的附件展示参数收窄为实际需要的安全元数据，不再要求完整存储字段。
- 兼容性：发送 payload 仍是 `attachmentIds: string[]`。

### 后端接口

无新增或变更：

- `GET /files`
- `GET /files/{file_id}`
- `GET /files/{file_id}/preview`
- `POST /files`
- 现有消息/下一条消息接口

## 错误处理与可观测性

- 本地上传失败：保留失败卡和重试/移除入口，阻止发送。
- 文件列表失败：Dialog 保持打开，显示重试，不影响 Composer 已选附件。
- 已有文件在确认前被删除：发送时服务端不会返回该附件；前端应在添加时读取 available 文件，并在失败时提示刷新选择。
- 缩略图失败：降级为文件图标，不提示阻塞错误。
- 拖入非文件内容：不拦截、不显示错误。
- 不记录本地路径、Blob URL、文件正文或鉴权头；必要日志只记录数量、来源和失败类别。

## 迁移与回滚

- 迁移：无数据库和历史文件迁移；已有上传附件自动使用新的卡片样式。
- 回滚：移除附件菜单、Dialog、拖拽覆盖和缩略图字段即可恢复当前文件输入；后端和历史数据不变。
- 分支：使用 `feature/chat-attachment-experience`，堆叠基线为已验收 Artifact 提交 `16ccd1e`。

## 风险

| 风险 | 可能性 | 影响 | 缓解措施 | 验证方式 |
| --- | --- | --- | --- | --- |
| 子元素 dragleave 导致覆盖层闪烁 | 中 | 低 | 进入深度与文件类型检测 | 嵌套元素拖动组件测试 |
| 页面内部拖动文字被误当文件 | 中 | 中 | 只接受 `DataTransfer.types` 的 Files | 文本/链接拖动测试 |
| 跨目录选择丢失 | 中 | 中 | selection map 独立于当前列表 | 跨目录/分页测试 |
| 已有文件 ID 越权 | 低 | 高 | API 与发送端均按 current user 查询 | 后端用户隔离回归 |
| Blob URL 泄漏 | 中 | 中 | 集中创建/撤销，覆盖所有退出路径 | URL 生命周期测试 |
| 旧预览请求覆盖新附件 | 中 | 低 | 请求版本或附件 ID 校验 | 快速移除/切换测试 |
| 运行中附件破坏下一条消息 | 低 | 高 | 不改发送协议，只扩展附件来源 | queue 集成回归 |
| 移动端 Dialog/菜单溢出 | 中 | 中 | 全宽 Dialog 与滚动区 | 390px 页面验收 |

## 重要假设

- 用户选择“先做第一组”表示第一组按推荐顺序逐项交付，当前先实施 A1。
- 现有文件列表与 `getFileInfo` 已提供当前用户可使用的 available 文件，发送端仍会二次校验所有权。
- 本批“预览”指 Composer 图片缩略图，不扩展消息内文件预览类型。
- 第二组特性不进入路线；第三组能力将在后续逐项设计，不提前抽象资源中心。
- 分享、导出和导入保持延期。

## 待决策项

无。第一版固定为 Composer 文件拖拽、附件菜单、我的文件多选和图片缩略图；外部云盘、Knowledge 与通用资源中心另行设计。

## 验收标准

- [ ] 本地文件拖入 Composer 后显示稳定覆盖提示，释放后进入现有上传队列。
- [ ] 文本、链接和页面内部拖动不触发上传，也不阻断默认行为。
- [ ] 粘贴上传、点击上传和拖拽上传共用相同状态、失败重试和发送规则。
- [ ] 回形针菜单可选择本地上传或打开“我的文件”。
- [ ] “我的文件”支持目录、搜索、类型/来源、分页、多选、加载/空/失败/重试。
- [ ] 取消 Dialog 不改变附件；确认后直接复用文件 ID且不调用上传 API。
- [ ] 同一个已有文件不会重复加入，跨目录和分页选择不丢失。
- [ ] 图片显示缩略图；加载失败降级为文件图标，不阻止发送。
- [ ] 所有 Blob URL 在移除、发送成功、Session 切换和卸载时撤销。
- [ ] 首页、普通 Session 和 running 下一条消息均可使用本地或已有文件。
- [ ] 发送失败保留附件；成功发送只清理当前 Session 的附件，不误清理快速切换后的 Session。
- [ ] 桌面、390px、暗色、Tab/Enter/Escape、焦点恢复和无横向溢出通过。
- [ ] 无数据库、迁移、后端接口、依赖、lockfile、shell、沙箱写入或工具批准变化。
