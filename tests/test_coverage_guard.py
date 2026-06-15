"""Coverage guard -- the single gate that makes a recette gap impossible to hide.

Every dimension of "is the corpus fully wired" is asserted here. Add a new role,
action, domain, or campaign agent that is NOT fully covered and THIS suite turns
red -- no manual hunting required. The known, deliberate exceptions are frozen in
explicit constants below: they cannot grow silently (the assertion pins the set
exactly), and closing one without updating the constant also fails.

Dimensions guarded:
  D1 every catalogued action is exercised by a coverage campaign
  D2 every catalogued action is handled by its lab server (I5 proxy)
  D3 every privileged role is probed over every catalogued action (role-matrix)
  D4 every domain has a catalog module + a lab handler + a coverage campaign
  D5 every corpus identification enum action is exercised, except the frozen set
  D6 no campaign action without an expected verdict; no orphan declared agent
  D7 every red-team violation_type has a corpus scenario (anti-silence gate)
  D8 every git red-team violation_type has a corpus git scenario
"""

from __future__ import annotations

import importlib
import json
import unittest
from collections import defaultdict
from pathlib import Path

from recette.lab.domains import HANDLER_MODULES
from recette.lab.errors import LabActionError
from recette.platform.catalog import load_catalog
from recette.platform.catalog.model import ActionSpec

REPO = Path(__file__).resolve().parent.parent
CAMPAIGNS = REPO / "campaigns"

# D5: corpus enum verbs declared in scenario.schema but not yet exercised by any
# ground-truth agent. Frozen so the gap cannot grow and cannot be closed silently.
# To exercise one: add it to a corpus agent scenario AND remove it from here.
# Currently empty: every enum verb is exercised by at least one corpus agent.
RESERVED_UNEXERCISED: frozenset[str] = frozenset()

# Red-team violation_types not yet exercised by any corpus scenario
# (corpus/sim/*.scenario.json). Frozen so the gap cannot grow and cannot be
# closed silently: add a scenario for one AND remove it here, or this fails.
REDTEAM_PENDING_VIOLATIONS: frozenset[str] = frozenset(
    {"identity_mismatch", "policy_violation", "behavior_anomaly"}
)

ALL_VIOLATION_TYPES: frozenset[str] = frozenset(
    {"identity_mismatch", "capability_overreach", "policy_violation", "behavior_anomaly"}
)

# Git red-team violation_types not yet exercised by a corpus git scenario
# (corpus/sim/*.git-scenario.json). Frozen so the gap cannot grow / close silently.
GIT_REDTEAM_PENDING_VIOLATIONS: frozenset[str] = frozenset(
    {"identity_mismatch", "policy_violation", "behavior_anomaly"}
)


def _campaign_action_keys(globpat: str) -> set[tuple[str, str]]:
    keys: set[tuple[str, str]] = set()
    for path in CAMPAIGNS.glob(globpat):
        doc = json.loads(path.read_text(encoding="utf-8"))
        for action in doc.get("actions", []):
            keys.add((action["target_system"], action["action_type"]))
    return keys


class TestCoverageGuard(unittest.TestCase):
    specs: list[ActionSpec]
    spec_keys: set[tuple[str, str]]
    domains: list[str]
    roles: list[str]

    @classmethod
    def setUpClass(cls) -> None:
        cls.specs = list(load_catalog().all())
        cls.spec_keys = {(s.target_system, s.action_type) for s in cls.specs}
        cls.domains = sorted({s.target_system for s in cls.specs})
        cls.roles = sorted({r for s in cls.specs for r in s.privileged_roles})

    def test_d1_every_action_in_a_coverage_campaign(self) -> None:
        covered = _campaign_action_keys("coverage/*.json")
        missing = self.spec_keys - covered
        self.assertEqual(missing, set(), f"catalogued actions with no coverage campaign: {missing}")

    def test_d2_every_action_handled_by_lab_server(self) -> None:
        # A handler has three outcomes (recette/lab/errors.py): a dict (success),
        # None (unknown action -> unhandled), or a raised LabActionError (a known
        # action rejecting the probe input -- still HANDLED). Only None counts as
        # an unhandled action here.
        missing: list[tuple[str, str]] = []
        for domain in self.domains:
            mod = importlib.import_module(f"recette.lab.domains.{HANDLER_MODULES[domain]}")
            for spec in self.specs:
                if spec.target_system != domain:
                    continue
                try:
                    handled = mod.handle(spec.action_type, "x/x", {}) is not None
                except LabActionError:
                    handled = True
                if not handled:
                    missing.append((domain, spec.action_type))
        self.assertEqual(missing, [], f"catalogued actions no lab server handles: {missing}")

    def test_d3_every_role_probed_over_every_action(self) -> None:
        by_role: dict[str, set[tuple[str, str]]] = defaultdict(set)
        for path in (CAMPAIGNS / "role-matrix").glob("*.json"):
            doc = json.loads(path.read_text(encoding="utf-8"))
            role = doc["agents"][0]["role"]
            for action in doc["actions"]:
                by_role[role].add((action["target_system"], action["action_type"]))
        self.assertEqual(set(by_role), set(self.roles), "role-matrix roles drifted from catalog")
        for role in self.roles:
            missing = self.spec_keys - by_role[role]
            self.assertEqual(missing, set(), f"role {role} not probed over: {missing}")

    def test_d4_every_domain_has_catalog_lab_and_coverage(self) -> None:
        coverage_domains = {
            json.loads(p.read_text(encoding="utf-8"))["agents"][0]["capability_scope"][0]
            for p in (CAMPAIGNS / "coverage").glob("*.json")
        }
        for domain in self.domains:
            self.assertIn(domain, HANDLER_MODULES, f"{domain}: no lab handler registered")
            self.assertIn(domain, coverage_domains, f"{domain}: no coverage campaign")

    def test_d5_corpus_enum_fully_exercised_except_frozen(self) -> None:
        schema = json.loads(
            (REPO / "corpus" / "schemas" / "scenario.schema.json").read_text(encoding="utf-8")
        )
        enum = set(schema["properties"]["actions"]["items"]["properties"]["action"]["enum"])
        used: set[str] = set()
        for scenario in (REPO / "corpus" / "agents").glob("*/*/scenario.json"):
            for action in json.loads(scenario.read_text(encoding="utf-8"))["actions"]:
                used.add(action["action"])
        unexercised = enum - used
        # Pinned exactly: a new unexercised verb fails; exercising a frozen one
        # without removing it from RESERVED_UNEXERCISED also fails.
        self.assertEqual(
            unexercised,
            set(RESERVED_UNEXERCISED),
            f"corpus enum coverage drift: unexercised={sorted(unexercised)}, "
            f"frozen={sorted(RESERVED_UNEXERCISED)}",
        )

    def test_d7_redteam_violation_type_coverage(self) -> None:
        covered: set[str] = set()
        for path in (REPO / "corpus" / "sim").glob("*.scenario.json"):
            doc = json.loads(path.read_text(encoding="utf-8"))
            violation = doc.get("expected", {}).get("violation_type")
            if violation is not None:
                covered.add(violation)
        # Every non-pending violation type must have at least one scenario
        # (this bites if the overreach scenario is removed).
        required = ALL_VIOLATION_TYPES - REDTEAM_PENDING_VIOLATIONS
        self.assertTrue(
            required <= covered,
            f"red-team violation_types with no scenario: {sorted(required - covered)}",
        )
        # Adding a scenario for a pending type without removing it from the
        # frozen set fails: forces an explicit constant update, no silent closure.
        self.assertEqual(
            REDTEAM_PENDING_VIOLATIONS & covered,
            frozenset(),
            "pending violation_type now covered -- remove it from "
            f"REDTEAM_PENDING_VIOLATIONS: {sorted(REDTEAM_PENDING_VIOLATIONS & covered)}",
        )
        # Sanity: every pending name is a real violation type (catches a typo).
        self.assertTrue(
            REDTEAM_PENDING_VIOLATIONS <= ALL_VIOLATION_TYPES,
            "REDTEAM_PENDING_VIOLATIONS holds an unknown violation_type: "
            f"{sorted(REDTEAM_PENDING_VIOLATIONS - ALL_VIOLATION_TYPES)}",
        )

    def test_d8_git_redteam_violation_type_coverage(self) -> None:
        covered: set[str] = set()
        for path in (REPO / "corpus" / "sim").glob("*.git-scenario.json"):
            doc = json.loads(path.read_text(encoding="utf-8"))
            violation = doc.get("expected", {}).get("violation_type")
            if violation is not None:
                covered.add(violation)
        # Every non-pending violation type must have at least one git scenario
        # (this bites if the git overreach seed is removed).
        required = ALL_VIOLATION_TYPES - GIT_REDTEAM_PENDING_VIOLATIONS
        self.assertTrue(
            required <= covered,
            f"git red-team violation_types with no git scenario: {sorted(required - covered)}",
        )
        # Adding a git scenario for a pending type without removing it from the
        # frozen set fails: forces an explicit constant update, no silent closure.
        self.assertEqual(
            GIT_REDTEAM_PENDING_VIOLATIONS & covered,
            frozenset(),
            "pending git violation_type now covered -- remove it from "
            f"GIT_REDTEAM_PENDING_VIOLATIONS: {sorted(GIT_REDTEAM_PENDING_VIOLATIONS & covered)}",
        )
        # Sanity: every pending name is a real violation type (catches a typo).
        self.assertTrue(
            GIT_REDTEAM_PENDING_VIOLATIONS <= ALL_VIOLATION_TYPES,
            "GIT_REDTEAM_PENDING_VIOLATIONS holds an unknown violation_type: "
            f"{sorted(GIT_REDTEAM_PENDING_VIOLATIONS - ALL_VIOLATION_TYPES)}",
        )

    def test_d6_every_campaign_action_has_verdict_and_no_orphan_agent(self) -> None:
        no_expect: list[str] = []
        orphans: list[str] = []
        for path in CAMPAIGNS.glob("**/*.campaign.json"):
            doc = json.loads(path.read_text(encoding="utf-8"))
            declared = {a["id"] for a in doc.get("agents", [])}
            used: set[str] = set()
            for action in doc.get("actions", []):
                used.add(action["agent_id"])
                if not action.get("expect"):
                    no_expect.append(f"{path.name}:{action.get('action_type')}")
            orphans.extend(f"{path.name}:{a}" for a in declared - used)
        self.assertEqual(no_expect, [], f"campaign actions without expect: {no_expect}")
        self.assertEqual(orphans, [], f"declared agents never used: {orphans}")


if __name__ == "__main__":
    unittest.main()
