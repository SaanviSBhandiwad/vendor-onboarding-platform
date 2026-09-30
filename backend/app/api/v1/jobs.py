import uuid
from typing import Annotated

from fastapi import APIRouter, Query

from app.api.deps import CurrentUser, DbSession, StaffUser
from app.models import JobStatus
from app.schemas.common import error_responses
from app.schemas.document import JobList, JobRead
from app.services import job_service

router = APIRouter(prefix="/jobs", tags=["jobs"])


@router.get("", response_model=JobList)
def list_jobs(
    db: DbSession,
    _: StaffUser,
    status: JobStatus | None = None,
    limit: Annotated[int, Query(ge=1, le=100)] = 20,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> JobList:
    """Staff view of background work, e.g. `?status=FAILED`."""
    items, total = job_service.list_jobs(db, status=status, limit=limit, offset=offset)
    return JobList(items=items, total=total, limit=limit, offset=offset)


@router.get("/{job_id}", response_model=JobRead, responses=error_responses(404))
def get_job(job_id: uuid.UUID, db: DbSession, user: CurrentUser) -> JobRead:
    """Poll this after uploading a document to see when processing finishes."""
    return job_service.get_job_for_user(db, job_id, user)
