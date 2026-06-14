"""Approval state machine (I6): only PENDING is transitionable.

Pure transition function -- no clock, no I/O. Timeout is an explicit action
whose reference time is captured at the API boundary, never read here.
"""

from __future__ import annotations

from enum import StrEnum

from ..events import ApprovalState


class ApprovalAction(StrEnum):
    APPROVE = "approve"
    DENY = "deny"
    TIMEOUT = "timeout"


class InvalidTransition(ValueError):
    """Raised on any transition from a non-pending state."""


_RESULT: dict[ApprovalAction, ApprovalState] = {
    ApprovalAction.APPROVE: ApprovalState.APPROVED,
    ApprovalAction.DENY: ApprovalState.DENIED,
    ApprovalAction.TIMEOUT: ApprovalState.TIMEOUT,
}


def transition(current: ApprovalState, action: ApprovalAction) -> ApprovalState:
    if current is not ApprovalState.PENDING:
        raise InvalidTransition(f"cannot {action} from state {current!r} (only pending)")
    return _RESULT[action]
