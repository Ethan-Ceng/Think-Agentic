# 本地开发指南

本文档用于“Docker 只启动中间件，本机调试 API 和 Web 前端”的开发方式。

## 目标架构

- Docker 容器：PostgreSQL、Redis
- 本机进程：FastAPI API、Vue 3 + Vite Web
- 可选 Docker 镜像：`manus-sandbox`，用于 API 动态创建沙箱容器

## 1. 启动中间件

在项目根目录执行：

```powershell
docker compose -f docker-compose.yml -f docker-compose.dev.yml up -d manus-redis manus-postgres
docker compose build manus-sandbox
```

该命令只启动 Redis 和 PostgreSQL，并把端口暴露到本机：

- PostgreSQL：`127.0.0.1:5432`
- Redis：`127.0.0.1:6379`

查看状态：

```powershell
docker ps --filter name=manus
```

## 2. 准备沙箱镜像

如需执行 Agent 任务或使用远程桌面能力，需要先构建沙箱镜像：

```powershell
docker compose build manus-sandbox
```

API 的本地配置中保持：

```env
SANDBOX_ADDRESS=
SANDBOX_IMAGE=manus-sandbox
SANDBOX_NAME_PREFIX=manus-sandbox
SANDBOX_NETWORK=manus-network
```

`SANDBOX_ADDRESS` 留空时，API 会通过 Docker 动态创建沙箱容器。

## 3. 配置并启动 API

进入 API 目录：

```powershell
cd api
Copy-Item .env.example .env
```

确认 `api/.env` 至少包含：

```env
SQLALCHEMY_DATABASE_URI=postgresql+asyncpg://postgres:postgres@127.0.0.1:5432/manus
REDIS_HOST=127.0.0.1
REDIS_PORT=6379
```

执行数据库迁移：

```powershell
uv run alembic upgrade head
```

启动 API：

```powershell
uv run uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload
```

访问 API 文档：

```text
http://localhost:8000/docs
```

健康检查：

```text
http://localhost:8000/api/status
```

## 4. 启动 Web 前端

新开一个终端，在项目根目录执行：

```powershell
cd web
pnpm install
pnpm dev
```

访问 Web 前端：

```text
http://localhost:5173
```

Web 默认直连：

```text
http://localhost:8000/api
```

如需覆盖 API 地址，可在 UI 启动前设置：

```powershell
$env:VITE_API_BASE_URL = "http://localhost:8000/api"
pnpm dev
```

## 5. 常用命令

停止本地中间件：

```powershell
docker compose -f docker-compose.yml -f docker-compose.dev.yml stop manus-redis manus-postgres
```

重新启动本地中间件：

```powershell
docker compose -f docker-compose.yml -f docker-compose.dev.yml up -d manus-redis manus-postgres
```

查看中间件日志：

```powershell
docker compose -f docker-compose.yml -f docker-compose.dev.yml logs -f manus-redis manus-postgres
```

停止并删除容器但保留数据卷：

```powershell
docker compose -f docker-compose.yml -f docker-compose.dev.yml down
```

清空数据库和 Redis 数据卷需谨慎执行：

```powershell
docker compose -f docker-compose.yml -f docker-compose.dev.yml down -v
```

## 6. 验证项

当前本地开发流程已验证：

- `docker compose -f docker-compose.yml -f docker-compose.dev.yml config`
- Redis/PostgreSQL 容器健康运行
- `127.0.0.1:5432` 和 `127.0.0.1:6379` 可连通
- `uv run alembic upgrade head`
- `uv run pytest -q tests/app/interfaces/endpoints/test_status_routes.py`

注意：Web 前端构建验证使用 `pnpm build`。
