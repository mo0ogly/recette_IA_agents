"""Contract tests for the inventory bridge (Rust AgentInventory JSON -> DiscoveryRisk).

Proven against REAL fixtures captured from the discoveryprobe-inventory CLI
(``scan <tree> --out ...``), never an invented payload (R4/R16). The fixtures
carry the kind-tagged shape emitted by the Rust model (Task 5): every enum value
is a JSON object with a ``"kind"`` key.
"""

import json
import unittest
from pathlib import Path

from recette.adapters import DiscoveryRisk
from recette.inventory_bridge import BridgedInventory, parse_inventory

_FIXTURES = Path(__file__).resolve().parent / "fixtures"


def _load(name: str) -> str:
    return (_FIXTURES / name).read_text(encoding="utf-8")


class InventoryBridgeTest(unittest.TestCase):
    def test_bridge_parses_the_real_shadow_fixture(self) -> None:
        """The shadow (absent-passport) agent maps to passport_status 'absent'
        and its PassportAbsent violation is surfaced in the bridged output."""
        bridged = parse_inventory(_load("agent_inventory.fixture.json"))
        self.assertIsInstance(bridged, BridgedInventory)
        self.assertEqual(len(bridged.risks), 1)
        risk = bridged.risks[0]
        self.assertIsInstance(risk, DiscoveryRisk)
        self.assertEqual(risk.passport_status, "absent")
        # Declaration-less record -> sentinel action_pattern / target_system.
        self.assertEqual(risk.action_pattern, "unknown")
        self.assertEqual(risk.target_system, "unknown")
        # The PassportAbsent violation is surfaced with its agent context.
        kinds = [v["kind"] for v in bridged.violations]
        self.assertIn("passport_absent", kinds)
        self.assertTrue(all(v["agent_id"] == "repo" for v in bridged.violations))

    def test_bridge_present_fixture(self) -> None:
        """A present-passport agent maps to passport_status 'present', one risk
        per declared action, real target system, and surfaces no violations."""
        bridged = parse_inventory(_load("agent_inventory_present.fixture.json"))
        self.assertEqual(bridged.violations, [])
        patterns = sorted(r.action_pattern for r in bridged.risks)
        self.assertEqual(patterns, ["open_pr", "read_repo"])
        for risk in bridged.risks:
            self.assertEqual(risk.passport_status, "present")
            self.assertEqual(risk.target_system, "github")
        # canonical_agent_id mirrors the reference adapter: sha256(principal)[:16].
        import hashlib

        expected = hashlib.sha256(b"acme-dependency-pr-bot[bot]").hexdigest()[:16]
        self.assertTrue(all(r.canonical_agent_id == expected for r in bridged.risks))

    def test_bridge_invalid_fixture(self) -> None:
        """An invalid-passport record maps to passport_status 'invalid' with a
        sentinel action (no declaration to enumerate)."""
        bridged = parse_inventory(_load("agent_inventory_invalid.fixture.json"))
        self.assertEqual(len(bridged.risks), 1)
        self.assertEqual(bridged.risks[0].passport_status, "invalid")
        self.assertEqual(bridged.risks[0].action_pattern, "unknown")

    def test_bridge_is_deterministic(self) -> None:
        raw = _load("agent_inventory.fixture.json")
        self.assertEqual(parse_inventory(raw), parse_inventory(raw))

    def test_malformed_json_raises_valueerror(self) -> None:
        with self.assertRaises(ValueError):
            parse_inventory("{not json")

    def test_missing_agents_key_raises_valueerror(self) -> None:
        with self.assertRaises(ValueError):
            parse_inventory(json.dumps({"schema_version": "1.0"}))


if __name__ == "__main__":
    unittest.main()
