# 慕课 LLMOps 原生AI 应用开发平台

## 一、项目启动（推荐 Docker Compose）

### 1. 环境准备

- Docker Desktop（含 Docker Compose）
- 可用端口：`3000`、`5011`、`5432`、`6379`、`8080`、`50051`

### 2. 一键启动

在仓库根目录执行：

```powershell
Copy-Item docker\.env.example docker\.env
```

按需编辑 `docker/.env`，至少配置自己的 LLM API Key。

```bash
docker compose -f docker/docker-compose.yaml up --build -d
```

Compose 文件已显式设置项目名为 `llmops`，网络名固定为 `llmops_default`。
Compose 会自动读取 `docker/.env`，该文件已加入 `.gitignore`，不要提交真实密钥。

如果旧环境曾经用默认项目名启动过，可能遇到
`container name "/llmops-ui" is already in use`。先停掉旧容器后再启动：

```powershell
docker rm -f llmops-ui llmops-backend-api llmops-backend-celery llmops-api llmops-celery llmops-db llmops-redis llmops-weaviate
docker compose -f docker/docker-compose.yaml up --build -d
```

### 3. 查看运行状态

```bash
docker compose -f docker/docker-compose.yaml ps
docker compose -f docker/docker-compose.yaml logs -f llmops-api
```

### 4. 访问地址

- 前端 UI: `http://localhost:3000`
- API: `http://localhost:5011`

> OAuth 本地回调地址已配置为：`http://localhost:3000/auth/authorize/github`

### 4.1 本地开发登录账号

本地 GitHub OAuth 需要在 GitHub OAuth App 中把回调地址配置为
`http://localhost:3000/auth/authorize/github`，否则会出现
`The redirect_uri is not associated with this application`。

本地调试推荐直接初始化一个密码登录账号：

```powershell
.\docker\init-dev-account.ps1
```

默认账号：

```text
Email: admin@example.com
Password: Llmops1234
```

如需自定义账号：

```powershell
.\docker\init-dev-account.ps1 -Email "dev@example.com" -Password "Dev123456" -Name "Dev"
```

脚本会对 `account` 表执行 upsert，并调用
`http://127.0.0.1:5011/auth/password-login` 自动验证登录。

### 4.2 本地文件上传

Docker Compose 默认使用本地文件存储：

```yaml
LOCAL_STORAGE_ROOT: /app/api/storage/uploads
LOCAL_STORAGE_BASE_URL: http://localhost:3100/api/upload-files
```

上传文件会保存在宿主机目录：

```text
docker/volumes/app/storage/uploads
```

上传接口返回的图片地址形如：

```text
http://localhost:3100/api/upload-files/2026/05/08/<file>.png
```

这里必须是完整 URL，因为工作流图标、应用图标、图片输入等字段会校验 URL 格式。
如需在生产环境使用腾讯 COS，优先在控制台 `设置 -> 存储` 中配置并保存到数据库。

### 4.3 模型供应商配置

模型供应商、Base URL、API Key 和默认模型优先在控制台 `设置 -> 模型供应商` 中配置，
并加密保存到数据库。`docker/.env` 不再作为本地调试的主要模型配置入口。

可用的 provider/model 定义在：

```text
api/app/core/language_model/providers/
```

内置工具凭据暂未纳入插件管理配置页，天气和搜索仍通过 `docker/.env` 中的
`GAODE_API_KEY`、`SERPER_API_KEY` 传入。

### 4.4 （可选）启用外层 Nginx（80/443）

默认不会启动 `llmops-nginx`（已改为 `edge` profile）。

```bash
docker compose -f docker/docker-compose.yaml --profile edge up -d llmops-nginx
```

### 5. 停止与清理

```bash
docker compose -f docker/docker-compose.yaml down
```

如需同时删除数据卷（会清空本地数据）：

```bash
docker compose -f docker/docker-compose.yaml down -v
```

---

## 二、项目启动（本地开发模式，可选）

详细的“Docker 启动基础依赖，API/Celery/UI 在本机单独启动”调试流程见：
[`docs/local-development.md`](docs/local-development.md)。

### 1. 启动前端

```bash
cd ui
pnpm install
pnpm dev
```

### 2. 启动后端

```bash
cd api
uv sync
uv run uvicorn app.main:app --host=0.0.0.0 --port=5011 --reload
```

> 说明：后端依赖 PostgreSQL / Redis / Weaviate，建议仍通过 Docker 启动这些依赖服务。

---

## 三、CI/CD 启动操作文档

当前仓库未发现现成 CI/CD 配置文件（例如 `.github/workflows/*.yml`）。  
建议使用 GitHub Actions，按以下步骤启用：

### 1. 创建工作流目录与文件

在仓库创建：

- `.github/workflows/ci.yml`

### 2. 写入最小 CI（示例）

```yaml
name: CI

on:
  push:
    branches: [ "main", "master" ]
  pull_request:
    branches: [ "main", "master" ]
  workflow_dispatch:

jobs:
  ui:
    runs-on: ubuntu-latest
    defaults:
      run:
        working-directory: ui
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-node@v4
        with:
          node-version: 20
      - run: corepack enable
      - run: pnpm install --frozen-lockfile
      - run: pnpm type-check
      - run: pnpm lint
      - run: pnpm test:unit --run
      - run: pnpm build

  api:
    runs-on: ubuntu-latest
    defaults:
      run:
        working-directory: api
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with:
          python-version: "3.11"
      - uses: astral-sh/setup-uv@v4
      - run: uv sync
      - run: uv run ruff check app tests
      - run: uv run pytest -q
```

### 3. 提交并推送触发 CI

```bash
git add .github/workflows/ci.yml README.md
git commit -m "docs: add startup and CI/CD instructions"
git push
```

### 4. 手动触发 CI（可选）

GitHub 页面路径：

`Actions` -> 选择 `CI` -> `Run workflow`

### 5. （可选）接入 CD

如需自动部署（CD），可在 `ci.yml` 增加 `deploy` job，并配置仓库 `Settings -> Secrets and variables -> Actions`（如服务器地址、密钥、镜像仓库凭据等）。

---

## 四、方案 B：进入容器执行 SQL 初始化账号

当 OAuth 不可用时，可直接在容器内初始化一个可登录账号（密码登录）。

推荐优先使用脚本：

```powershell
.\docker\init-dev-account.ps1
```

下面是手动 SQL 方式，通常只在需要排查脚本问题时使用。

### 1. 设置初始化账号信息（PowerShell）

```powershell
$EMAIL = "admin@example.com"
$PASSWORD = "Llmops1234"   # 8-16位，至少包含一个字母和一个数字
$NAME = "Admin"
```

### 2. 在 `llmops-api` 容器里生成密码哈希和盐值

```powershell
$vals = docker exec llmops-api python -c "import base64,secrets,hashlib,binascii,sys; pw=sys.argv[1]; salt=secrets.token_bytes(16); h=binascii.hexlify(hashlib.pbkdf2_hmac('sha256', pw.encode('utf-8'), salt, 10000)); print(base64.b64encode(h).decode()); print(base64.b64encode(salt).decode())" $PASSWORD
$PASSWORD_HASH = $vals[0]
$PASSWORD_SALT = $vals[1]
```

### 3. 进入 `llmops-db` 执行 SQL（存在则更新，不存在则插入）

```powershell
$sql = @"
WITH updated AS (
  UPDATE account
  SET name = '$NAME',
      password = '$PASSWORD_HASH',
      password_salt = '$PASSWORD_SALT'
  WHERE email = '$EMAIL'
  RETURNING id
)
INSERT INTO account (name, email, password, password_salt)
SELECT '$NAME', '$EMAIL', '$PASSWORD_HASH', '$PASSWORD_SALT'
WHERE NOT EXISTS (SELECT 1 FROM updated);
"@

docker exec -i llmops-db psql -U postgres -d llmops -v ON_ERROR_STOP=1 -c "$sql"
```

### 4. 验证是否可登录

```powershell
$body = @{ email = $EMAIL; password = $PASSWORD } | ConvertTo-Json
Invoke-RestMethod -Uri "http://localhost:5011/auth/password-login" -Method Post -ContentType "application/json" -Body $body
```

返回 `code = success` 即表示账号初始化成功。
