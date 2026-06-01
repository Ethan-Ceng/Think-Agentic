# LLMOps API

FastAPI service for the LLMOps Agent Platform.

## Local Startup

```bash
cd api
uv sync
uv run uvicorn app.main:app --host 0.0.0.0 --port 5011 --reload
```

## Health Checks

```text
GET /healthz
GET /readyz
GET /ping
```

## Database Migrations

```bash
cd api
uv run alembic upgrade head
```

## Tests

```bash
cd api
uv run pytest -q
uv run ruff check app tests
```
