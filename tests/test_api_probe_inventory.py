"""GET /probe/inventory serves a LIVE AgentInventory scan, or the sample fallback.

The route is read-only (I1): the Rust engine only reads agent-source trees, it
mediates nothing. When the compiled ``discoveryprobe-inventory`` binary is built
it runs a live on-demand scan of the configured trees and merges the results
(``live: true``); when it is not built the route falls back to the committed
sample and flags ``live: false`` with a reason -- the panel still renders.

Both paths are exercised here by controlling ``INSPECT_IA_AGENTS_INVENTORY_BIN``:
the fallback path is always tested (no binary needed, deterministic sample), and
the live path is tested only when the release binary is present.
"""

from __future__ import annotations

import os
import unittest
from pathlib import Path

try:
    from fastapi.testclient import TestClient

    from recette.api.app import create_app

    _HAS_FASTAPI = True
except ImportError:  # pragma: no cover - only without the [api] extra
    _HAS_FASTAPI = False

_REPO_ROOT = Path(__file__).resolve().parents[1]
_LIVE_BIN = _REPO_ROOT / "discoveryprobe" / "target" / "release" / "discoveryprobe-inventory"
_BIN_ENV = "INSPECT_IA_AGENTS_INVENTORY_BIN"


@unittest.skipUnless(_HAS_FASTAPI, "requires the [api] extra (fastapi)")
class TestProbeInventoryFallback(unittest.TestCase):
    """Force the sample fallback by pointing the binary env at a missing path."""

    def setUp(self) -> None:
        self._prev = os.environ.get(_BIN_ENV)
        os.environ[_BIN_ENV] = str(_REPO_ROOT / "does-not-exist-inventory-bin")
        self.client = TestClient(create_app())

    def tearDown(self) -> None:
        if self._prev is None:
            os.environ.pop(_BIN_ENV, None)
        else:
            os.environ[_BIN_ENV] = self._prev

    def test_falls_back_to_sample_flagged_not_live(self) -> None:
        body = self.client.get("/probe/inventory").json()
        self.assertIn("inventory", body)  # single-key envelope the client unwraps
        self.assertFalse(body["live"])
        self.assertIn("reason", body)
        self.assertEqual(body["inventory"]["schema_version"], "1.0")

    def test_sample_covers_all_three_passport_states(self) -> None:
        inv = self.client.get("/probe/inventory").json()["inventory"]
        kinds = {agent["passport"]["kind"] for agent in inv["agents"]}
        self.assertEqual(kinds, {"present", "absent", "invalid"})

    def test_sample_invalid_passport_carries_no_violation(self) -> None:
        # Consumer contract: an INVALID passport has status "invalid" but no
        # violation and not_observed conformity (the badge keys off the status).
        inv = self.client.get("/probe/inventory").json()["inventory"]
        invalid = [a for a in inv["agents"] if a["passport"]["kind"] == "invalid"]
        self.assertEqual(len(invalid), 1)
        self.assertEqual(invalid[0]["conformity"]["kind"], "not_observed")

    def test_sample_surfaces_passport_absent_violation(self) -> None:
        inv = self.client.get("/probe/inventory").json()["inventory"]
        absent = [a for a in inv["agents"] if a["passport"]["kind"] == "absent"]
        self.assertEqual(len(absent), 1)
        kinds = {v["kind"] for v in absent[0]["conformity"]["violations"]}
        self.assertIn("passport_absent", kinds)

    def test_sample_has_undeclared_and_gateway_edges(self) -> None:
        inv = self.client.get("/probe/inventory").json()["inventory"]
        self.assertTrue(inv["comm_graph"]["undeclared_edges"])
        self.assertTrue(inv["comm_graph"]["via_gateway_edges"])

    def test_fallback_is_deterministic(self) -> None:
        first = self.client.get("/probe/inventory").text
        second = self.client.get("/probe/inventory").text
        self.assertEqual(first, second)


@unittest.skipUnless(_HAS_FASTAPI, "requires the [api] extra (fastapi)")
@unittest.skipUnless(_LIVE_BIN.is_file(), "requires the built discoveryprobe-inventory binary")
class TestProbeInventoryLive(unittest.TestCase):
    """Live scan path: the real Rust engine walks corpus/repos on demand."""

    def setUp(self) -> None:
        self._prev = os.environ.get(_BIN_ENV)
        os.environ[_BIN_ENV] = str(_LIVE_BIN)
        self.client = TestClient(create_app())

    def tearDown(self) -> None:
        if self._prev is None:
            os.environ.pop(_BIN_ENV, None)
        else:
            os.environ[_BIN_ENV] = self._prev

    def test_live_scan_flags_live_true(self) -> None:
        body = self.client.get("/probe/inventory").json()
        self.assertTrue(body["live"])
        self.assertIn("discoveryprobe-inventory", body["engine"])

    def test_live_scan_finds_real_agents_across_passport_states(self) -> None:
        inv = self.client.get("/probe/inventory").json()["inventory"]
        kinds = {agent["passport"]["kind"] for agent in inv["agents"]}
        # corpus/repos carries present agents plus the shadow (absent) and the
        # broken-manifest (invalid) subjects added by this feature.
        self.assertIn("present", kinds)
        self.assertIn("absent", kinds)
        self.assertIn("invalid", kinds)

    def test_live_scan_relabels_bland_shadow_ids_to_the_slug(self) -> None:
        # A shadow/invalid agent scanned at <slug>/repo reads as <slug>, not the
        # bland mount id "repo".
        inv = self.client.get("/probe/inventory").json()["inventory"]
        ids = {a["agent_id"] for a in inv["agents"]}
        self.assertIn("gh-shadow-agent", ids)
        self.assertIn("gh-invalid-passport", ids)
        self.assertNotIn("repo", ids)

    def test_live_scan_surfaces_the_shadow_passport_absent_violation(self) -> None:
        inv = self.client.get("/probe/inventory").json()["inventory"]
        shadow = [a for a in inv["agents"] if a["agent_id"] == "gh-shadow-agent"]
        self.assertEqual(len(shadow), 1)
        self.assertEqual(shadow[0]["conformity"]["kind"], "violations")

    def test_live_scan_is_deterministic(self) -> None:
        first = self.client.get("/probe/inventory").text
        second = self.client.get("/probe/inventory").text
        self.assertEqual(first, second)


if __name__ == "__main__":
    unittest.main()
