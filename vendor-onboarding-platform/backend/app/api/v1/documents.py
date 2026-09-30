import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, File, Form, UploadFile, status
from fastapi.responses import FileResponse

from app.api.deps import CurrentUser, DbSession
from app.core.config import get_settings
from app.models import REQUIRED_DOCUMENT_TYPES, DocumentType
from app.schemas.common import ErrorResponse, error_responses
from app.schemas.document import DocumentList, DocumentRead, DocumentUploadResponse
from app.services import document_service
from app.services.document_service import JobQueue
from app.services.file_inspection import read_limited
from app.services.queue import get_job_queue
from app.services.storage import LocalStorage, get_storage

router = APIRouter(tags=["documents"])

Storage = Annotated[LocalStorage, Depends(get_storage)]
Queue = Annotated[JobQueue, Depends(get_job_queue)]


def get_max_upload_bytes() -> int:
    return get_settings().max_upload_bytes


@router.post(
    "/vendors/{vendor_id}/documents",
    response_model=DocumentUploadResponse,
    status_code=status.HTTP_202_ACCEPTED,
    responses={
        **error_responses(404, 409),
        400: {"model": ErrorResponse, "description": "Empty file"},
        413: {"model": ErrorResponse, "description": "File too large"},
        415: {"model": ErrorResponse, "description": "Not a PDF, PNG or JPEG"},
        503: {"model": ErrorResponse, "description": "Queue unavailable"},
    },
)
def upload_document(
    vendor_id: uuid.UUID,
    db: DbSession,
    user: CurrentUser,
    storage: Storage,
    queue: Queue,
    max_bytes: Annotated[int, Depends(get_max_upload_bytes)],
    document_type: Annotated[DocumentType, Form()],
    file: Annotated[UploadFile, File(description="PDF, PNG or JPEG")],
) -> DocumentUploadResponse:
    """Store the file and queue it for processing. Returns **202**: processing happens in the background."""
    data = read_limited(file, max_bytes)
    document, job = document_service.create_document(
        db, storage, vendor_id=vendor_id, user=user, document_type=document_type,
        filename=file.filename, data=data,
    )
    document_service.dispatch(db, job, queue)
    db.refresh(job)
    return DocumentUploadResponse(document=document, job=job)


@router.get("/vendors/{vendor_id}/documents", response_model=DocumentList, responses=error_responses(404))
def list_documents(vendor_id: uuid.UUID, db: DbSession, user: CurrentUser) -> DocumentList:
    items = document_service.list_documents(db, vendor_id, user)
    return DocumentList(
        items=items,
        required_types=sorted(REQUIRED_DOCUMENT_TYPES),
        missing_types=document_service.missing_required_types(db, vendor_id),
    )


@router.get("/documents/{document_id}", response_model=DocumentRead, responses=error_responses(404))
def get_document(document_id: uuid.UUID, db: DbSession, user: CurrentUser) -> DocumentRead:
    return document_service.get_document_for_user(db, document_id, user)


@router.get(
    "/documents/{document_id}/file",
    response_class=FileResponse,
    responses={200: {"content": {"application/pdf": {}, "image/png": {}, "image/jpeg": {}}},
               **error_responses(404)},
)
def download_document(document_id: uuid.UUID, db: DbSession, user: CurrentUser, storage: Storage) -> FileResponse:
    document = document_service.get_document_for_user(db, document_id, user)
    return FileResponse(
        storage.path(document.storage_key),
        media_type=document.content_type,
        filename=document.original_filename,
        headers={"X-Content-Type-Options": "nosniff"},
    )
