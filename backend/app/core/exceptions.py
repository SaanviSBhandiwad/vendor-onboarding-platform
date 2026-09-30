"""Domain errors mapped to a single, consistent JSON error envelope."""

import logging
from typing import Any

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

from app.core.logging import request_id_ctx

logger = logging.getLogger(__name__)


class AppError(Exception):
    status_code = 400
    code = "bad_request"
    headers: dict[str, str] | None = None

    def __init__(self, message: str, details: dict[str, Any] | None = None):
        super().__init__(message)
        self.message = message
        self.details = details or {}


class UnauthorizedError(AppError):
    status_code = 401
    code = "not_authenticated"
    headers = {"WWW-Authenticate": "Bearer"}


class ForbiddenError(AppError):
    status_code = 403
    code = "forbidden"


class NotFoundError(AppError):
    status_code = 404
    code = "not_found"


class ConflictError(AppError):
    status_code = 409
    code = "conflict"


class DuplicateVendorError(ConflictError):
    code = "duplicate_vendor"


class VendorProfileExistsError(ConflictError):
    code = "vendor_profile_exists"


class DuplicateUserError(ConflictError):
    code = "duplicate_user"


class SelfLockoutError(ConflictError):
    code = "self_lockout"


class InvalidTransitionError(ConflictError):
    code = "invalid_state_transition"


class DuplicateDocumentError(ConflictError):
    code = "duplicate_document"


class DocumentsLockedError(ConflictError):
    code = "documents_locked"


class EmptyFileError(AppError):
    status_code = 400
    code = "empty_file"


class FileTooLargeError(AppError):
    status_code = 413
    code = "file_too_large"


class UnsupportedFileTypeError(AppError):
    status_code = 415
    code = "unsupported_file_type"


class ServiceUnavailableError(AppError):
    status_code = 503
    code = "service_unavailable"


def _envelope(
    status: int, code: str, message: str, details: Any = None, headers: dict[str, str] | None = None
) -> JSONResponse:
    return JSONResponse(
        status_code=status,
        headers=headers,
        content={
            "error": {
                "code": code,
                "message": message,
                "details": details or {},
                "request_id": request_id_ctx.get(),
            }
        },
    )


def register_exception_handlers(app: FastAPI) -> None:
    @app.exception_handler(AppError)
    async def handle_app_error(_: Request, exc: AppError) -> JSONResponse:
        return _envelope(exc.status_code, exc.code, exc.message, exc.details, exc.headers)

    @app.exception_handler(RequestValidationError)
    async def handle_validation(_: Request, exc: RequestValidationError) -> JSONResponse:
        errors = [
            {"field": ".".join(str(p) for p in e["loc"][1:]), "message": e["msg"]}
            for e in exc.errors()
        ]
        return _envelope(422, "validation_error", "Request validation failed", {"errors": errors})

    @app.exception_handler(StarletteHTTPException)
    async def handle_http(_: Request, exc: StarletteHTTPException) -> JSONResponse:
        # Framework-level errors (unknown route, wrong method) use the same envelope.
        code = {404: "not_found", 405: "method_not_allowed"}.get(exc.status_code, "http_error")
        return _envelope(exc.status_code, code, str(exc.detail), headers=getattr(exc, "headers", None))

    @app.exception_handler(Exception)
    async def handle_unexpected(_: Request, exc: Exception) -> JSONResponse:
        logger.exception("unhandled_error")
        return _envelope(500, "internal_error", "An unexpected error occurred")
