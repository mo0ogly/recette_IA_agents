"""Approval plane (I6): pending actions block until resolved or timeout.

This Python state machine persisted in the event store is a PLACEHOLDER for a
Temporal durable workflow; ApprovalService is the interface Temporal would
replace. Timeout never auto-approves (failure-modes.md).
"""

from .service import ApprovalService, PendingApproval
from .state_machine import ApprovalAction, InvalidTransition, transition

__all__ = [
    "ApprovalAction",
    "ApprovalService",
    "InvalidTransition",
    "PendingApproval",
    "transition",
]
