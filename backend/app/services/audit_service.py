import uuid
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.logging import request_id_ctx
from app.models import AuditLog


def record(
    db: Session,
    *,
    entity_type: str,
    entity_id: uuid.UUID,
    action: str,
    actor: str,
    details: dict[str, Any] | None = None,
) -> AuditLog:
    """Add an audit entry to the current transaction (committed together with the change)."""
    entry = AuditLog(
        entity_type=entity_type,
        entity_id=entity_id,
        action=action,
        actor=actor,
        details=details or {},
        request_id=request_id_ctx.get(),
    )
    db.add(entry)
    return entry


def list_for_entity(db: Session, entity_type: str, entity_id: uuid.UUID) -> list[AuditLog]:
    stmt = (
        select(AuditLog)
        .where(AuditLog.entity_type == entity_type, AuditLog.entity_id == entity_id)
        .order_by(AuditLog.id)
    )
    return list(db.scalars(stmt))
