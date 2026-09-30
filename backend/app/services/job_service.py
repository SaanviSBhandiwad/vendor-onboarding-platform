import uuid

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.exceptions import NotFoundError
from app.models import Job, JobStatus, User
from app.services import vendor_service


def get_job_for_user(db: Session, job_id: uuid.UUID, user: User) -> Job:
    job = db.get(Job, job_id)
    if job is None:
        raise NotFoundError("Job not found", details={"job_id": str(job_id)})
    try:
        vendor_service.get_vendor_for_user(db, job.vendor_id, user)
    except NotFoundError:
        raise NotFoundError("Job not found", details={"job_id": str(job_id)}) from None
    return job


def list_jobs(
    db: Session, *, status: JobStatus | None = None, limit: int = 20, offset: int = 0
) -> tuple[list[Job], int]:
    filters = [Job.status == status] if status else []
    total = db.scalar(select(func.count()).select_from(Job).where(*filters)) or 0
    stmt = select(Job).where(*filters).order_by(Job.created_at.desc(), Job.id).limit(limit).offset(offset)
    return list(db.scalars(stmt)), total
