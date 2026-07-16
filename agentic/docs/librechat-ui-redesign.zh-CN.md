# Agentic Web 借鉴 LibreChat 的 Vue 3 UI 改造方案

整理日期：2026-07-15

状态：持续演进；Skills、Creator 与 Marketplace 闭环已于 2026-07-16 落地

参考基线：仓库内 `LibreChat` 前端 `v0.8.7`

## 1. 文档目标

本文用于指导 `agentic/web` 在保留 Vue 3 技术栈和 Agent 执行能力的前提下，借鉴 LibreChat 的产品信息架构、视觉体系与交互细节。

核心结论：

> 学习 LibreChat 的界面结构和交互模式，用 Vue 3 重新实现；不迁移 React 代码，不把 Agentic 降级为普通聊天应用。

本文后续应作为 Web UI 改造的主文档。开始实施某个阶段时，应同步更新本文件中的状态和实际落地文件，避免规划与代码脱节。

## 2. 改造原则与边界

### 2.1 必须保持

- Vue 3 Single File Component。
- Vue Router。
- Pinia。
- Element Plus。
- `lucide-vue-next`。
- 当前 API、SSE 和会话事件数据结构。
- Agentic 的 Plan、Thinking、Tool Call、Trace、文件预览、VNC 等执行工作台能力。

### 2.2 可以借鉴

- 页面信息架构。
- 侧栏和导航结构。
- 首页欢迎区与输入器布局。
- 消息排版、操作按钮、状态反馈。
- 搜索、项目、Prompt、Skill、Agent 市场等页面的产品模式。
- 颜色、间距、圆角、阴影和响应式策略。
- 键盘操作、ARIA、焦点管理等可访问性设计。

### 2.3 不直接照搬

- React Component、Hook、Context 和 Provider。
- Recoil、Jotai 状态代码。
- React Query 查询代码。
- Tailwind class 字符串。
- Radix UI、Headless UI、React Virtualized 组件。
- LibreChat 的模型 Endpoint、Assistant 等特定业务概念。
- 后端尚不支持的空壳功能。

### 2.4 不应发生的退化

- 不删除或弱化执行计划展示。
- 不把工具调用全部压缩成普通文本消息。
- 不移除文件、浏览器、Shell、MCP、A2A 等工具预览。
- 不用普通聊天会话模型替代 Agent Run / Step / Trace 语义。
- 不因为模仿 LibreChat 而重写整个前端技术栈。

## 3. 两套前端技术基线

| 领域 | Agentic | LibreChat | Agentic 改造策略 |
| --- | --- | --- | --- |
| UI 框架 | Vue 3.5 | React 18 | 保留 Vue 3 |
| 路由 | Vue Router | React Router | 用 Vue Router 表达相同页面层级 |
| 全局状态 | Pinia | Recoil / Jotai | 保留 Pinia，按领域拆 Store |
| 服务端状态 | Store + API 层 | TanStack React Query | 先保留现有 API；复杂缓存再评估 TanStack Vue Query |
| UI 组件 | Element Plus | Radix、Headless UI、自有组件 | 优先映射到 Element Plus |
| 图标 | Lucide Vue | Lucide React | 图标语义可以直接对应 |
| 样式 | 全局 CSS、Scoped CSS | Tailwind、CSS Token | 建立语义 Token，逐步整理现有 CSS |
| Markdown | markdown-it | react-markdown/remark/rehype | 保留 markdown-it，补齐展示能力 |
| 虚拟列表 | 暂无 | React Virtualized | 数据规模确有需要时再引入 Vue 虚拟列表 |

参考依赖：

- Agentic：`web/package.json`
- LibreChat：`../LibreChat/client/package.json`

## 4. Agentic 当前页面与界面清单

路由来源：`web/src/router/index.ts`。

### 4.1 正式路由页面

| 页面 | 路由 | 入口文件 | 当前能力 |
| --- | --- | --- | --- |
| 登录/注册 | `/auth` | `web/src/views/AuthView.vue` | 登录、注册模式切换、认证后重定向 |
| 新建任务首页 | `/` | `web/src/views/HomeView.vue` | 欢迎语、任务输入、附件、建议问题 |
| 任务会话 | `/sessions/:id` | `web/src/views/SessionView.vue` | 加载指定 Session，进入执行工作台 |
| 文件管理 | `/files` | `web/src/views/FilesView.vue` | 目录、上传、筛选、搜索、表格/网格、移动、删除、预览 |
| 我的 Skills | `/skills`、`/skills/:skillId` | `web/src/views/SkillsView.vue`、`SkillDetailView.vue` | 草稿、导入、校验、发布、启停、Creator |
| Skill 市场 | `/skills/marketplace` | `web/src/views/SkillMarketplaceView.vue` | 搜索、安装、固定版本、显式更新、卸载、Fork |

`/sessions` 当前只重定向到首页，不是独立页面。

### 4.2 嵌入式功能界面

这些界面虽然没有独立路由，但产品复杂度已接近独立页面：

| 界面 | 当前文件 | 作用 |
| --- | --- | --- |
| 左侧导航与任务列表 | `LeftPanel.vue`、`SessionList.vue` | 新建任务、文件入口、历史任务 |
| 任务执行工作台 | `SessionDetailView.vue` | 对话、执行事件、输入区、右侧预览编排 |
| 设置中心 | `SettingsModal.vue` | 通用、模型、存储、API Tools、A2A、MCP |
| 文件预览 | `FilePreviewPanel.vue` | 图片、文本与不支持文件展示 |
| 工具预览 | `chat/ToolPreviewPanel.vue` | Shell、浏览器、搜索、文件、MCP、A2A 结果 |
| Trace 面板 | `TracePanel.vue` | Run、Step、Tool Call、Model Call、Timeline |
| VNC 操作层 | `VNCOverlay.vue`、`VNCViewer.vue` | 浏览器/桌面实时操作 |
| 执行计划 | `chat/PlanPanel.vue` | 当前任务步骤与完成进度 |
| 思考与工具消息 | `chat/ThinkingBlock.vue`、`chat/ToolCallCard.vue` | Agent 执行过程可视化 |

### 4.3 当前前端优势

Agentic 的任务会话已经不是普通 Chat UI，而是：

```text
任务对话
+ 执行计划
+ 思考步骤
+ 工具调用
+ 生成文件
+ 浏览器/VNC
+ Run / Trace
+ 右侧详情预览
```

这部分是改造时必须保护的产品差异化。

### 4.4 当前主要 UI 短板

- 侧栏固定为 300px，收起后宽度直接变为 0，没有图标窄栏。
- 视觉颜色以硬编码灰色为主，缺少完整的语义 Token。
- 暗色主题尚未形成完整体系。
- 页面级全局搜索缺失。
- 历史任务缺少收藏、标签、归档和项目分组。
- Skills 侧边栏和独立管理/市场入口已实现；用户长期记忆面板仍待后续数据模型支持。
- 设置中心同时承载个人设置和系统能力管理，职责过重。
- 部分组件文件和全局 CSS 体积较大，后续维护成本高。
- 用户文案以硬编码中文为主，尚未形成统一国际化层。
- 认证页面只有登录/注册，尚未覆盖忘记密码、验证、2FA 等完整状态。

## 5. LibreChat 页面清单

路由来源：`../LibreChat/client/src/routes/index.tsx`。

### 5.1 公共与认证页面

| 页面 | LibreChat 路由 | Agentic 适用性 |
| --- | --- | --- |
| 登录 | `/login` | 可学习布局与错误状态 |
| 注册 | `/register` | 可学习表单层级 |
| 邮箱验证 | `/verify` | 后端支持后再做 |
| 忘记密码 | `/forgot-password` | 后端支持后再做 |
| 重置密码 | `/reset-password` | 后端支持后再做 |
| 两步验证 | `/login/2fa` | 后端支持后再做 |
| OAuth 结果 | `/oauth/success`、`/oauth/error` | 有第三方登录时再做 |
| 公开分享 | `/share/:shareId` | 有分享权限与脱敏机制后再做 |

### 5.2 主产品页面

| 页面 | LibreChat 路由 | 主要模式 |
| --- | --- | --- |
| 新建聊天 | `/c/new` | 居中欢迎区、输入器、建议问题 |
| 历史聊天 | `/c/:conversationId` | 消息流、固定输入器、消息操作 |
| 全局搜索 | `/search` | 跨会话消息搜索、结果列表、分页加载 |
| Prompt | `/prompts/new`、`/prompts/:promptId` | 列表、编辑、变量、预览、版本 |
| Skill | `/skills/...` | 列表、创建、查看、编辑、启停 |
| Project | `/projects`、`/projects/:projectId` | 项目卡片、项目内会话工作区 |
| Agent 市场 | `/agents`、`/agents/:category` | 搜索、分类、卡片、详情 |

### 5.3 全局与复合界面

- 可折叠、可调宽度的 Unified Sidebar。
- 会话搜索、收藏、书签、项目和历史列表。
- 设置中心。
- Agent/模型选择器。
- 文件上传和“我的文件”。
- Skills 侧边栏面板：搜索、创建入口、“我的 Skills”列表和状态展示。
- Memories 侧边栏面板：搜索、创建入口、使用量、引用开关和记忆卡片管理。
- Artifact 代码/预览面板。
- 分享、导入导出、语音、主题和快捷键。

## 6. 页面借鉴决策矩阵

| Agentic 目标 | 借鉴级别 | 学习内容 | 保留或限制 |
| --- | --- | --- | --- |
| 全局应用框架 | 高 | 图标窄栏、展开面板、宽度拖动、移动抽屉 | 保留任务语义和运行状态 |
| 新建任务首页 | 高 | 动态问候、Agent 身份、居中输入区、建议问题 | 不引入与业务无关的模型选项 |
| 任务会话 | 高但选择性 | 消息间距、悬浮操作、输入器、滚动、附件和状态 | 保留 Plan、Thinking、Tool、Trace、VNC、右侧预览 |
| 全局搜索 | 高 | 跨会话搜索、匹配高亮、结果定位、无限加载 | 搜索范围扩展到任务、工具、Trace、文件 |
| 设置中心 | 高 | 分组导航、卡片层级、开关、危险操作、响应式 | 按个人配置与系统能力拆分 |
| 文件管理 | 中高 | 上传状态、文件卡片、预览、空状态 | 保留 Agentic 更完整的目录与存储能力 |
| Artifact/产物面板 | 中高 | 代码/预览切换、下载、版本、面板交互 | 与现有文件和工具预览整合 |
| Project | 中高 | 卡片、搜索排序、项目工作区、项目内任务 | 等待任务分组数据模型 |
| Prompt | 中 | 模板列表、变量、预览、版本 | 确认模板复用需求后实施 |
| Agent 市场 | 中低 | 搜索、分类、Agent 卡片、详情 | 多 Agent Profile 成熟后实施 |
| Skill | 中 | 侧边栏入口、搜索、列表、详情、编辑和启停状态 | Skill 数据模型成熟后实施；当前只记录 UI 方案 |
| 用户长期记忆 | 中 | 侧边栏入口、搜索、使用量、引用状态、记忆卡片和编辑/删除 | 与 Knowledge、Session 内部记忆分离；当前只记录 UI 方案 |
| 分享页面 | 低到中 | 只读任务、复制链接、过期状态 | 依赖权限、脱敏和审计机制 |
| 完整认证 | 低到中 | 忘记密码、2FA、OAuth、验证状态 | 不做无后端支撑的空壳页 |

## 7. 目标信息架构

### 7.1 第一阶段目标路由

```text
/auth
/
/sessions/:id
/search
/files
```

第一阶段新增的正式路由只有 `/search`，其余主要是现有页面的视觉和结构改造。

### 7.2 后续候选路由

仅在对应数据模型落地后启用：

```text
/projects
/projects/:id
/prompts
/prompts/new
/prompts/:id
/agents
/agents/:id
/skills
/skills/:id
/skills/marketplace
/share/:id
```

### 7.3 目标应用外壳

桌面端：

```text
┌────────┬──────────────────────┬──────────────────────────────┐
│ 52px   │ 可展开/调宽的侧栏    │ 主页面                       │
│ 图标栏 │ 搜索/项目/任务历史   │ 首页、会话、搜索、文件       │
└────────┴──────────────────────┴──────────────────────────────┘
```

任务会话打开预览时：

```text
┌────────┬────────────────────┬──────────────────┐
│ 侧栏   │ 对话与执行时间线   │ 文件/工具/Trace  │
│        │ Plan + Composer    │ 详情预览         │
└────────┴────────────────────┴──────────────────┘
```

移动端：

- 侧栏变为带遮罩的抽屉。
- 右侧预览变为全屏 Sheet 或底部 Sheet。
- 主输入器始终保持可见。
- VNC 保持全屏模式。

### 7.4 后续侧边栏上下文面板：Skills 与记忆

本节只定义未来 UI 信息架构，不在当前阶段新增导航入口、正式路由、API 调用、静态占位页或业务逻辑。待对应能力具备真实数据和权限边界后，再将入口加入 `SidebarRail` 并接入可展开侧栏面板。

参考实现：

- `../LibreChat/client/src/hooks/Nav/useSideNavLinks.ts`
- `../LibreChat/client/src/components/Skills/sidebar/SkillsSidePanel.tsx`
- `../LibreChat/client/src/components/Skills/sidebar/SkillsAccordion.tsx`
- `../LibreChat/client/src/components/SidePanel/Memories/MemoryPanel.tsx`
- `../LibreChat/client/src/components/SidePanel/Memories/MemoryCard.tsx`

#### Skills 面板

侧边栏 Rail 使用 `ScrollText` 图标。点击后，展开区域从任务历史切换为 Skills 上下文面板；再次点击当前入口可收起侧栏，行为与 LibreChat 的 Unified Sidebar 保持一致。

建议视觉结构：

```text
Skills
  搜索                         新建

  我的 Skills
    Skill 名称
    一行能力摘要                 已启用
    Skill 名称
    一行能力摘要                 已停用
```

- 面板头部显示标题、搜索按钮和创建入口。
- 搜索展开后使用行内输入框，并提供明确的关闭按钮。
- 主体使用可滚动列表；列表项优先展示名称、简短描述和启停状态。
- 当前选中项使用语义 Active 状态，不只依赖颜色表达。
- 预留 Loading、Empty、Filtered Empty、Error 和无访问权限状态。
- 创建、编辑、启停和调用方式属于未来逻辑，本阶段不实现。

#### 用户长期记忆面板

侧边栏 Rail 使用 `Brain` 图标。记忆面板用于未来管理用户主动保存、可查看和可删除的长期信息，不等同于 Knowledge 知识库，也不直接展示 `sessions.memories` 中的 Agent 内部运行状态。

建议视觉结构：

```text
记忆
  搜索                         新建
  使用量 42%              引用已保存记忆

  偏好
    默认使用中文，回答保持简洁
                                      编辑 · 删除

  工作背景
    当前负责 Agentic 产品研发
                                      编辑 · 删除
```

- 顶部提供搜索和创建入口。
- 辅助控制区展示容量/使用量，并预留“是否引用已保存记忆”的状态控件。
- 记忆以卡片列表展示，突出简短标题与内容摘要。
- 编辑和删除使用次级操作；删除需在未来实现时提供明确确认。
- 列表较长时使用分页或增量加载，不在侧栏中无限堆叠。
- 预留 Loading、Empty、Filtered Empty、Error 和无访问权限状态。
- 自动提取、记忆写入、Token 统计和偏好同步属于未来逻辑，本阶段不实现。

#### 响应式与可访问性

- 桌面端复用现有 Rail + 可调宽 Panel，不另开第三层固定侧栏。
- 移动端在现有侧栏抽屉内切换上下文；进入详情或编辑时使用全屏 Sheet。
- Rail 按钮必须提供 `aria-label`、`aria-current` 或 `aria-pressed`。
- 搜索、列表数量、空状态和保存结果通过可读文本或 Live Region 表达。
- Skills 与记忆入口仅在能力真实可用时显示，不提前提供不可操作的“即将推出”入口。

## 8. 设计系统改造

### 8.1 语义颜色

逐步用以下语义变量替换散落在 `style.css` 和组件 Scoped CSS 中的十六进制颜色：

```css
:root {
  --surface-primary: #ffffff;
  --surface-secondary: #f7f7f5;
  --surface-tertiary: #f0f1f2;
  --surface-hover: #ececea;
  --surface-active: #e5e5e2;

  --text-primary: #171717;
  --text-secondary: #666b73;
  --text-tertiary: #9297a0;

  --border-light: #eceef0;
  --border-medium: #d9dde3;
  --border-heavy: #b6bcc5;

  --accent-primary: #111827;
  --status-success: #16803c;
  --status-warning: #b76b00;
  --status-danger: #c83232;
  --status-info: #2563eb;
}
```

实际颜色允许在视觉阶段调整，但变量命名和使用边界应稳定。

### 8.2 Element Plus 映射

| 交互 | Vue 实现 |
| --- | --- |
| 设置与编辑弹窗 | `ElDialog` |
| 移动端侧栏/预览 | `ElDrawer` 或自有 Sheet |
| 菜单 | `ElDropdown` |
| 悬浮提示 | `ElTooltip` |
| 工具与附件选择 | `ElPopover` |
| 分类切换 | `ElTabs` 或语义化按钮组 |
| 表单 | `ElForm`、`ElInput`、`ElSelect`、`ElSwitch` |
| 文件分页 | `ElPagination` |
| 操作反馈 | 现有 `useToast`，底层可继续使用 Element Plus |

### 8.3 推荐目录结构

目录按实际实施逐步迁移，不要求一次性重排：

```text
web/src/
├── layouts/
│   └── AppShell.vue
├── components/
│   ├── navigation/
│   │   ├── UnifiedSidebar.vue
│   │   ├── SidebarRail.vue
│   │   ├── SidebarPanel.vue
│   │   ├── SessionSearch.vue
│   │   └── SessionSections.vue
│   ├── chat/
│   │   ├── ChatComposer.vue
│   │   ├── ChatMessage.vue
│   │   ├── PlanPanel.vue
│   │   └── ...
│   ├── preview/
│   │   ├── PreviewShell.vue
│   │   ├── FilePreviewPanel.vue
│   │   ├── ToolPreviewPanel.vue
│   │   └── TracePanel.vue
│   └── settings/
│       ├── SettingsDialog.vue
│       ├── PersonalSettings.vue
│       ├── AgentSettings.vue
│       ├── ToolSettings.vue
│       └── ConnectionSettings.vue
├── views/
│   ├── HomeView.vue
│   ├── SessionView.vue
│   ├── SearchView.vue
│   └── FilesView.vue
└── styles/
    ├── tokens.css
    ├── themes.css
    └── utilities.css
```

## 9. 分阶段实施计划

### Phase UI-0：视觉基础

状态：进行中（基础 Token 与通用控件已落地，待主要页面暗色视觉回归）

目标：建立后续页面共同使用的视觉语言，不改变业务行为。

任务：

- [x] 新建语义颜色 Token。
- [x] 建立浅色和暗色主题变量。
- [x] 整理字体、字号、行高、圆角、阴影和间距。
- [x] 将 Element Plus 主题变量映射到语义 Token。
- [x] 统一 Button、Icon Button、Card、Input、Empty、Loading、Error 状态。
- [x] 避免继续在新组件中增加硬编码颜色。

主要实现文件：

- `web/src/styles/tokens.css`
- `web/src/styles/themes.css`
- `web/src/styles/ui.css`
- `web/src/style.css`
- `web/src/components/chat/chat.css`
- `web/src/components/ui/UiButton.vue`
- `web/src/components/ui/UiIconButton.vue`
- `web/src/components/ui/UiTextField.vue`
- `web/src/components/ui/UiState.vue`
- `web/src/views/FilesView.vue`
- `web/src/views/SearchView.vue`
- `web/src/components/FilePreviewPanel.vue`
- `web/src/components/SessionDetailView.vue`
- `web/src/components/TracePanel.vue`

当前说明：新应用外壳、首页、搜索、文件、设置和主要执行状态已使用语义 Token。原有 `.button` / `.icon-button` 继续作为兼容类，新增页面优先使用 `UiButton`、`UiIconButton`、`UiTextField` 和 `UiState`，避免重复实现可访问性与交互状态。文件中心的浅色硬编码已迁移为语义变量；低频旧组件中的既有硬编码颜色仍按页面阶段渐进迁移。

验证记录（2026-07-15）：`pnpm build` 已通过，包含 `vue-tsc -b` 与 Vite 生产构建；`git diff --check` 已通过。静态检查确认新 `UiIconButton` 必须提供可读 `label`，Loading 与 Error 状态分别使用 Live Region 和 Alert 语义。当前浏览器控制环境仍无可用实例，浅色/暗色以及桌面/移动端截图式回归待补充，因此阶段状态保持“进行中”。

验收标准：

- 首页、会话、文件、设置共享同一套颜色和控件规范。
- 浅色模式没有明显视觉回归。
- 暗色模式下主要页面可读、边界明确。
- 桌面和移动端均无横向页面溢出。

### Phase UI-1：统一侧栏和应用外壳

状态：进行中（主体交互已落地，待浏览器响应式与焦点回归）

参考：`../LibreChat/client/src/components/UnifiedSidebar/`。

任务：

- [x] 将当前 `LeftPanel.vue` 拆分为 Rail、Panel、Sections。
- [x] 收起后保留约 56px 图标栏。
- [x] 展开宽度可拖动，限制最小/最大宽度。
- [x] 使用 `localStorage` 保存用户选择的宽度和展开状态。
- [x] 新增任务、文件、任务搜索、设置入口。
- [x] 将设置和账号作为两个独立入口收口到侧栏底部，并移除页面头部的重复入口。
- [x] 历史任务支持按时间分组。
- [x] 移动端改为抽屉，并支持 Escape 和遮罩关闭。
- [x] 拖动分隔条支持键盘左右键调整。

主要实现文件：

- `web/src/components/LeftPanel.vue`
- `web/src/components/navigation/SidebarRail.vue`
- `web/src/components/navigation/SidebarPanel.vue`
- `web/src/components/navigation/SessionSections.vue`
- `web/src/components/SessionList.vue`
- `web/src/components/SettingsButton.vue`
- `web/src/components/UserMenu.vue`
- `web/src/App.vue`

决策记录：UI-1 初次落地时，侧栏搜索仅过滤已加载的任务标题和最近消息；Phase UI-4 完成后已升级为 `/search` 全局搜索，查询范围覆盖跨任务消息、Tool、Trace 和文件，侧栏输入框与搜索页通过 URL 查询状态同步。设置入口与账号入口固定在侧栏底部并彼此独立；账号入口展开后显示当前身份与退出登录操作，页面头部仅保留当前页面或任务相关操作。

验收标准：

- 收起状态仍可访问主要入口。
- 桌面端可拖动且刷新后保持宽度。
- 移动端打开侧栏时主内容不可误操作。
- 新建任务、任务切换和文件入口行为保持不变。

### Phase UI-2：首页与输入器

状态：进行中（首页与 Composer 第一版视觉已落地）

参考：

- `../LibreChat/client/src/components/Chat/Landing.tsx`
- `../LibreChat/client/src/components/Chat/Input/ChatForm.tsx`

任务：

- [x] 欢迎语根据时间和用户名生成。
- [x] 预留当前 Agent 名称、图标和简介位置。
- [x] 统一首页与会话页的 Composer 外观和交互。
- [x] 保留附件上传、进度、失败重试和删除。
- [x] 优化建议问题为轻量快捷入口。
- [x] 输入框自动增高并设置合理最大高度。
- [x] 明确发送、停止、禁用和上传中状态。
- [ ] 支持草稿保存时再增加草稿状态提示。

主要实现文件：

- `web/src/views/HomeView.vue`
- `web/src/components/chat/ChatComposer.vue`
- `web/src/components/chat/ChatInput.vue`
- `web/src/components/SuggestedQuestions.vue`
- `web/src/config/app.config.ts`

验证记录（2026-07-15）：`pnpm build` 已通过，包含 `vue-tsc -b` 与 Vite 生产构建。本地浏览器运行时当次无可用会话，桌面、平板和 360px 的截图式视觉回归尚待补充，因此 UI-0、UI-1、UI-2 暂不标记为“已完成”。

验收标准：

- 首屏在常见桌面高度下保持视觉居中。
- 输入器在首页和会话页操作一致。
- 中文输入法组合输入期间不会误发送。
- 上传和任务创建失败均有可恢复反馈。

### Phase UI-3：任务执行工作台

状态：进行中（工作台第一版视觉已落地，待真实运行会话视觉回归）

任务：

- [x] 统一用户消息、Assistant 消息、错误消息和系统状态的视觉层级。
- [x] 增加复制、重试等悬浮操作，并保证触屏可访问。
- [x] 优化 Plan 折叠、当前步骤和完成进度。
- [x] 优化 Thinking 与 Tool Call 的状态颜色和层级。
- [x] 统一 File、Tool、Trace 右侧面板外壳。
- [x] 桌面端支持合理的面板宽度；移动端使用全屏/Sheet。
- [x] 保留跳到底部、自动滚动和用户主动向上浏览逻辑。
- [x] 完善 Streaming、Stopped、Failed、Retrying 状态。
- [ ] 评估 Artifact 的代码/预览切换，但不替代现有文件模型。

主要实现文件：

- `web/src/components/SessionDetailView.vue`
- `web/src/components/SessionHeader.vue`
- `web/src/components/chat/ChatMessage.vue`
- `web/src/components/chat/PlanPanel.vue`
- `web/src/components/chat/ThinkingBlock.vue`
- `web/src/components/chat/ToolCallCard.vue`
- `web/src/components/FilePreviewPanel.vue`
- `web/src/components/chat/ToolPreviewPanel.vue`
- `web/src/components/TracePanel.vue`
- `web/src/components/chat/chat.css`
- `web/src/components/chat/tool-preview.css`

决策记录：桌面宽屏使用 `clamp(420px, 40vw, 640px)` 控制预览宽度；901–1100px 改为右侧覆盖面板，避免同时打开侧栏和预览时过度挤压对话；900px 以下沿用全屏文件/Trace 与底部 Tool Sheet。当前继续使用文件、Tool 和 Trace 三套业务组件，只统一外壳与状态语义，不为视觉复用强行合并数据模型。

验证记录（2026-07-15）：`pnpm build` 已通过。运行中工具自动打开预览、主动向上浏览不跟随滚动、VNC 返回后恢复最新工具等原有逻辑未改动。真实 SSE 运行会话、失败会话和移动触屏视觉回归仍待浏览器环境可用后补充，因此暂不标记为“已完成”。

验收标准：

- 任务运行时用户能区分计划、模型输出、工具执行和最终回答。
- 打开预览不会丢失对话滚动位置。
- 多个工具事件不会造成严重页面跳动。
- Trace、VNC、文件和工具预览功能完整保留。

### Phase UI-4：全局搜索

状态：进行中（前后端链路已落地，待真实数据与浏览器视觉回归）

参考：`../LibreChat/client/src/routes/Search.tsx`。

目标路由：`/search`。

建议搜索对象：

- Session 标题。
- 用户问题。
- Assistant 回复。
- Tool Call 名称和摘要。
- Trace 事件摘要。
- 生成文件名称。

任务：

- [x] 明确后端搜索 API 和分页方式。
- [x] 新增 `SearchView.vue`。
- [x] 侧栏搜索框与搜索页面共享查询状态。
- [x] 结果展示 Session、片段、时间、内容类型。
- [x] 高亮匹配文本。
- [x] 点击后进入 `/sessions/:id` 并定位消息/事件。
- [x] 完成加载、无结果、失败和分页状态。

后端协议：

```text
GET /api/search?q={query}&current_page=1&page_size=20
```

搜索结果由 PostgreSQL 在单次查询中合并 Session、Session Message、Tool Call、Trace Event 和 File，统一按时间倒序并使用 `count(*) over()` 返回总数。所有查询分支都必须包含当前认证用户的 `user_id` 条件；Tool 与 Trace 通过 `agent_runs.user_id` 校验归属，不接受前端传入用户标识。

主要实现文件：

- `api/app/controllers/search.py`
- `api/app/services/search_service.py`
- `api/app/repositories/search_repository.py`
- `api/app/repositories/db_search_repository.py`
- `api/app/schemas/search.py`
- `api/tests/app/services/test_search_service.py`
- `web/src/views/SearchView.vue`
- `web/src/lib/api/search.ts`
- `web/src/router/index.ts`
- `web/src/components/navigation/SidebarRail.vue`
- `web/src/components/navigation/SidebarPanel.vue`
- `web/src/components/SessionDetailView.vue`
- `web/src/lib/session-events.ts`

决策记录：查询状态使用 `/search?q=...&page=...` 保存，侧栏输入框与搜索页面通过 URL 同步；输入防抖为 320ms。搜索结果不返回完整 Tool 参数或文件内容，只返回已持久化的脱敏摘要与文件元数据。点击消息、工具或可定位的 Trace 结果时使用 `focus` 查询参数滚动到对应事件，并进行短暂焦点高亮。

验证记录（2026-07-15）：搜索服务单元测试 2 项通过；真实 PostgreSQL 已使用无匹配的隔离用户和查询词执行 SQL 冒烟测试，语句与分页参数可正常运行；`pnpm build` 已通过。真实用户数据的结果相关性、移动端视觉和屏幕阅读器回归仍待浏览器环境可用后补充，因此暂不标记为“已完成”。

验收标准：

- 搜索结果不会跨用户泄露。
- 查询有防抖并支持分页。
- 点击结果可定位到对应任务上下文。
- 键盘和屏幕阅读器能获知结果数量及加载状态。

### Phase UI-5：设置中心重构

状态：进行中（领域拆分与交互保护已落地，待浏览器视觉回归）

建议分类：

```text
个人
  主题 / 语言 / 消息显示 / 快捷键

模型
  Provider / Model / Temperature / Token

Agent
  最大迭代 / 重试 / 能力预检 / 执行策略

Tools
  API Tools / 风险 / 启停 / 测试

外部连接
  MCP / A2A

存储
  Local / COS / OSS

系统
  版本 / 诊断 / 缓存
```

任务：

- [x] 拆分当前大型 `SettingsModal.vue`。
- [x] 区分个人偏好与系统/运行时配置。
- [x] 保留现有所有保存、测试、删除和启停能力。
- [x] 为危险操作提供独立确认和明确后果说明。
- [x] 小屏幕改为一级分类列表＋二级详情，而不是挤压双栏。

主要实现文件：

- `web/src/components/SettingsModal.vue`
- `web/src/components/StorageSettings.vue`
- `web/src/components/settings/SettingsAppearancePanel.vue`
- `web/src/components/settings/SettingsGeneralPanel.vue`
- `web/src/components/settings/SettingsModelPanel.vue`
- `web/src/components/settings/SettingsApiToolsPanel.vue`
- `web/src/components/settings/SettingsA2aPanel.vue`
- `web/src/components/settings/SettingsMcpPanel.vue`
- `web/src/components/settings/types.ts`
- `web/src/lib/theme.ts`
- `web/src/main.ts`
- `web/src/style.css`

决策记录：设置外壳只负责分类导航、统一保存、关闭保护和移动端一级/二级切换，各领域组件自行加载并维护保存状态。Agent、模型、存储和 API Operation 使用显式保存；A2A、MCP 与 API Provider 的启停沿用即时生效。切换分类、返回移动端分类列表或关闭设置时，如当前表单存在未保存修改，会明确询问是否放弃。删除 API Provider、MCP 服务器和 A2A Agent 前展示影响范围并二次确认，历史运行记录不会随连接配置删除。

个人偏好当前只实现有真实行为支撑的主题选择，并通过 `localStorage` 在启动时恢复“跟随系统 / 浅色 / 深色”。语言、消息显示和快捷键尚无国际化或偏好数据基础，不创建不可用的空壳选项。API Key 与存储密钥继续使用密码输入，不写入前端日志；保存失败时组件不替换编辑态，用户输入会保留以便重试。

验证记录（2026-07-15）：`pnpm build` 已通过，包含 `vue-tsc -b` 与 Vite 生产构建；`git diff --check` 已通过。当前浏览器控制环境未发现可用浏览器实例，桌面、平板、360px 移动端以及确认弹窗的截图式交互回归仍待补充，因此暂不标记为“已完成”。

验收标准：

- 设置组件按领域拆分，单个文件职责清晰。
- 切换分类不会丢失尚未保存的修改，或有明确提示。
- 保存失败时能够恢复或保留用户输入。
- API Key 等敏感信息不出现在日志和页面明文中。

### Phase UI-6：资源型页面

状态：条件实施

#### Project

依赖：Session 分组或 Project 数据模型。

- 项目列表。
- 搜索和排序。
- 项目内任务列表。
- 从项目创建任务。

#### Prompt

依赖：Prompt 模板模型和执行入口。

- 模板列表和分类。
- Prompt 编辑器。
- 变量定义和预览。
- 版本或更新时间展示。

#### Agent Profile / Agent 市场

依赖：`agent_profiles` 等多 Agent 模型。

- Agent 列表、搜索、分类。
- Agent 详情和能力摘要。
- 创建任务时选择 Agent。
- 用户自建 Agent 与系统 Agent 的边界。

#### Skill

依赖：Skill 数据模型和运行时调用约定。

- 按 7.4 节增加侧边栏 Rail 入口和 Skills 上下文面板。
- Skill 列表、详情、编辑和启停。
- 自动/手动调用模式。
- Skill 与 Agent Profile 的关联。

#### 用户长期记忆

依赖：用户级长期记忆数据模型、容量策略和权限边界。

- 按 7.4 节增加侧边栏 Rail 入口和记忆上下文面板。
- 搜索、创建、编辑和删除记忆。
- 展示使用量和是否引用已保存记忆。
- 与 Knowledge 知识库、Session 内部记忆保持概念和入口分离。

这些页面和侧边栏面板不得只因为 LibreChat 存在就提前创建静态 UI。

## 10. 可访问性和响应式要求

所有改造阶段共同遵循：

- Icon Button 必须有 `aria-label` 或可见文本。
- 当前导航项使用 `aria-current="page"`。
- Dialog、Drawer 打开后需要焦点约束和关闭后焦点恢复。
- Streaming、搜索结果数量、错误等重要变化通过 Live Region 通知。
- 侧栏拖动条使用 `role="separator"`，并支持键盘。
- 移动端抽屉打开时，主内容使用 `inert` 或等效焦点隔离。
- 动画尊重 `prefers-reduced-motion`。
- 颜色不能作为状态的唯一表达方式。
- 触摸目标建议不小于 40px。
- 360px 宽度下不得出现非预期横向滚动。

## 11. 性能要求

- Streaming 时避免导致整个应用外壳或侧栏重新渲染。
- 大量历史 Session 应使用游标分页或增量加载。
- 只有数据规模确实造成性能问题时才引入虚拟列表。
- Markdown、代码高亮和大型工具输出应按需渲染。
- 文件、Tool、Trace 面板关闭后清理对象 URL、监听器和 VNC 连接。
- 侧栏拖动使用 `requestAnimationFrame` 或等效节流。
- 不因主题 Token 改造增加大量重复 Scoped CSS。

## 12. 授权与品牌边界

仓库内 LibreChat 使用 MIT License，可以依法参考和修改代码；若复制了具有实质性的代码片段，应保留相应版权与许可证声明。

产品层面仍建议：

- 学习交互模式而不是逐像素复制。
- 使用 Agentic 自己的名称、图标和品牌颜色。
- 保留 Agentic 的任务执行工作台差异。
- 不复制 LibreChat 商标、Logo、产品文案和演示数据。

## 13. 后续实施维护规则

每完成一个 Phase：

1. 将阶段状态从“待实施”更新为“进行中”或“已完成”。
2. 勾选实际完成项，不把未落地内容写成完成。
3. 在对应阶段补充主要实现文件。
4. 记录与本文方案不同的决策及原因。
5. 运行前端类型检查和生产构建。
6. 验证桌面端、平板和 360px 移动端。
7. 验证登录、首页、运行中会话、失败会话、文件和设置等关键路径。

建议验证命令：

```powershell
cd agentic/web
pnpm build
```

当前 `pnpm build` 会先运行 `vue-tsc -b`，再执行 Vite 生产构建。如果后续脚本发生变化，以 `web/package.json` 为准并同步修正文档。

## 14. 决策摘要

| 决策 | 结论 |
| --- | --- |
| 是否切换 React | 否 |
| 是否保留 Vue 3 | 是 |
| 是否直接复制 LibreChat 页面代码 | 否，按 Vue 组件重新实现 |
| 第一优先级 | 设计 Token、统一侧栏、首页和 Composer |
| 最重要新增页面 | 全局搜索 |
| 会话页改造策略 | 选择性学习，保护 Agent 执行工作台 |
| Skill | 已完成个人管理、Creator、运行时选择、Trace 与 Marketplace；后续只做增量体验优化 |
| Project/Prompt/Agent/用户长期记忆 | 数据模型就绪后条件实施；当前仅保留 UI 信息架构 |
| 设置中心 | 拆分个人设置与系统能力管理 |
| 文件中心 | 保留现有独立页面，只吸收交互细节 |
