#!/bin/sh
set -e

echo "==> Running database migrations..."
alembic upgrade head

echo "==> Starting Celery background worker..."
celery -A worker.celery_app worker --loglevel=info --pool=solo &

echo "==> Starting FastAPI Uvicorn server on port ${PORT:-8000}..."
exec uvicorn main:app --host 0.0.0.0 --port "${PORT:-8000}"
