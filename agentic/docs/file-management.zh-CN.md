# 文件管理与用户级对象存储

整理日期：2026-07-14

## 1. 能力边界

当前文件中心统一管理两类可交付文件：

- `user_upload`：用户从聊天输入框或文件中心上传的文件。
- `agent_generated`：Agent 在 Sandbox 中生成并作为最终消息附件交付的文件。

Sandbox 临时文件和中间过程文件不会进入文件中心。浏览器工具截图以临时 Data URL 展示，也不会产生文件资产。

## 2. 存储路由

每个用户拥有独立的 `storage` 配置，可选择 `local`、`qcloud_cos` 或 `aliyun_oss` 作为默认 Provider。默认 Provider 仅影响新文件；每条文件记录保存实际 Provider 和不含密钥的 Bucket/Endpoint 快照，因此切换默认值不会改变历史记录的读取目标。

Local 根目录由部署管理员通过 `LOCAL_STORAGE_PATH` 设置，普通用户不能从 UI 修改。COS/OSS 密钥使用 `CONFIG_ENCRYPTION_KEY` 加密后写入 `configs`，API 只返回 `******`。该主密钥必须保持稳定并通过部署环境注入。

阿里云 OSS Endpoint 必须使用 HTTPS，且运行时拒绝解析到本机、私网、链路本地或保留地址。远端 Provider 失败时不会静默回退到 Local。

## 3. 文件生命周期

文件中心支持分页、搜索、类型和来源筛选、目录、上传、预览、下载、重命名、移动及批量删除。删除后记录立即从文件中心隐藏且不能下载，`purge_after` 设置为 7 天后；后台清理任务到期删除物理对象和元数据。

单文件默认上限为 100 MB，可用 `MAX_UPLOAD_SIZE_MB` 调整。

## 4. 数据与 API

`files` 在原有字段上增加：

```text
parent_id, entry_type, storage_provider, storage_config,
source_type, status, sha256, metadata,
origin_session_id, origin_run_id, deleted_at, purge_after
```

迁移 `20260714_0001_file_management.py` 非破坏性扩展旧表：已有本地文件按 `filepath` 回填为 `local`，其余旧对象按 `qcloud_cos` 回填。

主要接口：

```text
GET/POST  /api/files
GET        /api/files/folders/tree
POST       /api/files/folders
PATCH      /api/files/{file_id}
DELETE     /api/files/{file_id}
POST       /api/files/batch-move
POST       /api/files/batch-delete
GET        /api/files/{file_id}/preview
GET        /api/files/{file_id}/download

GET/POST   /api/app-config/storage
POST       /api/app-config/storage/test
```

## 5. 部署要求

生产部署至少设置：

```text
CONFIG_ENCRYPTION_KEY=<长期稳定的高强度随机值>
RUN_MIGRATIONS_ON_STARTUP=true
```

完整 Docker 部署已将 `/app/storage` 挂载到持久化卷，Local 文件位于其 `files` 子目录。阿里云 OSS 依赖由 `oss2` 提供，腾讯 COS 继续使用 `cos-python-sdk-v5`。
