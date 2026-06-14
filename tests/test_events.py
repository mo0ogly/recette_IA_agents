"""Unit tests for the canonical event helpers in recette.events.

Locks the shared ``scenario_action_entry`` builder (the single source of truth
for a scenario.json action step, used by both the promote path and the red-team
freezer): the entry always carries action+resource, and the optional approved/
params keys appear ONLY when truthy, so the frozen JSON stays byte-stable.
"""

from __future__ import annotations

import unittest

from recette.events import scenario_action_entry


class ScenarioActionEntryTests(unittest.TestCase):
    def test_minimal_entry_has_only_action_and_resource(self) -> None:
        entry = scenario_action_entry(action="read_repo", resource="acme/widgets")
        self.assertEqual(entry, {"action": "read_repo", "resource": "acme/widgets"})

    def test_approved_included_only_when_true(self) -> None:
        # Falsy approved is omitted entirely (not approved=False) so the shape
        # matches the legacy hand-built entry byte-for-byte.
        self.assertNotIn("approved", scenario_action_entry(action="push", resource="r"))
        self.assertNotIn(
            "approved", scenario_action_entry(action="push", resource="r", approved=False)
        )
        self.assertEqual(
            scenario_action_entry(action="push", resource="r", approved=True),
            {"action": "push", "resource": "r", "approved": True},
        )

    def test_params_included_only_when_truthy(self) -> None:
        # Empty/None params are omitted; a non-empty dict is carried verbatim.
        self.assertNotIn("params", scenario_action_entry(action="a", resource="r", params=None))
        self.assertNotIn("params", scenario_action_entry(action="a", resource="r", params={}))
        entry = scenario_action_entry(action="a", resource="r", params={"title": "fix"})
        self.assertEqual(entry["params"], {"title": "fix"})

    def test_full_entry_key_order_is_stable(self) -> None:
        # action, resource, approved, params -- the order the builder emits, so
        # json.dumps produces a deterministic document (I4).
        entry = scenario_action_entry(
            action="open_pr", resource="acme/widgets", approved=True, params={"branch": "main"}
        )
        self.assertEqual(list(entry.keys()), ["action", "resource", "approved", "params"])


if __name__ == "__main__":
    unittest.main()
