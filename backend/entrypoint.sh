#!/bin/sh
# One image, two roles:  ./entrypoint.sh api  |  ./entrypoint.sh worker
set -e

case "${1:-api}" in
  api)
    alembic upgrade head
    exec uvicorn app.main:app --host 0.0.0.0 --port 8000
    ;;
  worker)
    exec celery -A app.workers.celery_app worker --loglevel="${LOG_LEVEL:-INFO}" --concurrency="${WORKER_CONCURRENCY:-2}"
    ;;
  *)
    exec "$@"
    ;;
esac
