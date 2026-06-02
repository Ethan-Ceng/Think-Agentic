# LLMOps 平台底座待执行事项

本文记录 `llmops` 在接入主动智能体之前，优先需要落地的平台底座事项。当前阶段目标是保持主线简单、可实施，先完善文件、模型、配置和能力注册，再升级 Router/Worker 自主 Agent。

## 1. 已确认原则

- 当前先不引入复杂的 `scope_type / scope_id` 设计。
- 当前先不引入 setting `version` 字段，后续如有并发编辑冲突再加 `revision` 或乐观锁。
- 当前跟随 `llmops` 主线资源隔离方式，优先使用 `account_id`，不是新建 `user_id`。
- `tenant_id` 相关模型保留给后续企业多租户、RBAC、Agent Runtime 增强，不在第一阶段强行迁移所有主线资源。
- 第一阶段不单独建立 `CredentialVault` 表，敏感配置先统一存入 setting 表，由 API/service 层按字段加密、脱敏和解密。
- 页面可以叫“系统设置”或“配置管理”，底层表建议叫 `account_settings`，避免和真正全局系统配置混淆。
- 如果 tenant/RBAC 只是实验性脚手架，没有形成主线业务闭环，应优先移除或隔离，减少后续代码阅读和实施干扰。

## 2. 现有 LLMOps 调研结论

当前核心业务资源主要使用 `account_id` 隔离：

- `App`
- `Workflow`
- `Dataset`
- `Document`
- `Segment`
- `ProcessRule`
- `ApiToolProvider`
- `ApiTool`
- `ApiKey`
- `UploadFile`
- `WorkflowResult`

项目中已经存在一部分 `tenant_id` 设计，包括 `Tenant`、`TenantMember`、RBAC、`Agent`、`AgentTask`、`AgentPlan`、`TraceEvent` 等。

这些代码不是纯模型定义，已经包含：

- Alembic 迁移。
- `console`、`router_agent`、`approval`、`trace` 路由。
- `IdentityService`、`RouterAgentManagerService`、`TaskEngineService`、`TraceService`、`ApprovalService`。
- `test_task_engine_service.py`、`test_router_agent_manager_service.py`、`test_approval_policy_trace.py` 等测试。

但这部分还没有成为 `llmops` 主线产品能力。当前主线 App、Workflow、Dataset、UploadFile、ApiTool 等仍然主要使用 `account_id`。因此第一阶段不应把文件、模型、设置等主线能力直接切到 tenant 作用域。

建议拆分处理：

- `Tenant`、`TenantMember`、RBAC：如果暂时不做企业多租户和权限系统，优先从主线中移除或隔离。
- `AgentTask`、`AgentPlan`、`AgentStep`、`WorkerCall`、`CapabilityCall`、`TraceEvent`、`ApprovalRequest`：概念上对后续主动智能体有价值，但不应继续绑定当前半成品 tenant 体系。后续可按 `account_id` 或新的 Agent Runtime 边界重新实现。

如果当前数据库迁移尚未进入正式环境，可以考虑直接清理相关 migration；如果已经应用到共享环境，应通过新的 migration 做兼容性删除或迁移，避免破坏已有库状态。

## 3. 第一阶段 Setting 底座

建议新增一张账号级配置表：

```text
account_settings

- id
- account_id        # 跟随当前 llmops 主线账号隔离
- category          # storage / llm_provider / upload / agent / tool
- key               # local / qcloud_cos / aliyun_oss / openai / default
- value             # JSON，完整配置对象，敏感字段保存密文
- enabled
- created_at
- updated_at
```

唯一索引：

```text
unique(account_id, category, key)
```

暂不加入：

- `scope_type`
- `scope_id`
- `version`
- 独立 `credentials` 表
- 独立 `credential_refs` 表

## 4. 敏感字段处理方式

敏感配置不拆表，统一由 service 层处理：

```text
管理 API 入参
  -> 根据 category/key 找到敏感字段
  -> 对敏感字段加密
  -> 写入 account_settings.value

管理 API 读取
  -> 返回普通字段
  -> 敏感字段只返回脱敏值

运行时读取
  -> SettingService 读取配置
  -> 对指定敏感字段解密
  -> 注入 Storage / LLM / Tool Runtime
```

建议第一版采用简单密文标记：

```json
{
  "bucket": "demo-bucket",
  "region": "ap-guangzhou",
  "secret_id": "enc:...",
  "secret_key": "enc:..."
}
```

需要新增：

- `SettingService`
- `SettingCrypto`
- `SECRET_FIELDS` 映射
- setting 管理 API
- setting runtime resolve API 或内部方法

## 5. Storage 配置落地

第一阶段先支持本地和云存储配置，参考 `docs/storage` 的 local、qcloud、aliyun 模式，但重新设计成 DB 配置。

建议配置：

```text
category = storage
key = default
value = {
  "provider": "local"
}
```

```text
category = storage
key = local
value = {
  "root": "...",
  "base_url": "..."
}
```

```text
category = storage
key = qcloud_cos
value = {
  "bucket": "...",
  "region": "...",
  "domain": "...",
  "secret_id": "enc:...",
  "secret_key": "enc:..."
}
```

```text
category = storage
key = aliyun_oss
value = {
  "bucket": "...",
  "region": "...",
  "endpoint": "...",
  "access_key": "enc:...",
  "secret_key": "enc:..."
}
```

读取优先级：

1. 优先读取 `account_settings`。
2. 未配置时回退到现有 `.env / Settings`。
3. 后续企业版再补全局默认配置和租户级覆盖。

## 6. LLM Provider 配置落地

第一阶段不要先做复杂模型市场，先让用户能在页面配置 provider 和密钥。

示例：

```text
category = llm_provider
key = openai
value = {
  "base_url": "https://api.openai.com/v1",
  "api_key": "enc:...",
  "default_model": "gpt-4.1",
  "enabled": true
}
```

```text
category = llm_provider
key = deepseek
value = {
  "base_url": "...",
  "api_key": "enc:...",
  "default_model": "...",
  "enabled": true
}
```

Agent 页面只选择已配置 provider/model，不直接录入 API Key。

## 7. File Asset 后续落地

Setting 底座确认后，再落地文件资产模块。

文件资产目标：

- 所有用户文件像云盘一样管理。
- 支持本地、腾讯云 COS、阿里云 OSS 等存储。
- 文件既可以作为用户上传，也可以作为知识库来源，也可以作为 Agent 产物。
- Worker 之间传递 `ArtifactRef`，不直接传二进制。

建议第一版文件资产继续使用 `account_id` 隔离。

## 8. 待执行清单

### 模块零：主线清理

- [x] 梳理 tenant/RBAC/Agent Runtime 脚手架的实际使用范围。
- [x] 确认 `console`、`router_agent`、`approval`、`trace` 这些实验性路由不继续挂载主 API。
- [x] 从 `api/router.py` 取消挂载，避免暴露半成品接口。
- [x] 删除 `Tenant`、`TenantMember`、RBAC 相关模型、schema、service 和 console 初始化入口。
- [x] 新增 Alembic 迁移 `20260601_0001_drop_tenant_rbac.py`，通过新迁移 drop tenant/RBAC 表，不直接删除历史迁移。
- [x] 保留可复用的 Agent Task、Trace、Approval 设计思想，但后续按 `account_id` 和新的 Agent Runtime 重新落地。

执行记录：

- 已取消主 API 中 `approval`、`console`、`router_agent`、`trace` 路由挂载。
- 已删除 tenant/RBAC/identity/console 相关代码文件。
- 已移除 `get_current_tenant`、`get_current_member`、`default_tenant_id`。
- 已保留 `AgentTask`、`TraceEvent`、`ApprovalRequest` 等运行面模型，避免提前破坏后续主动智能体设计参考。
- 已执行 `py -m py_compile` 验证修改文件语法。
- 当前环境全局 Python 未安装 `pytest`，且 `py -m uv` 不可用，因此未能运行 pytest。

### 模块一：Setting 底座

- [x] 新增 `account_settings` 模型和迁移。
- [x] 新增 `SettingCrypto` 工具类。
- [x] 新增 `SettingService`。
- [x] 定义 `SECRET_FIELDS` 映射。
- [x] 新增 setting 管理 API。
- [x] 管理 API 读取时脱敏敏感字段。
- [x] runtime 使用时解密敏感字段。
- [x] 增加本地配置 fallback，未配置 DB 时继续读取现有 `.env / Settings`。

### 模块二：Storage 配置

- [x] 把 local storage 的 root/base_url 接入 `account_settings`。
- [x] 增加 qcloud_cos 配置 schema。
- [x] 增加 aliyun_oss 配置 schema。
- [x] 重构上传服务，从 setting 中解析当前账号的默认 storage provider。
- [x] 保留现有本地上传能力，避免破坏已有接口。
- [ ] 接入 qcloud_cos / aliyun_oss SDK，实现云存储真实上传、读取和签名下载。

### 模块三：LLM Provider 配置

- [x] 增加 LLM provider/model 独立表、API 和页面。
- [x] 支持 provider API Key 加密保存。
- [x] 支持管理页面脱敏展示。
- [x] App/Workflow 配置中优先选择已配置 provider/model，未配置时回退 YAML/.env。

### 模块四：File Asset

- [x] 新增 `files` 主表，文件记录使用 `storage_provider + file_path`，不落库绝对 URL。
- [x] 文件列表支持类云盘管理。
- [x] 文件上传统一走 storage driver。
- [x] 文件可作为知识库来源。
- [ ] 文件可作为 Agent task 输入。
- [ ] Agent 产物登记为 Artifact。

执行记录：

- 已新增 `account_settings`、`files`、`llm_providers`、`llm_models` 迁移。
- 已将新上传文件写入 `files`，并把 `Document.upload_file_id` 的实际读取逻辑切到 `files.id`。
- 已保留 `/upload-files` 兼容 API 形状，前端现有上传流程不需要改调用方。
- 已新增 Storage、LLM Provider、文件管理页面，并在知识库添加文件页支持从文件库选择。
- 当前 COS/OSS 已支持配置保存、脱敏和 URL 解析；真实 SDK 上传/读取留到后续。

## 9. 后续迁移方向

第一阶段不做多租户 setting 抽象，但预留演进路径：

```text
account_settings
  -> tenant_settings
  -> system_settings
```

企业版真正需要 workspace/tenant 隔离时，再增加 tenant 级配置继承关系，而不是现在把所有配置都塞进通用 `scope_type/scope_id`。
