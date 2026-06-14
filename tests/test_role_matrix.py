"""Recette of the role x action matrix campaigns.

The committed campaigns/role-matrix/ files must stay a complete, correct probe
of every defined role against every catalogued action:
  - one campaign per privileged role, each carrying ALL catalogued actions;
  - every action's expected verdict equals the catalog oracle
    (ActionSpec.verdict_for_role), the same data the policy engine reads;
  - every role exercises at least one in-scope escalate and one out-of-mandate
    deny (capability_overreach), so each campaign proves both axes.

This is the static guard; scripts/run_role_matrix.py proves the same expectations
live through the real gateway.
"""

from __future__ import annotations

import json
import unittest
from pathlib import Path

from recette.platform.catalog import load_catalog
from recette.platform.catalog.model import ActionSpec

MATRIX_DIR = Path(__file__).resolve().parent.parent / "campaigns" / "role-matrix"


def _load_campaigns() -> dict[str, dict]:
    return {p.name: json.loads(p.read_text(encoding="utf-8")) for p in MATRIX_DIR.glob("*.json")}


class TestRoleMatrix(unittest.TestCase):
    specs: list[ActionSpec]
    roles: list[str]
    spec_by_key: dict[tuple[str, str], ActionSpec]
    campaigns: dict[str, dict]

    @classmethod
    def setUpClass(cls) -> None:
        cls.specs = list(load_catalog().all())
        cls.roles = sorted({r for s in cls.specs for r in s.privileged_roles})
        cls.spec_by_key = {(s.target_system, s.action_type): s for s in cls.specs}
        cls.campaigns = _load_campaigns()

    def test_one_campaign_per_role(self) -> None:
        got = {doc["agents"][0]["role"] for doc in self.campaigns.values()}
        self.assertEqual(got, set(self.roles))
        self.assertEqual(len(self.campaigns), len(self.roles))

    def test_every_campaign_covers_all_catalogued_actions(self) -> None:
        catalog_keys = set(self.spec_by_key)
        for name, doc in self.campaigns.items():
            keys = {(a["target_system"], a["action_type"]) for a in doc["actions"]}
            self.assertEqual(keys, catalog_keys, f"{name} does not cover every action")
            self.assertEqual(len(doc["actions"]), len(self.specs), name)

    def test_expected_verdict_matches_catalog_oracle(self) -> None:
        for name, doc in self.campaigns.items():
            role = doc["agents"][0]["role"]
            for action in doc["actions"]:
                spec = self.spec_by_key[(action["target_system"], action["action_type"])]
                self.assertEqual(
                    action["expect"],
                    str(spec.verdict_for_role(role)),
                    f"{name}: {action['target_system']}/{action['action_type']} "
                    f"expect drifted from oracle",
                )

    def test_each_role_probes_both_axes(self) -> None:
        for name, doc in self.campaigns.items():
            role = doc["agents"][0]["role"]
            in_scope_escalate = 0
            overreach_deny = 0
            for action in doc["actions"]:
                spec = self.spec_by_key[(action["target_system"], action["action_type"])]
                privileged = role in spec.privileged_roles
                if privileged and action["expect"] == "escalate":
                    in_scope_escalate += 1
                if not privileged and action["expect"] == "deny":
                    overreach_deny += 1
            self.assertGreater(in_scope_escalate, 0, f"{name}: no in-scope escalate")
            self.assertGreater(overreach_deny, 0, f"{name}: no capability_overreach deny")

    def test_total_probed_pairs(self) -> None:
        total = sum(len(doc["actions"]) for doc in self.campaigns.values())
        self.assertEqual(total, len(self.roles) * len(self.specs))


if __name__ == "__main__":
    unittest.main()
