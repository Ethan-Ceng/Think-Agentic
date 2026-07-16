# Skill 运维手册

本文面向 Agentic 部署管理员，覆盖 Marketplace 导入、存储、备份恢复、孤儿清理和 Trace 排障。个人包使用各用户自己的存储配置；Marketplace 包使用部署级凭据，两者不得混用。

## 数据与存储模型

- PostgreSQL：`skills`、`skill_versions`、`skill_installations`、`run_skills` 保存元数据、不可变版本、用户固定安装和历史 Run 引用。
- 个人对象：`personal/<user_id>/<skill_id>/<version>.skill`，由服务在运行时解密用户存储配置后写入。
- Marketplace 对象：`marketplace/<skill_id>/<version>.skill`，由部署设置写入；Aliyun OSS 可带配置前缀。
- 草稿：`SKILL_WORKSPACE_STORAGE_PATH/users/<user_id>/<draft_id>`，只在 API 受控工作区；发布后尽力清理。
- Sandbox：每次 Run 临时物化，不是权威备份来源。

版本对象只追加不覆盖。数据库提交失败时服务会尝试删除刚上传对象；删除失败可能留下孤儿，但不会产生可见版本。

## Marketplace 存储配置

默认本地配置：

```text
MARKETPLACE_SKILL_STORAGE_PROVIDER=local
SKILL_PACKAGE_STORAGE_PATH=/app/storage/skills/packages
SKILL_WORKSPACE_STORAGE_PATH=/app/storage/skill-workspaces
```

腾讯云 COS：

```text
MARKETPLACE_SKILL_STORAGE_PROVIDER=qcloud_cos
MARKETPLACE_SKILL_COS_BUCKET=...
MARKETPLACE_SKILL_COS_REGION=...
MARKETPLACE_SKILL_COS_DOMAIN=...
MARKETPLACE_SKILL_COS_SCHEME=https
MARKETPLACE_SKILL_COS_SECRET_ID=...
MARKETPLACE_SKILL_COS_SECRET_KEY=...
```

阿里云 OSS：

```text
MARKETPLACE_SKILL_STORAGE_PROVIDER=aliyun_oss
MARKETPLACE_SKILL_OSS_BUCKET=...
MARKETPLACE_SKILL_OSS_ENDPOINT=...
MARKETPLACE_SKILL_OSS_REGION=...
MARKETPLACE_SKILL_OSS_DOMAIN=...
MARKETPLACE_SKILL_OSS_PATH_PREFIX=...
MARKETPLACE_SKILL_OSS_ACCESS_KEY_ID=...
MARKETPLACE_SKILL_OSS_ACCESS_KEY_SECRET=...
```

凭据只通过环境或秘密管理器注入，不写入 `config.yaml`、Git、脚本参数或命令输出。启用云 provider 前先用最小权限账号验证 put/get/delete 和重启后读取；对象前缀应仅授权 Skill 包目录。

## 导入 Marketplace 包

管理员在可信主机或 API 容器内执行离线脚本：

```bash
cd api
python scripts/import_market_skill.py app/skills/bundled/skill-creator \
  --display-name "Skill Creator" \
  --changelog "Initial deployment release"
```

也可传 `.skill`/`.zip` 路径。脚本校验并重建确定性包，先上传部署存储，再提交数据库。输出仅含 Skill ID、version ID、版本号、hash、provider 和幂等标记。

重导相同内容会返回已有版本。要断言固定版本内容完全一致，可加 `--version 1`；同一版本的不同字节会冲突。省略版本且内容改变时，只能创建下一个连续版本。全局 Marketplace `name` 唯一。

导入后至少验证：列表可见、另一用户未安装时目录不可见、安装固定版本可调用、显式更新后新 Run 使用新版本、旧 Run 的 `run_skills` 仍指向旧版本。

## 孤儿包核对与清理

1. 从对象存储列出 `personal/` 和 `marketplace/`（含 OSS 前缀）下的 `.skill` key、大小和修改时间。
2. 从 `skill_versions` 导出 `storage_provider`、`storage_key`、`package_sha256`。
3. 对象存在但数据库无 key：标为候选孤儿，等待至少一个发布事务与备份周期后再删除。
4. 数据库有记录但对象不存在：不要改指针；立即从备份恢复相同字节并校验 SHA-256。
5. 删除前保存审计清单。不得按“不是 current version”删除，因为安装和历史 Run 可能仍固定旧版本。

不要把工作区临时文件或 Sandbox 物化目录上传为市场包，也不要自动清理被 `skill_installations` 或 `run_skills` 引用的版本。

## 备份与恢复

一次一致备份应包含：

- PostgreSQL 全库或至少 Skill/Run/用户关联表；
- 本地 `SKILL_PACKAGE_STORAGE_PATH` 卷，或云对象存储的版本化快照；
- 尚需保留的草稿工作区；
- 部署配置的非秘密部分和秘密管理器引用。

恢复顺序：先对象存储，再 PostgreSQL，再启动 API；执行 `alembic upgrade head`，抽样下载包并对照 `package_sha256`。随后验证个人隔离、Marketplace 安装固定版本、Fork lineage 和历史 Trace。恢复到另一 bucket 时必须同步更新受支持的 provider 配置，不能手工改 hash。

## Trace 排障

在会话 Trace 的 Skills 区域核对：

- `source`：bundled、personal 或 marketplace；
- `selection_mode`：manual 或 automatic；
- `skill_id`、`skill_version_id`、name、content SHA-256；
- 选择原因、置信度和 `sandbox_path`；
- 同一 Run 的模型调用、工具调用与错误事件。

常见定位顺序：目录授权 → 固定版本存在 → provider 配置有效 → 下载 hash 一致 → Sandbox 上传/解压成功 → Prompt 含当前 Run 指令。重启或继续失败 Run 时，使用 Trace 固定版本复现；不要改用 Marketplace 最新版本替代历史版本。

## 发布与回滚检查

发布前运行后端测试与 Ruff、迁移 upgrade/downgrade/upgrade、前端测试/类型检查/构建，并做双用户 Docker 验收。Skill migration 回滚会删除 Skill 相关表，必须先备份；生产环境不以 downgrade 作为普通内容回滚手段。应用回滚时保留数据库和不可变对象，以便旧代码或恢复后的新代码继续读取历史 Trace。
