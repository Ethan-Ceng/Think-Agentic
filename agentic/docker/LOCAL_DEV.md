# Agentic 本地开发

本文档用于“Docker 只启动本地开发依赖，本机调试 API 和 Web 前端”的开发方式。当前 compose 文件位于 `agentic/docker`，以下命令默认都在该目录执行。

## 快速总结

- `docker-compose.yml` 是完整部署栈：API、Web、Nginx、PostgreSQL、Redis、Sandbox 都在 Docker 中运行。
- `docker-compose.dev.yml` 是本地开发栈：默认只启动 Redis/PostgreSQL，本机运行 API 和 Web。
- 部署栈不再挂载整个 `../api:/app`，只挂载 `../api/config.yaml` 和 `api_storage` 数据卷。
- 本地开发和部署不要叠加 compose 文件，分别使用各自入口。

本地开发入口：

```powershell
cd agentic\docker
docker compose --env-file ../.env -f docker-compose.dev.yml up -d
docker compose --env-file ../.env -f docker-compose.dev.yml build manus-sandbox
```

完整部署入口：

```powershell
cd agentic\docker
docker compose --env-file ../.env -f docker-compose.yml up -d --build
```

配置解析验证：

```powershell
docker compose --env-file ../.env -f docker-compose.yml config
docker compose --env-file ../.env -f docker-compose.dev.yml config
docker compose --env-file ../.env -f docker-compose.dev.yml --profile sandbox config
```

## 文件分工

- `docker-compose.dev.yml`：本地开发栈，默认只启动 PostgreSQL 和 Redis，并暴露到 `127.0.0.1`。
- `docker-compose.yml`：完整 Docker 部署栈，API、Web、Nginx、PostgreSQL、Redis、Sandbox 都在 Docker 中运行。
- 本地开发栈使用 `manus_postgres_dev_data`、`manus_redis_dev_data`，和部署栈数据卷分开。
- 不要再把 `docker-compose.yml` 和 `docker-compose.dev.yml` 叠加使用；两者现在是独立入口。

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
docker compose --env-file ../.env -f docker-compose.dev.yml up -d
```

端口默认暴露到本机：

- PostgreSQL：`127.0.0.1:5432`
- Redis：`127.0.0.1:6379`

注意：`--env-file ../.env` 用于 compose 变量插值，例如 `POSTGRES_PORT`、`POSTGRES_USER`、`POSTGRES_PASSWORD`、`POSTGRES_DB`、`REDIS_PORT`。API 本机进程仍读取 `agentic/api/.env`。

查看状态：

```powershell
docker compose --env-file ../.env -f docker-compose.dev.yml ps
```

## 2. 准备沙箱镜像

如需执行 Agent 任务、浏览器任务或远程桌面能力，先构建沙箱镜像：

```powershell
docker compose --env-file ../.env -f docker-compose.dev.yml build manus-sandbox
```

本机调试 API 时，`agentic/api/.env` 建议保持：

```env
SANDBOX_ADDRESS=
SANDBOX_IMAGE=manus-sandbox
SANDBOX_NAME_PREFIX=manus-sandbox
SANDBOX_NETWORK=manus-network
```

`SANDBOX_ADDRESS` 留空时，API 会通过 Docker 动态创建沙箱容器，因此本机 API 进程需要能访问 Docker。`docker-compose.dev.yml` 会创建 `manus-network`，供动态沙箱加入。

如果只想启动一个固定沙箱容器调试，可运行：

```powershell
docker compose --env-file ../.env -f docker-compose.dev.yml --profile sandbox up -d manus-sandbox
```

固定沙箱模式下，本机 API 可使用：

```env
SANDBOX_ADDRESS=127.0.0.1
```

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

如果 API、Web、Nginx 都放进 Docker，只使用 `docker-compose.yml`：

```powershell
docker compose --env-file ../.env -f docker-compose.yml up -d --build
```

完整部署默认访问：

```text
http://localhost:8088
```

`manus-api` 在完整 Docker 部署中默认设置 `RUN_MIGRATIONS_ON_STARTUP=true`，新库启动时会自动执行 Alembic 迁移。

完整部署模式默认只通过 Nginx 暴露服务，PostgreSQL 和 Redis 不暴露到宿主机。`manus-api` 不再挂载整个 `../api` 源码目录，只挂载 `../api/config.yaml` 和 `api_storage` 数据卷。

如需只监听本机，可在 `agentic/.env` 中设置：

```env
NGINX_BIND=127.0.0.1
```

PostgreSQL 容器会挂载 `agentic/docker/init.sql` 到 `/docker-entrypoint-initdb.d/10-init.sql`。该脚本只在 `postgres_data` 数据卷首次创建时执行；如果数据卷已经存在，需要继续使用 Alembic 迁移更新数据库结构。

## 6. 常用命令

停止本地中间件：

```powershell
docker compose --env-file ../.env -f docker-compose.dev.yml stop
```

重新启动本地中间件：

```powershell
docker compose --env-file ../.env -f docker-compose.dev.yml up -d
```

查看中间件日志：

```powershell
docker compose --env-file ../.env -f docker-compose.dev.yml logs -f
```

停止并删除容器但保留数据卷：

```powershell
docker compose --env-file ../.env -f docker-compose.dev.yml down
```

清空数据库和 Redis 数据卷需谨慎执行：

```powershell
docker compose --env-file ../.env -f docker-compose.dev.yml down -v
```

## 7. 验证项

建议至少验证：

- `docker compose --env-file ../.env -f docker-compose.dev.yml config`
- `docker compose --env-file ../.env -f docker-compose.yml config`
- Redis/PostgreSQL 容器健康运行。
- `127.0.0.1:5432` 和 `127.0.0.1:6379` 可连通。
- `uv run alembic upgrade head`。
- `http://localhost:8000/api/status` 返回健康状态。

Web 前端构建验证使用 `pnpm build`。
