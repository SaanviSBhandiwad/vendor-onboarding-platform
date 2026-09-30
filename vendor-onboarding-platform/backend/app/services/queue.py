import uuid

from app.core.logging import request_id_ctx
from app.services.document_service import JobQueue


def enqueue_document_processing(job_id: uuid.UUID) -> None:
    from app.workers.tasks import process_document  # imported lazily: the API doesn't need Celery at import time

    # Celery task id = job id, so a job can be traced in Celery tooling and in the database with one id.
    process_document.apply_async(
        args=[str(job_id)], kwargs={"request_id": request_id_ctx.get()}, task_id=str(job_id)
    )


def get_job_queue() -> JobQueue:
    return enqueue_document_processing
