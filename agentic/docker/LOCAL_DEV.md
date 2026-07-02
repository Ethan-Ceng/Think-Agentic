# Agentic Local Docker Development

本文档用于“Docker 只启动中间件，本机调试 API 和 Web 前端”的开发方式。当前 compose 文件位于 `agentic/docker`，以下命令默认都在该目录执行。

## 目标架构

- Docker 容器：PostgreSQL、Redis。
- 本机进程：FastAPI API、Vue 3 + Vite Web。
- 可选 Docker 镜像：`manus-sandbox`，用于 API 动态创建沙箱容器。

## 1. 启动中间件

进入 docker 目录：

```powershell
cd agentic\docker
```

启动 Redis 和 PostgreSQL：

```powershell
docker compose --env-file ../.env -f docker-compose.yml -f docker-compose.dev.yml up -d manus-redis manus-postgres
```

端口默认暴露到本机：

- PostgreSQL：`127.0.0.1:5432`
- Redis：`127.0.0.1:6379`

注意：`env_file: ../.env` 只会注入容器运行时环境变量，不负责 compose 自身的变量插值。需要让 `POSTGRES_PORT`、`POSTGRES_USER`、`NGINX_PORT` 等变量参与 compose 解析时，应显式带上 `--env-file ../.env`。

查看状态：

```powershell
docker ps --filter name=manus
```

## 2. 准备沙箱镜像

如需执行 Agent 任务、浏览器任务或远程桌面能力，先构建沙箱镜像：

```powershell
docker compose --env-file ../.env -f docker-compose.yml build manus-sandbox
```

本机调试 API 时，`agentic/api/.env` 建议保持：

```env
SANDBOX_ADDRESS=
SANDBOX_IMAGE=manus-sandbox
SANDBOX_NAME_PREFIX=manus-sandbox
SANDBOX_NETWORK=manus-network
```

`SANDBOX_ADDRESS` 留空时，API 会通过 Docker 动态创建沙箱容器，因此本机 API 进程需要能访问 Docker。

## 3. 配置并启动 API

进入 API 目录：

```powershell
cd ..\api
Copy-Item .env.example .env
```

确认 `agentic/api/.env` 至少包含：

```env
SQLALCHEMY_DATABASE_URI=postgresql+asyncpg://postgres:postgres@127.0.0.1:5432/manus
REDIS_HOST=127.0.0.1
REDIS_PORT=6379
RUN_MIGRATIONS_ON_STARTUP=false
```

执行数据库迁移：

```powershell
uv run alembic upgrade head
```

启动 API：

```powershell
uv run uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload
```

访问地址：

- API 文档：`http://localhost:8000/docs`
- 健康检查：`http://localhost:8000/api/status`

## 4. 启动 Web 前端

新开一个终端，在仓库根目录执行：

```powershell
cd agentic\web
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

如需覆盖 API 地址，可在启动前设置：

```powershell
$env:VITE_API_BASE_URL = "http://localhost:8000/api"
pnpm dev
```

## 5. 完整 Docker 部署

如果 API、Web、Nginx 都放进 Docker，仍然在 `agentic/docker` 目录执行：

```powershell
docker compose --env-file ../.env -f docker-compose.yml up -d --build
```

完整部署默认访问：

```text
http://localhost:8088
```

`manus-api` 在完整 Docker 部署中默认设置 `RUN_MIGRATIONS_ON_STARTUP=true`，新库启动时会自动执行 Alembic 迁移。

PostgreSQL 容器会挂载 `agentic/docker/init.sql` 到 `/docker-entrypoint-initdb.d/10-init.sql`。该脚本只在 `postgres_data` 数据卷首次创建时执行；如果数据卷已经存在，需要继续使用 Alembic 迁移更新数据库结构。

## 6. 常用命令

停止本地中间件：

```powershell
docker compose --env-file ../.env -f docker-compose.yml -f docker-compose.dev.yml stop manus-redis manus-postgres
```

重新启动本地中间件：

```powershell
docker compose --env-file ../.env -f docker-compose.yml -f docker-compose.dev.yml up -d manus-redis manus-postgres
```

查看中间件日志：

```powershell
docker compose --env-file ../.env -f docker-compose.yml -f docker-compose.dev.yml logs -f manus-redis manus-postgres
```

停止并删除容器但保留数据卷：

```powershell
docker compose --env-file ../.env -f docker-compose.yml -f docker-compose.dev.yml down
```

清空数据库和 Redis 数据卷需谨慎执行：

```powershell
docker compose --env-file ../.env -f docker-compose.yml -f docker-compose.dev.yml down -v
```

## 7. 验证项

建议至少验证：

- `docker compose --env-file ../.env -f docker-compose.yml -f docker-compose.dev.yml config`
- Redis/PostgreSQL 容器健康运行。
- `127.0.0.1:5432` 和 `127.0.0.1:6379` 可连通。
- `uv run alembic upgrade head`。
- `http://localhost:8000/api/status` 返回健康状态。

Web 前端构建验证使用 `pnpm build`。
