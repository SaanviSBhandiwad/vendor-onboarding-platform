import uuid
from typing import Annotated

from fastapi import APIRouter, Query, status

from app.api.deps import CurrentUser, DbSession, StaffUser, VendorUser
from app.core.exceptions import NotFoundError
from app.models import VendorStatus
from app.schemas.common import error_responses
from app.schemas.vendor import AuditLogRead, StatusTransitionRequest, VendorCreate, VendorList, VendorRead
from app.services import audit_service, vendor_service

router = APIRouter(prefix="/vendors", tags=["vendors"])


@router.post("", response_model=VendorRead, status_code=status.HTTP_201_CREATED, responses=error_responses(409))
def register_vendor(payload: VendorCreate, db: DbSession, user: VendorUser) -> VendorRead:
    """Vendor users create their (single) application."""
    return vendor_service.create_vendor(db, payload, owner=user)


@router.get("", response_model=VendorList)
def list_vendors(
    db: DbSession,
    user: CurrentUser,
    status_filter: Annotated[VendorStatus | None, Query(alias="status")] = None,
    region: str | None = None,
    limit: Annotated[int, Query(ge=1, le=100)] = 20,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> VendorList:
    """Staff see all applications; vendors see only their own."""
    items, total = vendor_service.list_vendors_for_user(
        db, user, status=status_filter, region=region, limit=limit, offset=offset
    )
    return VendorList(items=items, total=total, limit=limit, offset=offset)


@router.get("/me", response_model=VendorRead, responses=error_responses(404))
def my_vendor(db: DbSession, user: VendorUser) -> VendorRead:
    vendor = vendor_service.get_vendor_by_owner(db, user.id)
    if vendor is None:
        raise NotFoundError("You have not submitted a vendor application yet")
    return vendor


@router.get("/{vendor_id}", response_model=VendorRead, responses=error_responses(404))
def get_vendor(vendor_id: uuid.UUID, db: DbSession, user: CurrentUser) -> VendorRead:
    return vendor_service.get_vendor_for_user(db, vendor_id, user)


@router.post("/{vendor_id}/status", response_model=VendorRead, responses=error_responses(404, 409))
def change_status(
    vendor_id: uuid.UUID, payload: StatusTransitionRequest, db: DbSession, user: CurrentUser
) -> VendorRead:
    return vendor_service.transition_status(db, vendor_id, payload.to_status, user=user, reason=payload.reason)


@router.get("/{vendor_id}/audit-logs", response_model=list[AuditLogRead], responses=error_responses(404))
def get_audit_logs(vendor_id: uuid.UUID, db: DbSession, user: StaffUser) -> list[AuditLogRead]:
    vendor_service.get_vendor_for_user(db, vendor_id, user)  # 404 if missing
    return audit_service.list_for_entity(db, vendor_service.ENTITY, vendor_id)
