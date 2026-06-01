# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project overview

LLMOps is a full-stack AI application development platform. It is a monorepo with two main apps:

- `ui/` — Vue 3 SPA (Vite, TypeScript, Element Plus, Pinia, Vue Flow)
- `api/` — FastAPI service (SQLAlchemy 2.0, Alembic, Celery, LangChain/LangGraph, Weaviate)
- `docker/` — multi-service orchestration (PostgreSQL, Redis, Weaviate, Nginx)

## Commands

### UI (`cd ui`)

| Task | Command |
|------|---------|
| Install | `pnpm install` |
| Dev server | `pnpm dev` |
| Build | `pnpm build` |
| Type-check | `pnpm type-check` |
| Lint | `pnpm lint` |
| All tests | `pnpm test:unit` |
| Single test | `pnpm test:unit --run src/path/to/file.spec.ts` |

### API (`cd api`)

| Task | Command |
|------|---------|
| Install | `uv sync` |
| Dev server | `uv run uvicorn app.main:app --host 0.0.0.0 --port 5011 --reload` |
| All tests | `uv run pytest -q` |
| Single test | `uv run pytest test/path/to/test_file.py::ClassName::test_method` |
| DB migrations | `uv run alembic -c app/alembic/alembic.ini upgrade head` |
| Init DB (fresh) | `psql "postgresql://postgres:postgres@localhost:5432/llmops" -f scripts/init_schema.sql` |
| Seed dev account | `psql "postgresql://postgres:postgres@localhost:5432/llmops" -f scripts/seed_dev_account.sql` |

Default dev account: `dev@llmops.com` / `admin123`

### Full stack

```bash
docker compose -f docker/docker-compose.yaml up --build -d
```

## Architecture

### Backend request flow

The backend is the current FastAPI runtime. Routes are registered in `app/api/router.py`, request dependencies live in `app/api/deps.py`, and services own business logic.

1. **Routers** (`app/api/routers/*`) — map URLs to service calls
2. **Dependencies** (`app/api/deps.py`) — provide auth, sessions, tenants, and service instances
3. **Services** (`app/services/*`) — own business logic and persistence
4. **Response helpers** (`app/shared/response.py`) — normalize output to `{ code, message, data }` envelope
5. **Error handling** (`app/api/middleware.py`, `app/app_factory.py`) — converts custom exceptions to the shared envelope

### Workflow engine

- `app/core/workflow/` — compiles workflows into LangGraph `StateGraph`
- Node types: `start`, `llm`, `tool`, `dataset_retrieval`, `template_transform`, `http_request`, `code`, `end`
- Validation enforces: exactly one start/end, unique node IDs/titles, acyclic graph, valid variable references

### Agent execution

- `app/core/agent/` — queue/event primitives for streaming agent execution
- Queue-based event streaming via `AgentQueueManager`; consumed by SSE endpoints

### Frontend integration

- API clients: `ui/src/services/*.ts`
- Business hooks: `ui/src/hooks/use-*.ts`
- Type contracts: `ui/src/models/*.ts` — assume backend envelope `{ code, message, data }`
- `ui/src/utils/request.ts` — centralizes auth headers, business-code handling, SSE parsing
- Workflow editor: `ui/src/views/space/workflows/DetailView.vue` serializes graph to backend format via `convertGraphToReq`

## Key conventions

1. **Backend layering is strict**: routers validate + orchestrate; services execute business logic; schemas serialize/validate; response helpers format output.
2. **Use request-scoped SQLAlchemy sessions**: write through services and let FastAPI dependencies commit/rollback.
3. **Response envelope**: frontend assumes `code/message/data` and specific `httpCode` values (`success`, `validate_error`, `unauthorized`, etc.).
4. **Workflow node type strings must stay cross-layer consistent**: UI `type` values and backend `NodeType` enum must match exactly.
5. **Streaming is first-class**: backend returns generator-based SSE via `compact_generate_response`; frontend consumes via `ssePost()` expecting `event:`/`data:` frames.
6. **Auth is dependency-driven by route surface**: console/web routes use account access tokens; `openapi` routes use bearer API keys.
7. **Dependency injection**: `app/api/deps.py` wires request-scoped dependencies; prefer local service factories over global containers.
