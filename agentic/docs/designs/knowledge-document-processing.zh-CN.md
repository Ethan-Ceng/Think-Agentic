# Knowledge 与文档处理平台

## 文档状态

- 状态：`DESIGN_READY`
- 负责人：Codex
- 创建日期：2026-07-27
- 最近更新：2026-07-27
- 关联路线：第三组大型能力中的 Knowledge

## 背景

当前 Agentic 已经具备用户级文件中心、会话附件、Local/COS/OSS 对象存储、Session 单层 Project、运行 Trace 和 Agent Sandbox，但这些能力尚未形成文档知识能力：

- `files` 保存原始对象及文件元数据，不解析文档内容；
- 单文件默认限制为 100 MB，API 会把整个上传读入 `BytesIO`，不适合简单调大上限来接收大文件；
- PDF、DOCX、PPTX、XLSX 目前只能下载，不能在产品内结构化预览或定位引用；
- 会话附件会复制到短生命周期 Sandbox，由 Agent 通过文件路径操作，不会形成可复用索引；
- 全局搜索使用 PostgreSQL `ILIKE` 搜索标题、消息、Trace 摘要和文件名，不搜索文档正文；
- Project 当前只是 Session 的单层目录，不会向模型隐式注入文件、Prompt 或记忆；
- Agent 运行时目前只有会话 Memory、分支上下文和 Skill Runtime Context，没有 Knowledge Runtime Context；
- 仓库中尚无 PDF/Office 解析、OCR、embedding、向量数据库或专用文档 Worker 依赖。

因此，本批不能只实现“上传文档、切块、转向量”。Knowledge 需要建立在可复用的文档处理底座上，并明确区分：

1. 原始文件资产；
2. 文档解析与结构化产物；
3. 临时或长期检索索引；
4. 用户可管理的 Knowledge；
5. Project、Agent、Session 与 Knowledge 的显式绑定；
6. 一次 Run 中实际使用了哪些知识和引用。

## 目标

- 支持 PDF、DOCX、PPTX、XLSX 以及现有文本类文件的结构化处理。
- 建立可被用户和 Agent 复用的文档操作能力，覆盖检查、转换、渲染、编辑、拆分合并和生成，而不只服务于 RAG。
- 对扫描 PDF 按页识别并只在必要页面执行 OCR。
- 对大文件提供可恢复上传、异步处理、进度、取消、重试和部分成功状态。
- 原始文件、解析产物和检索索引相互解耦，任何 embedding 都能从原文件和解析产物重建。
- 明确临时知识与长期 Knowledge 的生命周期、成本、删除和重建规则。
- 使用关键词、向量、结构和元数据过滤组成混合检索，不把向量相似度当作唯一答案。
- 引用可稳定定位到 PDF 页、Word 标题、PPT 页或 Excel Sheet/单元格范围。
- Knowledge 可显式绑定 Project，并为未来 Agent Profile / Skill 绑定预留稳定边界。
- 每次检索进入 Trace，用户能看见本次回答用了哪些 Knowledge、文档和位置。
- 文件或 embedding 服务局部失败时可降级，而不是让整个 Knowledge 不可用。

## 功能范围

### 子系统 A：文件接入与文档处理

- 复用 `files` 作为原始文件资产，不把解析状态和向量直接堆入 `files.metadata`。
- 保留现有小文件上传接口，新增大文件分片/直传协议。
- 对文件执行类型嗅探、完整性校验、配额检查、压缩炸弹防护和密码保护检测。
- 异步执行解析、OCR、结构归一化、派生产物生成和质量评估。
- 产出稳定的文档 Revision、结构化 Block、可选页面预览和机器可读文本。
- 提供受控的文档转换与编辑 Job；默认保留原件并生成新的 File Asset。

### 子系统 B：检索索引

- 从 Document Revision 生成 Chunk、关键词索引和可选 embedding。
- 内容 Index 与 Scope Binding 分离；Binding 支持 `session_ephemeral` 与 `knowledge_durable` 两种生命周期。
- 支持 embedding 模型与 chunking 版本化、并行重建和原子切换。
- 提供混合检索、元数据过滤、去重、重排和引用定位。

### 子系统 C：Knowledge 管理

- 创建、重命名、删除 Knowledge Base。
- 从文件中心选择文件或上传文件加入 Knowledge。
- 展示每个文档的处理状态、解析质量、索引版本和失败原因。
- 支持移除、重新处理、重新索引及查看来源。
- 支持显式绑定 Project；Agent Profile / Skill 在对应模型完成后接入。

### 子系统 D：会话与 Agent 使用

- 会话上传附件时可按需建立临时文档能力，不自动成为长期 Knowledge。
- Planner/ReAct 通过检索工具读取相关片段，不把完整 Knowledge 隐式塞进系统 Prompt。
- 运行时只注入简短的可用知识清单和检索协议。
- 检索结果与引用进入本次 Run 的临时上下文和 Trace，不自动写入用户长期记忆。

### 子系统 E：文档操作

- 用户可在文件预览或对话中发起受控的 PDF、Word、PowerPoint 和 Excel 操作。
- Agent 使用结构化 Document Tool，而不是通过不透明 Shell 命令修改正式资产。
- 所有修改默认采用 copy-on-write：原始文件保持不变，结果作为 `agent_generated` 新文件进入文件中心。
- 记录输入文件、输出文件、操作、工具版本和 Run/Job，形成可追踪派生关系。
- 大文件转换与编辑复用 Document Worker、Job 状态、配额和进度能力。

## 非功能范围

- 不实现 Google Docs、Microsoft 365 的在线协同编辑。
- 不实现完整 Office 桌面编辑器；首期以解析、预览、检索、引用和下载为主。
- 不承诺 PDF 到可编辑 Word、任意复杂版式还原或跨 Office 格式的像素级无损转换。
- 不把任意 Agent Sandbox 命令作为正式文档处理流水线。
- 首期不执行 Office 宏、嵌入脚本或文档中的外部链接。
- 首期不实现企业组织、部门、角色继承和文档级复杂 ACL，但所有记录必须有 `user_id` 隔离。
- 首期不自动把所有历史文件和附件转成向量。
- 首期不将对话 Memory、用户长期记忆和 Knowledge 合并为一个存储概念。
- 音频、视频转写和通用图片理解属于后续多模态文档能力。
- 旧版 `.doc/.xls/.ppt` 转换、手写 OCR 和复杂图表视觉理解放在后续阶段。

## 概念边界

```text
File Asset
  原始二进制、文件名、哈希、对象存储位置
        |
        v
Document Revision
  某个文件内容在某个解析器版本下的结构化结果
        |
        v
Content Index Generation
  keyword + vector + structure，可重建
        |
        +--------------------+
        |                    |
        v                    v
Session Scope Binding    Knowledge Scope Binding
带 TTL                   长期保留
        |                    |
        +----------+---------+
                   v
             Hybrid Retrieval
      keyword + vector + structure + filters
                   |
                   v
       Citation + Run Trace + Agent answer
```

核心定义：

- **文件不是知识库**：同一文件可未处理、临时使用或加入一个/多个 Knowledge。
- **解析结果不是向量**：Document Revision 是有结构、可检查、可重建的中间事实。
- **向量不是事实源**：embedding 是带模型版本的派生索引，删除后可以重建。
- **Project 不是 Knowledge**：Project 继续组织 Session；Project 与 Knowledge 通过显式 Binding 关联。
- **Memory 不是 Knowledge**：Session Memory 保存运行上下文，用户长期记忆保存个人事实，Knowledge 保存来源可追溯的文档资料。

## Worker、RAG 与 System Tool 的归属

三者不是互斥选择，而是不同层级：

```text
Document Processing Service
  系统底座：解析、OCR、结构化、渲染、转换
  执行载体：document-worker
          |
          v
Context Index / Retrieval Service
  RAG 能力：chunk、关键词、embedding、融合检索、引用
  同时服务临时 Context 与长期 Knowledge
          |
          v
System Tool Facade
  Agent 接口：context_prepare / context_search / context_open
  文档接口：document_inspect / document_action
```

### 方案 1：全部放入 RAG

- RAG Worker 自己读取 PDF/Office、执行 OCR、结构化、chunk 和 embedding。
- 优点：单体交付快，上传到检索链路短。
- 缺点：
  - 文档预览、转换、编辑和 Agent 文件操作无法自然复用；
  - 解析器升级与检索策略耦合；
  - 容易把所有结构化产物降格为“给 embedding 用的纯文本”。
- 结论：不采用。

### 方案 2：全部作为 Agent System Tool

- Agent 调用工具，在 Sandbox 或工具进程中完成解析、OCR、向量化和查询。
- 优点：Agent 可自由编排，首期接口数量少。
- 缺点：
  - 每次 Run 可能重复处理；
  - 生命周期、权限、幂等、进度和缓存难以治理；
  - Sandbox 销毁后临时索引丢失；
  - 模型需要承担本应由系统确定的技术决策。
- 结论：不采用。

### 方案 3：系统文档底座 + RAG Context Index + Tool 门面

- Worker 归 Document Processing Service，产出与 RAG 无关的 Revision/Block。
- Context Index Service 消费 Block，提供临时或长期检索能力。
- Agent 通过受控 Tool 使用能力；标准附件由系统自动准备，特殊场景才由 Planner 调用 `context_prepare`。
- 优点：
  - 文档能力可被预览、编辑、Knowledge 和 Agent 共用；
  - RAG 可以独立演进 chunk、embedding 和检索策略；
  - Tool 接口简洁且不暴露 Worker、路径或向量数据库；
  - 同一文档的索引可被临时和长期 Scope 复用。
- 缺点：需要明确两个服务的状态衔接和失败语义。
- 结论：推荐。

关键原则：

- **Worker 是部署与执行组件，不是 Agent Tool。**
- **RAG 是 Context Index/Retrieval 能力，不负责成为通用 Office 处理平台。**
- **RAG 可以作为 System Tool 暴露“准备临时上下文、搜索、展开引用”的能力。**
- **标准上传不依赖 LLM 决定是否解析；系统根据文件和意图自动准备，避免重复 Tool Call。**
- **Agent 可以创建临时 Context，但不能通过 Tool 把资料永久加入 Knowledge；长期化需要明确用户动作。**

## Sandbox 与资源成本边界

常规文档处理需要安全隔离，但不需要当前这种“每个 Session 一套完整 Agent Sandbox”。

现有 Agent Sandbox 镜像包含 Chrome、Xvfb、VNC、Websockify、Node、Python、sudo 和交互式文件/Shell 服务；`AgentTaskRunner` 还会在 Run 开始时调用 `ensure_sandbox()` 并把附件复制进去。它适合浏览器、Shell 和任意代码任务，不适合成为 PDF/Office 解析的默认执行环境。

### 方案 A：每个 Session 使用完整 Agent Sandbox

- 优点：现有路径可复用，任意库和脚本灵活。
- 缺点：
  - Chrome/VNC 等无关进程占用 CPU、内存和启动时间；
  - 同一文件可能在多个 Session 重复复制和解析；
  - Sandbox TTL 与 Knowledge/临时 Context 生命周期不一致；
  - 模型容易看到 Shell/File 工具和大段输出，增加 Tool Schema 与上下文 Token。
- 结论：不用于常规文档处理。

### 方案 B：直接在 API 进程解析

- 优点：部署组件少、调用开销低。
- 缺点：
  - PDF/Office/OCR 属于 CPU、内存和异常风险较高的任务；
  - 恶意或损坏文件可能拖慢 API；
  - 长任务、取消、重试和资源限制难以治理。
- 结论：仅允许非常小的安全元数据读取，不承担正式解析。

### 方案 C：共享的轻量 Document Worker Pool

- Worker Pool 是常驻或按负载弹性的共享服务，不为每个 Session 创建完整环境。
- 镜像只包含 PDF/OOXML 解析器、OCR、可选 LibreOffice 和必要字体。
- 不安装或不启动 Chrome、VNC、Xvfb、Node、sudo、交互式 Shell。
- 每个 Job 使用独立临时目录、低权限用户、只读基础镜像、CPU/内存/超时/文件大小限制。
- Worker 从对象存储读取输入，把 Revision/Artifact 写回系统；不持有 Session 对话上下文。
- 同一文件解析结果按哈希和版本复用。
- 结论：推荐。

### Sandbox 懒启动

要真正节省资源，Agent Runtime 还需要从“Run 启动即创建 Sandbox”调整为“首次使用 Sandbox Tool 才创建”：

```text
纯问答 / Knowledge / Context Search
  -> 不创建 Sandbox
  -> 只注册 context_* / message 等必要工具

首次调用 shell / browser / workspace file tool
  -> SandboxProvider.ensure()
  -> 按需同步相关附件
  -> 注册或启用对应执行能力
```

普通附件不再默认复制到 `/home/ubuntu/upload`。只有 Planner 确实选择 Sandbox 文件操作时，才把指定 File 同步进去。

### Token 成本

- PDF 文本抽取、OOXML 解析、OCR、chunking 和本地关键词索引不消耗聊天模型 Token。
- embedding 会处理文本 Token，但属于一次性、可缓存的索引成本，不应在每轮对话重复。
- Sandbox 本身不直接消耗模型 Token；真正增加 Token 的是：
  - 每轮都向模型暴露不需要的 Shell/Browser/File Tool Schema；
  - 把完整文档、命令输出或解析 JSON 塞入对话；
  - 同一文件在不同 Run 重复总结或向量化。
- Context Tool 只返回短 Manifest、Top-K 片段、Outline 和 Citation Ref；二进制、全文和大型结构产物不进入模型消息。
- 纯文档问答按意图裁剪工具集，不向模型提供 Shell、Browser、VNC 或文档编辑工具。
- OCR 默认使用本地引擎；只有低质量特殊页面才可配置视觉模型回退，并单独统计预算。

对于 3–5 万字合同/论文，合理路径是“一次解析与 embedding，多轮只取相关片段”。单次问答通常只需要少量命中 Chunk，而不是每轮重复发送全文。

## 文档类型处理策略

### PDF

- 优先读取已有文本层并保留页码、段落、字符范围和可用坐标。
- 逐页判断文本层质量；只对扫描页或低质量页执行 OCR。
- 表格作为独立 Block，保留表头、行列和页码，不只输出拼接文本。
- 目录、标题层级、页眉页脚、脚注和重复水印分别标记。
- 密码保护、损坏页、超大页面和 OCR 语言缺失产生明确质量告警。
- 引用定位至少为 `page`，有坐标时可进一步高亮区域。

### DOCX

- 保留标题层级、段落、列表、表格、分页信息、页眉页脚、脚注和链接文本。
- Chunk 优先沿标题和段落边界生成，避免固定字符数切断表格或列表。
- 文档修改后形成新 Revision；旧引用仍指向旧 Revision，并标记“已有新版本”。

### PPTX

- 按 Slide 处理标题、正文、备注、表格和图表文字。
- 图表数据与视觉标题分别保存；首期不根据图像猜测未提供的数据。
- 图片 OCR 为可选增强，不阻塞已有文本进入可用状态。
- 引用定位到 Slide 编号和元素区域。

### XLSX

- 保留 Workbook、Sheet、命名区域、表格、表头、单元格范围、显示值和公式。
- 检索结果同时提供显示值和必要的公式来源，不能把整个 Workbook 展平成一段文本。
- Chunk 以逻辑表、行窗口或命名区域为单位，并重复必要表头。
- 大 Sheet 支持按区域处理和分页读取，避免一次加载整表。
- 引用定位到 `sheet + cell_range`。

### 文本、Markdown、HTML、CSV 与代码

- 复用安全文本读取能力，但统一转换为 Document Block。
- HTML 只解析静态内容，不执行脚本、网络请求或表单。
- CSV 按表格处理并保留表头。
- 代码文件按语言结构或行范围切分；引用定位到行号。

### 旧版 Office 与特殊格式

- `.doc/.xls/.ppt` 首期返回“暂不支持直接处理，可转换为现代格式”的明确状态。
- 后续可在隔离的 Document Worker 中通过 LibreOffice 无宏、无网络转换为 PDF/OOXML。
- 转换产物只作为派生物，原文件仍是资产事实源。

## 文档操作能力

Knowledge 使用文档的“读取路径”，但文档平台还要提供独立的“操作路径”。两条路径复用格式适配器、Worker、质量报告和对象存储，不共享业务状态：

```text
Read Path
  file -> parse -> revision/blocks -> retrieval index -> citation

Action Path
  source file(s) -> validate operation -> transform/render -> verify
                 -> new file asset + derivation + optional new revision
```

### 能力矩阵

| 格式 | 读取与检查 | 首期受控操作 | 后续增强 |
| --- | --- | --- | --- |
| PDF | 页、文本层、表格、图片、表单、书签、元数据、OCR 质量 | 合并、拆分、旋转、重排、抽取页面/图片、加水印、生成可搜索 PDF、填写已有表单、渲染页面 | 真正内容编辑、可靠脱敏、签名、复杂 PDF/UA |
| DOCX | 标题、段落、样式、列表、表格、页眉页脚、脚注、批注 | 按锚点插入/替换内容、增删表格行列、套用模板、渲染 PDF、生成新 DOCX | 修订模式、复杂域、目录刷新、像素级版式复刻 |
| PPTX | Slide、版式、标题、正文、备注、表格、图表数据、媒体清单 | 新增/删除/重排 Slide、替换文本/图片、更新表格、基于模板生成、渲染 PDF/图片 | 动画、复杂 SmartArt、母版深度编辑 |
| XLSX | Sheet、表格、命名区域、单元格、公式、样式、图表定义 | 读写单元格/区域、增删 Sheet、筛选排序、公式写入、基础样式与图表、导出 CSV/PDF | 完整公式重算、宏、数据透视表深度编辑、外部数据连接 |

### 操作级别

```text
inspect
  只读，返回结构与质量信息

render / convert
  不改变语义，生成 PDF、图片或机器可读派生物

transform
  按结构化参数修改内容，生成新文件

compose
  从模板或结构化内容生成新文档
```

所有操作必须声明格式、输入数量、预计输出、是否可能丢失格式以及验证方式。无法可靠完成时返回明确限制，不能静默生成看似成功但内容缺失的文件。

### 写入与版本规则

1. 默认不覆盖 `files` 指向的原始对象。
2. 每次转换、编辑或生成创建新的 File Asset，并记录 `file_derivations`。
3. 用户明确选择“替换”时也先生成新对象和校验结果，再通过独立的资产替换/版本操作切换；首期可不开放原地替换。
4. 多输入操作（例如合并 PDF）记录全部输入及顺序。
5. 输出文件可再次进入 Document Revision 和 Knowledge，但不会自动加入原 Knowledge。
6. Knowledge 中的源文件被编辑后，用户可选择：
   - 保留当前版本；
   - 将新文件作为新文档加入；
   - 在索引就绪后切换 active Revision。
7. 宏、外部链接、嵌入脚本和远程数据连接不执行；输出是否保留这些内容必须在结果中说明。
8. 每个操作完成后执行格式重新打开、页/Sheet/Slide 数、关键结构和输出大小等最小验证。

### Agent 使用边界

- `document_inspect` 和受控 `document_render` 是只读/派生操作，可按工具策略自动执行。
- `document_transform` 和 `document_compose` 只生成新文件时属于可恢复写入，不应因为底层实现使用 Worker 而逐次弹出高风险 Shell 批准。
- 删除、覆盖原件、提交外部系统、数字签名或发布仍按高风险策略处理。
- 任意复杂编辑可以由 Skill 编排多个结构化操作；确需 Sandbox 自定义代码时，输出仍必须通过标准 File Asset、Derivation 和验证入口收口。
- Document Tool 不直接把二进制或完整文档内容塞回模型，只返回结构摘要、Job 状态和输出文件引用。

## 大文件处理

### 当前问题

现有上传链路受到两层 100 MB 限制：

- Nginx `client_max_body_size 100m`；
- `ManagedFileStorage._read_upload()` 把上传内容全部读取到内存并计算 SHA-256。

直接把限制调到 1 GB 会使 API 内存、连接时长、失败重传和反向代理超时不可控，因此不采用。

### 推荐上传协议

```text
1. initiate
   -> 校验用户配额、文件名、声明大小和目标用途
   -> 返回 upload_id、part_size、过期时间和上传方式

2. upload parts
   -> COS/OSS 优先使用 Provider Multipart 直传
   -> Local 使用受控分片端点和临时目录
   -> 每片可重试，记录 ETag/checksum

3. complete
   -> 服务端确认所有分片、最终大小和对象完整性
   -> 创建或激活 files 记录
   -> 写入 document_processing_job

4. process asynchronously
   -> 状态和阶段可轮询或通过事件流更新
```

现有 `POST /api/files` 保留为兼容快速路径，适用于小文件。大文件客户端自动切换到可恢复协议，不要求用户选择技术模式。

### 资源与安全限制

限制不能只按原始 MB 判断，至少需要独立配置：

- 单文件原始字节上限；
- 解压后总字节和文件数上限；
- PDF 最大页数和单页像素上限；
- OCR 最大页数、并发数和计算预算；
- XLSX 最大 Sheet、有效单元格和公式数量；
- 提取后最大 Block/Token 数；
- 用户原文件容量、派生产物容量和向量容量；
- 单用户同时处理 Job 数。

解析器必须流式读取或分页处理，并设置 CPU、内存、磁盘、网络和执行时间限制。文档 Worker 不继承 Agent 的工具权限，也不执行文档宏。

## 业务流程

### 流程 1：会话附件临时使用

1. 用户上传或从文件中心选择文档并发送消息。
2. 系统确保该文件已有可用 Document Revision；没有则创建异步处理 Job。
3. 小文档在可控上下文预算内可直接形成临时结构化上下文。
4. 内容超过预算、包含多个文档或需要跨段语义查询时，建立或复用内容 Index，并创建 `session_ephemeral` Scope Binding。
5. Planner 获得“本会话可检索文档”的简短清单，需要时调用 `context_search`。
6. 回答展示引用，引用能打开原始文档对应位置。
7. 临时索引在最后使用后一段时间过期；原始文件仍遵循文件中心生命周期。
8. 用户点击“加入 Knowledge”时只创建长期关联和必要的持久索引，不重复上传原文件。

#### 3–5 万字合同/论文的推荐路径

3–5 万汉字通常已经超出“把全文直接塞进一次模型调用”的合理默认范围，即使模型上下文窗口容得下，也会产生重复 Token 成本、注意力稀释和引用不稳定。它在存储上不算大文件，但在上下文上属于中长文档，应自动进入临时 Context Index：

```text
上传合同/论文
  -> 文档解析（有文本层时通常无需 OCR）
  -> 识别标题、章节、条款、表格、脚注和页码
  -> 先生成关键词/结构索引，尽快达到 keyword_ready
  -> 后台生成 embedding，达到 hybrid_ready
  -> Session 获得带 TTL 的临时 Scope Binding
  -> Agent 调用 context_search / context_open
```

建议规则：

- 提取后超过可配置的直接上下文预算时自动准备临时索引；首期建议预算约为 8k–12k Token，而不是按文件 MB 判断。
- 3–5 万字文档默认建立 embedding，不等待用户额外点击“转向量”。
- Chunk 按章节、合同条款和论文小节切分，目标约 400–800 Token，并保留少量重叠和标题路径；实际块数由结构决定，不把固定数量作为验收标准。
- 关键词/结构索引先可用，embedding 完成前也能检索条款号、金额、日期、术语和论文标题。
- embedding 完成后自动切换为混合检索，不中断当前 Session。
- 临时 Binding 建议按 `last_used_at + 7 天` 到期；到期只解除临时 Scope。用户回到旧 Session 时可从 Revision/Index 快速重新绑定或重建。
- 用户选择“加入 Knowledge”时增加长期 Scope Binding；若 parser、chunker 和 embedding 配置一致，复用同一内容索引，不重复 embedding。

这类文档需要两种读取模式：

1. `focused`：查某个条款、定义、实验结论或数字，使用混合 Top-K 检索。
2. `comprehensive`：总结整份合同、审查遗漏条款、总结整篇论文，先读取目录/章节摘要，再按章节覆盖执行；不能只取相似度最高的几个 Chunk。

因此 Context Tool 还应提供 `document_outline`，或允许 `context_search(mode="comprehensive")` 返回章节覆盖计划。合同审查和论文总结不能被实现成一次普通 Top-K RAG。

### 流程 2：加入长期 Knowledge

1. 用户创建 Knowledge Base。
2. 用户从文件中心选择已有文件，或在 Knowledge 页面上传文件。
3. 系统复用相同 SHA-256、解析器版本和权限范围内已有的 Document Revision；否则异步处理。
4. 结构化解析成功后立即建立关键词索引。
5. 默认复用或建立 embedding，并创建长期 Scope Binding；embedding 暂时失败时以 `PARTIAL_READY` 提供关键词检索并后台重试。
6. 文档进入 `READY` 后可被绑定的 Project、Agent 或手工选择范围检索。
7. 用户替换文件时产生新 Revision 和新 Index Generation，构建完成后原子切换。
8. 删除 Knowledge 文档只解除长期关联；是否删除原始文件由文件中心单独决定。

### 流程 3：Project / Agent 使用

1. 当前 Session 解析出显式 Knowledge Scope：
   - 本次消息附件；
   - Session 手工选择的 Knowledge；
   - Session 所属 Project 绑定的 Knowledge；
   - 未来选中 Agent Profile / Skill 绑定的 Knowledge。
2. 所有 Scope 先按当前 `user_id` 做授权过滤，再进行检索。
3. Planner 只看知识清单、名称和能力摘要，不接收全部正文。
4. `context_search` 返回经过过滤、去重和重排的片段与引用。
5. `context_open` 可在同一引用附近读取受限窗口或结构化表格。
6. Trace 记录查询、Scope、文档/Chunk ID、分数、索引版本和最终使用的引用。
7. Session 从一个 Project 移到另一个 Project 后，只影响后续 Run 的可用范围，不改写历史 Run。

## 核心规则

1. 上传成功只代表原始资产可用，不代表文档已解析或已进入 Knowledge。
2. 原始文件、Document Revision、Chunk 和 embedding 都必须能独立标识版本。
3. 不因文件扩展名信任格式，必须执行 MIME/文件签名嗅探。
4. 解析 Job 必须幂等；相同 `file_sha256 + parser_version + options_hash` 不重复处理。
5. embedding 失败不能使关键词索引失效。
6. 内容索引本身不区分临时或长期；生命周期属于 Scope Binding，同一 Index Generation 可同时被 Session 和 Knowledge 引用。
7. 临时 Binding 过期先解除 Session Scope；只有没有任何临时或长期 Binding 时，Index/Chunk/embedding 才能按缓存策略回收。
8. 长期 Knowledge 文档在用户移除或删除前持续可用，不能随 Sandbox 或 Session Task 销毁。
9. Retrieval 必须先应用授权和 Scope 过滤，再计算或返回候选，禁止检索后仅在应用层隐藏越权结果。
10. Knowledge Binding 只扩大“可被选择的范围”，不能授予不属于当前用户的文件权限。
11. 引用必须携带 Revision 和结构位置，不能只保存易变化的 Chunk 序号。
12. 回答中没有被实际使用的检索结果不得展示为引用。
13. Project Binding 必须显式可见、可移除，不改变 Project 的单层目录语义。
14. Knowledge 内容不会自动写入 Session Memory 或用户长期记忆。
15. 解析器、chunking、embedding 或 reranker 版本变化时必须建立新 Generation，完成后再切换。
16. 删除与权限撤销必须使后续检索立即不可见；后台物理清理可以异步。
17. 文档处理是平台内部异步 Job，不作为高风险 Agent Tool 要求用户逐次批准；上传、加入 Knowledge、重新处理和删除本身是明确用户动作。
18. 普通附件由系统自动触发 `context_prepare`；Agent Tool 调用使用同一幂等入口，不能建立重复索引。
19. Agent 只能创建有期限的 Session/Run Context Binding，不能创建永久 Knowledge Binding。
20. 纯文档解析、检索和引用不得创建完整 Agent Sandbox；使用共享轻量 Worker Pool。
21. Sandbox、Browser 和附件同步必须懒启动，只有实际调用对应 Tool 时发生。
22. 每次模型调用只注册当前 Plan 需要的 Tool Schema；Context Search 不携带 Shell/Browser/VNC 能力。
23. Worker 产出的全文、Block JSON 和向量不得直接写入 Session Memory；模型只接收预算内的检索结果。

## 是否转向量

结论：**不是所有上传都立即转向量，但长期 Knowledge 默认建立向量索引；检索不能只有向量。**

### 决策矩阵

| 场景 | 结构化解析 | 关键词索引 | 向量索引 | 生命周期 |
| --- | --- | --- | --- | --- |
| 小型单次会话附件，内容可放入预算 | 必须 | 可选/轻量 | 默认不建 | Run/Session 临时 |
| 3–5 万字合同/论文 | 必须 | 必须，优先就绪 | 默认建立，可异步补齐 | Session Scope + TTL |
| 更大型或多文件会话附件 | 必须 | 必须 | 默认建立并支持分层检索 | Session Scope + TTL |
| 用户主动加入 Knowledge | 必须 | 必须 | 默认建立 | `knowledge_durable` |
| embedding 服务不可用 | 必须 | 必须 | 标记待重试 | 仍可部分使用 |
| Excel 精确数字/编号查询 | 必须 | 主要通道 | 辅助通道 | 依所属 Scope |
| 扫描 PDF | OCR 后必须 | 必须 | 按策略建立 | 依所属 Scope |

向量化判断不使用“文件大于多少 MB”作为唯一条件，而使用：

- 提取后的 Token/Block 数；
- 文档数量；
- 是否需要跨段语义召回；
- 是否会被长期重复使用；
- 当前 embedding 预算和队列压力；
- 文档类型与结构。

### 临时向量库与长期向量库

首期不部署两套数据库，也不为同一文档复制两份 embedding。推荐把“内容索引”和“谁可以使用它”分开：

```text
retrieval_index
  revision + parser/chunker/embedding generation
  不带 Session/Knowledge 生命周期

retrieval_scope_binding:
  lifecycle = session_ephemeral
  scope_id = session_id
  expires_at != null
  last_used_at 定期续期

retrieval_scope_binding:
  lifecycle = knowledge_durable
  scope_id = knowledge_base_id
  expires_at = null
  由 Knowledge 文档关系控制删除
```

同一个 `retrieval_index` 可以同时拥有临时和长期 Binding。用户把临时合同加入 Knowledge 时，只增加长期 Binding；配置一致时不重新切块和 embedding。

这样可以共用：

- parser/chunker/embedding 管线；
- 关键词与向量查询代码；
- 权限过滤；
- 引用和 Trace；
- 重建、监控与容量统计。

不同生命周期仍保持独立 Binding 和清理策略，不能把临时 Context 伪装成用户可见 Knowledge Base。最后一个 Binding 删除或过期后，内容 Index 才进入可回收状态。

## 现有实现分析

### 相关代码与文档

- `agentic/api/app/core/entities/file.py`
  - 已有 `user_id`、SHA-256、Provider、来源和软删除字段；
  - 适合作为原始资产，不适合承载多 Revision、多 Job 和多 Index 状态。
- `agentic/api/app/extensions/managed_file_storage.py`
  - 支持 Local/COS/OSS 和流式分块读取；
  - 当前仍把完整文件写入内存，且 Provider 接口没有 multipart 能力。
- `agentic/api/app/controllers/file.py`
  - 提供上传、下载、预览和文件管理；
  - 可保留现有接口并扩展 resumable upload。
- `agentic/api/app/repositories/db_search_repository.py`
  - 当前是 `ILIKE` 全局搜索，不具备文档正文、FTS、向量或引用定位能力；
  - Knowledge Retrieval 应是独立服务，之后再把 Knowledge 类型接入全局搜索。
- `agentic/api/app/core/agent/agent_task_runner.py`
  - 会把附件复制到 Sandbox，并在每次 Run 建立 Skill Runtime Context；
  - 当前 Run 会无条件 `ensure_sandbox()`，即使只需要对话或 Knowledge；
  - 可在同一阶段新增 Knowledge Scope 构建，但正式解析不能依赖短生命周期 Sandbox；
  - K1 需要把附件同步和 Sandbox 创建改为 Sandbox Tool 首次调用时的懒行为。
- `agentic/api/app/services/agent_service.py`
  - 当前创建 Task 时会先创建/恢复 Sandbox 并取得 Browser；
  - 纯 Context Search 路径需要允许 `sandbox=None`，通过 Lazy Provider 在实际调用 Shell/Browser/File Workspace Tool 时再创建。
- `agentic/api/app/core/agent/base.py`
  - Skill Runtime Context 以短系统消息注入；
  - Knowledge 只应注入 Scope Manifest，正文通过工具按需读取。
- `agentic/api/app/core/entities/memory.py`
  - 当前 Session Memory 是消息列表并进行有限压缩；
  - 不能用它保存长期文档正文或索引。
- `agentic/api/app/models/project.py`
  - Project 是用户拥有的一级目录；
  - Knowledge 通过独立 Binding 关联，不能向 Project 表追加隐藏上下文字段。
- `agentic/web/src/lib/file-preview.ts`
  - 当前支持文本、Markdown、HTML、SVG 和图片；
  - PDF/Office 的结构化预览需要 Document Revision/派生产物支持。
- `agentic/docs/file-management.zh-CN.md`
  - 现有文件中心生命周期和对象存储约定继续保留。
- `agentic/docs/designs/session-project-directory.zh-CN.md`
  - 明确 Project 不隐式注入上下文，本设计遵循该边界。

### 可复用能力

- `files`、用户隔离、SHA-256 和对象存储 Provider。
- 文件中心上传、选择、软删除、到期清理和来源追踪。
- Redis 基础设施与现有运行事件模型。
- Run Trace、Tool Call 和 UI 引用卡片的展示经验。
- Skill Runtime Context 的“一次 Run 临时上下文”边界。
- Project 与 Session 已有显式关联。

### 当前约束

- PostgreSQL 使用普通 `postgres:16-alpine`，尚未包含 pgvector 扩展。
- API 与 Sandbox 镜像未安装正式文档解析/OCR/Office 转换依赖。
- 当前没有独立异步 Worker；Agent Task 的进程内 `asyncio.Task` 不适合长时间、CPU 密集、可恢复的文档 Job。
- Agent Profile 数据模型尚未实现，不能在 Knowledge 首期创建无目标实体的强外键。
- 现有文件 API 暴露的是同步完成语义，大文件协议需保持兼容而不能直接替换。
- 当前全局搜索不是检索服务，不能在其 SQL 中继续堆叠 RAG 逻辑。

## 可选方案

### 方案 A：上传即永久向量化

- 实现方式：
  - 每个上传文件立即解析、切块和 embedding；
  - 所有向量进入一个用户级永久集合；
  - Session、Project 和 Agent 从集合中过滤。
- 优点：
  - 概念和首版查询代码简单；
  - 文件上传后无需再次等待 embedding；
  - 适合非常小、全部资料都长期使用的产品。
- 缺点：
  - 临时附件产生永久存储和 embedding 成本；
  - 删除、权限、重复文件和版本边界不清晰；
  - 解析失败会污染普通文件上传体验；
  - 用户无法判断哪些资料实际进入了 Agent 知识范围。
- 风险：
  - 很快形成不可治理的“向量垃圾场”；
  - 上传和聊天延迟被文档处理拖累。

### 方案 B：文档处理底座 + 同后端生命周期分层

- 实现方式：
  - 文件、Revision、解析 Block、索引和 Knowledge Binding 分层；
  - 会话附件使用临时 Scope，长期 Knowledge 使用持久 Scope；
  - 两者共用 PostgreSQL FTS + pgvector 的混合检索；
  - 大文件交给独立 Document Worker 异步处理。
- 优点：
  - 用户意图、成本和生命周期清晰；
  - 临时与长期逻辑复用，不维护双基础设施；
  - 可在 embedding 故障时使用关键词降级；
  - 与现有 PostgreSQL、用户隔离、Project 和 Trace 更容易保持一致；
  - 后续可平滑迁移到专用向量服务。
- 缺点：
  - 数据模型和状态机比方案 A 多；
  - 需要新增 Worker、pgvector 部署和清理任务；
  - 初期必须认真处理索引版本与引用稳定性。
- 风险：
  - 若没有容量监控和 TTL 清理，临时索引仍可能累积；
  - PostgreSQL 向量规模扩大后需评估专用服务。

### 方案 C：临时本地索引 + 长期专用向量数据库

- 实现方式：
  - Session 临时索引放 Redis、本地磁盘或每 Sandbox 的轻量向量库；
  - 长期 Knowledge 放 Qdrant/Milvus/Weaviate 等专用服务；
  - 应用层统一两套查询结果。
- 优点：
  - 长期向量可独立扩容；
  - 临时数据物理隔离且自然随环境销毁；
  - 适合一开始就有超大向量规模和独立检索团队的场景。
- 缺点：
  - 两套索引、备份、权限、监控、评分和故障语义；
  - Sandbox 销毁会让同一 Session 后续无法复用临时索引；
  - 结果融合和引用一致性复杂；
  - 当前产品规模与运维基础不支持这笔成本。
- 风险：
  - 基础设施复杂度先于业务价值增长；
  - 两种相似度和版本策略导致难以复现回答。

## 方案对比

| 维度 | 方案 A：上传即永久向量化 | 方案 B：同后端生命周期分层 | 方案 C：临时/长期双基础设施 |
| --- | --- | --- | --- |
| 实现复杂度 | 中 | 中高 | 高 |
| 用户意图清晰度 | 低 | 高 | 中 |
| 临时成本控制 | 低 | 高 | 高 |
| 长期治理 | 低 | 高 | 高 |
| 权限一致性 | 中 | 高 | 中低 |
| 引用可复现性 | 中 | 高 | 中 |
| 故障降级 | 低 | 高 | 中 |
| 当前架构兼容性 | 中 | 高 | 低 |
| 运维成本 | 中 | 中 | 高 |
| 后续扩展上限 | 中 | 中高，可迁移 | 高 |
| 测试难度 | 中 | 中高 | 高 |
| 主要风险 | 数据和成本失控 | 状态机与清理不完整 | 双系统长期漂移 |

## 推荐方案

选择方案 B：**独立文档处理底座 + 同一检索后端中的临时/长期生命周期分层 + 混合检索**。

首期检索存储建议：

- PostgreSQL 保存 Metadata、状态、Binding、Block/Chunk 和关键词索引；
- PostgreSQL FTS 负责词项、编号、专有名词和精确匹配；
- pgvector 保存 embedding，负责语义召回；
- 对象存储保存原文件、大型结构化产物、页面预览和可重建派生物；
- Redis 只做 Job 协调、锁、短期进度和事件，不做知识事实源；
- 共享 `document-worker` 执行解析、OCR 和格式处理；
- `context-index-worker` 执行 chunking、关键词索引和 embedding；首期可与 Document Worker 共用轻量 Worker 进程组，但不使用完整 Agent Sandbox。

推荐 pgvector 不是因为向量应该主导产品，而是它能在首期保持授权过滤、事务、备份和部署边界一致。满足以下任一条件后再评估专用向量服务：

- 向量查询延迟在优化索引和分区后仍持续不达标；
- Chunk/embedding 规模使主业务 PostgreSQL 的备份、写入或维护不可接受；
- 需要跨区域、大规模多副本或独立检索弹性；
- 检索团队需要独立发布和扩容周期。

届时通过 `RetrievalIndexRepository` 抽象迁移向量部分，Knowledge、Revision、Binding、权限和引用事实仍留在 PostgreSQL。

## 文档处理状态机

```text
UPLOADING
  -> RECEIVED
  -> VALIDATING
  -> QUEUED
  -> EXTRACTING
  -> OCR (optional)
  -> NORMALIZING
  -> INDEXING_KEYWORD
  -> INDEXING_VECTOR (optional)
  -> READY

任意处理阶段
  -> PARTIAL_READY  已有可用产物，但存在页/元素/embedding 告警
  -> FAILED         无可用产物
  -> CANCELED       用户取消或配额终止
```

Job 状态与文档可用状态分离：

- 重建新 Generation 失败时，旧 Generation 仍保持 `READY`；
- embedding 失败时关键词索引可为 `PARTIAL_READY`；
- 单页 OCR 失败时其余页面仍可用，并展示质量告警；
- 原始文件删除或权限撤销时，所有关联索引立即从可检索范围移除。

## 数据结构

### 现有 `files`

继续保存原始文件。仅在大文件协议需要时增加：

| 字段 | 类型 | 必填 | 说明 | 约束/默认值 |
| --- | --- | --- | --- | --- |
| `upload_state` | string | 是 | 对象接收状态 | `uploading/available/failed`，旧记录回填 `available` |

解析、OCR 和索引状态不写入 `files`。

### `file_uploads`

| 字段 | 类型 | 必填 | 说明 | 约束/默认值 |
| --- | --- | --- | --- | --- |
| `id` | string | 是 | 大文件上传 ID | PK |
| `user_id` | string | 是 | 所有者 | FK users |
| `provider` | string | 是 | Local/COS/OSS | 创建后不可变 |
| `declared_size` | bigint | 是 | 客户端声明大小 | 必须在配额内 |
| `received_size` | bigint | 是 | 已确认大小 | 默认 0 |
| `part_size` | int | 是 | 分片大小 | 服务端决定 |
| `state` | string | 是 | 上传状态 | uploading/completing/completed/failed/canceled |
| `expires_at` | datetime | 是 | 未完成上传过期时间 | 到期清理分片 |
| `metadata` | jsonb | 是 | Provider upload ID、分片摘要 | 不含凭据 |

### `file_derivations`

| 字段 | 类型 | 必填 | 说明 | 约束/默认值 |
| --- | --- | --- | --- | --- |
| `id` | string | 是 | 派生关系 ID | PK |
| `user_id` | string | 是 | 所有者 | 授权过滤字段 |
| `output_file_id` | string | 是 | 新生成文件 | FK files，唯一 |
| `input_file_ids` | jsonb | 是 | 有序输入文件 ID | 至少一个，生成类操作可为空数组 |
| `operation` | string | 是 | merge/split/render/transform/compose 等 | 稳定枚举 |
| `parameters_hash` | string | 是 | 脱敏参数摘要 | 幂等与审计 |
| `toolchain_version` | string | 是 | 操作工具链版本 |  |
| `job_id` | string | 否 | 异步 Job |  |
| `session_id` | string | 否 | 发起 Session |  |
| `run_id` | string | 否 | 发起 Run |  |
| `validation_report` | jsonb | 是 | 输出重新打开与结构检查结果 | 默认 `{}` |
| `created_at` | datetime | 是 | 创建时间 |  |

派生关系只记录文件 ID 和脱敏操作摘要，不保存用户正文或完整 Tool 参数。

### `document_revisions`

| 字段 | 类型 | 必填 | 说明 | 约束/默认值 |
| --- | --- | --- | --- | --- |
| `id` | string | 是 | Revision ID | PK |
| `user_id` | string | 是 | 所有者 | 授权过滤字段 |
| `file_id` | string | 是 | 原始文件 | FK files |
| `file_sha256` | string | 是 | 内容哈希 | 去重与幂等 |
| `parser_version` | string | 是 | 解析工具链版本 | 不可原地修改 |
| `options_hash` | string | 是 | OCR/语言等选项摘要 | 幂等键一部分 |
| `status` | string | 是 | 可用状态 | processing/ready/partial_ready/failed |
| `media_type` | string | 是 | 嗅探后的真实类型 | 不只信扩展名 |
| `page_count` | int | 否 | PDF/PPT 页数 | 可空 |
| `token_count` | bigint | 是 | 提取后 Token 估算 | 默认 0 |
| `quality_report` | jsonb | 是 | OCR、缺页、表格等告警 | 默认 `{}` |
| `artifact_manifest` | jsonb | 是 | 派生产物对象引用 | 不含签名 URL |
| `created_at` | datetime | 是 | 创建时间 |  |

唯一约束：`user_id + file_sha256 + parser_version + options_hash`。

### `document_blocks`

| 字段 | 类型 | 必填 | 说明 | 约束/默认值 |
| --- | --- | --- | --- | --- |
| `id` | string | 是 | 稳定 Block ID | PK |
| `revision_id` | string | 是 | 所属 Revision | FK |
| `ordinal` | int | 是 | 文档顺序 | Revision 内唯一 |
| `block_type` | string | 是 | heading/paragraph/table/slide/cell_range/code/image_text |  |
| `text` | text | 是 | 归一化文本 | 可为空字符串但 Block 存在 |
| `heading_path` | jsonb | 是 | 标题路径 | 默认 `[]` |
| `locator` | jsonb | 是 | page/slide/sheet/cells/line/bbox | 引用核心 |
| `structure` | jsonb | 是 | 表格、列表、公式等结构数据 | 默认 `{}` |
| `content_hash` | string | 是 | Block 内容摘要 | 增量重建 |

大型结构数据可保存在对象存储，`structure` 只保存摘要和 Artifact 引用。

### `document_processing_jobs`

| 字段 | 类型 | 必填 | 说明 | 约束/默认值 |
| --- | --- | --- | --- | --- |
| `id` | string | 是 | Job ID | PK |
| `user_id` | string | 是 | 所有者 |  |
| `file_id` | string | 否 | 解析/索引的主文件 | 文档操作可空 |
| `input_file_ids` | jsonb | 是 | 有序输入文件 | 默认 `[]` |
| `output_file_id` | string | 否 | 操作成功后的输出文件 | 完成验证后写入 |
| `revision_id` | string | 否 | 目标 Revision | 创建后补充 |
| `job_type` | string | 是 | parse/reparse/reindex/action |  |
| `operation` | string | 否 | 具体文档操作 | action Job 必填 |
| `stage` | string | 是 | 当前阶段 |  |
| `state` | string | 是 | queued/running/succeeded/partial/failed/canceled |  |
| `progress` | int | 是 | 0–100 的 UI 进度 | 不能作为精确业务事实 |
| `attempt` | int | 是 | 当前尝试次数 | 默认 0 |
| `error_code` | string | 否 | 稳定错误码 |  |
| `error_detail` | jsonb | 是 | 脱敏错误与部分失败 | 默认 `{}` |
| `heartbeat_at` | datetime | 否 | Worker 租约心跳 | 卡死恢复 |
| `created_at/updated_at` | datetime | 是 | 时间 |  |

### `retrieval_indexes`

| 字段 | 类型 | 必填 | 说明 | 约束/默认值 |
| --- | --- | --- | --- | --- |
| `id` | string | 是 | Index Generation ID | PK |
| `user_id` | string | 是 | 所有者 | 授权过滤字段 |
| `revision_id` | string | 是 | 输入 Revision | FK |
| `chunker_version` | string | 是 | Chunk 规则版本 |  |
| `embedding_model` | string | 否 | embedding 标识 | 关键词模式可空 |
| `embedding_dimension` | int | 否 | 向量维度 | 与模型一致 |
| `config_hash` | string | 是 | Chunk/embedding 配置摘要 | 复用与幂等 |
| `status` | string | 是 | building/keyword_ready/hybrid_ready/partial_ready/failed/superseded | 关键词先用、向量后补齐 |
| `created_at` | datetime | 是 | 创建时间 |  |

唯一约束：`user_id + revision_id + config_hash`。Index 不直接拥有 Session 或 Knowledge 生命周期。

### `retrieval_scope_bindings`

| 字段 | 类型 | 必填 | 说明 | 约束/默认值 |
| --- | --- | --- | --- | --- |
| `id` | string | 是 | Scope Binding ID | PK |
| `user_id` | string | 是 | 所有者 | 授权过滤字段 |
| `index_id` | string | 是 | 内容 Index Generation | FK |
| `lifecycle` | string | 是 | 使用生命周期 | session_ephemeral/knowledge_durable |
| `scope_type` | string | 是 | Session 或 Knowledge | session/knowledge_base |
| `scope_id` | string | 是 | 对应 Session/Knowledge ID | Service 校验所有权 |
| `expires_at` | datetime | 否 | 临时 Binding 到期时间 | 长期必须为空 |
| `last_used_at` | datetime | 否 | 临时 Binding 续期依据 |  |
| `created_at` | datetime | 是 | 创建时间 |  |

唯一约束：`index_id + scope_type + scope_id`。清理任务先删除过期 Binding，再回收没有任何 Binding 的 Index 派生数据。

### `retrieval_chunks`

| 字段 | 类型 | 必填 | 说明 | 约束/默认值 |
| --- | --- | --- | --- | --- |
| `id` | string | 是 | Chunk ID | PK |
| `index_id` | string | 是 | Index Generation | FK |
| `user_id` | string | 是 | 冗余授权过滤字段 | 与 Index 一致 |
| `ordinal` | int | 是 | 顺序 | Index 内唯一 |
| `text` | text | 是 | 检索文本 |  |
| `token_count` | int | 是 | Token 估算 |  |
| `source_spans` | jsonb | 是 | Block ID 与字符区间 | 引用回溯 |
| `search_vector` | tsvector | 是 | PostgreSQL FTS | GIN index |
| `metadata` | jsonb | 是 | 标题、类型、页、Sheet 等 | 过滤字段需要独立列或表达式索引 |

### `retrieval_embeddings`

| 字段 | 类型 | 必填 | 说明 | 约束/默认值 |
| --- | --- | --- | --- | --- |
| `chunk_id` | string | 是 | Chunk | PK/FK |
| `user_id` | string | 是 | 授权过滤字段 |  |
| `model_id` | string | 是 | embedding 模型 |  |
| `dimension` | int | 是 | 维度 |  |
| `embedding` | vector | 是 | pgvector | 索引策略按规模评估 |
| `created_at` | datetime | 是 | 创建时间 |  |

首期只支持一个激活 embedding 维度；更换维度时创建新 Generation，不能在同一 ANN 索引中混用。

### `knowledge_bases`

| 字段 | 类型 | 必填 | 说明 | 约束/默认值 |
| --- | --- | --- | --- | --- |
| `id` | string | 是 | Knowledge ID | PK |
| `user_id` | string | 是 | 所有者 |  |
| `name` | string | 是 | 名称 | 用户内大小写不敏感唯一 |
| `description` | text | 是 | 用途摘要 | 默认空 |
| `retrieval_config` | jsonb | 是 | top_k、混合权重、rerank 策略 | 只允许白名单字段 |
| `status` | string | 是 | active/deleted | 默认 active |
| `created_at/updated_at` | datetime | 是 | 时间 |  |

### `knowledge_documents`

| 字段 | 类型 | 必填 | 说明 | 约束/默认值 |
| --- | --- | --- | --- | --- |
| `knowledge_base_id` | string | 是 | Knowledge | 复合唯一键 |
| `file_id` | string | 是 | 原始文件 | 复合唯一键 |
| `active_revision_id` | string | 否 | 当前 Revision | 构建完成后切换 |
| `active_index_id` | string | 否 | 当前长期 Index | 构建完成后切换 |
| `status` | string | 是 | processing/ready/partial_ready/failed/removed |  |
| `added_at` | datetime | 是 | 加入时间 |  |

### `knowledge_bindings`

| 字段 | 类型 | 必填 | 说明 | 约束/默认值 |
| --- | --- | --- | --- | --- |
| `id` | string | 是 | Binding ID | PK |
| `user_id` | string | 是 | 所有者 |  |
| `knowledge_base_id` | string | 是 | Knowledge | FK |
| `target_type` | string | 是 | project/agent_profile/skill | 首期只开放 project |
| `target_id` | string | 是 | 目标 ID | Service 校验所有权 |
| `enabled` | bool | 是 | 是否生效 | 默认 true |
| `created_at` | datetime | 是 | 创建时间 |  |

唯一约束：`knowledge_base_id + target_type + target_id`。

Agent Profile 尚不存在，因此首期 API 可以保留枚举但必须拒绝创建 `agent_profile` Binding，直到目标实体和所有权校验完成。

### `session_document_bindings`

| 字段 | 类型 | 必填 | 说明 | 约束/默认值 |
| --- | --- | --- | --- | --- |
| `session_id` | string | 是 | Session | 复合唯一键 |
| `file_id` | string | 是 | 附件文件 | 复合唯一键 |
| `revision_id` | string | 否 | 可用 Revision |  |
| `ephemeral_scope_binding_id` | string | 否 | Session 临时 Scope | 指向 retrieval_scope_bindings |
| `last_used_at` | datetime | 是 | 最后使用 | TTL 依据 |
| `expires_at` | datetime | 是 | 临时检索产物过期时间 | 可续期 |

该表不改变消息附件事实；临时 Binding 过期后可重新绑定仍存在的 Index，或由 Revision/原文件重建。

## 接口设计

### 大文件上传

#### `POST /api/uploads`

- 输入：文件名、声明大小、MIME、可选客户端 SHA-256、目标目录和用途。
- 输出：`upload_id`、上传方式、分片大小、过期时间和 Provider 所需的临时上传信息。
- 权限：当前用户。
- 幂等：支持 `Idempotency-Key`；同一 Key 返回同一未过期 Upload。

#### `POST /api/uploads/{upload_id}/parts`

- Local 模式上传一个分片；COS/OSS 模式可替换为获取签名分片 URL。
- 每片带序号、大小和 checksum；重复上传相同分片幂等覆盖。

#### `POST /api/uploads/{upload_id}/complete`

- 校验分片清单和最终对象；
- 成功后返回标准 File 摘要与可选 Processing Job；
- 重复 complete 返回相同 File。

#### `DELETE /api/uploads/{upload_id}`

- 取消未完成上传并异步清理分片。

### 文档处理

#### `POST /api/files/{file_id}/process`

- 输入：用途 `session/knowledge/preview`、OCR 语言、是否强制重建。
- 输出：Job 摘要。
- 幂等：相同文件、解析器和选项复用 Revision 或进行中的 Job。

#### `GET /api/files/{file_id}/document`

- 输出：当前 Revision、处理阶段、质量报告、可用引用类型和派生产物摘要。
- 不返回对象存储密钥或未签名内部路径。

#### `GET /api/document-jobs/{job_id}`

- 输出：状态、阶段、进度、稳定错误码、可重试性和部分成功信息。

#### `POST /api/document-jobs/{job_id}/retry`

- 仅失败或部分失败 Job 可重试；
- 不覆盖已有可用 Revision/Index。

#### `DELETE /api/document-jobs/{job_id}`

- 请求取消；Worker 在安全检查点停止。

### 文档操作

#### `POST /api/document-actions`

- 输入：
  - `operation`：受支持的稳定操作名；
  - `input_file_ids`：有序输入；
  - `parameters`：由每个操作的 Pydantic Schema 校验；
  - `output_name`：可选结果名称；
  - `idempotency_key`：防止重复生成。
- 输出：Document Job、预计输出类型和已知格式损失提示。
- 权限：所有输入必须属于当前用户且可用。
- 并发：相同 Idempotency Key 只产生一个输出。
- 安全：不接受任意命令、Python 代码、文件系统路径或 Provider Key。

#### `GET /api/document-actions/capabilities`

- 按格式返回当前部署实际支持的 inspect/render/transform/compose 操作；
- 包含工具链版本、限制和可能的格式损失；
- UI 和 Agent Tool 都以此为准，不把未部署能力写死在 Prompt。

#### `GET /api/files/{file_id}/derivations`

- 返回该文件的来源与派生结果摘要；
- 只返回当前用户可访问的 File；
- 可从 Agent 生成文件追溯到源文档和操作。

### Knowledge

#### `GET/POST /api/knowledge-bases`

- 列表与创建用户自己的 Knowledge。

#### `GET/PATCH/DELETE /api/knowledge-bases/{knowledge_base_id}`

- 查询、更新和软删除。
- 删除立即撤销可检索性，物理索引异步清理。

#### `POST /api/knowledge-bases/{knowledge_base_id}/documents`

- 输入：`file_ids`；
- 校验所有文件归当前用户；
- 返回每个文档的复用、处理或失败状态；
- 重复加入幂等。

#### `DELETE /api/knowledge-bases/{knowledge_base_id}/documents/{file_id}`

- 解除 Knowledge 关系；
- 不删除文件中心原始文件；
- 若没有其他长期/临时引用，派生索引可异步回收。

#### `POST /api/knowledge-bases/{knowledge_base_id}/bindings`

- 输入：`target_type`、`target_id`；
- 首期支持 Project，校验 Project 与 Knowledge 同属当前用户。

#### `DELETE /api/knowledge-bases/{knowledge_base_id}/bindings/{binding_id}`

- 解除绑定，只影响后续 Run。

#### `POST /api/knowledge-bases/{knowledge_base_id}/search`

- 面向 UI 调试和人工验证；
- 输入：query、过滤器、top_k；
- 输出：结果、分数组成、引用和索引版本；
- 不允许客户端传任意 user/scope 绕过授权。

### Agent 内部工具

#### `context_prepare`

- 输入：当前 Run 已授权的 `source_refs`，首期支持 File/文本附件；不接受任意服务器路径或其他用户 ID。
- 行为：
  - 复用或创建 Document Revision；
  - 先准备关键词/结构索引，再异步补齐 embedding；
  - 创建或续期 Session 临时 Scope Binding；
  - 标准消息附件由系统在 Run 前自动调用同一幂等服务。
- 输出：
  - `context_ref`；
  - `state`：processing/keyword_ready/hybrid_ready/partial_ready/failed；
  - 文档、章节和 Token 摘要；
  - 可用的查询模式。
- 权限：Agent 只能创建有 TTL 的临时 Binding，不能创建长期 Knowledge。
- 幂等：相同 Session、Revision 和 Index 配置返回同一 Context。

#### `context_search`

输入：

```json
{
  "query": "合同的自动续约条件是什么？",
  "context_refs": ["current"],
  "mode": "focused",
  "filters": {
    "document_types": ["pdf", "docx"]
  },
  "top_k": 8
}
```

输出：

```json
{
  "results": [
    {
      "content": "……",
      "document_id": "file-id",
      "revision_id": "revision-id",
      "chunk_id": "chunk-id",
      "source_name": "合同.pdf",
      "locator": {"page": 12},
      "scores": {
        "keyword": 0.71,
        "vector": 0.83,
        "rerank": 0.91
      },
      "citation_ref": "cite:revision-id:block-id"
    }
  ]
}
```

规则：

- Agent 只能使用服务端为本次 Run 解析出的 Scope；
- 客户端或 LLM 不能通过猜测 Knowledge ID 扩大范围；
- 返回内容有单次 Token 上限；
- 表格结果优先返回结构化行列，而不是不可读的文本拼接。
- `focused` 返回相关 Top-K；`comprehensive` 返回章节覆盖结果或继续处理计划。

#### `context_open`

- 输入：`citation_ref`、前后 Block 数或表格范围；
- 输出：同一 Revision 的受限邻近内容；
- 用于确认上下文，不进行新的全库召回。

#### `document_outline`

- 输入：当前 Context 内的文档引用；
- 输出：标题/章节/条款层级、页码、章节摘要状态和覆盖游标；
- 用于整份合同审查、论文总结和跨章节比较；
- 不以向量相似度删除“看起来不相关”的章节。

#### `document_inspect`

- 输入：当前 Run 可访问的 File 引用和检查类型；
- 输出：结构、质量、页/Slide/Sheet 摘要和可用操作；
- 只读，不创建 Knowledge 或索引绑定。

#### `document_action`

- 输入：Capability 列表中的操作、File 引用和结构化参数；
- 输出：Job 或完成后的新 File 引用、格式损失提示与验证摘要；
- 不接受原始路径、任意脚本或“覆盖原件”参数；
- Run Trace 记录 operation、输入/输出 File ID、版本和验证状态。

## 混合检索流程

1. 解析当前 Run 的合法 Scope。
2. 应用 `user_id`、Scope、状态、Revision 和文档类型过滤。
3. 并行执行：
   - PostgreSQL FTS/精确词项召回；
   - pgvector 语义召回；
   - 结构化定位召回，例如页、标题、Sheet、编号。
4. 使用 Reciprocal Rank Fusion 或等价方法合并，避免直接混加不可比原始分数。
5. 按文档、标题路径和重叠 Source Span 去重。
6. 可选 reranker 对有限候选重排；失败则保留融合排序。
7. 组装引用和受控内容窗口。
8. 写入 Trace，返回 Agent。

对精确数字、公式、合同编号、代码符号和表格查询，提高关键词/结构通道权重；对概念解释和同义表达，提高向量通道权重。权重策略由服务端根据查询分类和 Knowledge 配置决定，不交给 LLM 任意设置。

## Runtime 与上下文设计

新增 `KnowledgeRuntimeContext`，生命周期为单个 Run：

```text
KnowledgeRuntimeContext
  scope ids（仅服务端）
  可见 Knowledge 名称与说明
  本次附件文档状态
  可用检索工具
  引用协议
```

注入模型的 Prompt Block 只包含：

- 当前可用资料的简短清单；
- 哪些资料仍在处理中或部分可用；
- 何时调用 `context_search`、`context_open` 或 `document_outline`；
- 回答时必须保留引用的协议。

不注入：

- 整个文档正文；
- embedding；
- 对象存储路径；
- 其他用户 Scope；
- 已过期临时索引；
- 与本次意图无关的所有 Knowledge 摘要。

Skill Runtime Context 与 Knowledge Runtime Context 独立组装。Skill 可以声明“需要 Knowledge 检索能力”，但不能把某个用户 Knowledge ID 写死在 Skill Package 中。

## 权限与删除

- 首期所有实体按 `user_id` 隔离。
- `knowledge_bindings` 是选择范围，不是 ACL 授权来源。
- Project 绑定要求 Project、Knowledge、Session 都属于同一用户。
- 文件软删除后立即：
  - 不能下载；
  - 不能新增 Revision；
  - 不能进入新检索；
  - 已有 Binding 返回“来源已删除”。
- 到期物理删除顺序：
  1. 撤销 Scope；
  2. 删除 embedding；
  3. 删除 Chunk/Block 和派生产物；
  4. 删除 Revision；
  5. 最后按文件中心策略删除原始对象。
- 若同一原文件仍被其他 Knowledge 或 Session 引用，只删除本次关系。
- Trace 保留不可反查正文的 ID、状态和分数；原文删除后历史引用显示“来源已删除或无权访问”。

## 错误处理与可观测性

### 稳定错误类别

- `unsupported_format`
- `mime_mismatch`
- `password_protected`
- `malformed_document`
- `archive_limit_exceeded`
- `page_limit_exceeded`
- `ocr_budget_exceeded`
- `parser_timeout`
- `parser_oom`
- `operation_not_supported`
- `transform_failed`
- `output_validation_failed`
- `format_loss_requires_confirmation`
- `embedding_unavailable`
- `embedding_model_changed`
- `quota_exceeded`
- `upload_incomplete`
- `source_deleted`
- `permission_denied`

### 用户可见状态

- 上传中、等待处理、正在解析、正在 OCR、正在建立索引；
- 可用、部分可用、处理失败、已取消；
- 质量提示，例如“第 8–10 页 OCR 失败，其他 42 页可检索”；
- 明确的重试、取消、下载原文件和移除入口。

### 指标

- 上传成功率、分片重试率、未完成上传容量；
- 按格式统计解析成功率、耗时、页数和峰值内存；
- OCR 页数、失败率和队列等待；
- Job 队列深度、租约超时、重试和死信；
- Worker Pool 并发、冷启动、CPU/内存峰值和每页处理成本；
- 文档 Run 的 Sandbox 创建率与懒启动命中率；
- Chunk/embedding 数量、临时/长期容量和 TTL 清理量；
- 关键词、向量、融合、rerank 各阶段延迟；
- 每次 Context Tool 返回 Token、每轮注册 Tool Schema 数和全文误注入拦截次数；
- 零结果率、引用打开率、引用失效率；
- embedding 降级次数与长期失败数；
- 每用户配额使用量。

### Trace

每次检索记录：

- Run、Session、用户和服务端 Scope 摘要；
- 查询文本的脱敏摘要或哈希策略；
- 检索通道和配置版本；
- 候选/返回数量；
- 文档、Revision、Chunk 和 Citation ID；
- 分数组成、延迟和降级原因；
- Agent 最终引用了哪些结果。

默认不把整段命中文本复制到长期 Trace，避免正文重复存储和删除失效。

## 部署结构

```text
Web
  -> API
      -> Object Storage (original + derived artifacts)
      -> PostgreSQL (metadata + FTS + pgvector)
      -> Redis (job queue/lease/progress)
      -> document-worker
           PDF/OOXML parser
           OCR engine
           PDF/Office action adapters
           renderer/converter
      -> context-index-worker
           normalizer/chunker
           embedding client
      -> retrieval-service
           keyword/vector/structure fusion
           citation/context tools
```

`document-worker` 与 Agent Sandbox 分离：

- Worker 镜像版本可控且只包含文档工具链；
- 禁止外网或仅允许配置的 embedding endpoint；
- 不提供交互式 shell、浏览器、VNC 或 Agent 工具；
- Job 可恢复、有租约、有幂等键；
- 解析器升级通过 `parser_version` 生成新 Revision。
- 编辑与转换适配器只读取受控输入对象并写入隔离的 Job 工作目录，成功验证后才上传输出 File。

`context-index-worker` 消费稳定 Document Revision，不直接打开 Office 宏或执行文档内容。首期它可以与 `document-worker` 运行在同一 Worker 镜像/进程组以减少部署组件，但代码模块、队列、Job 类型和版本必须分开，避免未来拆分时重做数据边界。

## 迁移与回滚

### 迁移

1. R0 先完成 Sandbox Lazy Provider、按需附件同步和 Tool Schema 裁剪，不改变现有文件/Session 业务语义。
2. D0 新增 Revision、Block、Processing Job 和 Worker 协议，用 TXT/Markdown 基线解析验证底层。
3. D1 再加入大文件分片直传、PDF/Office 解析、选择性 OCR 与预览产物；为旧 `files` 回填必要的上传状态。
4. 现有历史文件不自动解析、不自动 embedding；用户显式处理时才按需创建 Revision。
5. K1 先上线临时关键词索引，再按阈值/意图异步补充 embedding。
6. K2 长期 Knowledge 确认需要向量检索时再新增 pgvector 能力、Index 表和 Project Binding。
7. Agent Profile Binding 等目标模型存在后再启用。

当前 `postgres:16-alpine` 不包含 pgvector。D0、D1 不要求替换数据库镜像；K2 实施时再选用带 pgvector 的受控 PostgreSQL 镜像或构建自有镜像，并在迁移前验证备份、升级和回滚。

### 回滚

- UI 可关闭 Knowledge 入口和自动临时处理；
- Agent 可移除 Knowledge Runtime Context 与工具，恢复现有附件 Sandbox 路径行为；
- 原始 `files`、Session、Project、Memory 和 Trace 仍可使用；
- 新表和派生产物保留到确认无回滚需要后再清理；
- pgvector 扩展留在数据库中不会改变现有表行为；
- 不在代码回滚过程中删除原始文件或用户创建的 Knowledge 元数据。

## 分阶段交付

### R0：Agent Runtime Cost Foundation

- 计划：`agentic/docs/plans/agent-runtime-lazy-sandbox-plan.md`；
- Sandbox Lazy Provider 和并发安全的首次创建；
- 附件只在 Sandbox Tool 实际需要时同步；
- Planner 使用紧凑 Capability Catalog，不携带完整 Tool Schema；
- ReAct 只接收当前 Step 需要的 Tool Schema；
- Trace 记录 Sandbox 创建率、Schema count/bytes 和懒启动命中率。

### D0：Document Processing Foundation

- 计划：`agentic/docs/plans/document-processing-foundation-plan.md`；
- 独立轻量 Document Worker、Job 状态机、租约、心跳、取消、重试和幂等；
- Revision、Block、Locator、Capability 和 Artifact Manifest 协议；
- Worker 不持有业务数据库/对象存储长期凭据，通过内部 API 租借输入和回传产物；
- TXT/Markdown 基线解析打通完整链路；
- Document System Tool 门面；
- 暂不实现 PDF/Office/OCR、向量索引和 Knowledge UI。

### D1：PDF/Office Processing

- PDF、DOCX、PPTX、XLSX、文本结构化解析；
- 扫描 PDF 按页 OCR；
- 大文件 resumable upload；
- Revision、Block、质量报告和处理状态 UI；
- 暂不开放长期 Knowledge。

### D2：Document Actions

- Document Capability Registry 与结构化 Action Schema；
- PDF 常用拆分、合并、旋转、重排、OCR 和渲染；
- DOCX/PPTX/XLSX 的受控生成、编辑和渲染首期集合；
- copy-on-write、`file_derivations`、输出验证和 Trace；
- 文件预览与聊天中的操作入口；
- 与 Knowledge 独立验收，结果文件可按用户选择进入 Knowledge。

### K1：Session Temporary Knowledge

- 会话附件按需处理；
- 纯文档 Run 的 Sandbox 懒启动与按需附件同步；
- 根据意图只注册 Context Tool，避免无关 Tool Schema；
- 小文档直接上下文，3–5 万字及更长文档自动准备临时混合索引；
- `context_prepare` / `context_search` / `context_open` / `document_outline`；
- focused 与 comprehensive 两种读取模式；
- 引用卡片与 Trace；
- TTL、续期、重建和清理。

### K2：Durable Knowledge

- Knowledge Base CRUD；
- 从文件中心加入/移除文档；
- 长期关键词 + embedding 索引；
- 重新处理、Generation 切换、容量和状态；
- Project Binding；
- Knowledge 页面和检索调试。

### K3：Advanced Processing and Bindings

- Agent Profile / Skill Binding；
- 旧版 Office 隔离转换；
- 更复杂表格、图表、图片和多模态理解；
- 企业 ACL/Workspace；
- reranker 与检索评测集；
- 达到迁移条件时评估专用向量服务。

R0、D0、D1、D2、K1、K2 是独立计划和可验收批次，不在一个实施分支中一次完成。当前实施顺序为 `R0 -> D0 -> D1 -> K1`；D2 在 D1 之后可独立排期，K2 在 K1 检索稳定后开始。D0 是 D1/D2/K1 的领域和 Worker 前置，R0 是 K1 的运行时前置。

## 风险

| 风险 | 可能性 | 影响 | 缓解措施 | 验证方式 |
| --- | --- | --- | --- | --- |
| 大文件导致 API/Worker OOM | 中 | 高 | multipart、流式/分页解析、资源限制和压力测试 | 超过现有 100 MB 的恢复上传与受限内存测试 |
| 文档问答仍无条件创建完整 Sandbox | 中 | 高 | Lazy Provider、按需工具注册和 Sandbox 创建指标 | 纯 Context Run 断言零 Sandbox |
| 共享 Worker 被恶意/超大文档拖垮 | 中 | 高 | 每 Job 进程隔离、资源限制、租约和 Worker 回收 | OOM/超时/恶意文件故障注入 |
| PDF/Office 解析质量不稳定 | 高 | 高 | 格式专用解析器、质量报告、部分成功和基准语料 | 文本/扫描/表格/损坏/密码文档矩阵 |
| 文档操作输出损坏或格式丢失 | 中 | 高 | copy-on-write、Capability 限制、重新打开和结构验证 | 每种操作的黄金文件与渲染对比 |
| OCR 成本和时延失控 | 中 | 高 | 按页检测、预算、并发与可取消 | 混合文本/扫描 PDF 测试和指标 |
| 向量召回遗漏精确数字 | 高 | 高 | FTS、结构检索、融合和查询分类 | 合同编号、金额、公式、单元格评测集 |
| 临时索引没有及时清理 | 中 | 中 | expires_at、last_used_at、配额和清理指标 | 时间推进和重复续期测试 |
| Project 绑定变成隐藏 Prompt | 中 | 高 | 只注入 Scope Manifest，正文必须显式检索并 Trace | Runtime 消息快照测试 |
| 删除后仍能检索 | 低 | 高 | 授权/状态前置过滤和立即撤销 Scope | 删除并发与缓存失效测试 |
| embedding 模型升级导致结果漂移 | 中 | 中 | Generation 并行构建、版本 Trace 和原子切换 | 双 Generation 回归评测 |
| pgvector 影响主库负载 | 中 | 高 | 独立索引、连接池、慢查询指标和迁移门槛 | 数据量级压测与数据库监控 |
| 双写派生产物产生孤儿 | 中 | 中 | Job 幂等、Artifact Manifest、补偿清理 | 各阶段故障注入 |
| Agent 引用未实际使用的结果 | 中 | 中 | Citation Ref 协议与最终引用追踪 | 回答/引用一致性测试 |
| 合同审查/论文总结只检索 Top-K 导致章节遗漏 | 中 | 高 | focused/comprehensive 分流、Outline 和章节覆盖游标 | 全文覆盖评测集 |
| 同文件多 Knowledge 重复处理 | 中 | 中 | Revision 内容寻址、Index Generation 复用规则 | 同 SHA 多关系测试 |
| Worker 解析恶意文档 | 中 | 高 | 无网络、无宏、沙箱化、超时、解压限制 | 恶意 Office/PDF 安全语料 |

## 重要假设

- Knowledge 第一阶段仍以单用户私有资料为主，不提前建设组织级 ACL。
- 用户希望会话附件“现在可用”，但不希望所有附件自动进入长期知识库。
- Project 继续是 Session 单层目录；Knowledge Binding 是后续 Run 的显式可见范围。
- Agent Profile 尚未实现，因此首期只实现 Project Binding，并保留未来接口边界。
- 原始文件继续使用现有 Local/COS/OSS Provider；派生产物可以使用同一 Provider 的独立前缀。
- K2 首期可接受 PostgreSQL FTS + pgvector 的规模上限，且会通过指标决定是否迁移专用向量服务。
- embedding Provider 可以是外部 API 或私有模型，但必须有稳定 `model_id`、维度、超时和隐私配置。
- 文档处理 Worker 是新的部署组件，不能复用当前短生命周期 Agent Sandbox 代替。
- 临时索引的具体 TTL、单文件上限和 OCR 预算由实施计划中的容量测试确定，不写死为产品承诺。

## 待决策项

以下决策不改变总体架构，也不阻塞 R0/D0，但会影响 D1/D2/K1 的实施范围：

1. D1 是否首期包含 PPTX 和 XLSX，还是先完成 PDF + DOCX 后再扩展。
2. 扫描 PDF 的首期 OCR 语言是否只支持中文/英文。
3. 大文件首期是否同时支持 Local、COS、OSS multipart，还是先实现当前默认 Provider。
4. embedding 默认使用私有部署模型还是现有 OpenAI-compatible Provider。
5. K1 临时索引 TTL、用户容量和并发 Job 默认值。
6. 文档预览首期是否要求 PDF 页高亮，以及 Office 是否先转换为 PDF 派生预览。
7. D2 首期优先 PDF 操作，还是同时交付 DOCX/PPTX/XLSX 的最小编辑集合。
8. Office 输出验证是否要求服务端渲染对比，还是首期只做重新打开和结构检查。

这些项目应在编写 D1/D2/K1 实施计划前确认；“上传不等于永久向量化、临时/长期共用检索后端、长期 Knowledge 默认混合索引”不再作为开放问题。

## 验收标准

### R0

- [ ] 普通无工具对话、Document Tool 和 Context Tool 不创建或恢复 Agent Sandbox。
- [ ] Sandbox 只在首次实际调用 Sandbox/Browser Tool 时创建，同一 Session 并发只创建一个实例。
- [ ] 普通附件不在 Run 开始时复制进 Sandbox，只同步当前 Sandbox Tool 明确需要的文件。
- [ ] Planner 不携带完整 Tool Schema；ReAct 只接收当前 Step capability 所需 Schema。
- [ ] 历史 waiting Run、审批恢复、下一条消息队列、分支、VNC、Shell 和 Browser 行为无回归。
- [ ] Trace 能比较优化前后的 Sandbox 创建数和 Tool Schema count/bytes，且不记录完整 Schema。

### D0

- [ ] Revision、Block、Locator、Processing Job 和 Capability 协议可在无数据库/Redis/Sandbox 环境中独立测试。
- [ ] Worker 不含 Chrome/VNC/Node/sudo，不持有业务数据库或对象存储长期凭据。
- [ ] TXT/Markdown 能异步生成唯一 Revision、有序 Block 和稳定行号/标题定位。
- [ ] 相同文件、解析器版本和选项重复提交复用结果；重复消息和晚到回执不产生两个成功 Revision。
- [ ] Worker 崩溃、lease 超时、Redis 重投、取消和重试可恢复，临时文件被清理。
- [ ] 跨用户、伪造 Worker 身份、过期 lease、MIME 欺骗和超限输入被拒绝。
- [ ] Document Tool 只返回 Job/Revision/Block 摘要和受限分页结果，不自动把全文放入模型。
- [ ] PDF/Office 在本批返回明确 unsupported capability，不 fallback 到 Agent Sandbox。

### D1

- [ ] 现有小文件上传、文件中心、下载、软删除和 Session 附件行为无回归。
- [ ] 常规 PDF/Office 解析运行于不含 Chrome/VNC/交互 Shell 的轻量 Worker Pool，不创建 Agent Sandbox。
- [ ] 超过现有同步限制的大文件可分片上传、暂停后续传、重复 complete 幂等，API 内存不随完整文件大小线性增长。
- [ ] PDF 文本页与扫描页能形成同一 Revision，OCR 只处理需要的页面。
- [ ] DOCX 标题、段落、列表和表格结构可检查。
- [ ] PPTX 可定位 Slide，XLSX 可定位 Sheet/Cell Range（若纳入 K0 首期）。
- [ ] 密码、损坏、格式伪装、压缩炸弹和超配额文档返回稳定错误。
- [ ] Worker 崩溃或超时后 Job 可恢复/重试，不产生多个激活 Revision。
- [ ] 同一文件和处理版本重复请求复用结果。
- [ ] 用户能看到处理阶段、部分成功、质量告警、取消和重试。

### D2

- [ ] 所有修改操作默认生成新 File，原始对象和现有 Knowledge Revision 不变化。
- [ ] PDF 合并、拆分、旋转、重排、OCR 或渲染按 Capability 声明工作，并可追溯有序输入。
- [ ] 纳入首期的 DOCX/PPTX/XLSX 操作使用结构化参数，不接收任意代码或文件路径。
- [ ] 输出文件可被对应解析器重新打开，并产生页/Slide/Sheet、关键结构、大小和警告验证报告。
- [ ] 同一 Idempotency Key 重试不会生成多个输出文件。
- [ ] 不支持或可能明显丢失格式的操作在执行前返回明确能力限制。
- [ ] Agent Tool 只返回 Job/File 引用和摘要，不把完整二进制或文档正文放入模型上下文。
- [ ] 删除或覆盖原件仍进入高风险批准边界；只生成新文件不弹出 Shell 批准。
- [ ] 输出文件不会自动加入 Knowledge，用户可以明确选择加入或替换版本。

### K1

- [ ] 小型单次附件不强制创建永久向量。
- [ ] 只进行上传文档问答、临时索引和引用的 Run 不创建或恢复 Agent Sandbox。
- [ ] 纯文档 Run 的模型 Tool Schema 不包含 Shell、Browser、VNC 和 Sandbox File Tool。
- [ ] 只有首次实际调用 Sandbox Tool 时才创建 Sandbox 并同步指定附件。
- [ ] 3–5 万字合同/论文自动形成关键词可用、embedding 后补齐的临时 Context，不要求用户手工点击“转向量”。
- [ ] 大型/多文件附件建立带 TTL 的 Session Scope Binding，并可在同一 Session 后续消息复用。
- [ ] 临时 Binding 过期后不再进入 Session Scope，但保留原始文件；无其他 Binding 的 Index 可回收并可重建。
- [ ] 临时 Context 加入 Knowledge 时，在配置一致的情况下复用同一 Index/embedding，只增加长期 Binding。
- [ ] 关键词、向量和结构通道可单独故障并按规则降级。
- [ ] 检索结果引用可打开 PDF 页、Word 标题、PPT Slide 或 Excel Range。
- [ ] Planner 只收到 Scope Manifest，不收到完整 Knowledge 正文。
- [ ] LLM 无法通过自行构造 Knowledge ID 越权扩大 Scope。
- [ ] Trace 能复现检索版本、结果 ID、分数和最终引用，不复制完整文档正文。
- [ ] focused 查询能定位条款/结论；comprehensive 查询按 Outline 覆盖全部章节，而不是只返回 Top-K。
- [ ] 多轮询问同一文档不重复解析或 embedding；每轮只向模型返回预算内的命中片段/Outline。

### K2

- [ ] 用户可创建 Knowledge、加入/移除文件、查看状态并重新处理。
- [ ] 长期 Knowledge 默认同时具备关键词和向量索引；embedding 故障时显示部分可用并可检索关键词。
- [ ] 同一文件加入多个 Knowledge 不重复解析，关系删除互不影响。
- [ ] 新 Revision/Index Generation 完成前旧版本持续可用，切换原子完成。
- [ ] Project Binding 显式可见；Session 移动 Project 只影响后续 Run。
- [ ] 删除文件、Knowledge 或 Binding 后，后续查询立即不可见。
- [ ] 两个用户即使拥有同名、同哈希文件也不能互相检索或打开引用。
- [ ] 相关迁移、回滚、容量压测、安全语料、检索评测、后端测试、前端测试和页面验收通过后，才可进入合并门禁。
