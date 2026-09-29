"""Vendor onboarding state machine: the only place allowed transitions are defined."""

from app.core.exceptions import InvalidTransitionError
from app.models.vendor import VendorStatus as S

ALLOWED_TRANSITIONS: dict[S, frozenset[S]] = {
    S.PENDING: frozenset({S.DOCUMENTS_SUBMITTED, S.REJECTED}),
    S.DOCUMENTS_SUBMITTED: frozenset({S.UNDER_REVIEW, S.PENDING}),
    S.UNDER_REVIEW: frozenset({S.APPROVED, S.REJECTED, S.MANUAL_REVIEW, S.PENDING}),
    S.MANUAL_REVIEW: frozenset({S.APPROVED, S.REJECTED, S.PENDING}),
    S.APPROVED: frozenset(),
    S.REJECTED: frozenset(),
}

TERMINAL_STATES = frozenset(s for s, nxt in ALLOWED_TRANSITIONS.items() if not nxt)


def can_transition(current: S, target: S) -> bool:
    return target in ALLOWED_TRANSITIONS[current]


def assert_transition(current: S, target: S) -> None:
    if not can_transition(current, target):
        raise InvalidTransitionError(
            f"Cannot move vendor from {current.value} to {target.value}",
            details={
                "current_status": current.value,
                "requested_status": target.value,
                "allowed": sorted(s.value for s in ALLOWED_TRANSITIONS[current]),
            },
        )
