# 文档处理基础设施实施计划

## 关联设计

- 设计文档：`agentic/docs/designs/knowledge-document-processing.zh-CN.md`
- 前置优化计划：`agentic/docs/plans/agent-runtime-lazy-sandbox-plan.md`
- 开发分支：`feature/document-processing-foundation`
- 实施基线：Sandbox 懒启动分支合并后的 `master`；若两批并行开发，必须先冻结本文的接口边界，再由后续分支显式 rebase

## 当前进度

- 整体状态：`PLAN_READY`
- 当前阶段：planning
- 当前任务：无
- 已完成：0 / 7
- 阻塞问题：无
- 最近更新时间：2026-07-27（Asia/Shanghai）

## 本批交付边界

本批只建设“文档处理平台”的可复用底座，并用 TXT/Markdown 的确定性解析打通完整链路。PDF、Office、OCR、向量索引、Knowledge 管理界面和复杂文档编辑分别进入后续批次，不在本分支伪装成已支持。

交付内容：

- 文档 Revision、Block、Processing Job、Capability 的稳定领域协议。
- 独立、轻量、可横向扩展的 `document-worker`。
- API 控制面、Redis Job 通知、租约、心跳、重试、取消和幂等。
- Worker 通过受控内部 API 租借输入并回传产物，不直接持有业务数据库或对象存储凭据。
- TXT/Markdown 基线解析器、结构化 Block 和可追踪 Locator。
- 面向 Agent 的受控 Document System Tool 门面。
- 可观测性、配额/超时边界、部署与故障恢复基础。

明确不交付：

- PDF/DOCX/PPTX/XLSX 正式解析器、OCR、页面渲染。
- embedding、pgvector、临时 Context Index、长期 Knowledge Index。
- Knowledge Base、Project/Agent Binding 和引用卡片 UI。
- 任意 Shell、宏、脚本、外链执行或通用 Office 桌面环境。
- 自动把文档全文或解析产物注入模型上下文。

## 全局约束

- 文档处理不得启动、恢复或依赖 Agent Sandbox；不得依赖 Chrome、Xvfb、VNC、Node、sudo。
- 原始 `File Asset` 不可变；解析结果属于版本化 `Document Revision`，编辑/转换结果后续采用 copy-on-write。
- 幂等键至少包含 `user_id + file_sha256 + parser_name + parser_version + options_hash`。
- 所有领域记录必须以 `user_id` 隔离；公共 API 使用现有用户认证，内部 Worker API 使用独立服务身份。
- Worker 不直接访问业务数据库，不持有 COS/OSS/S3 长期密钥；输入和产物都通过带范围与时效的内部协议交换。
- Job 必须支持 `queued/running/succeeded/partial/failed/cancelled`，并记录 attempt、lease、heartbeat、progress、error_code。
- Job 领取和完成必须具备 compare-and-set 语义；重复消息、Worker 崩溃和晚到回执不能生成两个有效 Revision。
- 不信任扩展名和客户端 MIME；实际格式探测、压缩包防护、大小/页数/条目数限制属于处理前置条件。
- 日志和 Trace 不记录文档正文、内部下载凭据或完整结构化产物。
- Document Tool 返回摘要、定位符和资源 ID；完整内容只在后续显式读取/检索时按预算进入模型。
- 本批不添加向量扩展或 embedding 依赖，避免把“能解析”与“必须向量化”耦合。
- 不自动提交、推送、创建 PR 或合并。
- 一次只推进一个 Task；状态、偏差和验证证据必须立即写回本计划。

## 状态变更记录

| 日期时间 | 整体状态 | 当前任务 | 变更原因 |
| --- | --- | --- | --- |
| 2026-07-27 | `PLAN_READY` | 无 | 总体设计确认后，拆出独立的文档处理基础设施批次 |

## Task 1：冻结领域协议、Capability 与安全边界

状态：pending

### 目标

先用纯领域对象和协议固定 Document Worker、API、System Tool 与未来解析器之间的接口，防止实现过程中把 PDF/OCR、RAG 或 Sandbox 依赖泄漏进底层。

### 涉及文件

- `agentic/api/app/core/entities/document.py`（新建）
- `agentic/api/app/core/documents/__init__.py`（新建）
- `agentic/api/app/core/documents/protocols.py`（新建）
- `agentic/api/app/core/documents/capabilities.py`（新建）
- `agentic/api/app/schemas/document.py`（新建）
- `agentic/api/tests/app/core/documents/test_protocols.py`（新建）
- `agentic/api/tests/app/core/documents/test_capabilities.py`（新建）

### 依赖与接口

- 前置任务：无。
- 输入：现有 `File` 实体、用户隔离规则、对象存储抽象。
- 输出：
  - `DocumentRevision`、`DocumentBlock`、`DocumentLocator`、`DocumentProcessingJob`；
  - `DocumentCapabilityDescriptor`；
  - `DocumentSourceLease`、`DocumentArtifactManifest`、`DocumentJobResult`；
  - Parser/Worker/API 共同使用的枚举、错误码和版本字段。

### 实施步骤

1. 定义 Job 状态、Revision 状态、Block 类型、Locator 类型和标准错误码；状态转换由单一函数校验。
2. 定义 Capability Descriptor，至少包含 `name`、`version`、输入 MIME、输出类型、资源等级、是否需要 OCR、最大文件限制和稳定性等级。
3. 定义 Parser Protocol：探测、计划、执行、产物清单；不得暴露业务数据库、对象存储客户端或 Sandbox。
4. 定义结构化 Block 的最小字段：顺序、类型、文本、层级、来源定位、元数据、内容哈希；文本可为空但定位符必须可序列化。
5. 定义 Worker 与 API 的租约、心跳、进度、完成、部分成功、失败和取消数据契约。
6. 为状态机非法转换、未知能力、协议版本不兼容、Locator 序列化建立纯单元测试。
7. 在协议注释中明确未来 PDF 页、Word 标题路径、PPT 页和 Excel Sheet/范围如何扩展，首批不实现其解析器。

### 验证方式

- 运行：`uv run pytest tests/app/core/documents/test_protocols.py tests/app/core/documents/test_capabilities.py -q`
- 运行：`uv run ruff check app/core/entities/document.py app/core/documents app/schemas/document.py tests/app/core/documents`
- 运行：`uv run python -m py_compile app/core/entities/document.py app/core/documents/protocols.py app/core/documents/capabilities.py app/schemas/document.py`
- 预期：领域层无需数据库、Redis、对象存储、LLM 或 Sandbox 即可导入和测试。

### 完成条件

- 后续 API、Worker 和 Tool 可以只依赖本任务协议并独立实现。
- 不存在“解析成功即自动向量化”或“读取文档即注入全文”的隐式语义。

### 执行结果

待执行。

### 验证证据

待执行后填写。

## Task 2：建立 Revision、Block 与 Processing Job 持久化

状态：pending

### 目标

为不可变解析结果、可定位结构块和可恢复 Job 建立正式数据模型、Repository、迁移和事务边界。

### 涉及文件

- `agentic/api/app/models/document.py`（新建）
- `agentic/api/app/models/__init__.py`
- `agentic/api/app/repositories/document_repository.py`（新建）
- `agentic/api/app/repositories/db_document_repository.py`（新建）
- `agentic/api/app/repositories/document_job_repository.py`（新建）
- `agentic/api/app/repositories/db_document_job_repository.py`（新建）
- `agentic/api/app/repositories/uow.py`
- `agentic/api/app/repositories/db_uow.py`
- `agentic/api/alembic/versions/<revision>_document_processing_foundation.py`（新建，实施时以当前唯一 head 生成 revision）
- `agentic/api/tests/app/repositories/test_document_repository.py`（新建）
- `agentic/api/tests/app/repositories/test_document_job_repository.py`（新建）

### 依赖与接口

- 前置任务：Task 1。
- 输入：`files.id`、`files.user_id`、文件 SHA-256；当前数据库与 Repository 模式。
- 输出：
  - `document_revisions`；
  - `document_blocks`；
  - `document_processing_jobs`；
  - 原子 Job 领取、续租、取消、重试与完成接口。

### 实施步骤

1. 先检查实施时 Alembic 唯一 head，不在计划阶段硬编码 `down_revision`。
2. Revision 记录输入文件、解析器/协议版本、options hash、状态、质量摘要、产物 manifest 和时间戳。
3. Block 使用稳定顺序与 Revision 外键，保存结构文本、内容哈希、Locator JSON 和受控元数据；为分页读取建立索引。
4. Job 保存 capability、优先级、状态、progress、attempt、max_attempts、lease_owner、lease_expires_at、heartbeat_at、cancel_requested_at 和结构化错误。
5. 建立幂等唯一约束；并发重复提交只允许一个有效 Job/Revision，其余返回已有资源。
6. Repository 用条件更新实现领取、续租和完成；过期租约可重领，旧 Worker 的完成回执必须被拒绝。
7. 数据库只保存必要结构与 manifest；大型渲染产物和机器可读文件继续进入对象存储。
8. 覆盖用户隔离、重复消息、租约过期、晚到完成、取消与失败重试测试。
9. 验证迁移 upgrade/downgrade/upgrade，并确认现有 File、Session、Project 数据不变。

### 验证方式

- 运行：`uv run alembic heads`
- 运行：`uv run alembic upgrade head`
- 运行：`uv run pytest tests/app/repositories/test_document_repository.py tests/app/repositories/test_document_job_repository.py -q`
- 运行：`uv run alembic downgrade -1`
- 运行：`uv run alembic upgrade head`
- 运行：`uv run ruff check app/models/document.py app/repositories/document_repository.py app/repositories/db_document_repository.py app/repositories/document_job_repository.py app/repositories/db_document_job_repository.py tests/app/repositories`
- 预期：仅一个 Alembic head；并发幂等与租约测试稳定通过；迁移可逆。

### 完成条件

- API 可在不启动 Worker 的情况下可靠创建、查询、取消和恢复 Job。
- Worker 崩溃或重复消费不会产生两个成功 Revision。

### 执行结果

待执行。

### 验证证据

待执行后填写。

## Task 3：实现用户侧编排 API 与幂等服务

状态：pending

### 目标

把现有 File Asset 转换为显式、异步、可查询的 Document Processing Job，不把解析等待时间占用在上传请求或对话 Run 内。

### 涉及文件

- `agentic/api/app/services/document_service.py`（新建）
- `agentic/api/app/services/document_job_service.py`（新建）
- `agentic/api/app/controllers/document.py`（新建）
- `agentic/api/app/controllers/__init__.py`
- `agentic/api/app/schemas/document.py`
- `agentic/api/app/config.yaml`
- `agentic/api/app/core/config.py`
- `agentic/api/tests/app/services/test_document_job_service.py`（新建）
- `agentic/api/tests/app/controllers/test_document_controller.py`（新建）

### 依赖与接口

- 前置任务：Task 1、Task 2。
- 输入：当前用户拥有的 `file_id`、capability、options、可选 client idempotency key。
- 输出：
  - `POST /api/files/{file_id}/document-jobs`；
  - `GET /api/document-jobs/{job_id}`；
  - `POST /api/document-jobs/{job_id}/cancel`；
  - `POST /api/document-jobs/{job_id}/retry`；
  - `GET /api/files/{file_id}/document-revisions`；
  - `GET /api/document-revisions/{revision_id}` 与分页 Block 查询。

### 实施步骤

1. 检查 File 所有权、状态、实际大小、声明 MIME 与 capability 是否匹配，再创建 Job。
2. 由服务端计算稳定 options hash 和幂等键；重复请求返回已有 Job，不重复排队。
3. 配置每用户并发 Job 数、单文件大小、超时、最大尝试次数和 Block 分页上限。
4. 提交事务完成后再发布 Job 通知；若 Redis 发布失败，Job 保持 `queued` 并允许恢复扫描器重新发布。
5. 查询接口只返回摘要、进度、错误码和资源 ID；默认不返回全文 Block。
6. 取消采用 `cancel_requested` 协作语义；queued Job 可直接取消，running Job 由 Worker 在安全点终止。
7. retry 仅创建新 attempt 或安全重排失败 Job，不覆盖历史错误和 Revision。
8. 对不存在资源和越权资源统一使用现有防枚举语义。
9. 覆盖 Redis 暂时不可用、重复提交、越权、取消竞态和分页上限测试。

### 验证方式

- 运行：`uv run pytest tests/app/services/test_document_job_service.py tests/app/controllers/test_document_controller.py -q`
- 运行：`uv run ruff check app/services/document_service.py app/services/document_job_service.py app/controllers/document.py app/schemas/document.py tests/app/services/test_document_job_service.py tests/app/controllers/test_document_controller.py`
- 运行：`uv run python -m py_compile app/services/document_service.py app/services/document_job_service.py app/controllers/document.py`
- 预期：API 请求快速返回；Worker 离线时不丢 Job；任何用户不能读取他人的 Revision、Block 或 Job。

### 完成条件

- 上传、存储和异步处理相互解耦。
- 一个 3–5 万字文档的处理不会阻塞对话 HTTP/SSE 生命周期。

### 执行结果

待执行。

### 验证证据

待执行后填写。

## Task 4：实现内部 Worker 协议、队列通知与服务身份

状态：pending

### 目标

建立“Redis 只传 Job ID、业务数据通过内部 API 租借”的安全控制面，使 Worker 可以无数据库和对象存储长期凭据运行。

### 涉及文件

- `agentic/api/app/core/documents/queue.py`（新建）
- `agentic/api/app/services/document_worker_service.py`（新建）
- `agentic/api/app/controllers/internal_document.py`（新建）
- `agentic/api/app/schemas/document.py`
- `agentic/api/app/core/config.py`
- `agentic/api/app/config.yaml`
- `agentic/api/tests/app/core/documents/test_queue.py`（新建）
- `agentic/api/tests/app/services/test_document_worker_service.py`（新建）
- `agentic/api/tests/app/controllers/test_internal_document_controller.py`（新建）

### 依赖与接口

- 前置任务：Task 1、Task 2、Task 3。
- 输入：Redis 中的 Job ID、Worker 身份、Job lease token。
- 输出：
  - claim、heartbeat、progress、source lease、artifact upload、complete、partial、fail 内部接口；
  - at-least-once 消息消费下的幂等完成语义；
  - queued Job 恢复扫描器。

### 实施步骤

1. Redis payload 只包含协议版本、Job ID 和调度元数据，不包含正文、对象存储密钥或用户 Token。
2. Worker 以独立内部密钥或签名身份调用 API；密钥必须支持轮换并与普通用户认证分离。
3. claim 返回短时 lease token；后续 heartbeat、source、artifact 和 complete 都绑定 Job、attempt、Worker 与 lease。
4. source 采用短时、只读、单对象访问；artifact 采用短时、限定目标和大小的上传协议，或由 API 流式中转。
5. complete 在同一事务内验证 lease、写 Revision/Block manifest、切换 Job 状态；提交后才确认 Redis 消息。
6. heartbeat 更新租约与阶段化 progress，不允许倒退；取消请求通过 heartbeat/查询返回给 Worker。
7. 恢复扫描器重发长期 queued Job，并把超时 running Job 恢复为可重领状态。
8. 限制 Worker 接口网络暴露、请求体大小和速率；内部日志只记录 ID、阶段、耗时、资源量和错误码。
9. 覆盖伪造身份、过期 lease、重复 complete、晚到 Worker、Redis 重投和恢复扫描测试。

### 验证方式

- 运行：`uv run pytest tests/app/core/documents/test_queue.py tests/app/services/test_document_worker_service.py tests/app/controllers/test_internal_document_controller.py -q`
- 运行：`uv run ruff check app/core/documents/queue.py app/services/document_worker_service.py app/controllers/internal_document.py tests/app/core/documents/test_queue.py tests/app/services/test_document_worker_service.py tests/app/controllers/test_internal_document_controller.py`
- 预期：重复投递只产生一个结果；无有效服务身份或 lease 的请求全部失败；Redis/Worker 短暂中断后 Job 可恢复。

### 完成条件

- Worker 只持有 Redis 消费和内部 API 所需的最小配置。
- API 仍是用户隔离、业务状态和对象访问授权的唯一控制面。

### 执行结果

待执行。

### 验证证据

待执行后填写。

## Task 5：建立轻量 Document Worker 与基线解析器

状态：pending

### 目标

创建独立 Worker 进程，用 TXT/Markdown 解析验证领取、下载、隔离临时目录、结构化、回传、心跳、取消和清理的完整链路。

### 涉及文件

- `agentic/document-worker/pyproject.toml`（新建）
- `agentic/document-worker/uv.lock`（由包管理器生成）
- `agentic/document-worker/Dockerfile`（新建）
- `agentic/document-worker/app/__init__.py`（新建）
- `agentic/document-worker/app/config.py`（新建）
- `agentic/document-worker/app/client.py`（新建）
- `agentic/document-worker/app/worker.py`（新建）
- `agentic/document-worker/app/parsers/__init__.py`（新建）
- `agentic/document-worker/app/parsers/text.py`（新建）
- `agentic/document-worker/app/parsers/markdown.py`（新建）
- `agentic/document-worker/tests/test_worker_lifecycle.py`（新建）
- `agentic/document-worker/tests/test_text_parser.py`（新建）
- `agentic/document-worker/tests/test_markdown_parser.py`（新建）

### 依赖与接口

- 前置任务：Task 1、Task 4。
- 输入：Redis Job ID、内部 API、短时 source lease。
- 输出：Revision manifest、顺序化 Block、文本/Markdown Locator、质量与资源摘要。

### 实施步骤

1. 使用精简 Python slim 基础镜像；只安装 Redis/HTTP/验证/格式探测和基线解析所需依赖。
2. Worker 启动时注册协议版本和 capability；不支持的能力必须拒绝领取或返回稳定 `unsupported_capability`。
3. 每个 Job 使用独立临时目录；校验下载大小、SHA-256 和实际 MIME，完成/失败/取消后清理。
4. 解析在受控子进程或等价资源边界中执行，设置 wall-time、内存、输出大小和 Block 数限制。
5. TXT 解析保留行号定位；Markdown 解析生成 heading path、段落/列表/代码块类型和行号范围。
6. 解析结果不调用 LLM、不做 embedding；Block 以批次回传，避免一次把 3–5 万字常驻内存或塞入单个请求。
7. 周期发送 heartbeat/progress；处理取消时终止解析、停止上传并报告 cancelled。
8. MIME 不匹配、编码异常、超限、加密/压缩炸弹疑似输入返回结构化错误。
9. 故障注入覆盖 Worker 崩溃、网络断开、重复消息、回传中断、取消和临时文件清理。
10. 检查镜像中不存在 Chrome/Chromium、Node、Xvfb、VNC、websockify 和 sudo。

### 验证方式

- 在 `agentic/document-worker` 运行：`uv sync`
- 运行：`uv run pytest -q`
- 运行：`uv run ruff check app tests`
- 运行：`uv run python -m py_compile app/config.py app/client.py app/worker.py app/parsers/text.py app/parsers/markdown.py`
- 构建：`docker build -t manus-document-worker:test .`
- 检查：`docker run --rm manus-document-worker:test sh -lc 'for c in google-chrome chromium node Xvfb x11vnc websockify sudo; do command -v "$c" && exit 1 || true; done'`
- 预期：TXT/Markdown 端到端产出稳定 Block；故障可恢复；镜像无浏览器/VNC/Node/sudo。

### 完成条件

- 基线解析全程不创建 Agent Sandbox，也不经过 Agent LLM。
- Worker 能安全处理 3–5 万字文本，并按批次回传结构化结果。

### 执行结果

待执行。

### 验证证据

待执行后填写。

## Task 6：提供受控 Document System Tool 门面

状态：pending

### 目标

让 Agent 能显式查看文档状态、启动受支持处理和分页读取结构块，同时保持工具 Schema 紧凑且不把全文自动放进上下文。

### 涉及文件

- `agentic/api/app/core/tools/document.py`（新建）
- `agentic/api/app/core/tools/builtin/catalog.py`
- `agentic/api/app/core/tools/registry.py`
- `agentic/api/app/core/tools/factory.py`
- `agentic/api/app/services/tool_capability_service.py`
- `agentic/api/tests/app/core/tools/test_document_tools.py`（新建）
- `agentic/api/tests/app/services/test_document_tool_capability.py`（新建）

### 依赖与接口

- 前置任务：Task 1、Task 3、Task 5。
- 外部依赖：`agent-runtime-lazy-sandbox-plan.md` 完成后的 capability scope 接口；若尚未合并，只实现 Tool 本体与 descriptor，集成步骤等待前置分支。
- 输入：`file_id`、`job_id`、`revision_id`、Block 分页范围。
- 输出：
  - `document_inspect`：文件、Revision、能力和状态摘要；
  - `document_process`：显式启动受支持 capability；
  - `document_read_blocks`：按数量/字符预算读取结构块。

### 实施步骤

1. 将三个 Tool 注册为 `document` capability group，descriptor 明确 `requires_sandbox=false`、`requires_browser=false`。
2. Tool 只接受资源 ID、受控枚举和有上限的分页参数，不接受服务器路径、Shell 命令或任意解析器名称。
3. `document_inspect` 返回元数据、可用能力、进度、错误和定位摘要，不返回完整正文。
4. `document_process` 返回 Job 资源和状态，不在 Tool 调用中同步等待解析完成。
5. `document_read_blocks` 强制 Block 数与字符预算，结果包含 Revision、Block ID 和 Locator，超出部分返回 continuation。
6. 所有 Tool 复用用户身份和 Service 层隔离，不允许 Agent 通过 ID 访问其他用户文件。
7. 在 Trace 中记录 capability、Job/Revision ID、读取字符数、耗时和状态，不记录正文。
8. 验证 Planner 只看到紧凑 document capability 描述，只有相应 Step 的 ReAct 才看到完整 Tool Schema。
9. 验证调用这三个 Tool 时 `sessions.sandbox_id` 保持 null。

### 验证方式

- 运行：`uv run pytest tests/app/core/tools/test_document_tools.py tests/app/services/test_document_tool_capability.py -q`
- 运行：`uv run ruff check app/core/tools/document.py app/core/tools/builtin/catalog.py app/core/tools/registry.py app/core/tools/factory.py app/services/tool_capability_service.py tests/app/core/tools/test_document_tools.py tests/app/services/test_document_tool_capability.py`
- 联合运行：`uv run pytest tests/app/core/agent/test_runtime_tool_scope.py tests/app/core/tools/test_document_tools.py -q`
- 预期：Document Tool 无 Sandbox，Schema 仅按 capability 暴露，全文不会由 inspect/process 自动进入模型。

### 完成条件

- 文档处理是正式 System Tool 能力，不需要 Agent 猜 Shell 命令。
- Tool 的默认响应规模可预测，并支持后续 Context Index Tool 复用 Revision/Locator。

### 执行结果

待执行。

### 验证证据

待执行后填写。

## Task 7：部署、端到端故障验证与合并前审查

状态：pending

### 目标

把 API、Redis 和轻量 Worker 组成可部署链路，用真实容器验证安全、恢复、资源和 Sandbox/Token 隔离，并完成独立代码审查。

### 涉及文件

- `agentic/docker/docker-compose.yml`
- `agentic/docker/docker-compose.dev.yml`
- `agentic/docker/.env.example`（新建；不得提交真实内部密钥）
- `agentic/api/tests/integration/test_document_processing_pipeline.py`（新建）
- `agentic/document-worker/tests/integration/test_worker_api_contract.py`（新建）
- 本计划文档

### 依赖与接口

- 前置任务：Task 1–Task 6。
- 输入：API、Redis、数据库、对象存储和 `manus-document-worker` 镜像。
- 输出：可复现的部署配置、端到端测试证据、资源对比和代码审查结论。

### 实施步骤

1. 在 Compose 新增 `manus-document-worker`，只挂载必要配置；不挂 Docker socket，不继承 Sandbox 特权或宿主目录。
2. 配置健康检查、优雅停止、并发数、临时目录上限、Job 超时和内部服务身份。
3. 用真实 TXT/Markdown 文件验证上传后显式处理、轮询、Revision、分页 Block 和 Locator。
4. 验证相同文件/选项重复提交、两个 Worker 竞争、Worker 被强制停止、lease 到期、重启恢复和重复 complete。
5. 验证取消、超限、MIME 欺骗、未支持 PDF/DOCX、伪造 Worker 身份和跨用户访问。
6. 验证整个文档链路不创建 Sandbox；对比无文档普通对话、文档 inspect/process Run 的 Sandbox 创建数和 Tool Schema bytes。
7. 记录 Worker 镜像大小、空闲内存、处理 3–5 万字样本文档的峰值内存/耗时和 API 响应时间；本批不设置未经测量的硬性性能承诺。
8. 执行 API、Worker、Web 受影响测试、lint、类型检查、构建和迁移验证。
9. 使用 `supercoder:verification-before-completion` 写回完整验证证据。
10. 使用 `supercoder:code-review` 审查权限隔离、租约并发、幂等、迁移、日志泄露、资源限制和维护性；修复 blocking/major 后重新验证。

### 验证方式

- API：`cd agentic/api && uv run pytest -q`
- API lint：`cd agentic/api && uv run ruff check app tests`
- 迁移：`cd agentic/api && uv run alembic heads && uv run alembic upgrade head`
- Worker：`cd agentic/document-worker && uv run pytest -q && uv run ruff check app tests`
- Web 回归：`cd agentic/web && pnpm test:run && pnpm type-check && pnpm build`
- 容器：`cd agentic/docker && docker compose build manus-api manus-document-worker`
- 启动：`cd agentic/docker && docker compose up -d postgres redis manus-api manus-document-worker`
- 状态：`cd agentic/docker && docker compose ps`
- 日志：`cd agentic/docker && docker compose logs --no-color --tail=200 manus-api manus-document-worker`
- 集成测试：`cd agentic/api && uv run pytest tests/integration/test_document_processing_pipeline.py -q`
- 差异检查：`git diff --check --`

### 端到端验收矩阵

| 场景 | 预期 |
| --- | --- |
| TXT/Markdown 首次处理 | 快速返回 queued/running，最终生成唯一 Revision 和有序 Block |
| 3–5 万字文本 | 分批处理和回传，不进入 LLM，不启动 Sandbox |
| 相同内容与选项重复提交 | 返回已有 Job/Revision，不重复处理 |
| Worker 崩溃或重启 | lease 到期后恢复，旧 Worker 回执被拒绝 |
| Redis 重复消息 | 只产生一个有效完成结果 |
| 运行中取消 | 在安全点停止，状态为 cancelled，无残留临时文件 |
| MIME 欺骗或超限 | 稳定错误码，无危险解析 |
| PDF/DOCX 输入 | 返回 unsupported capability，不声称已解析 |
| 非法用户或 Worker 身份 | 不能读取 source、Revision、Block 或回传产物 |
| 普通对话与 Document Tool | `sandbox_id` 保持 null，Document Tool Schema 只按需进入 ReAct |
| Worker 容器检查 | 不含 Chrome、Node、Xvfb、VNC、websockify、sudo |

### 完成条件

- 所有 Task 状态为 completed，计划包含实际命令、结果和证据。
- 合并结论只能是 `READY_TO_MERGE`、`BLOCKED` 或 `FAILED`。
- blocking/major 审查问题为零。
- 未支持能力清晰失败，没有 fallback 到 Agent Sandbox。

### 执行结果

待执行。

### 验证证据

待执行后填写。

## 最终验收

整体状态：待执行。

最终结论：待验证后填写，当前不得声称 `READY_TO_MERGE`。

必须提供：

- 实际分支与基线 commit。
- Alembic upgrade/downgrade/upgrade 结果与唯一 head。
- API、Worker、Web 测试/lint/type-check/build 结果。
- 真实容器健康状态和故障恢复证据。
- 并发幂等、租约、取消、权限隔离和未支持格式测试。
- Document Worker 镜像依赖与资源测量。
- 普通对话和文档链路的 Sandbox 创建数、Tool Schema count/bytes 对比。
- 独立代码审查结论及 blocking/major 修复记录。

## 后续独立批次

本计划完成后按价值和依赖顺序继续：

1. `document-parsers-pdf-office-plan.md`：PDF/DOCX/PPTX/XLSX、选择性 OCR、页面/标题/Sheet Locator 和预览产物。
2. `session-context-index-plan.md`：临时关键词索引起步，按阈值/意图升级 embedding，TTL 与 Run Trace。
3. `knowledge-durable-index-plan.md`：Knowledge Base、混合检索、索引代际、Project Binding 和引用。
4. `document-operations-plan.md`：受控转换、编辑、渲染、拆分合并和 copy-on-write 派生文件。
