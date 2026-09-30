"""Authorization rules in one place, so they are easy to review and test.

Checks run in this order for vendor operations:
  1. authenticated?                   -> 401
  2. allowed to *see* this vendor?    -> 404 (not 403, so IDs of other vendors are not revealed)
  3. role allowed to do this action?  -> 403
  4. valid state transition?          -> 409
"""

from app.core.exceptions import ForbiddenError, NotFoundError
from app.models import User, UserRole, Vendor, VendorStatus

STAFF_ROLES = frozenset({UserRole.OPERATIONS, UserRole.ADMIN})

# Vendors may only hand their application over for review. Every decision
# (approve, reject, send back, manual review) is made by staff or the system.
VENDOR_ALLOWED_TARGETS = frozenset({VendorStatus.DOCUMENTS_SUBMITTED})


def is_staff(user: User) -> bool:
    return user.role in STAFF_ROLES


def can_view_vendor(user: User, vendor: Vendor) -> bool:
    return is_staff(user) or (vendor.owner_id is not None and vendor.owner_id == user.id)


def assert_can_view_vendor(user: User, vendor: Vendor) -> None:
    if not can_view_vendor(user, vendor):
        raise NotFoundError("Vendor not found", details={"vendor_id": str(vendor.id)})


def assert_can_set_status(user: User, target: VendorStatus) -> None:
    if is_staff(user):
        return
    if target not in VENDOR_ALLOWED_TARGETS:
        raise ForbiddenError(
            f"Your role cannot move an application to {target.value}",
            details={"role": user.role.value, "allowed_targets": sorted(s.value for s in VENDOR_ALLOWED_TARGETS)},
        )


def actor_id(user: User) -> str:
    """Stable identifier written to the audit log (emails can change, ids cannot)."""
    return f"user:{user.id}"
