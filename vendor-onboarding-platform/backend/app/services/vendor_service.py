import logging
import uuid
from datetime import UTC, datetime

from sqlalchemy import func, or_, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.exceptions import DuplicateVendorError, NotFoundError
from app.models import Vendor, VendorStatus
from app.schemas.vendor import VendorCreate
from app.services import audit_service
from app.services.state_machine import assert_transition

logger = logging.getLogger(__name__)
ENTITY = "vendor"


def find_duplicate_fields(db: Session, email: str, gstin: str) -> list[str]:
    stmt = select(Vendor.email, Vendor.gstin).where(
        or_(Vendor.email == email, Vendor.gstin == gstin)
    )
    fields: set[str] = set()
    for row_email, row_gstin in db.execute(stmt):
        if row_email == email:
            fields.add("email")
        if row_gstin == gstin:
            fields.add("gstin")
    return sorted(fields)


def create_vendor(db: Session, data: VendorCreate, actor: str) -> Vendor:
    # 1) Fast, friendly check that tells the client *which* field collides.
    duplicates = find_duplicate_fields(db, data.email, data.gstin)
    if duplicates:
        raise DuplicateVendorError(
            "A vendor with these details already exists", details={"fields": duplicates}
        )

    vendor = Vendor(**data.model_dump(), status=VendorStatus.PENDING)
    db.add(vendor)
    try:
        db.flush()  # assigns id, surfaces constraint violations
        audit_service.record(
            db, entity_type=ENTITY, entity_id=vendor.id, action="vendor_created",
            actor=actor, details={"status": vendor.status.value},
        )
        db.commit()
    except IntegrityError as exc:
        # 2) Safety net: two concurrent requests can both pass the check above;
        #    the unique constraint guarantees only one insert succeeds.
        db.rollback()
        logger.warning("duplicate_vendor_race", extra={"email": data.email})
        raise DuplicateVendorError(
            "A vendor with these details already exists", details={"fields": []}
        ) from exc

    db.refresh(vendor)
    logger.info("vendor_created", extra={"vendor_id": str(vendor.id)})
    return vendor


def get_vendor(db: Session, vendor_id: uuid.UUID, *, for_update: bool = False) -> Vendor:
    stmt = select(Vendor).where(Vendor.id == vendor_id)
    if for_update:
        stmt = stmt.with_for_update()  # row lock so concurrent transitions serialize
    vendor = db.scalars(stmt).first()
    if vendor is None:
        raise NotFoundError("Vendor not found", details={"vendor_id": str(vendor_id)})
    return vendor


def list_vendors(
    db: Session,
    *,
    status: VendorStatus | None = None,
    region: str | None = None,
    limit: int = 20,
    offset: int = 0,
) -> tuple[list[Vendor], int]:
    filters = []
    if status is not None:
        filters.append(Vendor.status == status)
    if region is not None:
        filters.append(Vendor.region == region.strip().lower())

    total = db.scalar(select(func.count()).select_from(Vendor).where(*filters)) or 0
    stmt = (
        select(Vendor)
        .where(*filters)
        .order_by(Vendor.created_at.desc(), Vendor.id)
        .limit(limit)
        .offset(offset)
    )
    return list(db.scalars(stmt)), total


def transition_status(
    db: Session, vendor_id: uuid.UUID, to_status: VendorStatus, *, actor: str, reason: str | None
) -> Vendor:
    vendor = get_vendor(db, vendor_id, for_update=True)
    from_status = vendor.status
    assert_transition(from_status, to_status)

    vendor.status = to_status
    vendor.status_changed_at = datetime.now(UTC)
    audit_service.record(
        db, entity_type=ENTITY, entity_id=vendor.id, action="status_changed", actor=actor,
        details={"from": from_status.value, "to": to_status.value, "reason": reason},
    )
    db.commit()
    db.refresh(vendor)
    logger.info(
        "vendor_status_changed",
        extra={"vendor_id": str(vendor.id), "from": from_status.value, "to": to_status.value},
    )
    return vendor
