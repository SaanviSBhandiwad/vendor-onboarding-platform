import re
import uuid
from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, EmailStr, Field, field_validator

from app.models.vendor import VendorStatus

# Indian GSTIN: 2-digit state code, 10-char PAN, entity number, 'Z', checksum char.
GSTIN_PATTERN = re.compile(r"^[0-9]{2}[A-Z]{5}[0-9]{4}[A-Z][1-9A-Z]Z[0-9A-Z]$")


class VendorCreate(BaseModel):
    legal_name: str = Field(min_length=2, max_length=255)
    email: EmailStr
    gstin: str = Field(description="15-character GST identification number")
    contact_phone: str | None = Field(default=None, pattern=r"^\+?[0-9]{7,15}$")
    region: str = Field(min_length=2, max_length=64)
    service_type: str = Field(min_length=2, max_length=64)

    @field_validator("legal_name", mode="before")
    @classmethod
    def strip_name(cls, v: Any) -> Any:
        return " ".join(v.split()) if isinstance(v, str) else v

    @field_validator("email")
    @classmethod
    def normalize_email(cls, v: str) -> str:
        # Normalizing before storage is what makes the unique constraint meaningful.
        return v.strip().lower()

    @field_validator("gstin", mode="before")
    @classmethod
    def normalize_gstin(cls, v: Any) -> Any:
        return v.strip().upper() if isinstance(v, str) else v

    @field_validator("gstin")
    @classmethod
    def validate_gstin(cls, v: str) -> str:
        if not GSTIN_PATTERN.match(v):
            raise ValueError("Invalid GSTIN format")
        return v

    @field_validator("region", "service_type", mode="before")
    @classmethod
    def normalize_category(cls, v: Any) -> Any:
        # Consistent categories matter later as ML features.
        return "_".join(v.strip().lower().split()) if isinstance(v, str) else v


class VendorRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    legal_name: str
    email: str
    gstin: str
    contact_phone: str | None
    region: str
    service_type: str
    status: VendorStatus
    status_changed_at: datetime
    created_at: datetime
    updated_at: datetime


class VendorList(BaseModel):
    items: list[VendorRead]
    total: int
    limit: int
    offset: int


class StatusTransitionRequest(BaseModel):
    to_status: VendorStatus
    reason: str | None = Field(default=None, max_length=500)


class AuditLogRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    entity_type: str
    entity_id: uuid.UUID
    action: str
    actor: str
    details: dict[str, Any]
    request_id: str | None
    created_at: datetime
