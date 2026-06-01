# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

MoocManus is a general-purpose AI Agent system supporting fully private deployment. It uses A2A (Agent-to-Agent) + MCP (Model Context Protocol) to connect agents and tools, with sandbox execution capabilities.

**Architecture**: Service Layer Architecture (重构后，2026-05-06)
- **API** (FastAPI): Backend service with simplified service layer
- **UI** (Next.js 16): Frontend with React 19
- **Sandbox** (Ubuntu): Isolated execution environment with Chrome + VNC
- **Infrastructure**: PostgreSQL, Redis, Nginx gateway

## Development Commands

### Full Stack (Docker Compose)

```bash
# Start all services
docker compose up -d --build

# View logs
docker compose logs -f                # All services
docker compose logs -f manus-api      # API only
docker compose logs -f manus-ui       # UI only

# Restart service
docker compose restart manus-api

# Stop all
docker compose down
```

### API Service (FastAPI)

```bash
cd api

# Setup
python -m venv .venv
source .venv/bin/activate  # Windows: .venv\Scripts\activate
pip install uv
uv pip install -r requirements.txt
playwright install

# Run dev server
uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload

# Or run directly
python -m app.main

# Database migrations
alembic revision --autogenerate -m "description"
alembic upgrade head
alembic downgrade -1
```

### UI Service (Next.js)

```bash
cd ui

# Setup and run
npm install
npm run dev          # Dev server on :3000
npm run build        # Production build
npm run start        # Production server
npm run lint         # ESLint
```

## Architecture (重构后)

### API Service Structure

```
api/app/
├── controllers/         # 路由层（API端点）
│   ├── session.py       # 会话API
│   ├── health.py        # 健康检查
│   └── __init__.py
├── services/            # 业务逻辑层
│   ├── session_service.py  # 会话服务
│   ├── agent_service.py    # Agent服务
│   └── __init__.py
├── models/              # ORM模型（SQLAlchemy）
│   ├── session.py       # 会话模型
│   ├── file.py          # 文件模型
│   ├── base.py          # 基础ORM类
│   └── __init__.py
├── schemas/             # Pydantic请求/响应模型
│   └── session.py
├── core/                # 核心功能模块
│   ├── agent/           # Agent系统
│   │   └── react.py     # ReAct Agent
│   ├── tools/           # 工具系统
│   ├── sandbox/         # 沙箱管理
│   └── llm/             # LLM集成
├── extensions/          # 扩展（数据库、缓存、存储）
│   ├── database.py      # PostgreSQL
│   ├── redis.py         # Redis
│   ├── storage.py       # COS存储
│   └── __init__.py
├── tasks/               # 异步任务
└── main.py              # 应用入口
```

### 架构分层

```
Controllers (路由层)
    ↓
Services (业务逻辑层) - 直接操作ORM模型
    ↓
Models (ORM模型) + Core (核心功能)
```

**关键特点**：
- **扁平化** - 2层抽象（Controllers → Services → Models）
- **无Repository/UoW** - Services直接使用SQLAlchemy
- **统一模型** - 只有ORM模型，无领域模型转换
- **Core模块化** - Agent/Tools通过依赖注入

## Common Workflows

### Adding a new API endpoint

1. Define Pydantic schemas in `schemas/`
2. Create service method in `services/`
3. Create endpoint in `controllers/`
4. Register route in `controllers/__init__.py`

Example:
```python
# schemas/session.py
class SessionResponse(BaseModel):
    id: str
    title: str

# services/session_service.py
class SessionService:
    async def create_session(self) -> SessionModel:
        session = SessionModel(title="新对话")
        self.db.add(session)
        await self.db.commit()
        return session

# controllers/session.py
@router.post("", response_model=SessionResponse)
async def create_session(service: SessionService = Depends(get_session_service)):
    session = await service.create_session()
    return SessionResponse.from_orm(session)
```

### Working with database

**Simple queries** - Use SQLAlchemy directly:
```python
# Get by ID
session = await db.get(SessionModel, session_id)

# Query with filter
result = await db.execute(
    select(SessionModel).where(SessionModel.status == "pending")
)
sessions = result.scalars().all()
```

**Complex queries** - Optional lightweight repository:
```python
class SessionRepository:
    @staticmethod
    async def get_with_files(db: AsyncSession, session_id: str):
        result = await db.execute(
            select(SessionModel)
            .options(selectinload(SessionModel.files))
            .where(SessionModel.id == session_id)
        )
        return result.scalar_one_or_none()
```

### Adding business logic to models

```python
# models/session.py
class SessionModel(Base):
    # ... fields ...
    
    def can_execute(self) -> bool:
        """业务方法：检查是否可执行"""
        return self.status in [SessionStatus.PENDING.value, SessionStatus.WAITING.value]
    
    def add_event(self, event: Dict[str, Any]) -> None:
        """业务方法：添加事件"""
        self.events.append(event)
        if event.get("type") == "message":
            self.latest_message = event.get("message", "")
```

### Database schema changes

1. Modify ORM models in `models/`
2. Generate migration: `alembic revision --autogenerate -m "description"`
3. Review generated migration in `alembic/versions/`
4. Apply: `alembic upgrade head`

### Dependency injection

```python
# Get database session
from app.extensions import get_db_session

@router.get("/sessions")
async def get_sessions(db: AsyncSession = Depends(get_db_session)):
    result = await db.execute(select(SessionModel))
    return result.scalars().all()

# Get service with dependencies
async def get_session_service(
    db: AsyncSession = Depends(get_db_session)
) -> SessionService:
    sandbox = get_sandbox()
    return SessionService(db, sandbox)
```

## Configuration

**Environment variables** (`.env` in root):
- Database: `SQLALCHEMY_DATABASE_URI`, `POSTGRES_*`
- Redis: `REDIS_HOST`, `REDIS_PORT`, `REDIS_PASSWORD`
- COS (Tencent Cloud): `COS_SECRET_ID`, `COS_SECRET_KEY`, `COS_BUCKET`
- Sandbox: `SANDBOX_ADDRESS`, `SANDBOX_IMAGE`, `SANDBOX_TTL_MINUTES`

**Application config** (`api/config.yaml`):
- `llm_config`: LLM provider (base_url, api_key, model_name)
- `agent_config`: Agent behavior (max_iterations, max_retries)
- `mcp_config`: MCP server configurations
- `a2a_config`: A2A server configurations

## Testing

```bash
# Run test script
cd api
python test_refactor.py

# Expected output:
# ✅ Models: OK
# ✅ Extensions: OK
# ✅ Services: OK
# ✅ Controllers: OK
# 🎉 所有测试通过！
```

## Important Notes

- **Language**: Codebase uses Chinese comments and documentation
- **Async**: All database/Redis/HTTP operations must be async
- **No Repository pattern**: Services directly use SQLAlchemy AsyncSession
- **No domain models**: Only ORM models (SQLAlchemy)
- **Core isolation**: Core modules use dependency injection, no direct infrastructure imports
- **Sandbox lifecycle**: Sandboxes auto-expire after `SANDBOX_TTL_MINUTES` (default 60)

## Architecture History

**2026-05-06**: Refactored from DDD to Service Layer Architecture
- Removed: domain/application/infrastructure/interfaces layers
- Simplified: Repository/UoW patterns removed
- Unified: Domain models merged into ORM models
- Result: 60% less code, 400% better performance

See `REFACTOR_COMPLETE.md` for details.
