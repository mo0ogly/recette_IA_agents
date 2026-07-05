"""AGENT_ADMISSION event kind: additive record type for the runtime admission
verdict, audited at agent launch (I1 immutable log, I3 identity-bound).

This is a pure enum-membership guard. It asserts the new member exists with its
canonical value, is a distinct (non-aliasing) StrEnum member that round-trips as
its string value, and -- critically for an ADDITIVE change (I1, no destructive
migration) -- that the seven pre-existing kinds are untouched (same names, same
values). A renumber/rename regression turns this test red.
"""

from __future__ import annotations

import unittest

from recette.platform.events import EventKind


class TestAgentAdmissionEventKind(unittest.TestCase):
    def test_member_exists_with_canonical_value(self) -> None:
        self.assertEqual(EventKind.AGENT_ADMISSION, "agent_admission")
        self.assertEqual(EventKind.AGENT_ADMISSION.value, "agent_admission")

    def test_is_a_distinct_member_not_an_alias(self) -> None:
        # A distinct member owns its value; it does not alias any existing kind.
        self.assertEqual(EventKind.AGENT_ADMISSION.name, "AGENT_ADMISSION")
        others = [k for k in EventKind if k is not EventKind.AGENT_ADMISSION]
        self.assertNotIn(EventKind.AGENT_ADMISSION.value, [k.value for k in others])

    def test_round_trips_as_a_str_enum(self) -> None:
        self.assertIsInstance(EventKind.AGENT_ADMISSION, str)
        self.assertEqual(str(EventKind.AGENT_ADMISSION), "agent_admission")
        self.assertIs(EventKind("agent_admission"), EventKind.AGENT_ADMISSION)

    def test_existing_kinds_are_unaffected(self) -> None:
        # The addition is additive (I1): the seven pre-existing kinds keep their
        # exact names and values. A renumber/rename regression fails here.
        expected = {
            "ACTION_REQUESTED": "action_requested",
            "ACTION_EXECUTED": "action_executed",
            "ACTION_DENIED": "action_denied",
            "APPROVAL_RESOLVED": "approval_resolved",
            "PLATFORM_ERROR": "platform_error",
            "BYPASS_DETECTED": "bypass_detected",
            "RESOLUTION_DENIED": "resolution_denied",
        }
        for name, value in expected.items():
            self.assertEqual(EventKind[name].value, value)


if __name__ == "__main__":
    unittest.main()
