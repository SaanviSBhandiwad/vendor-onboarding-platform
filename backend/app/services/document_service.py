import hashlib
import logging
import uuid
from collections.abc import Callable
from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.exceptions import (
    DocumentsLockedError,
    DuplicateDocumentError,
    NotFoundError,
    ServiceUnavailableError,
)
from app.models import (
    REQUIRED_DOCUMENT_TYPES,
    DocumentType,
    Job,
    JobStatus,
    JobType,
    User,
    Vendor,
    VendorDocument,
    VendorStatus,
)
from app.services import audit_service, permissions, vendor_service
from app.services.file_inspection import detect_kind, safe_display_name
from app.services.state_machine import assert_transition
from app.services.storage import LocalStorage

logger = logging.getLogger(__name__)

# Documents can be added or replaced until review starts.
UPLOAD_ALLOWED_STATUSES = frozenset({VendorStatus.PENDING, VendorStatus.DOCUMENTS_SUBMITTED})

JobQueue = Callable[[uuid.UUID], None]


def uploaded_types(db: Session, vendor_id: uuid.UUID) -> set[DocumentType]:
    stmt = select(VendorDocument.document_type).where(VendorDocument.vendor_id == vendor_id).distinct()
    return set(db.scalars(stmt))


def missing_required_types(db: Session, vendor_id: uuid.UUID) -> list[DocumentType]:
    return sorted(REQUIRED_DOCUMENT_TYPES - uploaded_types(db, vendor_id))


def _maybe_mark_submitted(db: Session, vendor: Vendor, user: User) -> None:
    if vendor.status != VendorStatus.PENDING or not REQUIRED_DOCUMENT_TYPES <= uploaded_types(db, vendor.id):
        return
    assert_transition(vendor.status, VendorStatus.DOCUMENTS_SUBMITTED)
    vendor.status = VendorStatus.DOCUMENTS_SUBMITTED
    vendor.status_changed_at = datetime.now(UTC)
    audit_service.record(
        db, entity_type=vendor_service.ENTITY, entity_id=vendor.id, action="status_changed",
        actor=permissions.actor_id(user),
        details={
            "from": VendorStatus.PENDING.value, "to": VendorStatus.DOCUMENTS_SUBMITTED.value,
            "reason": "All required documents uploaded", "automatic": True, "role": user.role.value,
        },
    )


def create_document(
    db: Session,
    storage: LocalStorage,
    *,
    vendor_id: uuid.UUID,
    user: User,
    document_type: DocumentType,
    filename: str | None,
    data: bytes,
) -> tuple[VendorDocument, Job]:
    # Row lock on the vendor serializes concurrent uploads for the same application.
    vendor = vendor_service.get_vendor_for_user(db, vendor_id, user, for_update=True)
    if vendor.status not in UPLOAD_ALLOWED_STATUSES:
        raise DocumentsLockedError(
            f"Documents cannot be changed while the application is {vendor.status.value}",
            details={"status": vendor.status.value},
        )

    kind = detect_kind(data)
    sha256 = hashlib.sha256(data).hexdigest()
    existing = db.scalars(
        select(VendorDocument.id).where(VendorDocument.vendor_id == vendor.id, VendorDocument.sha256 == sha256)
    ).first()
    if existing:
        raise DuplicateDocumentError("This file has already been uploaded", details={"document_id": str(existing)})

    document_id = uuid.uuid4()
    # Storage key is generated, never derived from the user's filename.
    key = f"vendors/{vendor.id}/{document_id}{kind.extension}"
    storage.save(key, data)

    try:
        document = VendorDocument(
            id=document_id, vendor_id=vendor.id, uploaded_by_id=user.id, document_type=document_type,
            original_filename=safe_display_name(filename, f"{document_type.value.lower()}{kind.extension}"),
            content_type=kind.content_type, size_bytes=len(data), sha256=sha256, storage_key=key,
        )
        job = Job(job_type=JobType.DOCUMENT_PROCESSING, status=JobStatus.QUEUED, vendor_id=vendor.id,
                  document_id=document_id)
        db.add_all([document, job])
        db.flush()
        audit_service.record(
            db, entity_type=vendor_service.ENTITY, entity_id=vendor.id, action="document_uploaded",
            actor=permissions.actor_id(user),
            details={"document_id": str(document_id), "document_type": document_type.value,
                     "size_bytes": len(data), "sha256": sha256, "job_id": str(job.id)},
        )
        _maybe_mark_submitted(db, vendor, user)
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        storage.delete(key)  # compensate: no orphaned file without a database row
        raise DuplicateDocumentError("This file has already been uploaded") from exc
    except BaseException:
        db.rollback()
        storage.delete(key)
        raise

    db.refresh(document)
    db.refresh(job)
    logger.info("document_uploaded", extra={"document_id": str(document_id), "job_id": str(job.id)})
    return document, job


def dispatch(db: Session, job: Job, enqueue: JobQueue) -> None:
    """Hand the job to the queue *after* commit, so the worker always finds the rows."""
    try:
        enqueue(job.id)
    except Exception as exc:
        logger.exception("enqueue_failed", extra={"job_id": str(job.id)})
        job.status = JobStatus.FAILED
        job.error = f"Could not enqueue job: {type(exc).__name__}"
        job.finished_at = datetime.now(UTC)
        db.commit()
        raise ServiceUnavailableError(
            "The processing queue is unavailable. The document is saved; processing failed to start.",
            details={"job_id": str(job.id)},
        ) from exc


def list_documents(db: Session, vendor_id: uuid.UUID, user: User) -> list[VendorDocument]:
    vendor_service.get_vendor_for_user(db, vendor_id, user)
    stmt = (
        select(VendorDocument)
        .where(VendorDocument.vendor_id == vendor_id)
        .order_by(VendorDocument.created_at, VendorDocument.id)
    )
    return list(db.scalars(stmt))


def get_document_for_user(db: Session, document_id: uuid.UUID, user: User) -> VendorDocument:
    document = db.get(VendorDocument, document_id)
    if document is None:
        raise NotFoundError("Document not found", details={"document_id": str(document_id)})
    try:
        vendor_service.get_vendor_for_user(db, document.vendor_id, user)
    except NotFoundError:
        raise NotFoundError("Document not found", details={"document_id": str(document_id)}) from None
    return document
