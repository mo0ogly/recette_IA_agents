"""resolution_denied: audited containment signal (I1 immutable, I4 deterministic).

A private-DNS resolution that is denied (name not in the declared allowlist) is
recorded as a first-class AUDITED event. The builder is pure: the captured
timestamp is an INJECTED input (never read from the host clock), so replay
reproduces the event byte for byte (I4); the dataclass is frozen (I1).
"""

from __future__ import annotations

import dataclasses
import unittest

from recette.platform.events import EventKind, build_resolution_denied


class TestResolutionDeniedEvent(unittest.TestCase):
    def test_carries_name_and_agent_and_reason(self) -> None:
        evt = build_resolution_denied(
            agent_id="agent-1", name="evil.com", reason="not_in_allowlist"
        )
        self.assertEqual(evt.agent_id, "agent-1")
        self.assertEqual(evt.name, "evil.com")
        self.assertEqual(evt.reason, "not_in_allowlist")

    def test_kind_is_the_resolution_denied_discriminator(self) -> None:
        evt = build_resolution_denied(agent_id="x", name="n", reason="r")
        self.assertEqual(evt.kind, EventKind.RESOLUTION_DENIED)

    def test_timestamp_is_an_injected_input(self) -> None:
        # No wall clock inside the builder: default is None, an explicit value is
        # carried verbatim (I4 captured input).
        self.assertIsNone(build_resolution_denied(agent_id="x", name="n", reason="r").timestamp)
        ts = "2026-06-15T00:00:00Z"
        self.assertEqual(
            build_resolution_denied(agent_id="x", name="n", reason="r", timestamp=ts).timestamp,
            ts,
        )

    def test_is_deterministic_given_inputs(self) -> None:
        a = build_resolution_denied(agent_id="x", name="n", reason="r")
        b = build_resolution_denied(agent_id="x", name="n", reason="r")
        self.assertEqual(a, b)

    def test_to_dict_is_byte_stable(self) -> None:
        a = build_resolution_denied(agent_id="x", name="n", reason="r", timestamp="T").to_dict()
        b = build_resolution_denied(agent_id="x", name="n", reason="r", timestamp="T").to_dict()
        self.assertEqual(a, b)
        self.assertEqual(a["kind"], EventKind.RESOLUTION_DENIED)
        self.assertEqual(a["name"], "n")
        self.assertEqual(a["agent_id"], "x")
        self.assertEqual(a["reason"], "r")

    def test_event_is_immutable(self) -> None:
        evt = build_resolution_denied(agent_id="x", name="n", reason="r")
        with self.assertRaises(dataclasses.FrozenInstanceError):
            evt.name = "changed"  # type: ignore[misc]  # frozen dataclass (I1)


if __name__ == "__main__":
    unittest.main()
