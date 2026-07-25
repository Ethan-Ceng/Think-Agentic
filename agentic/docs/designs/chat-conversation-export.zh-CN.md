# 对话安全导出

## 文档状态

- 状态：`DESIGN_READY (DEFERRED)`
- 负责人：Codex
- 创建日期：2026-07-25
- 最近更新：2026-07-25

> 2026-07-25 优先级调整：用户认为文件导出不是当前核心能力，本设计保留为备选，不进入实施；后续仅在重新明确需要时恢复。

## 背景

前几批 LibreChat 学习已经完成会话可靠性、运行中下一条消息、工具审批、HITL、会话整理、消息编辑、重新生成、分支导航以及只读 Artifact/生成文件统一预览。当前仍适合在不建设 Project、Prompt、Agent Profile 或长期 Memory 数据模型的前提下学习的高价值能力，是 LibreChat 的对话导出：

- 会话标题栏提供可发现的导出入口；
- 用户可以选择文件名和导出格式；
- 导出直接在浏览器生成并下载，不依赖 shell 或沙箱文件；
- 导出内容是经过明确投影的用户可见对话，而不是数据库、Memory、Trace 或工具内部状态的原样转储。

LibreChat 的相关实现集中在：

- `LibreChat/client/src/components/Chat/ExportAndShareMenu.tsx`
- `LibreChat/client/src/components/Nav/ExportConversation/ExportModal.tsx`
- `LibreChat/client/src/hooks/Conversations/useExportConversation.ts`
- `LibreChat/client/src/hooks/Conversations/format.ts`

LibreChat 支持 screenshot、text、Markdown、JSON、CSV、分支和 endpoint options。Agentic 当前以 Session 隔离 Agent Run、Memory、Trace、文件和分支，直接复制全部导出选项会把隐藏运行数据与用户可分享的对话文本混在一起。第一版应学习“入口、格式选择、文件名、安全投影、浏览器下载”，而不是复制完整审计或分享系统。

## 目标

- 在当前 Session 标题栏提供“导出对话”入口。
- 支持 Markdown 与 JSON 两种可移植格式，并允许用户编辑安全文件名。
- 只导出服务端已经持久化、用户可见的消息、附件元数据和错误提示。
- 明确排除 Tool 原始参数/结果、Trace、Memory、审批参数、Plan 内部状态、文件正文和下载 URL。
- 运行中的 Session 可以导出当前已持久化快照，并明确提示导出不会自动更新。
- 导出完全在浏览器内完成，不新增后端接口、数据库迁移、依赖或工具批准。
- 桌面、390px、暗色和键盘操作可用，Dialog 关闭后焦点返回入口。

## 功能范围

- SessionHeader 增加“导出对话”图标按钮。
- 新建导出 Dialog：
  - 文件名输入；
  - Markdown / JSON 格式选择；
  - 当前快照和隐私边界说明；
  - 导出、取消。
- 从当前已持久化事件投影构建稳定导出快照。
- 导出以下内容：
  - Session ID、标题、状态、导出时间；
  - user/assistant 消息正文和时间；
  - 与消息相邻的附件文件名、扩展名和大小；
  - 用户界面已经展示的 Session 错误及时间。
- Markdown 输出面向阅读，JSON 输出使用版本化 schema。
- 安全文件名、UTF-8 MIME、Blob 下载和成功/失败 toast。
- 空会话、运行中快照、特殊字符、多消息、附件、错误和下载失败测试。

## 非功能范围

- 不实现公开分享链接、跨用户访问、协作权限或脱敏审批。
- 不实现导入、恢复、重新运行或把 JSON 当成内部备份。
- 不导出 Tool 原始输入/输出、Trace、Memory、审批参数/答案、Plan、Skill 内容、系统提示或模型配置。
- 不下载或打包附件正文，不生成 ZIP，不创建签名 URL。
- 不实现 screenshot、PDF、CSV、纯文本或网页导出。
- 不导出当前 Session 的 sibling 分支、来源分支或整个 lineage。
- 不包含尚未成功持久化的本地草稿、sending/failed optimistic 消息或排队中输入。
- 不新增后端 API、数据库表、迁移、后台导出任务或服务端文件。
- 不把 Markdown 导出重新渲染到 Agentic 主页面，也不执行其中的 HTML 或代码。

## 业务流程

### 导出已完成会话

1. 用户打开一个已有持久化消息的 Session。
2. 标题栏展示“导出对话”按钮；用户点击后打开 Dialog。
3. Dialog 使用 Session 标题生成安全默认文件名，默认选择 Markdown。
4. 用户可修改基础文件名并选择 Markdown 或 JSON。
5. 用户确认导出时，系统从当前服务端事件投影重新构建快照。
6. 快照只保留白名单字段并序列化为 UTF-8 Blob。
7. 浏览器下载文件并提示成功；Dialog 关闭，焦点返回导出按钮。

### 导出运行中会话

1. Session 状态为 running 或 waiting。
2. Dialog 明确提示“仅导出当前已保存快照，后续消息不会自动加入”。
3. 导出时读取点击确认这一刻的持久化事件，不冻结、不停止也不影响 SSE。
4. 本地草稿、optimistic sending/failed 消息和排队输入不进入文件。

### 导出失败

1. 序列化或 Blob 下载抛出异常。
2. Dialog 保持打开，文件名和格式不丢失。
3. 页面提示“导出失败”，不调用 shell、后端或重试工具。
4. 用户可以修改选择后再次导出或取消。

## 核心规则

1. 导出是当前 Session 的只读、即时、浏览器内快照，不是审计备份。
2. 数据源必须是服务端事件形成的 `baseTimeline`，不能使用叠加了 pending 本地消息的展示 timeline。
3. 只允许 user/assistant message、相邻 attachment metadata 和 visible error 进入快照。
4. Tool、Step、Interaction、Plan、Trace、Memory 和系统配置即使存在于当前页面状态，也不得进入导出结构。
5. 附件只包含 `filename`、`extension`、`size`；不包含 file ID、路径、URL、正文或鉴权信息。
6. Markdown 与 JSON 必须由同一个白名单快照生成，不能各自读取原始事件。
7. JSON schema 使用固定标识和版本；第一版文件明确不可导入。
8. 文件名移除路径分隔符、控制字符、Windows 保留名和尾部点/空格，限制长度并由格式决定扩展名。
9. 空白标题回退为 `session-export`；用户输入的伪扩展不能覆盖所选格式。
10. running/waiting 导出不改变 Session 状态、SSE、Composer、排队消息或自动工具跟随。
11. 浏览器 Blob 下载不调用 `/files`、新 API、shell 或沙箱写入，因此不触发工具批准。
12. 关闭 Dialog 或切换 Session 后不得保留上一个 Session 的文件名、格式或快照。

## 现有实现分析

### 相关代码与文档

- `agentic/web/src/components/SessionHeader.vue`：已有状态、Trace 和文件入口，适合增加导出按钮及事件。
- `agentic/web/src/components/SessionDetailView.vue`：同时持有服务端 `baseTimeline` 与叠加 pending 消息的 `timeline`；应只把前者交给导出组件。
- `agentic/web/src/lib/session-events.ts`：已把原始 SSE 事件投影为 message、attachments、tool、step、interaction 和 error，可作为白名单投影输入。
- `agentic/web/src/lib/utils.ts`：已有 `downloadBlob`，可复用浏览器 Blob URL 生命周期。
- `agentic/web/src/lib/chat-artifacts.ts`：已有文件名安全化和浏览器下载经验，但类型名称绑定 Artifact，需要决定复用或提取通用实现。
- `agentic/web/src/components/SettingsModal.vue`：已有 Element Plus Dialog、移动宽度和关闭保护模式。
- `agentic/web/src/components/SessionDetailView.spec.ts`、`agentic/web/src/lib/session-events.spec.ts`：已有 Session 事件、pending 消息和 Header 集成测试基础。
- `agentic/docs/librechat-ui-redesign.zh-CN.md`：把分享/导入导出列为需独立设计的后续能力，不允许添加无行为入口。

### 可复用能力

- `eventsToTimeline` 已过滤不可见 message，并把附件紧邻放在所属 message 后。
- SessionDetail 已区分 `baseTimeline` 与包含本地 pending 的展示 timeline。
- `downloadBlob` 已处理对象 URL 创建、点击和撤销。
- UiButton、UiIconButton、UiTextField、toast、Element Plus Dialog 和响应式 Token 可直接复用。
- Artifact 文件名测试可作为路径、保留名和特殊字符边界参考。
- 全量测试已经覆盖运行中输入、排队、审批、HITL、分支和预览，可用于回归门禁。

### 当前约束

- Session 事件 JSONB 包含 Tool、Interaction、Plan 等隐藏或敏感运行数据，不能直接 `JSON.stringify(detail.events)`。
- `timeline` 还会临时加入 pending 用户消息及附件；导出必须绕开这一层。
- 附件下载需要鉴权；第一版不能将文件正文或临时 URL 嵌入导出。
- 当前没有通用 Export 数据模型、后台任务、ZIP、screenshot 或 CSV 依赖。
- 当前分支 `feature/chat-conversation-export` 堆叠在已验收但尚未合并到 `master` 的 `feature/chat-artifact-preview` 提交之上；实施前需保持分支关系可识别。

## 可选方案

### 方案 A：标题栏一键 Markdown

- 实现方式：点击按钮后直接把 user/assistant 文本拼接为 Markdown 并下载，不显示 Dialog。
- 优点：改动最小、交付快、没有格式状态。
- 缺点：用户不能确认隐私范围、文件名或格式；运行中快照含义不清楚；后续增加 JSON 会再次改入口。
- 风险：简单字符串拼接容易让 Markdown 与未来 JSON 形成两套不一致投影。

### 方案 B：浏览器内安全投影 + Markdown/JSON Dialog

- 实现方式：先用纯函数把 `baseTimeline` 投影为版本化白名单快照；Dialog 只负责文件名、格式和说明；Markdown/JSON 共用快照并通过 Blob 下载。
- 优点：学习 LibreChat 的核心导出体验，同时不新增后端；隐私边界、运行中快照和测试输入明确；未来若增加新格式仍可复用快照。
- 缺点：需要新增 Dialog、序列化模块、集成事件和较完整测试。
- 风险：附件归属、特殊 Markdown、文件名和 Session 切换状态需要严格测试。

### 方案 C：服务端完整任务审计包

- 实现方式：新增导出 API/后台任务，把消息、Plan、Tool、Trace、审批、文件 manifest 和可选附件打成 ZIP，并提供下载记录。
- 优点：内容完整、适合审计和迁移，可处理超大 Session。
- 缺点：需要权限模型、脱敏策略、异步任务、临时文件、对象存储、过期清理和审计日志。
- 风险：极易泄漏工具参数、Memory、密钥、文件内容或跨用户数据；交付范围远超 LibreChat UI 学习。

## 方案对比

| 维度 | 方案 A：一键 Markdown | 方案 B：安全投影 Dialog | 方案 C：审计包 |
| --- | --- | --- | --- |
| 实现复杂度 | 低 | 中 | 高 |
| 维护成本 | 低，但扩展易分叉 | 中，投影与格式分层 | 高，需长期维护导出任务 |
| 兼容性 | 仅阅读用途 | Markdown/JSON 可移植 | 依赖服务端版本与存储 |
| 测试难度 | 低 | 中 | 高 |
| 隐私边界 | 弱提示 | 白名单结构明确 | 高风险且需完整脱敏 |
| 运行中行为 | 不透明 | 明确快照语义 | 需一致性与任务协调 |
| 交付成本 | 低 | 中 | 很高 |

## 推荐方案

选择方案 B：浏览器内安全投影 + Markdown/JSON Dialog。

它保留 LibreChat 最值得学习的交互：标题栏入口、格式选择、文件名、导出说明和浏览器下载；同时利用 Agentic 已有的 `baseTimeline` 建立比原始事件转储更严格的安全边界。Markdown 面向阅读，JSON 提供稳定的机器可读结构，但都只表达用户可见对话，不伪装成完整备份。

不选择方案 A，是因为它缺少隐私确认和格式扩展边界；不选择方案 C，是因为完整任务包涉及权限、脱敏、后台任务和文件生命周期，属于独立审计产品而不是当前 UI 学习。

## 数据结构

无数据库结构变化。

### `ConversationExportSnapshot`

| 字段 | 类型 | 必填 | 说明 | 约束/默认值 |
| --- | --- | --- | --- | --- |
| `schema` | `'agentic.session.transcript'` | 是 | 导出结构标识 | 固定值 |
| `version` | `1` | 是 | schema 版本 | 固定值 |
| `exported_at` | `string` | 是 | 导出时间 | ISO 8601 UTC |
| `session` | `ExportSessionMetadata` | 是 | 当前 Session 安全元数据 | 仅 ID、标题、状态 |
| `entries` | `ConversationExportEntry[]` | 是 | 白名单对话条目 | 保持服务端事件顺序 |

### `ExportSessionMetadata`

| 字段 | 类型 | 必填 | 说明 | 约束/默认值 |
| --- | --- | --- | --- | --- |
| `id` | `string` | 是 | Session 标识 | 当前用户已授权 Session |
| `title` | `string` | 是 | Session 标题 | 空白回退“未命名任务” |
| `status` | `SessionStatus` | 是 | 导出时状态 | 不触发刷新或状态改变 |

### `ConversationExportEntry`

| 字段 | 类型 | 必填 | 说明 | 约束/默认值 |
| --- | --- | --- | --- | --- |
| `type` | `'message' \| 'error'` | 是 | 条目类型 | Tool/Step/Interaction 不允许出现 |
| `role` | `'user' \| 'assistant'` | message 是 | 消息角色 | 其他角色不导出 |
| `text` | `string` | message 是 | 原始可见消息正文 | 不从 DOM 反解析 |
| `created_at` | `string \| null` | 是 | 可用时的 ISO 时间 | 无合法时间为 null |
| `attachments` | `ExportAttachment[]` | message 是 | 所属附件 manifest | 默认 `[]` |
| `message` | `string` | error 是 | 可见错误文本 | 不附带堆栈 |

### `ExportAttachment`

| 字段 | 类型 | 必填 | 说明 | 约束/默认值 |
| --- | --- | --- | --- | --- |
| `filename` | `string` | 是 | 可见文件名 | 不包含路径 |
| `extension` | `string` | 是 | 扩展名 | 去除前导点 |
| `size` | `number` | 是 | 字节数 | 非负有限数，否则 0 |

## 接口设计

### `buildConversationExportSnapshot`

- 输入：Session ID、标题、状态、`TimelineItem[]`（必须为 `baseTimeline`）、导出时间。
- 输出：`ConversationExportSnapshot`。
- 权限：不访问 API；调用方只能传入当前已授权 Session 的现有投影。
- 幂等/并发：相同输入和导出时间得到相同结果；运行中新增事件只影响下一次调用。
- 兼容性：纯函数新增，不改变 `eventsToTimeline`。

### `serializeConversationMarkdown`

- 输入：`ConversationExportSnapshot`。
- 输出：UTF-8 Markdown 字符串。
- 规则：包含标题、状态、导出时间、按顺序的 user/assistant 小节、附件 manifest 和可见错误；不嵌入 URL 或 HTML 执行容器。

### `serializeConversationJson`

- 输入：`ConversationExportSnapshot`。
- 输出：带两个空格缩进和末尾换行的 JSON 字符串。
- 规则：保持 schema/version，不能加入原始事件或未声明字段。

### `SessionExportDialog`

- 输入：
  - `modelValue: boolean`
  - `sessionId: string`
  - `title: string`
  - `status: SessionStatus`
  - `timeline: TimelineItem[]`
- 输出：
  - `update:modelValue`
  - 可选 `exported(format, filename)` 仅供测试/埋点，不包含正文。
- 行为：
  - 打开或 Session ID 变化时重置默认文件名与 Markdown 格式；
  - 确认时重新构建快照；
  - 下载成功后关闭；失败保留编辑态；
  - running/waiting 显示快照提示；
  - 关闭后焦点由 Dialog/触发器机制恢复。

### `SessionHeader`

- 新增输入：`exportable?: boolean`。
- 新增输出：`openExport()`。
- 不直接读取消息、事件或生成文件，保持 Header 只负责入口。

### 后端接口

无新增或变更。

## 错误处理与可观测性

- 没有可导出 message/error 时按钮禁用或不展示，并提供可访问说明。
- 文件名为空、为保留名或含路径字符时自动安全化并使用 fallback。
- 序列化、Blob、DOM 或浏览器下载失败时 toast“导出失败”，Dialog 不关闭。
- 下载成功提示最终文件名，不记录对话正文。
- 前端日志不得输出 snapshot、消息正文或附件名；若增加埋点，只记录 format、entry_count、attachment_count、session_status 和 success/failure。
- 不进行后端重试、shell fallback 或沙箱写入。

## 迁移与回滚

- 迁移：无数据库、历史 Session、文件或配置迁移；已有会话加载后自动获得导出入口。
- 回滚：移除 Header 入口、Dialog 和浏览器序列化模块即可；服务端数据不需要清理。
- 分支：当前功能分支堆叠在 Artifact 分支之上；若 Artifact 先合并到 master，可对本分支进行普通 rebase/merge-base 调整，但本设计不自动执行。

## 风险

| 风险 | 可能性 | 影响 | 缓解措施 | 验证方式 |
| --- | --- | --- | --- | --- |
| 原始事件泄漏 Tool/Memory/审批参数 | 中 | 高 | 只接收 baseTimeline，并二次白名单为 message/error | 敏感混合 timeline 单元测试 |
| 把 pending 本地消息误当持久化记录 | 中 | 中 | SessionDetail 显式传 baseTimeline | 集成测试同时放置 pending message |
| 附件导出 file ID、路径或 URL | 中 | 高 | ExportAttachment 固定三个字段 | JSON 字段精确断言 |
| running 导出结果与稍后页面不同 | 高 | 低 | Dialog 明示当前快照和 exported_at | 运行中增量前后两次快照测试 |
| Markdown 中的用户文本被外部查看器解释 | 中 | 中 | 只下载、不在 Agentic 执行；文档声明内容不可信 | 验证应用内无预览/执行入口 |
| 文件名路径穿越或保留名 | 中 | 中 | 通用安全化、固定扩展和长度限制 | 特殊字符/Windows 名称测试 |
| Session 切换后导出旧内容 | 中 | 高 | Session ID 变化重置 Dialog，确认时读取当前 props | 快速切换集成测试 |
| 大会话占用浏览器内存 | 低 | 中 | 仅处理已加载文本投影，不读取附件正文 | 大文本序列化性能测试 |
| 导出动作触发工具批准 | 低 | 中 | 仅 Clipboard/Blob/DOM，无 API 和 shell | API mock 与页面手工验收 |

## 重要假设

- 当前 `detail.events` 是已授权 Session 的服务端持久化事件集合，`baseTimeline` 不包含 ChatInput 本地草稿。
- 第一版“对话导出”是阅读/交换格式，不是可恢复备份或法定审计包。
- 用户委托按推荐顺序继续 LibreChat 学习，因此优先实现导出，而不是先建设 Project、Prompt、Agent 或长期 Memory。
- JSON 中的 Session ID 不授予任何访问权限；所有后端接口仍按当前用户鉴权。
- 当前已有 Element Plus Dialog 与浏览器 Blob 能力，不新增第三方包。
- 当前分支是从 `16ccd1e` 创建的堆叠分支，不代表 Artifact 分支已经合并到 master。

## 待决策项

无。第一版固定为当前 Session、安全白名单、Markdown/JSON、浏览器下载；公开分享、附件正文和完整执行审计另行设计。

## 验收标准

- [ ] 有持久化 user/assistant message 或 visible error 的 Session 显示可访问的导出入口；空 Session 不可导出。
- [ ] Dialog 可编辑文件名并选择 Markdown/JSON，打开或 Session 切换时状态正确重置。
- [ ] Markdown 按服务端顺序包含标题、状态、时间、消息、附件 manifest 和可见错误。
- [ ] JSON 精确符合 `agentic.session.transcript` v1，不包含未声明字段。
- [ ] Tool、Step、Interaction、Plan、Trace、Memory、系统提示、模型配置和审批参数不会进入任何格式。
- [ ] 附件仅包含文件名、扩展名和大小，不包含 ID、路径、URL 或正文。
- [ ] pending/failed optimistic 消息、本地草稿和排队输入不会进入导出。
- [ ] 运行中导出明确提示当前快照，不停止任务、不改变 SSE 或 Composer。
- [ ] 文件名对路径字符、控制字符、保留名、伪扩展和超长输入安全处理。
- [ ] 下载成功/失败反馈正确；失败保留 Dialog 编辑态。
- [ ] 导出只使用浏览器 Blob，不产生后端、shell、沙箱写入或工具批准请求。
- [ ] 桌面、390px、暗色、Tab/Enter/Escape 和焦点恢复通过。
- [ ] 当前聊天、文件、Artifact、Tool、Trace、分支、审批、HITL 和下一条消息队列回归通过。
- [ ] 无数据库迁移、后端接口、依赖或 lockfile 变化。
