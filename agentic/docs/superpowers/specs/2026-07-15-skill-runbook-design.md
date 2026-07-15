# Agent Skills / Runbook 设计方案

日期：2026-07-15
状态：已确认方向，待实施

## 1. 目标

在不引入多 Agent Profile、DAG Workflow 或通用审批流的前提下，为当前单 Agent 增加可复用、可移植、可追踪的专业能力：

- 严格遵循开放的 Agent Skills `SKILL.md` 能力包格式。
- 同时支持用户手动选择和 Agent 自动识别 Skill。
- 支持个人 Skill、系统内置 Skill 和全局市场 Skill。
- Skill 包内容存储在文件/对象存储中，数据库只保存基础信息、版本、安装关系和运行记录。
- 每个用户的 Skill Workspace、草稿、安装和运行时物化目录互相隔离。
- Skill 仍由现有 Planner / ReAct 自主执行；Runbook 是 Markdown 指导，不是流程引擎。
- Skill 使用情况进入 Run / Trace，能够复盘选择来源、版本和内容哈希。

规范依据：

- Agent Skills Specification：https://agentskills.io/specification
- Agent Skills reference implementation：https://github.com/agentskills/agentskills
- LibreChat 本地参考：`D:/AI/LibreChat/packages/api/src/skills/`、`D:/AI/LibreChat/packages/data-schemas/src/schema/skill.ts`
- OpenSquilla 本地参考：`D:/AI/opensquilla/src/opensquilla/skills/loader.py`
- OpenClaw 官方参考：https://docs.openclaw.ai/tools/creating-skills

## 2. 分阶段边界

这项能力拆成三个可独立验收的阶段。

### 阶段 A：Skill Runtime Foundation

- 标准 Skill 包解析、校验、导入和版本化。
- 个人 Skill CRUD、启停和用户隔离。
- 手动 `$skill-name` 选择。
- 基于 LLM 的自动选择。
- Skill 正文注入 Planner / ReAct。
- Skill 包物化到当前 Session Sandbox。
- Run / Trace 记录。
- Skills 侧边栏、管理页和输入器选择器。

### 阶段 B：Skill Creator

- 内置、只读的 `skill-creator` 标准 Skill。
- 用户隔离的草稿 Workspace。
- AI 创建、校验、预览和发布。
- 文件树与 Markdown 编辑。

### 阶段 C：Skill Marketplace

- 全局市场目录。
- 市场 Skill 的不可变版本与云端包。
- 用户安装、启停、固定版本、更新和卸载。
- 编辑市场 Skill 时 Fork 为个人 Skill。
- 首版市场内容通过管理员脚本导入，不建设支付、评分、评论和开放发布审核。

## 3. 不做的内容

- 不创建自有 Skill 正文协议。
- 不增加自定义顶层 frontmatter 字段。
- 不实现 Workflow DAG、步骤调度器、回滚、SLA 或人工审批。
- 不依赖 Agent Profile。
- 不把 Skill 当成新的可执行权限边界；Sandbox 与现有 ToolConfig 仍是安全边界。
- 不允许 Skill 的 `allowed-tools` 自动启用用户已禁用的工具。
- 不把个人 Skill 正文重复保存到数据库 JSONB。
- 第一轮不做 GitHub 自动同步、跨部署公共 SaaS 市场或 Skill 付费交易。

## 4. 标准 Skill 包

每个 Skill 是一个目录，至少包含 `SKILL.md`：

```text
report-writer/
├── SKILL.md
├── scripts/
├── references/
└── assets/
```

`SKILL.md` 仅接受官方字段：

```yaml
---
name: report-writer
description: Create evidence-based reports. Use when the user asks for a structured research or analysis report.
license: Apache-2.0
compatibility: Requires Python 3.12 and optional network access.
metadata:
  author: agentic
  version: "1.0"
allowed-tools: search_web read_file write_file
---

# Instructions

Produce reports whose claims are traceable to evidence. Confirm the goal and audience, prefer primary sources, separate facts from inference, and state material uncertainty.

## Runbook

1. Clarify the report goal and audience when missing.
2. Collect and verify sources.
3. Draft the report.
4. Validate citations and deliver the artifact.
```

约束：

- `name` 必填，1–64 字符，只允许小写字母、数字和连字符，不能以连字符开头或结尾。
- `description` 必填，1–1024 字符，必须同时说明能力与触发场景。
- `license`、`compatibility`、`metadata`、`allowed-tools` 按官方规范解析。
- `metadata` 只接受字符串键值。
- Skill 目录名必须等于 `name`。
- Runbook 写在 Markdown 正文中，不解析成平台专有步骤模型。
- `scripts/`、`references/`、`assets/` 按需加载，不在启动时注入上下文。

渐进加载：

1. Catalog 阶段只加载 `name`、`description`、来源、版本和兼容性摘要。
2. Skill 被手动或自动选中后才读取完整 `SKILL.md`。
3. 附属文件只在执行时物化到 Sandbox，由 Agent 按相对路径读取或运行。

## 5. 总体架构

```text
Bundled Skills ───────────────┐
                             │
Personal Skill Metadata ─────┼─> SkillCatalogService
Personal Version Archives ───┤          │
                             │          ├─ manual selections
Marketplace + Installations ─┘          └─ SkillSelectionService (LLM)
                                                │
                                                v
                                     SelectedSkillContext
                                      │        │       │
                                      │        │       └─ RunSkill / Trace
                                      │        └─ Planner / ReAct prompt context
                                      └─ Sandbox materialization
```

核心边界：

- `SkillPackageParser`：只负责解析标准 `SKILL.md`。
- `SkillPackageValidator`：只负责规范、路径和包限制校验。
- `SkillPackageStorage`：只负责版本包的对象存储读写。
- `SkillWorkspaceService`：只负责用户草稿与 Sandbox 物化。
- `SkillRepository`：只负责元数据、版本和安装关系。
- `SkillCatalogService`：合并 bundled、个人和已安装市场 Skill。
- `SkillSelectionService`：解析手动选择并让 LLM 自动补选。
- `SkillRuntimeService`：加载正文、检查工具可用性、生成运行时上下文。
- `SkillService`：编排个人 Skill 和市场安装 API。

## 6. 数据模型

### 6.1 `skills`

```text
id                    UUID/string PK
owner_user_id         nullable FK users.id
name                  varchar(64)
display_name          varchar(128)
description           text
scope                 personal | marketplace
status                draft | active | archived
enabled               bool
auto_invoke           bool
current_version_id    nullable FK skill_versions.id
forked_from_skill_id  nullable FK skills.id
forked_from_version_id nullable FK skill_versions.id
created_at
updated_at
```

- 个人 Skill 必须有 `owner_user_id`。
- 市场 Skill 对所有已登录用户可见，但只有安装后才进入运行时 Catalog。
- 同一用户的个人 Skill 名称唯一。
- 活跃市场 Skill 名称全局唯一。
- `display_name` 仅用于 UI，不进入标准包触发逻辑。

### 6.2 `skill_versions`

```text
id                    UUID/string PK
skill_id              FK skills.id
version               int
manifest              JSONB（标准 frontmatter + 文件清单）
storage_provider      local | qcloud_cos | aliyun_oss
storage_key           text
storage_config        JSONB（不含密钥的定位快照）
package_sha256        char(64)
package_size          bigint
file_count            int
status                draft | published
changelog             text
created_by_user_id    nullable FK users.id
created_at
```

- 发布版本不可原地修改。
- 包内容是标准 Skill 目录的确定性 `.skill` ZIP。
- 数据库 manifest 用于快速 Catalog 和校验结果展示，不是正文真源。

### 6.3 `skill_installations`

```text
id                    UUID/string PK
user_id               FK users.id
skill_id              FK skills.id
pinned_version_id     FK skill_versions.id
enabled               bool
auto_invoke           bool
auto_update           bool
installed_at
updated_at
```

- 只用于市场 Skill。
- 安装默认固定到明确版本，确保 Run 可复现。
- `auto_update` 首版默认关闭。

### 6.4 `run_skills`

```text
id                    UUID/string PK
run_id                FK agent_runs.id
skill_id              nullable FK skills.id
skill_version_id      nullable FK skill_versions.id
name                  varchar(64)
source                bundled | personal | marketplace
selection_mode        manual | automatic
content_sha256        char(64)
confidence            nullable numeric
reason                text
sandbox_path          text
created_at
```

Bundled Skill 没有数据库 Skill ID，因此 `skill_id`、`skill_version_id` 可为空，但必须记录名称、内容哈希和来源。

## 7. 存储与 Workspace 隔离

### 7.1 内容真源

- 发布后的 Skill 版本包是唯一内容真源。
- 个人包使用当前用户配置的 local / COS / OSS Provider。
- 市场包使用部署级市场存储配置，避免依赖发布者后续修改个人存储凭证。
- 本地开发默认存放到 `/app/storage/skills/packages`，由现有 `api_storage` Volume 持久化。

### 7.2 草稿 Workspace

```text
/app/storage/skill-workspaces/
└── users/
    └── <user_id>/
        └── <draft_id>/
            └── <skill-name>/
                ├── SKILL.md
                ├── scripts/
                ├── references/
                └── assets/
```

- `user_id` 只取认证上下文，不接受客户端传入。
- 所有路径先 `resolve()`，再验证仍位于当前用户草稿根目录。
- 草稿发布时生成确定性 ZIP、计算 SHA-256、上传对象存储并创建不可变版本。
- 发布成功后可清理草稿；失败保留草稿和校验结果。

### 7.3 Sandbox Workspace

```text
/home/ubuntu/.agentic/skills/
└── <run_id>/
    └── <skill-name>/
        ├── SKILL.md
        ├── scripts/
        ├── references/
        └── assets/
```

- 只物化当前 Run 选中的 Skill。
- Personal 缓存按 `user_id + package_sha256` 隔离；Marketplace/Bundled 可按哈希共享 API 侧只读缓存。
- Sandbox 中是一次性副本，Agent 修改副本不会修改云端版本。
- Session Sandbox 已按会话隔离；服务端仍要验证 Session 属于当前用户。
- Run 完成后无需同步回 Skill 包；Sandbox 销毁时统一清理。

## 8. 包安全与限制

默认限制：

```text
上传压缩包最大             50 MiB
解压后总大小最大          100 MiB
文件数量最大              256
单文件最大                 10 MiB
SKILL.md 最大             256 KiB
相对路径最大              240 字符
手动选择 Skill 最大        5
自动选择 Skill 最大        3
单 Run 合计 Skill 最大     5
自动选择候选 Catalog 最大  100
```

导入必须拒绝：

- 绝对路径、`..`、空路径段和反斜杠混淆。
- ZIP Slip、符号链接、硬链接和设备文件。
- 大小写折叠后重复的路径。
- 多个根目录或缺少根级 `SKILL.md`。
- 目录名与 frontmatter `name` 不一致。
- 非 UTF-8 `SKILL.md`、非法 YAML 或不符合官方字段约束。

脚本不在 API 主机执行，只能在 Session Sandbox 中由现有工具执行。

## 9. 选择与触发

### 9.1 手动触发

- 输入器支持 `$` 打开 Skill 选择器。
- 前端发送稳定的 Skill 引用，不依赖从消息文本再次解析。
- 手动选择优先级最高，不被自动选择覆盖。
- 服务端验证 Skill 属于当前用户、是 bundled，或是当前用户已安装的市场 Skill。

### 9.2 自动触发

自动选择采用小型两阶段流程：

1. `SkillCatalogService` 提供已启用且 `auto_invoke=true` 的标准元数据。
2. `SkillSelectionService` 使用当前模型进行一次 `tool_choice=none` 的结构化选择，最多返回 3 个 Skill。

输入只包含：用户消息、附件类型、Skill 名称与 description、兼容性摘要和可用工具名称。输出：

```json
{
  "skills": [
    {
      "name": "report-writer",
      "confidence": 0.92,
      "reason": "用户要求生成结构化研究报告"
    }
  ]
}
```

规则：

- 手动 Skill 先占用总数上限，自动选择只补足剩余位置。
- 没有候选 Skill 时跳过模型调用。
- 自动选择失败时记录警告并回退为仅手动 Skill，不阻断任务。
- 手动 Skill 不可用时明确返回错误，不静默忽略用户意图。
- 自动选择模型调用记录为 `model_calls.agent_name = skill_selector`。

### 9.3 工具与兼容性

- `allowed-tools` 只作为可用性声明和选择 gating。
- Skill 不能通过 `allowed-tools` 启用 ToolConfig 中已禁用的工具。
- 自动选择遇到缺失工具时排除候选并记录原因。
- 手动选择遇到缺失工具时停止当前 Run，返回缺少哪些工具的可操作错误。
- 多个 Skill 的工具声明取并集做可用性检查，不缩减 Agent 本来可用的工具集合。

## 10. Prompt 注入

现有 Planner / ReAct 使用持久化 Memory，不能把动态 Skill 写成永久 system message，否则下一轮可能继续使用过期 Skill。

改造方式：

- `BaseAgent` 增加仅存在于当前 TaskRunner 实例的 runtime context，不写入 Session Memory。
- 每次 LLM 调用时，在基础 system prompt 后临时插入当前 Skill context。
- Planner 与 ReAct 共用同一个 `SelectedSkillContext`，但各自保留现有 Memory。
- 新 Run 会重新选择并替换 runtime context。

上下文格式：

```text
<active_skills>
<skill name="report-writer" source="personal" root="/home/ubuntu/.agentic/skills/<run-id>/report-writer">
[完整 SKILL.md Markdown 正文]
</skill>
</active_skills>
```

正文中引用的相对路径以 `root` 为基准。附属文件不自动读入上下文。

## 11. Run / Trace

任务流程：

```text
MessageEvent
  -> TraceService.start_run()
  -> skill.selection.started
  -> manual resolution
  -> automatic selector model call
  -> skill.selected / skill.skipped
  -> run_skills rows
  -> materialize packages
  -> Planner / ReAct
```

Trace 面板新增 Skills 标签，展示：

- Skill 名称、来源和版本。
- 手动或自动选择。
- 自动选择置信度和理由。
- 内容哈希与 Sandbox 路径。
- 选择或物化失败原因。

`GET /api/runs/{run_id}` 返回 `skills` 数组；单独提供 `GET /api/runs/{run_id}/skills`。

## 12. API

### 12.1 个人 Skill

```text
GET    /api/skills
POST   /api/skills/import
POST   /api/skills/drafts
GET    /api/skills/{skill_id}
POST   /api/skills/{skill_id}/enabled
POST   /api/skills/{skill_id}/auto-invoke
POST   /api/skills/{skill_id}/archive

GET    /api/skill-drafts/{draft_id}/tree
GET    /api/skill-drafts/{draft_id}/files/{path}
PUT    /api/skill-drafts/{draft_id}/files/{path}
DELETE /api/skill-drafts/{draft_id}/files/{path}
POST   /api/skill-drafts/{draft_id}/validate
POST   /api/skill-drafts/{draft_id}/publish
```

### 12.2 市场

```text
GET    /api/skills/marketplace
POST   /api/skills/marketplace/{skill_id}/install
POST   /api/skills/marketplace/{skill_id}/update
POST   /api/skills/marketplace/{skill_id}/uninstall
POST   /api/skills/marketplace/{skill_id}/fork
```

### 12.3 对话

`ChatRequest` 新增：

```json
{
  "message": "生成一份竞品分析报告",
  "attachments": [],
  "skills": [
    {
      "source": "personal",
      "skill_id": "9cc91bd6-2329-4c5c-b751-f6f6075fac94",
      "name": "report-writer"
    }
  ]
}
```

Bundled Skill 的 `skill_id` 固定为空；个人和市场 Skill 必须发送服务端返回的稳定 ID。客户端不传 `user_id`、版本包路径或 Sandbox 路径。

## 13. UI

### 13.1 侧边栏

- Rail 增加 Skills 图标。
- Sidebar Panel 支持 `history | skills` 两种上下文。
- Skills 面板提供搜索、新建入口、个人/已安装分组和启停状态。
- 移动端继续使用现有抽屉，不新增第三层固定侧栏。

### 13.2 管理页

```text
/skills
/skills/:id
/skills/marketplace
```

- 个人 Skill：查看版本、编辑草稿、启停、自动触发、导入、归档。
- 市场 Skill：查看来源、版本、许可、兼容性、安装、更新、Fork。
- 文件树：`SKILL.md`、scripts、references、assets。
- 校验错误必须精确到文件和字段。

### 13.3 输入器

- 输入 `$` 弹出已启用 Skill。
- 选择后显示可移除的 Skill Chip。
- 发送时 Skill 引用独立进入请求体，不把 `$name` 当普通消息文本。
- 自动选择结果通过 Skill 事件显示在任务时间线中。

## 14. Skill Creator

系统内置：

```text
api/app/skills/bundled/skill-creator/
├── SKILL.md
├── references/specification.md
└── scripts/validate_skill.py
```

它本身必须是标准 Skill，不拥有绕过隔离的文件权限。

创建流程：

1. 用户在 Skills 页面选择“用 AI 创建”，或手动选择 `$skill-creator`。
2. Agent 收集用途、触发场景、依赖工具、输出与边界。
3. Skill Creator 通过受限的 `skill_draft_*` 工具写入当前用户草稿 Workspace。
4. 服务端执行同一套 `SkillPackageValidator`。
5. UI 展示文件树、Markdown 和校验结果。
6. 用户发布后生成个人 Skill 的新不可变版本。

`skill_draft_*` 工具只接受 `draft_id + relative_path + content`；服务端从当前 AgentTaskRunner 注入的 `user_id` 判断所有权。

## 15. Marketplace

首版市场是当前部署内的全局目录：

- 管理员通过 `scripts/import_market_skill.py` 导入标准包。
- 发布时复制到部署级市场对象存储并创建不可变版本。
- 普通用户只能浏览和安装，不能修改市场源。
- 安装记录固定明确版本。
- 更新只切换安装记录，不覆盖个人 Fork。
- Fork 会复制指定市场版本为新的个人 Skill，保留来源字段。

以后如建设跨部署云市场，只需实现新的 Marketplace Catalog / Package Provider，运行时仍消费相同 Skill、Version、Installation 接口。

## 16. 错误处理

- Trace、自动选择记录失败：降级并继续任务。
- 手动 Skill 无权限、已停用或缺少工具：拒绝本轮执行并返回可操作错误。
- 包下载、哈希校验或 Sandbox 物化失败：拒绝使用该 Skill；手动选择阻断，自动选择降级。
- 市场更新失败：保留原固定版本。
- 发布失败：不修改 `current_version_id`，保留草稿。
- 对象存储成功但数据库提交失败：补偿删除孤儿对象。
- 数据库成功但清理草稿失败：记录日志，由后台清理任务回收。

## 17. 验收标准

### 阶段 A

- 能导入符合规范的 `.md`、`.zip` 或 `.skill` 包，并拒绝恶意路径与非法 frontmatter。
- 用户 A 无法列出、读取、修改或选择用户 B 的个人 Skill。
- 手动选择能稳定绑定具体版本并进入当前 Run。
- 自动选择能基于 description 选中合适 Skill，失败不影响普通任务。
- 完整 Skill 正文只在选中后加载。
- Skill 附属文件只物化到当前 Session Sandbox。
- Planner、ReAct 和 Trace 使用同一组选中 Skill。
- Trace 能显示 Skill 来源、版本、选择方式、哈希和理由。
- 前端支持侧边栏管理和 `$` 手动选择。

### 阶段 B

- AI 能创建符合官方规范的 Skill 草稿。
- 草稿文件只能写入当前用户 Workspace。
- 校验失败不能发布。
- 发布生成不可变版本，旧 Run 仍能按原版本复盘。

### 阶段 C

- 所有用户能浏览全局市场，但只有安装的市场 Skill 进入个人 Catalog。
- 安装、更新、卸载不影响其他用户。
- 编辑市场 Skill 自动 Fork，不改变市场源。
- 市场包使用部署级存储，发布者个人存储变化不影响已发布版本。

## 18. 设计自审

- 所有协议字段和架构分支均已明确。
- Skill 正文格式完全依赖 Agent Skills 标准。
- Runbook 是 Markdown 内容，不是自建 DAG。
- 个人、市场、Bundled 三类来源都有明确的内容真源和隔离边界。
- 自动与手动选择、Workspace、Sandbox、Trace、Creator 和 Marketplace 均有闭环。
- 三阶段可分别上线；阶段 A 不依赖阶段 B/C。
