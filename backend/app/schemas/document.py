import uuid
from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict

from app.models import DocumentStatus, DocumentType, JobStatus, JobType


class DocumentRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    vendor_id: uuid.UUID
    document_type: DocumentType
    status: DocumentStatus
    original_filename: str
    content_type: str
    size_bytes: int
    sha256: str
    page_count: int | None
    extracted_chars: int | None
    created_at: datetime
    updated_at: datetime


class JobRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    job_type: JobType
    status: JobStatus
    vendor_id: uuid.UUID
    document_id: uuid.UUID | None
    attempts: int
    error: str | None
    result: dict[str, Any] | None
    created_at: datetime
    started_at: datetime | None
    finished_at: datetime | None


class DocumentUploadResponse(BaseModel):
    document: DocumentRead
    job: JobRead


class DocumentList(BaseModel):
    items: list[DocumentRead]
    required_types: list[DocumentType]
    missing_types: list[DocumentType]


class JobList(BaseModel):
    items: list[JobRead]
    total: int
    limit: int
    offset: int
