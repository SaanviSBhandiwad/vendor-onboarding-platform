import uuid

from app.core.database import SessionLocal
from app.core.logging import request_id_ctx
from app.services import document_processing
from app.services.storage import get_storage
from app.workers.celery_app import celery_app


@celery_app.task(name="documents.process")
def process_document(job_id: str, request_id: str | None = None) -> None:
    # Carry the API request's id into the worker, so one id links the upload request,
    # the worker's logs and the audit entries it writes.
    token = request_id_ctx.set(request_id)
    try:
        with SessionLocal() as db:
            document_processing.run_job(db, get_storage(), uuid.UUID(job_id))
    finally:
        request_id_ctx.reset(token)
