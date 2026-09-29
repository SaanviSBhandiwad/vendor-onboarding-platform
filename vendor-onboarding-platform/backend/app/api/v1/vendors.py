import uuid
from typing import Annotated

from fastapi import APIRouter, Query, status

from app.api.deps import Actor, DbSession
from app.models import VendorStatus
from app.schemas.vendor import (
    AuditLogRead,
    StatusTransitionRequest,
    VendorCreate,
    VendorList,
    VendorRead,
)
from app.services import audit_service, vendor_service

router = APIRouter(prefix="/vendors", tags=["vendors"])


@router.post("", response_model=VendorRead, status_code=status.HTTP_201_CREATED)
def register_vendor(payload: VendorCreate, db: DbSession, actor: Actor) -> VendorRead:
    return vendor_service.create_vendor(db, payload, actor)


@router.get("", response_model=VendorList)
def list_vendors(
    db: DbSession,
    status_filter: Annotated[VendorStatus | None, Query(alias="status")] = None,
    region: str | None = None,
    limit: Annotated[int, Query(ge=1, le=100)] = 20,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> VendorList:
    items, total = vendor_service.list_vendors(
        db, status=status_filter, region=region, limit=limit, offset=offset
    )
    return VendorList(items=items, total=total, limit=limit, offset=offset)


@router.get("/{vendor_id}", response_model=VendorRead)
def get_vendor(vendor_id: uuid.UUID, db: DbSession) -> VendorRead:
    return vendor_service.get_vendor(db, vendor_id)


@router.post("/{vendor_id}/status", response_model=VendorRead)
def change_status(
    vendor_id: uuid.UUID, payload: StatusTransitionRequest, db: DbSession, actor: Actor
) -> VendorRead:
    return vendor_service.transition_status(
        db, vendor_id, payload.to_status, actor=actor, reason=payload.reason
    )


@router.get("/{vendor_id}/audit-logs", response_model=list[AuditLogRead])
def get_audit_logs(vendor_id: uuid.UUID, db: DbSession) -> list[AuditLogRead]:
    vendor_service.get_vendor(db, vendor_id)  # 404 if missing
    return audit_service.list_for_entity(db, vendor_service.ENTITY, vendor_id)
