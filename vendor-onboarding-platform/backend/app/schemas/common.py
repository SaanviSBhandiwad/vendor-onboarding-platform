from typing import Any

from pydantic import BaseModel


class ErrorBody(BaseModel):
    code: str
    message: str
    details: dict[str, Any]
    request_id: str | None


class ErrorResponse(BaseModel):
    """Shape of every error returned by the API."""

    error: ErrorBody


def error_responses(*codes: int) -> dict[int | str, dict[str, Any]]:
    descriptions = {
        401: "Missing, invalid or expired token",
        403: "Authenticated but not allowed",
        404: "Resource not found",
        409: "Conflict with current state",
        422: "Request validation failed",
    }
    return {c: {"model": ErrorResponse, "description": descriptions[c]} for c in codes}
