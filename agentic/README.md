# MoocManus - 通用 AI Agent 系统

MoocManus 是一个通用的 AI Agent 系统，支持完全私有化部署，使用 A2A + MCP 连接 Agent/Tool，同时支持在沙箱中运行各种内置工具和操作。

## 项目结构

```
mooc-manus/
├── api/              # 后端 API 服务（FastAPI）
├── web/              # 前端服务（Vue 3 + Vite）
├── sandbox/          # 沙箱服务（Ubuntu + Chrome + VNC）
├── docker/           # Docker 部署文件
│   ├── docker-compose.yml
│   ├── docker-compose.dev.yml
│   ├── init.sql
│   └── nginx/
│       ├── nginx.conf
│       └── conf.d/
│           └── default.conf
├── .env              # 环境变量配置
└── README.md
```

## 快速部署
```shell

cd docker
docker compose --env-file ../.env -f docker-compose.yml up -d --build


```

### 前置要求

- Docker >= 20.10
- Docker Compose >= 2.0

### 一键部署

1. **配置环境变量**

   项目根目录下的 `.env` 文件包含所有配置项，请根据实际情况修改：

   ```bash
   # 必须修改的配置
   COS_SECRET_ID=your_cos_secret_id_here       # 腾讯云 COS SecretId
   COS_SECRET_KEY=your_cos_secret_key_here     # 腾讯云 COS SecretKey
   COS_BUCKET=your_cos_bucket_here             # COS 存储桶名称

   # 可选修改
   POSTGRES_PASSWORD=postgres                   # 数据库密码
   NGINX_PORT=8088                              # 对外访问端口
   NGINX_BIND=0.0.0.0                            # 监听地址，本机访问可改为 127.0.0.1
   ```

2. **配置 AI 模型**

   修改 `api/config.yaml` 中的 LLM 配置：

   ```yaml
   llm_config:
     base_url: https://api.deepseek.com/
     api_key: your_api_key_here
     model_name: deepseek-v4-pro
   ```

3. **启动所有服务**

   ```bash
   cd docker
   docker compose --env-file ../.env -f docker-compose.yml up -d --build
   ```

4. **访问系统**

   打开浏览器访问 `http://your-server-ip:8088`

### 服务架构

```
                    ┌─────────────┐
     Port 8088      │   Nginx     │
   ─────────────────►  (Gateway)  │
                    └──────┬──────┘
                           │
              ┌────────────┴────────────┐
              │ /                       │ /api
              ▼                         ▼
       ┌─────────────┐          ┌─────────────┐
       │ Vue Web UI  │          │  FastAPI     │
       │  (Port 80)  │          │  (Port 8000) │
       └─────────────┘          └──────┬──────┘
                                       │
                    ┌──────────────────┼──────────────────┐
                    │                  │                   │
                    ▼                  ▼                   ▼
             ┌───────────┐     ┌───────────┐       ┌───────────┐
             │ PostgreSQL│     │   Redis   │       │  Sandbox  │
             │(Port 5432)│     │(Port 6379)│       │ (VNC/HTTP)│
             └───────────┘     └───────────┘       └───────────┘
```

### 容器列表

| 容器名称 | 服务 | 说明 |
|---------|------|------|
| manus-nginx | Nginx | 反向代理网关，唯一对外暴露端口 |
| manus-web | Vue 3 + Vite | 前端 Web 服务 |
| manus-api | FastAPI | 后端 API 服务 |
| manus-postgres | PostgreSQL | 数据库 |
| manus-redis | Redis | 缓存 |
| manus-sandbox | Sandbox | 沙箱环境（Chrome + VNC） |

### 常用命令

```bash
# 启动所有服务（后台运行）
cd docker
docker compose --env-file ../.env -f docker-compose.yml up -d --build

# 查看所有服务状态
docker compose --env-file ../.env -f docker-compose.yml ps

# 查看服务日志
docker compose --env-file ../.env -f docker-compose.yml logs -f              # 所有服务
docker compose --env-file ../.env -f docker-compose.yml logs -f manus-api    # 仅 API 服务
docker compose --env-file ../.env -f docker-compose.yml logs -f manus-web    # 仅 Web 前端服务

# 重启单个服务
docker compose --env-file ../.env -f docker-compose.yml restart manus-api

# 停止所有服务
docker compose --env-file ../.env -f docker-compose.yml down

# 停止并清除数据卷（谨慎操作）
docker compose --env-file ../.env -f docker-compose.yml down -v
```

### 启用 HTTPS

1. 将 SSL 证书放入 `docker/nginx/ssl/` 目录：
   - `fullchain.pem`（证书链）
   - `privkey.pem`（私钥）

2. 修改 `docker/nginx/conf.d/default.conf`，取消 SSL server 块注释

3. 修改 `docker/docker-compose.yml`，取消 443 端口映射注释

4. 重启 Nginx：
   ```bash
   docker compose --env-file ../.env -f docker-compose.yml restart manus-nginx
   ```

## 本地开发

如需只用 Docker 启动中间件，在本机调试 API 和 Web 前端：

`docker-compose.dev.yml` 是独立的本地开发入口，不需要和 `docker-compose.yml` 叠加。

```bash
# 只启动本地开发需要的 Redis/PostgreSQL，并暴露到 127.0.0.1
cd docker
docker compose --env-file ../.env -f docker-compose.dev.yml up -d

# 首次需要沙箱镜像时构建一次；API 动态创建沙箱容器时会使用该镜像
docker compose --env-file ../.env -f docker-compose.dev.yml build manus-sandbox

# API
cd ../api
cp .env.example .env
uv run alembic upgrade head
uv run uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload

# Web
cd ../web
pnpm install
pnpm dev
```

本地调试入口：

- API 文档：`http://localhost:8000/docs`
- Web：`http://localhost:5173`

各子项目的本地开发说明请参考对应目录下的 README：

- [API 服务](./api/README.md)
- [前端 Web](./web/README.md)
- [沙箱服务](./sandbox/README.md)
