#!/usr/bin/env bash
set -euo pipefail

if [[ "${MIGRATION_ENABLED:-false}" == "true" ]]; then
  alembic upgrade head
fi

if [[ "${MODE:-api}" == "celery" ]]; then
  exec celery -A app.main.celery_app worker --loglevel="${CELERY_LOG_LEVEL:-INFO}" --concurrency="${CELERY_WORKER_AMOUNT:-2}"
fi

exec uvicorn app.main:app --host 0.0.0.0 --port "${PORT:-5001}" --workers "${SERVER_WORKER_AMOUNT:-1}"
