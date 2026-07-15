# Agent Skills / Runbook Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use `superpowers:subagent-driven-development` when the user explicitly requests delegated execution; otherwise use `superpowers:executing-plans` and execute one task at a time. Every checkbox is a review checkpoint.

**Goal:** 为当前单 Agent 增加遵循 Agent Skills `SKILL.md` 规范的可复用专业能力，支持个人 Skill、内置 Skill、市场 Skill、手动选择、智能自动选择、Skill Creator、用户隔离、Sandbox 执行和完整 Trace。

**Architecture:** Skill 正文及附属文件以不可变 `.skill` ZIP 包保存在文件或对象存储，PostgreSQL 仅保存元数据、版本、安装关系和运行记录。运行时先合并用户可见 Catalog，再解析手动选择并由 LLM 自动补选，随后将选中 Skill 物化到当前 Session Sandbox，并把完整 `SKILL.md` 作为单次 Run 的临时上下文注入 Planner / ReAct。Skill 不扩大工具权限，脚本只能在现有 Sandbox 中运行。

**Tech Stack:** Python 3.12、FastAPI、Pydantic 2、SQLAlchemy 2、Alembic、PostgreSQL、`skills-ref`、Vue 3、TypeScript、Element Plus、Pinia、Vitest、Vue Test Utils、Docker Sandbox。

**Design baseline:** [2026-07-15-skill-runbook-design.md](../specs/2026-07-15-skill-runbook-design.md)

## Global constraints

- [ ] 不创建平台私有的 Skill 正文格式；`SKILL.md` 只接受 Agent Skills 官方字段。
- [ ] `Runbook` 只是一段 Markdown 执行规范，不引入 DAG、审批流或 Agent Profile。
- [ ] 用户 ID 只从认证上下文取得；所有个人 Skill、草稿、安装记录和缓存都按用户隔离。
- [ ] 发布版本不可原地修改；每次发布生成确定性 ZIP、SHA-256 和新版本记录。
- [ ] API 主机不执行 Skill 脚本；脚本与附属资源只物化到 Session Sandbox。
- [ ] `allowed-tools` 只做兼容性检查，不能启用 ToolConfig 中已禁用的工具，也不缩减 Agent 原有工具集。
- [ ] 手动 Skill 不可用时返回明确错误；自动选择失败时降级为仅使用手动 Skill，不阻断普通任务。
- [ ] Skill 正文不写入持久化 Memory；每个新 Run 都重新选择并替换临时上下文。
- [ ] 保留现有 UI 未提交修改，不重置、不覆盖与本计划无关的工作树内容。

## Phase A — Skill Runtime Foundation

### Task 1: 增加规范解析依赖与核心领域类型

**Files:**

- Modify: `agentic/api/pyproject.toml`
- Modify: `agentic/api/uv.lock`
- Modify: `agentic/api/requirements.txt`
- Create: `agentic/api/app/core/entities/skill.py`
- Modify: `agentic/api/app/core/entities/__init__.py`
- Create: `agentic/api/app/schemas/skill.py`
- Modify: `agentic/api/app/schemas/__init__.py`
- Test: `agentic/api/tests/app/core/skills/test_skill_entities.py`

**Interfaces to implement:**

```python
class SkillSource(StrEnum):
    BUNDLED = "bundled"
    PERSONAL = "personal"
    MARKETPLACE = "marketplace"

class SkillSelectionMode(StrEnum):
    MANUAL = "manual"
    AUTOMATIC = "automatic"

class SkillRef(BaseModel):
    source: SkillSource
    skill_id: str | None = None
    name: str

class SkillManifest(BaseModel):
    name: str
    description: str
    license: str | None = None
    compatibility: str | None = None
    metadata: dict[str, str] = Field(default_factory=dict)
    allowed_tools: str | None = Field(default=None, alias="allowed-tools")

class SelectedSkill(BaseModel):
    ref: SkillRef
    version_id: str | None
    version: int | None
    manifest: SkillManifest
    selection_mode: SkillSelectionMode
    confidence: float | None
    reason: str
    package_sha256: str
```

- [ ] Write failing tests for enum serialization, official manifest fields, `SkillRef` identity, confidence bounds and unknown top-level fields.
- [ ] Run `uv run pytest tests/app/core/skills/test_skill_entities.py -q` from `agentic/api`; confirm failure because types do not exist.
- [ ] Add `skills-ref>=0.1.1,<0.2` as a direct dependency and regenerate `uv.lock` plus `requirements.txt` with the repository's existing `uv` workflow.
- [ ] Implement domain and API schemas. Configure the manifest model to reject unknown top-level fields while allowing only string-to-string `metadata`.
- [ ] Re-run the focused test and confirm it passes.
- [ ] Run `uv run ruff check app/core/entities/skill.py app/schemas/skill.py tests/app/core/skills/test_skill_entities.py`.
- [ ] Commit: `feat(skills): add standard skill domain types`

### Task 2: 建立 Skill 数据模型、迁移、Repository 与 UoW

**Files:**

- Create: `agentic/api/alembic/versions/20260715_0001_agent_skills.py`
- Create: `agentic/api/app/models/skill.py`
- Modify: `agentic/api/app/models/__init__.py`
- Create: `agentic/api/app/repositories/skill_repository.py`
- Create: `agentic/api/app/repositories/db_skill_repository.py`
- Modify: `agentic/api/app/repositories/__init__.py`
- Modify: `agentic/api/app/repositories/uow.py`
- Modify: `agentic/api/app/repositories/db_uow.py`
- Test: `agentic/api/tests/app/repositories/test_skill_repository.py`

**Schema contract:**

- `skills`: owner、name、display name、description、scope、status、enabled、auto invoke、current version、fork lineage、timestamps。
- `skill_versions`: immutable package metadata、official manifest JSONB、storage location snapshot、SHA-256、size、file count、status、changelog、creator。
- `skill_installations`: user、market Skill、pinned version、enabled、auto invoke、auto update、timestamps。
- `run_skills`: run、Skill/version nullable references、source、selection mode、hash、confidence、reason、sandbox path、timestamp。

**Required database constraints:**

- Personal Skill unique key: `(owner_user_id, name)` where scope is `personal` and status is not `archived`.
- Marketplace Skill unique key: `(name)` where scope is `marketplace` and status is not `archived`.
- Published version unique key: `(skill_id, version)`.
- Installation unique key: `(user_id, skill_id)`.
- Cascade-delete draft-only records; published version and `run_skills` history must remain traceable.

- [ ] Write repository tests proving user A cannot list, read, update or archive user B's personal Skill and cannot see user B's installations.
- [ ] Add tests proving marketplace rows are globally readable but runtime queries return only rows installed by the current user.
- [ ] Run the repository test and confirm it fails.
- [ ] Add SQLAlchemy models and Alembic upgrade/downgrade operations with all indexes, foreign keys and partial unique indexes.
- [ ] Define `SkillRepository` methods for personal CRUD, version lookup, installation CRUD, catalog queries and `run_skills` persistence. Every user-scoped method must require `user_id` explicitly.
- [ ] Wire `skill: SkillRepository` into `IUnitOfWork` and `DatabaseUnitOfWork`.
- [ ] Run `uv run pytest tests/app/repositories/test_skill_repository.py -q`.
- [ ] Run `uv run alembic upgrade head`, inspect the four tables, then run `uv run alembic downgrade -1` and `uv run alembic upgrade head` against the test database.
- [ ] Commit: `feat(skills): persist skill versions installations and run usage`

### Task 3: 实现安全、确定性的标准 Skill 包处理

**Files:**

- Create: `agentic/api/app/core/skills/__init__.py`
- Create: `agentic/api/app/core/skills/limits.py`
- Create: `agentic/api/app/core/skills/package.py`
- Test: `agentic/api/tests/app/core/skills/test_skill_package.py`
- Fixture: `agentic/api/tests/fixtures/skills/report-writer/SKILL.md`
- Fixture: `agentic/api/tests/fixtures/skills/report-writer/references/style.md`

**Interfaces to implement:**

`SkillPackageLimits` 固定为：压缩包 50 MiB、解压后 100 MiB、256 个文件、单文件 10 MiB、`SKILL.md` 256 KiB、相对路径 240 字符。`SkillPackageService` 必须提供四个带类型的同步边界：`inspect_directory(root: Path) -> InspectedSkillPackage`、`inspect_archive(archive: BinaryIO) -> InspectedSkillPackage`、`build_archive(root: Path, output: BinaryIO) -> PackageBuildResult`、`extract_archive(archive: BinaryIO, destination: Path) -> PackageBuildResult`。

- [ ] Write passing-case tests using the fixture and verify `skills_ref.validate` plus `skills_ref.read_properties` are called through the package service.
- [ ] Write rejection tests for ZIP Slip, absolute paths, `..`, backslashes, empty segments, symlink entries, device files, duplicate case-folded paths, multiple roots, missing root `SKILL.md`, non-UTF-8 Markdown, directory/name mismatch and every size/count limit.
- [ ] Write a reproducibility test: building the same directory twice must produce identical bytes and SHA-256 regardless of file mtime.
- [ ] Run the focused test and confirm failure.
- [ ] Implement validation before extraction. Normalize ZIP timestamps, ordering and permission bits when publishing.
- [ ] Return stable error codes such as `skill_invalid_manifest`, `skill_unsafe_archive`, `skill_package_too_large` and `skill_name_mismatch`.
- [ ] Run the focused test, then `uv run ruff check app/core/skills tests/app/core/skills`.
- [ ] Commit: `feat(skills): validate and archive standard skill packages`

### Task 4: 实现版本包存储和用户草稿 Workspace

**Files:**

- Create: `agentic/api/app/extensions/storage_drivers.py`
- Modify: `agentic/api/app/extensions/managed_file_storage.py`
- Create: `agentic/api/app/extensions/skill_package_storage.py`
- Create: `agentic/api/app/services/skill_workspace_service.py`
- Modify: `agentic/api/app/core/config.py`
- Modify: `agentic/api/app/config.yaml`
- Modify: `agentic/api/app/dependencies/infrastructure.py`
- Test: `agentic/api/tests/app/extensions/test_skill_package_storage.py`
- Test: `agentic/api/tests/app/services/test_skill_workspace_service.py`

**Storage roots:**

```text
/app/storage/skills/packages/personal/<user-id>/<skill-id>/<version>.skill
/app/storage/skills/packages/marketplace/<skill-id>/<version>.skill
/app/storage/skill-workspaces/users/<user-id>/<draft-id>/<skill-name>/
```

- [ ] Extract reusable local/COS/OSS byte-object operations from `managed_file_storage.py` without changing existing file-management behavior.
- [ ] Write storage contract tests for upload, stream download, delete, missing object, SHA mismatch and provider snapshot redaction.
- [ ] Write workspace tests for create, tree listing, UTF-8 read/write, path traversal rejection, user isolation and atomic publish staging.
- [ ] Run both focused tests and confirm failure.
- [ ] Implement `SkillPackageStorage` so personal packages use the authenticated user's configured storage provider and marketplace packages use deployment-level storage settings.
- [ ] Implement `SkillWorkspaceService`; resolve every requested relative path and assert it remains below the authenticated user's draft root.
- [ ] Add settings for package roots, workspace roots, limits and marketplace provider without placing secrets in database snapshots or API responses.
- [ ] Re-run focused tests plus existing `tests/app/services/test_file_management.py` to prove the extraction did not regress Files.
- [ ] Commit: `feat(skills): add isolated package storage and draft workspaces`

### Task 5: 实现个人 Skill 服务与管理 API

**Files:**

- Create: `agentic/api/app/services/skill_service.py`
- Create: `agentic/api/app/controllers/skills.py`
- Modify: `agentic/api/app/controllers/__init__.py`
- Modify: `agentic/api/app/dependencies/services.py`
- Modify: `agentic/api/app/service_dependencies.py`
- Modify: `agentic/api/app/schemas/skill.py`
- Test: `agentic/api/tests/app/services/test_skill_service.py`
- Test: `agentic/api/tests/app/interfaces/endpoints/test_skill_routes.py`

**Phase A API contract:**

```text
GET    /api/skills
POST   /api/skills/import
GET    /api/skills/{skill_id}
PATCH  /api/skills/{skill_id}
DELETE /api/skills/{skill_id}
POST   /api/skills/{skill_id}/enable
POST   /api/skills/{skill_id}/disable
POST   /api/skills/{skill_id}/auto-invoke
POST   /api/skill-drafts
GET    /api/skill-drafts/{draft_id}/tree
GET    /api/skill-drafts/{draft_id}/files/{path}
PUT    /api/skill-drafts/{draft_id}/files/{path}
POST   /api/skill-drafts/{draft_id}/validate
POST   /api/skill-drafts/{draft_id}/publish
```

- [ ] Write service tests for import, validation failure, first publish, second immutable version, archive, enable/disable, auto-invoke and stale draft conflict.
- [ ] Write route tests proving all endpoints require authentication and ignore any client-supplied owner ID.
- [ ] Write cross-user tests returning 404 rather than revealing another user's Skill or draft.
- [ ] Run focused tests and confirm failure.
- [ ] Implement orchestration order for publish: validate draft, build deterministic package, upload, persist version/current pointer in one database transaction, then clean the draft only after commit.
- [ ] On database failure after upload, delete the unreferenced object; on object-store failure, do not create a version row.
- [ ] Return validation diagnostics with file, line, column, code and human-readable message.
- [ ] Register `/marketplace` and `/skill-drafts` static route groups before `/{skill_id}` routes so FastAPI never treats the static segment as a Skill ID.
- [ ] Re-run focused tests and OpenAPI generation smoke test.
- [ ] Commit: `feat(skills): expose personal skill management api`

### Task 6: 实现合并 Catalog 和手动/自动选择器

**Files:**

- Create: `agentic/api/app/services/skill_catalog_service.py`
- Create: `agentic/api/app/services/skill_selection_service.py`
- Create: `agentic/api/app/core/prompts/skill_selector.py`
- Modify: `agentic/api/app/core/prompts/__init__.py`
- Modify: `agentic/api/app/schemas/skill.py`
- Test: `agentic/api/tests/app/services/test_skill_catalog_service.py`
- Test: `agentic/api/tests/app/services/test_skill_selection_service.py`

**Interfaces to implement:**

`SkillSelectionRequest` 包含 `user_id: str`、`message: str`、`attachment_media_types: list[str]`、`manual_refs: list[SkillRef]` 和 `available_tool_names: set[str]`。`SkillSelectionResult` 包含 `selected: list[SelectedSkill]`、`skipped: list[SkillSelectionSkip]` 和 `selector_model_call_id: str | None`。服务入口固定为 `await SkillSelectionService.select(request: SkillSelectionRequest) -> SkillSelectionResult`。

- [ ] Write Catalog tests proving it merges bundled, enabled personal and enabled installed-marketplace entries, deduplicates stable refs and never exceeds 100 automatic candidates.
- [ ] Write selection tests for manual priority, maximum 5 manual, maximum 3 automatic, maximum 5 combined, missing tools, disabled Skill, hallucinated selector names, malformed JSON and selector model failure.
- [ ] Verify no candidate means no LLM call and model failure returns manual selections with a recorded warning.
- [ ] Run focused tests and confirm failure.
- [ ] Implement manual resolution before automatic selection. Use the current configured model with tools disabled and a strict structured response.
- [ ] Keep reasons short and persistable; do not put full Skill bodies into the selector prompt.
- [ ] Record selector calls with `agent_name="skill_selector"` through the existing model-call trace path.
- [ ] Re-run focused tests.
- [ ] Commit: `feat(skills): select skills manually and automatically`

### Task 7: 将 Skill 安全接入任务运行时、Prompt 与 Sandbox

**Files:**

- Create: `agentic/api/app/services/skill_runtime_service.py`
- Modify: `agentic/api/app/core/agent/base.py`
- Modify: `agentic/api/app/core/agent/planner.py`
- Modify: `agentic/api/app/core/agent/react.py`
- Modify: `agentic/api/app/core/flows/planner_react.py`
- Modify: `agentic/api/app/core/agent/agent_task_runner.py`
- Modify: `agentic/api/app/services/agent_service.py`
- Modify: `agentic/api/app/core/entities/event.py`
- Modify: `agentic/api/app/schemas/event.py`
- Modify: `agentic/api/app/schemas/session.py`
- Modify: `agentic/api/app/controllers/session.py`
- Test: `agentic/api/tests/app/core/agent/test_skill_runtime_context.py`
- Test: `agentic/api/tests/app/services/test_agent_skill_runtime.py`

**Runtime contract:**

`SkillRuntimeContext` 包含 `selected: list[SelectedSkill]`、`prompt_block: str` 和 `sandbox_roots: dict[str, str]`。服务入口固定为 `await SkillRuntimeService.prepare_run(user_id: str, session_id: str, run_id: str, request: SkillSelectionRequest) -> SkillRuntimeContext`。

- [ ] Extend `ChatRequest` and user `MessageEvent` with `skills: list[SkillRef]`, defaulting to an empty list for backward compatibility.
- [ ] Write tests proving a selected Skill is visible to both Planner and ReAct, relative paths point at `/home/ubuntu/.agentic/skills/<run-id>/<name>`, and auxiliary files are not injected into the prompt.
- [ ] Write a regression test proving runtime context is absent from persistent Session Memory and disappears on the next Run when no Skill is selected.
- [ ] Write security tests proving a run cannot materialize another user's personal or uninstalled marketplace package.
- [ ] Run focused tests and confirm failure.
- [ ] Add an instance-scoped runtime context to `BaseAgent`; construct LLM messages by inserting the transient context immediately after the base system prompt without mutating Memory.
- [ ] Materialize only selected packages into the current Session Sandbox. Reject conflicting selected names before extraction.
- [ ] Invoke selection and materialization after `TraceService.start_run()` and before Planner execution so all outcomes have a run ID.
- [ ] Preserve existing failed-run recovery: `continue` and `restart` each perform a new selection for the new Run rather than reusing stale prompt state.
- [ ] Re-run focused tests plus `tests/app/services/test_agent_service_recovery.py` and `tests/app/interfaces/endpoints/test_session_recovery_route.py`.
- [ ] Commit: `feat(skills): inject selected skills into agent runtime`

### Task 8: 补齐 Skill Trace 与运行查询

**Files:**

- Modify: `agentic/api/app/repositories/trace_repository.py`
- Modify: `agentic/api/app/repositories/db_trace_repository.py`
- Modify: `agentic/api/app/services/trace_service.py`
- Modify: `agentic/api/app/models/run_trace.py`
- Modify: `agentic/api/app/core/entities/event.py`
- Modify: `agentic/api/app/schemas/event.py`
- Modify: `agentic/api/app/schemas/skill.py`
- Modify: `agentic/api/app/controllers/runs.py`
- Test: `agentic/api/tests/app/services/test_skill_trace.py`
- Test: `agentic/api/tests/app/interfaces/endpoints/test_run_skill_routes.py`

**Events and endpoint:**

```text
skill.selection.started
skill.selected
skill.skipped
skill.materialized
skill.selection.failed
GET /api/runs/{run_id}/skills
```

- [ ] Write tests for manual and automatic `run_skills` rows, bundled nullable IDs, package hash, selector confidence/reason and materialized path.
- [ ] Write authorization tests proving a user cannot query another user's run Skill history.
- [ ] Run focused tests and confirm failure.
- [ ] Persist `run_skills` in the same UoW boundary as selection events and expose them in run detail plus the dedicated endpoint.
- [ ] Ensure failure events never include storage credentials, full package content or raw selector prompts.
- [ ] Re-run focused tests plus existing trace tests.
- [ ] Commit: `feat(trace): record skill selection and materialization`

### Task 9: 建立前端 Skill API、类型、Store 与测试基线

**Files:**

- Modify: `agentic/web/package.json`
- Modify: `agentic/web/pnpm-lock.yaml`
- Create: `agentic/web/vitest.config.ts`
- Create: `agentic/web/src/test/setup.ts`
- Create: `agentic/web/src/types/skill.ts`
- Create: `agentic/web/src/lib/api/skills.ts`
- Modify: `agentic/web/src/lib/api/index.ts`
- Modify: `agentic/web/src/lib/api/types.ts`
- Create: `agentic/web/src/stores/skills.ts`
- Test: `agentic/web/src/stores/skills.spec.ts`

- [ ] Add `vitest`, `@vue/test-utils` and `happy-dom` as dev dependencies; add `test` and `test:run` scripts.
- [ ] Write store tests for list loading, detail caching, optimistic enable rollback, auto-invoke update, validation diagnostics and auth-user reset.
- [ ] Run `pnpm test:run src/stores/skills.spec.ts` from `agentic/web`; confirm failure.
- [ ] Add TypeScript types that mirror backend `SkillRef`, summary, detail, draft tree, validation diagnostic and `RunSkill` contracts.
- [ ] Implement API calls through the existing authenticated fetch wrapper and Pinia store through the existing application pattern.
- [ ] Re-run focused tests and `pnpm type-check`.
- [ ] Commit: `feat(web): add skill api and state management`

### Task 10: 增加 Skills 侧边栏入口、管理页和标准包编辑器

**Files:**

- Modify: `agentic/web/src/composables/useSidebar.ts`
- Modify: `agentic/web/src/components/navigation/SidebarRail.vue`
- Modify: `agentic/web/src/components/navigation/SidebarPanel.vue`
- Create: `agentic/web/src/components/navigation/SkillsSidePanel.vue`
- Modify: `agentic/web/src/router/index.ts`
- Create: `agentic/web/src/views/SkillsView.vue`
- Create: `agentic/web/src/views/SkillDetailView.vue`
- Create: `agentic/web/src/components/skills/SkillListItem.vue`
- Create: `agentic/web/src/components/skills/SkillFileTree.vue`
- Create: `agentic/web/src/components/skills/SkillEditor.vue`
- Create: `agentic/web/src/components/skills/SkillValidationPanel.vue`
- Test: `agentic/web/src/components/skills/SkillEditor.spec.ts`
- Test: `agentic/web/src/components/navigation/SkillsSidePanel.spec.ts`

- [ ] Change sidebar state from a single open boolean to `{ open, section: "sessions" | "skills" }` while preserving current conversation behavior.
- [ ] Write component tests for Skill navigation, source/status labels, enable and auto-recognition switches, empty/error/loading states and authenticated-user isolation.
- [ ] Write editor tests for file selection, dirty state, save, validation diagnostics navigation and publish blocking when validation fails.
- [ ] Run focused tests and confirm failure.
- [ ] Add an independent Skills rail icon and render `SkillsSidePanel` without moving Settings and Account from the sidebar bottom.
- [ ] Add routes `/skills` and `/skills/:skillId`; support import, new draft, edit, validate, publish and archive.
- [ ] Display the actual standard directory tree and keep `SKILL.md` as the primary editing surface; do not transform it into proprietary form fields.
- [ ] Re-run tests, `pnpm type-check` and `pnpm build`.
- [ ] Commit: `feat(web): add personal skill management ui`

### Task 11: 在对话输入器中支持 `$` 手动选择和 Skill chips

**Files:**

- Create: `agentic/web/src/components/skills/SkillPicker.vue`
- Create: `agentic/web/src/components/skills/SkillChip.vue`
- Modify: `agentic/web/src/components/chat/ChatComposer.vue`
- Modify: `agentic/web/src/components/chat/ChatInput.vue`
- Modify: `agentic/web/src/components/chat/ChatMessage.vue`
- Modify: `agentic/web/src/views/HomeView.vue`
- Modify: `agentic/web/src/components/SessionDetailView.vue`
- Modify: `agentic/web/src/composables/useSessionDetail.ts`
- Modify: `agentic/web/src/lib/api/session.ts`
- Modify: `agentic/web/src/lib/session-events.ts`
- Test: `agentic/web/src/components/skills/SkillPicker.spec.ts`
- Test: `agentic/web/src/components/chat/ChatComposer.skills.spec.ts`

**Frontend send contract:**

```typescript
export interface SendMessageInput {
  message: string
  attachmentIds: string[]
  skills: SkillRef[]
}
```

- [ ] Write tests proving `$` opens filtered enabled Skills, keyboard selection works, duplicate choices are rejected, maximum 5 is enforced and removing a chip does not alter typed text.
- [ ] Write serialization tests proving stable Skill refs are sent separately from message text for both new and existing sessions.
- [ ] Run focused tests and confirm failure.
- [ ] Implement the picker and selected chips. The UI may show `$name`, but the request body must contain source, ID and name.
- [ ] Show selected/auto-selected Skill pills on the user message or associated Skill event after the server stream confirms selection.
- [ ] Keep plain `$` text valid when no catalog match is chosen.
- [ ] Re-run tests and `pnpm build`.
- [ ] Commit: `feat(web): select skills from the chat composer`

### Task 12: 在 Trace UI 展示 Skill 决策并完成 Phase A 验收

**Files:**

- Modify: `agentic/web/src/lib/api/runs.ts`
- Modify: `agentic/web/src/components/TracePanel.vue`
- Create: `agentic/web/src/components/skills/RunSkillsPanel.vue`
- Test: `agentic/web/src/components/skills/RunSkillsPanel.spec.ts`
- Create: `agentic/api/tests/app/integration/test_skill_runtime_flow.py`

- [ ] Write frontend tests for manual/automatic labels, version/hash, confidence/reason, missing-tool skip and selection failure.
- [ ] Write an integration test that imports a fixture Skill, manually invokes it, verifies Sandbox files and Trace, then starts a second Run without it and verifies the transient prompt is gone.
- [ ] Add an integration test with two users and identically named personal Skills; verify metadata, package bytes, runtime path and Trace do not cross.
- [ ] Run the new tests and confirm failure before the final wiring.
- [ ] Add a Skills tab to TracePanel and connect it to `/api/runs/{run_id}/skills`.
- [ ] Fix only defects exposed by the tests; do not begin Creator or Marketplace work during Phase A acceptance.
- [ ] Run `uv run pytest tests/app/core/skills tests/app/services/test_skill_service.py tests/app/services/test_skill_catalog_service.py tests/app/services/test_skill_selection_service.py tests/app/services/test_agent_skill_runtime.py tests/app/services/test_skill_trace.py tests/app/integration/test_skill_runtime_flow.py -q`.
- [ ] Run `uv run ruff check app tests` and `pnpm test:run`, `pnpm type-check`, `pnpm build`.
- [ ] Run Docker smoke: migrate, log in as two users, import a Skill, execute manual selection, execute auto selection, inspect Sandbox and Trace, restart API, then verify the published version remains available.
- [ ] Commit: `test(skills): verify runtime foundation end to end`

## Phase B — Skill Creator

### Task 13: 增加只读 bundled Skill loader 与标准 `skill-creator`

**Files:**

- Create: `agentic/api/app/skills/bundled/skill-creator/SKILL.md`
- Create: `agentic/api/app/skills/bundled/skill-creator/references/agent-skills-spec.md`
- Create: `agentic/api/app/skills/bundled/skill-creator/references/quality-checklist.md`
- Create: `agentic/api/app/services/bundled_skill_service.py`
- Modify: `agentic/api/app/services/skill_catalog_service.py`
- Test: `agentic/api/tests/app/services/test_bundled_skill_service.py`

- [ ] Write tests for startup discovery, standard validation, deterministic content hash, duplicate-name rejection, read-only semantics and Catalog visibility.
- [ ] Run focused tests and confirm failure.
- [ ] Implement layered discovery from the application bundled root; validate each directory with the same package service used for user imports.
- [ ] Author `skill-creator/SKILL.md` as a standard Skill that teaches requirement capture, directory design, concise instructions, progressive disclosure, validation and iterative improvement.
- [ ] Keep platform-specific draft operations out of its frontmatter; describe available draft tools in the Markdown instructions.
- [ ] Re-run focused tests and validate the bundled Skill through `skills-ref`.
- [ ] Commit: `feat(skills): bundle a standard skill creator`

### Task 14: 增加用户隔离的 Skill 草稿工具

**Files:**

- Create: `agentic/api/app/core/tools/skill_draft.py`
- Modify: `agentic/api/app/core/tools/factory.py`
- Modify: `agentic/api/app/core/tools/registry.py`
- Modify: `agentic/api/app/core/flows/planner_react.py`
- Modify: `agentic/api/app/core/agent/agent_task_runner.py`
- Test: `agentic/api/tests/app/core/tools/test_skill_draft_tools.py`

**Tool contract:**

```text
skill_draft_create(name, description)
skill_draft_tree(draft_id)
skill_draft_read(draft_id, path)
skill_draft_write(draft_id, path, content)
skill_draft_validate(draft_id)
```

- [ ] Write tests proving the tools receive authenticated `user_id` through dependency construction, never accept owner IDs, reject traversal and cannot access another user's draft ID.
- [ ] Write tests proving draft tools appear only when `bundled:skill-creator` is selected and cannot publish directly.
- [ ] Run focused tests and confirm failure.
- [ ] Implement thin Tool adapters over `SkillWorkspaceService`; do not duplicate filesystem safety logic.
- [ ] Inject the adapters per Run through `ToolFactory`, preserving current ToolConfig filtering.
- [ ] Keep publish as an explicit UI/API action after validation; the Agent may prepare and validate a draft but cannot silently publish it.
- [ ] Re-run focused tests and existing tool-management tests.
- [ ] Commit: `feat(skills): let skill creator edit isolated drafts`

### Task 15: 实现“用 AI 创建 Skill”交互和 Creator 验收

**Files:**

- Create: `agentic/web/src/components/skills/SkillCreatorDialog.vue`
- Modify: `agentic/web/src/views/SkillsView.vue`
- Modify: `agentic/web/src/views/SkillDetailView.vue`
- Modify: `agentic/web/src/components/skills/SkillEditor.vue`
- Modify: `agentic/web/src/lib/api/session.ts`
- Test: `agentic/web/src/components/skills/SkillCreatorDialog.spec.ts`
- Create: `agentic/api/tests/app/integration/test_skill_creator_flow.py`

- [ ] Write UI tests for opening Creator, collecting goal/examples/required resources, starting a conversation with a manual `bundled:skill-creator` ref and opening the resulting draft.
- [ ] Write integration tests proving the Agent can create files, validate, revise after diagnostics and hand the draft to the user without auto-publishing.
- [ ] Run tests and confirm failure.
- [ ] Implement the dialog and handoff. Creator sessions remain normal conversations and use the same task recovery controls if a run fails.
- [ ] Show draft file changes and validation state in the Skill editor; require the user to click Publish after reviewing the final package.
- [ ] Run backend Creator integration tests, frontend tests, type-check and build.
- [ ] Commit: `feat(web): create skills with the bundled agent skill`

## Phase C — Skill Marketplace

### Task 16: 实现市场包导入、不可变目录和管理脚本

**Files:**

- Create: `agentic/api/scripts/import_market_skill.py`
- Create: `agentic/api/app/services/marketplace_skill_service.py`
- Modify: `agentic/api/app/extensions/skill_package_storage.py`
- Modify: `agentic/api/app/services/skill_catalog_service.py`
- Modify: `agentic/api/app/core/config.py`
- Modify: `agentic/api/app/config.yaml`
- Test: `agentic/api/tests/app/services/test_marketplace_skill_import.py`

- [ ] Write tests for a valid import, invalid package, duplicate version hash, changed version hash, global name conflict, deployment storage failure and idempotent re-import.
- [ ] Run focused tests and confirm failure.
- [ ] Implement an authenticated-offline admin script accepting local directory or `.skill` path, changelog and display metadata. It must validate, build deterministic bytes, upload to marketplace storage and commit an immutable published version.
- [ ] Do not reuse a publishing user's personal storage credentials for marketplace content.
- [ ] Add structured output containing Skill ID, version ID, version, hash and storage provider without secrets.
- [ ] Re-run focused tests and execute the script against the fixture in a local development database.
- [ ] Commit: `feat(skills): import immutable marketplace packages`

### Task 17: 实现市场浏览、安装、固定版本、更新、卸载与 Fork API

**Files:**

- Modify: `agentic/api/app/controllers/skills.py`
- Modify: `agentic/api/app/services/marketplace_skill_service.py`
- Modify: `agentic/api/app/services/skill_service.py`
- Modify: `agentic/api/app/schemas/skill.py`
- Test: `agentic/api/tests/app/services/test_marketplace_installations.py`
- Test: `agentic/api/tests/app/interfaces/endpoints/test_marketplace_routes.py`

**Marketplace API contract:**

```text
GET    /api/skills/marketplace
GET    /api/skills/marketplace/{skill_id}
POST   /api/skills/marketplace/{skill_id}/install
POST   /api/skills/marketplace/{skill_id}/update
DELETE /api/skills/marketplace/{skill_id}/install
POST   /api/skills/marketplace/{skill_id}/fork
```

- [ ] Write tests for install latest, install explicit version, immutable pin, update, uninstall, enable/disable, auto-invoke and fork lineage.
- [ ] Prove an available update does not change an existing installation or historical Run until the user explicitly updates; keep `auto_update=false` in the first release.
- [ ] Prove editing marketplace content creates a personal fork and never changes the market package.
- [ ] Run focused tests and confirm failure.
- [ ] Implement list/detail/install/update/uninstall/fork with user-scoped installation rows and stable version refs.
- [ ] Exclude uninstalled market Skills from manual picker and auto Catalog.
- [ ] Re-run focused tests plus runtime selection tests.
- [ ] Commit: `feat(skills): install and fork marketplace skills`

### Task 18: 实现 Marketplace UI

**Files:**

- Modify: `agentic/web/src/router/index.ts`
- Create: `agentic/web/src/views/SkillMarketplaceView.vue`
- Create: `agentic/web/src/components/skills/MarketplaceSkillCard.vue`
- Create: `agentic/web/src/components/skills/MarketplaceSkillDetail.vue`
- Modify: `agentic/web/src/components/navigation/SkillsSidePanel.vue`
- Modify: `agentic/web/src/lib/api/skills.ts`
- Modify: `agentic/web/src/stores/skills.ts`
- Test: `agentic/web/src/views/SkillMarketplaceView.spec.ts`
- Test: `agentic/web/src/components/skills/MarketplaceSkillDetail.spec.ts`

- [ ] Write tests for browse/search, installed badge, version information, install, update available, uninstall, fork and backend error rollback.
- [ ] Run focused tests and confirm failure.
- [ ] Add `/skills/marketplace`; keep “我的 Skills”和“Skill 市场” as distinct destinations under the Skills sidebar section.
- [ ] Require no generic confirmation dialog for install/update; uninstall may use a lightweight confirmation because it changes the user's own runtime catalog but does not delete market content.
- [ ] Route Edit on a market Skill to Fork and then open the new personal draft.
- [ ] Re-run frontend tests, type-check and build.
- [ ] Commit: `feat(web): add skill marketplace experience`

### Task 19: 文档、兼容性、全量回归与最终验收

**Files:**

- Modify: `agentic/docs/roadmap.zh-CN.md`
- Modify: `agentic/docs/librechat-ui-redesign.zh-CN.md`
- Create: `agentic/docs/skill-authoring.zh-CN.md`
- Create: `agentic/docs/skill-operations.zh-CN.md`
- Modify: `agentic/README.md`
- Create: `agentic/api/tests/app/integration/test_skill_marketplace_flow.py`

- [ ] Document the supported official fields, directory layout, Runbook guidance, limits, personal/market storage model, manual and automatic invocation, Creator workflow and troubleshooting.
- [ ] Document operator procedures for marketplace import, storage configuration, orphan package cleanup, backup/restore and Trace investigation.
- [ ] Update roadmap only after each phase's acceptance commands pass; mark Phase A, B and C separately rather than claiming one combined completion early.
- [ ] Add end-to-end integration coverage: market import, user A install and invoke, user B cannot invoke before install, explicit update, personal fork, API restart and historical Trace reproduction.
- [ ] Run backend full suite: `uv run pytest -q`.
- [ ] Run backend static checks: `uv run ruff check app tests scripts`.
- [ ] Run migrations from the pre-Skill revision to head, downgrade the Skill revision, then upgrade to head again on a disposable database.
- [ ] Run frontend full suite: `pnpm test:run`, `pnpm type-check`, `pnpm build`.
- [ ] Run `git diff --check` and inspect `git diff --stat`; confirm no secrets, generated archives, workspaces or object-store payloads are tracked.
- [ ] Perform Docker acceptance with two users, local storage and one configured cloud provider. Verify manual selection, auto selection, Creator, market install/update/fork, failed-run restart and Trace.
- [ ] Commit: `docs(skills): document authoring operations and acceptance`

## Release gates

### Phase A gate

- [ ] Personal standard Skill can be imported, edited, validated, versioned and archived.
- [ ] Manual and automatic selection both work; manual takes priority and failures follow the defined degradation rules.
- [ ] Selected package contents exist only in the owning Session Sandbox and scripts never execute on the API host.
- [ ] Planner and ReAct see current-run instructions; the next Run has no stale Skill context.
- [ ] Run/Trace shows source, selection mode, version/hash, reason and materialized path.
- [ ] Skills sidebar, management page, composer picker and Trace panel pass accessibility and responsive checks.

### Phase B gate

- [ ] Bundled `skill-creator` itself passes the official validator.
- [ ] Creator can create and revise an isolated draft using standard files only.
- [ ] Agent cannot publish silently and cannot access another user's workspace.
- [ ] Failed Creator conversations can use the existing continue/restart controls.

### Phase C gate

- [ ] Marketplace packages are globally readable, deployment-owned and immutable.
- [ ] Installation is user-scoped and version-pinned; updates are explicit and historical Runs remain reproducible.
- [ ] Editing market content creates a personal fork with lineage.
- [ ] No payments, ratings, comments or open self-publishing are included in the first release.

## Execution order and review discipline

1. Execute tasks strictly in order within each phase; Phase B starts only after the Phase A gate passes, and Phase C starts only after the Phase B gate passes.
2. At every task, observe the failing test before implementation, make the smallest scoped change, run focused verification, then inspect the diff before committing.
3. Do not mix existing UI cleanup changes into Skill commits. Stage only the files named by the current task after reviewing `git diff -- <paths>`.
4. If the official Agent Skills specification or `skills-ref` behavior conflicts with this plan, stop implementation, record the exact conflict and update the design plus this plan before changing the protocol.
5. A task is not complete when only code exists; its focused tests, static checks and stated user-isolation assertions must pass.
