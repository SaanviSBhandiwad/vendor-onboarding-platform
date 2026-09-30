import pytest

from app.core.exceptions import InvalidTransitionError
from app.models import VendorStatus as S
from app.services.state_machine import (
    ALLOWED_TRANSITIONS,
    TERMINAL_STATES,
    assert_transition,
    can_transition,
)


def test_every_status_has_a_transition_rule():
    assert set(ALLOWED_TRANSITIONS) == set(S)


def test_terminal_states():
    assert TERMINAL_STATES == {S.APPROVED, S.REJECTED}


@pytest.mark.parametrize(
    ("current", "target"),
    [
        (S.PENDING, S.DOCUMENTS_SUBMITTED),
        (S.DOCUMENTS_SUBMITTED, S.UNDER_REVIEW),
        (S.UNDER_REVIEW, S.MANUAL_REVIEW),
        (S.UNDER_REVIEW, S.APPROVED),
        (S.MANUAL_REVIEW, S.REJECTED),
        (S.UNDER_REVIEW, S.PENDING),
    ],
)
def test_valid_transitions(current, target):
    assert can_transition(current, target)
    assert_transition(current, target)


@pytest.mark.parametrize(
    ("current", "target"),
    [
        (S.PENDING, S.APPROVED),          # cannot skip compliance
        (S.PENDING, S.UNDER_REVIEW),
        (S.APPROVED, S.PENDING),          # terminal
        (S.REJECTED, S.APPROVED),         # terminal
        (S.PENDING, S.PENDING),           # no self-loops
    ],
)
def test_invalid_transitions(current, target):
    assert not can_transition(current, target)
    with pytest.raises(InvalidTransitionError) as exc:
        assert_transition(current, target)
    assert exc.value.details["current_status"] == current.value
