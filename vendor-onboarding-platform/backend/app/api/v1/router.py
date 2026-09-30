from fastapi import APIRouter

from app.api.v1 import auth, users, vendors
from app.schemas.common import error_responses

# 401/403/422 can come from any endpoint; declaring them here documents the real
# error envelope in Swagger instead of FastAPI's default {"detail": ...} shape.
api_router = APIRouter(prefix="/api/v1", responses=error_responses(401, 403, 422))
api_router.include_router(auth.router)
api_router.include_router(users.router)
api_router.include_router(vendors.router)
