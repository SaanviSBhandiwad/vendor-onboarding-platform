from celery import Celery, signals

from app.core.config import get_settings
from app.core.logging import configure_logging

settings = get_settings()

celery_app = Celery("vendor_onboarding", broker=settings.redis_url, include=["app.workers.tasks"])
celery_app.conf.update(
    task_serializer="json",
    accept_content=["json"],
    timezone="UTC",
    # Job state lives in PostgreSQL; Celery's result backend is not needed.
    task_ignore_result=True,
    # Acknowledge only after the task finishes: a worker crash puts the message back on the queue.
    task_acks_late=True,
    task_reject_on_worker_lost=True,
    # One message at a time per worker process, so long jobs don't hold others hostage.
    worker_prefetch_multiplier=1,
    broker_connection_retry_on_startup=True,
    # Fail fast if Redis is down, so the API can report it instead of hanging.
    task_publish_retry_policy={"max_retries": 2, "interval_start": 0, "interval_step": 0.2},
)


@signals.setup_logging.connect
def _use_json_logging(**_: object) -> None:
    configure_logging(settings.log_level)
