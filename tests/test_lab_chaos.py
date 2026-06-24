"""Tests for the deterministic mock-lab fault injection (recette/lab/chaos.py).

Proves the resilience-recette property the lab was missing: an INFRA fault layer
that is OFF by default, configurable per system, and PURE (I4) -- the same logical
event always faults identically, so a chaos run is replayable. See
.claude/rules/failure-modes.md (the agent must freeze/retry on a 429/503/504,
never execute optimistically).
"""

from __future__ import annotations

import unittest

from recette.lab import chaos


class TestChaosLoading(unittest.TestCase):
    def test_off_by_default(self) -> None:
        # No env value -> no policy -> the lab serves 200 as before.
        self.assertIsNone(chaos.load_policy(""))
        self.assertIsNone(chaos.load_policy(None if False else ""))

    def test_malformed_disables_not_crashes(self) -> None:
        # A bad config must fall back to OFF (the lab must still serve), never raise.
        self.assertIsNone(chaos.load_policy("{not json"))
        self.assertIsNone(chaos.load_policy("/no/such/chaos/file.json"))
        self.assertIsNone(chaos.load_policy('{"systems": {}}'))
        self.assertIsNone(chaos.load_policy('{"systems": {"okta": {"error_rate": 0}}}'))

    def test_inline_json_loads(self) -> None:
        pol = chaos.load_policy('{"seed":"s","systems":{"okta":{"error_rate":1.0}}}')
        self.assertIsNotNone(pol)
        assert pol is not None
        self.assertEqual(pol.seed, "s")
        self.assertIn("okta", pol.systems)

    def test_error_rate_clamped(self) -> None:
        pol = chaos.policy_from_dict({"systems": {"okta": {"error_rate": 5}}})
        assert pol is not None
        self.assertEqual(pol.systems["okta"].error_rate, 1.0)


class TestChaosDecision(unittest.TestCase):
    def test_rate_zero_never_faults(self) -> None:
        pol = chaos.policy_from_dict({"systems": {"*": {"error_rate": 0}}})
        self.assertIsNone(pol)  # an all-zero policy disables entirely

    def test_rate_one_always_faults(self) -> None:
        pol = chaos.policy_from_dict(
            {"seed": "s", "systems": {"okta": {"error_rate": 1.0, "statuses": [503]}}}
        )
        assert pol is not None
        for i in range(50):
            fault = pol.fault_for("okta", "suspend_user", f"evt-{i}")
            self.assertIsNotNone(fault)
            assert fault is not None
            self.assertEqual(fault[0], 503)

    def test_deterministic_same_event_same_decision(self) -> None:
        # I4: identical (seed, event_id, target, action) -> identical decision.
        pol = chaos.policy_from_dict(
            {"seed": "rec", "systems": {"finance": {"error_rate": 0.5, "statuses": [429, 503]}}}
        )
        assert pol is not None
        a = pol.fault_for("finance", "create_payment", "evt-42")
        b = pol.fault_for("finance", "create_payment", "evt-42")
        self.assertEqual(a, b)

    def test_partial_rate_splits_events(self) -> None:
        # A 0.5 rate must fault SOME events and pass OTHERS (not all-or-nothing),
        # and the split is stable across calls.
        pol = chaos.policy_from_dict(
            {"seed": "rec", "systems": {"okta": {"error_rate": 0.5, "statuses": [503]}}}
        )
        assert pol is not None
        results = [pol.fault_for("okta", "read_org_directory", f"evt-{i}") for i in range(200)]
        faulted = sum(1 for r in results if r is not None)
        self.assertGreater(faulted, 0)
        self.assertLess(faulted, 200)
        # re-run is identical (determinism over the whole batch)
        again = [pol.fault_for("okta", "read_org_directory", f"evt-{i}") for i in range(200)]
        self.assertEqual(results, again)

    def test_wildcard_default_applies(self) -> None:
        pol = chaos.policy_from_dict(
            {"seed": "s", "systems": {"*": {"error_rate": 1.0, "statuses": [504]}}}
        )
        assert pol is not None
        fault = pol.fault_for("any_system", "any_action", "evt-1")
        self.assertIsNotNone(fault)
        assert fault is not None
        self.assertEqual(fault[0], 504)

    def test_unconfigured_system_passes_through(self) -> None:
        pol = chaos.policy_from_dict({"seed": "s", "systems": {"okta": {"error_rate": 1.0}}})
        assert pol is not None
        self.assertIsNone(pol.fault_for("finance", "create_payment", "evt-1"))

    def test_status_chosen_from_configured_set(self) -> None:
        pol = chaos.policy_from_dict(
            {"seed": "s", "systems": {"okta": {"error_rate": 1.0, "statuses": [429, 503, 504]}}}
        )
        assert pol is not None
        seen = {pol.fault_for("okta", "a", f"e-{i}")[0] for i in range(100)}  # type: ignore[index]
        self.assertTrue(seen <= {429, 503, 504})


if __name__ == "__main__":
    unittest.main()
