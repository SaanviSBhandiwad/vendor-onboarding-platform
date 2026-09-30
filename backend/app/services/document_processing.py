"""What a worker does for one DOCUMENT_PROCESSING job. Plain function: easy to test without Celery."""

import hashlib
import logging
import uuid
from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import DocumentStatus, Job, JobStatus, VendorDocument
from app.services import audit_service, vendor_service
from app.services.storage import LocalStorage
from app.services.text_extraction import extract_text

logger = logging.getLogger(__name__)
WORKER_ACTOR = "system:document_worker"


def run_job(db: Session, storage: LocalStorage, job_id: uuid.UUID) -> None:
    # Lock the job row and only proceed from QUEUED: if the broker delivers the same
    # message twice, the second delivery sees RUNNING/SUCCEEDED and does nothing.
    job = db.scalars(select(Job).where(Job.id == job_id).with_for_update()).first()
    if job is None:
        logger.warning("job_not_found", extra={"job_id": str(job_id)})
        return
    if job.status != JobStatus.QUEUED:
        logger.info("job_skipped", extra={"job_id": str(job_id), "status": job.status.value})
        return

    document = db.get(VendorDocument, job.document_id)
    job.status = JobStatus.RUNNING
    job.attempts += 1
    job.started_at = datetime.now(UTC)
    document.status = DocumentStatus.PROCESSING
    db.commit()
    logger.info("job_started", extra={"job_id": str(job_id), "document_id": str(document.id)})

    try:
        data = storage.read(document.storage_key)
        if hashlib.sha256(data).hexdigest() != document.sha256:
            raise ValueError("Stored file does not match its checksum")
        result = extract_text(data, document.content_type)
    except Exception as exc:
        _fail(db, job, document, exc)
        return

    document.extracted_text = result.text
    document.extracted_chars = len(result.text)
    document.page_count = result.page_count
    document.status = DocumentStatus.PROCESSED
    job.status = JobStatus.SUCCEEDED
    job.finished_at = datetime.now(UTC)
    job.result = {
        "page_count": result.page_count,
        "characters": len(result.text),
        "method": result.method,
        "needs_ocr": result.needs_ocr,
    }
    audit_service.record(
        db, entity_type=vendor_service.ENTITY, entity_id=job.vendor_id, action="document_processed",
        actor=WORKER_ACTOR, details={"document_id": str(document.id), "job_id": str(job.id), **job.result},
    )
    db.commit()
    duration_ms = round((job.finished_at - job.started_at).total_seconds() * 1000, 1)
    logger.info("job_succeeded", extra={"job_id": str(job_id), "duration_ms": duration_ms})


def _fail(db: Session, job: Job, document: VendorDocument, exc: Exception) -> None:
    # Retries with backoff and a dead-letter queue arrive in Phase 4.
    logger.exception("job_failed", extra={"job_id": str(job.id)})
    job.status = JobStatus.FAILED
    job.error = f"{type(exc).__name__}: {exc}"[:2000]
    job.finished_at = datetime.now(UTC)
    document.status = DocumentStatus.FAILED
    audit_service.record(
        db, entity_type=vendor_service.ENTITY, entity_id=job.vendor_id, action="document_processing_failed",
        actor=WORKER_ACTOR, details={"document_id": str(document.id), "job_id": str(job.id), "error": job.error},
    )
    db.commit()
