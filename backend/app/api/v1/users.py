import uuid
from typing import Annotated

from fastapi import APIRouter, Query, status

from app.api.deps import AdminUser, DbSession
from app.models import UserRole
from app.schemas.common import error_responses
from app.schemas.user import UserCreate, UserList, UserRead, UserUpdate
from app.services import permissions, user_service

router = APIRouter(prefix="/users", tags=["users (admin)"])


@router.post("", response_model=UserRead, status_code=status.HTTP_201_CREATED, responses=error_responses(409))
def create_user(payload: UserCreate, db: DbSession, admin: AdminUser) -> UserRead:
    return user_service.create_user(db, payload, actor=permissions.actor_id(admin))


@router.get("", response_model=UserList)
def list_users(
    db: DbSession,
    _: AdminUser,
    role: UserRole | None = None,
    limit: Annotated[int, Query(ge=1, le=100)] = 20,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> UserList:
    items, total = user_service.list_users(db, role=role, limit=limit, offset=offset)
    return UserList(items=items, total=total, limit=limit, offset=offset)


@router.patch("/{user_id}", response_model=UserRead, responses=error_responses(404, 409))
def update_user(user_id: uuid.UUID, payload: UserUpdate, db: DbSession, admin: AdminUser) -> UserRead:
    return user_service.update_user(db, user_id, payload, current=admin, actor=permissions.actor_id(admin))
