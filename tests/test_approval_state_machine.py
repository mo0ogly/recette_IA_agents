"""I6: full transition matrix -- only PENDING is transitionable, timeout never approves."""

from __future__ import annotations

import unittest

from recette.platform.approvals.state_machine import (
    ApprovalAction,
    InvalidTransition,
    transition,
)
from recette.platform.events import ApprovalState


class TestApprovalStateMachine(unittest.TestCase):
    def test_pending_transitions(self) -> None:
        self.assertIs(
            transition(ApprovalState.PENDING, ApprovalAction.APPROVE), ApprovalState.APPROVED
        )
        self.assertIs(transition(ApprovalState.PENDING, ApprovalAction.DENY), ApprovalState.DENIED)
        self.assertIs(
            transition(ApprovalState.PENDING, ApprovalAction.TIMEOUT), ApprovalState.TIMEOUT
        )

    def test_non_pending_states_reject_every_action(self) -> None:
        for state in (
            ApprovalState.NONE,
            ApprovalState.APPROVED,
            ApprovalState.DENIED,
            ApprovalState.TIMEOUT,
        ):
            for action in ApprovalAction:
                with self.assertRaises(InvalidTransition):
                    transition(state, action)

    def test_timeout_never_yields_approved(self) -> None:
        self.assertIsNot(
            transition(ApprovalState.PENDING, ApprovalAction.TIMEOUT), ApprovalState.APPROVED
        )


if __name__ == "__main__":
    unittest.main()
