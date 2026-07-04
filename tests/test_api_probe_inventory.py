"""GET /probe/inventory serves the committed sample AgentInventory (Task 14).

The route is read-only (I1) and deterministic (I4): it serves a frozen document
assembled from real ``discoveryprobe-inventory`` CLI output -- no live Rust
binary in the request path, no clock, no randomness. It answers the standard raw
JSON body wrapped under ``inventory`` (mirroring the client's single-key
unwrap). The sample carries all three passport states (present / absent /
invalid) so the console panel can assert each badge, a real undeclared comm
edge, and the PassportAbsent violation.

Fail-safe contract: a malformed sample is a loud 500 (validated through the
inventory bridge), never a silently served broken document.
"""

from __future__ import annotations

import unittest

try:
    from fastapi.testclient import TestClient

    from recette.api.app import create_app

    _HAS_FASTAPI = True
except ImportError:  # pragma: no cover - only without the [api] extra
    _HAS_FASTAPI = False


@unittest.skipUnless(_HAS_FASTAPI, "requires the [api] extra (fastapi)")
class TestProbeInventoryApi(unittest.TestCase):
    def setUp(self) -> None:
        self.client = TestClient(create_app())

    def test_inventory_returns_wrapped_agent_inventory(self) -> None:
        resp = self.client.get("/probe/inventory")
        self.assertEqual(resp.status_code, 200)
        body = resp.json()
        # single-key envelope the client unwraps (.inventory)
        self.assertIn("inventory", body)
        inv = body["inventory"]
        self.assertEqual(inv["schema_version"], "1.0")
        self.assertIsInstance(inv["agents"], list)

    def test_inventory_covers_all_three_passport_states(self) -> None:
        inv = self.client.get("/probe/inventory").json()["inventory"]
        kinds = {agent["passport"]["kind"] for agent in inv["agents"]}
        self.assertEqual(kinds, {"present", "absent", "invalid"})

    def test_invalid_passport_carries_no_violation(self) -> None:
        # Consumer contract: an INVALID passport has status "invalid" but no
        # violation and not_observed conformity (the badge keys off the status,
        # never a non-empty violations list).
        inv = self.client.get("/probe/inventory").json()["inventory"]
        invalid = [a for a in inv["agents"] if a["passport"]["kind"] == "invalid"]
        self.assertEqual(len(invalid), 1)
        self.assertEqual(invalid[0]["conformity"]["kind"], "not_observed")

    def test_inventory_surfaces_passport_absent_violation(self) -> None:
        inv = self.client.get("/probe/inventory").json()["inventory"]
        absent = [a for a in inv["agents"] if a["passport"]["kind"] == "absent"]
        self.assertEqual(len(absent), 1)
        self.assertEqual(absent[0]["conformity"]["kind"], "violations")
        kinds = {v["kind"] for v in absent[0]["conformity"]["violations"]}
        self.assertIn("passport_absent", kinds)

    def test_inventory_has_an_undeclared_comm_edge(self) -> None:
        inv = self.client.get("/probe/inventory").json()["inventory"]
        self.assertTrue(inv["comm_graph"]["undeclared_edges"])
        # via_gateway edges are carried separately from undeclared (design rule 4)
        self.assertTrue(inv["comm_graph"]["via_gateway_edges"])

    def test_inventory_is_deterministic(self) -> None:
        # Same request twice -> byte-identical body (I4: no clock in the path).
        first = self.client.get("/probe/inventory").text
        second = self.client.get("/probe/inventory").text
        self.assertEqual(first, second)


if __name__ == "__main__":
    unittest.main()
