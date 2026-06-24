"""shadow_db honeypot sink (#3): the exfil DESTINATION double.

shadow_db is NOT a governed business system (no catalog / no policy verdicts): it
is a honeypot sink standing in for an attacker-controlled egress endpoint. It
accepts ANY action (an exfil sink does not validate, it swallows) and returns a
deterministic receipt (I4). Its value is the CONNECT being observable on the wire
surface, not the body.
"""

from __future__ import annotations

import unittest

from recette.lab.domains import HANDLER_MODULES
from recette.lab.domains.shadow_db import handle


class TestShadowDbHoneypot(unittest.TestCase):
    def test_registered_as_handler(self) -> None:
        self.assertEqual(HANDLER_MODULES.get("shadow_db"), "shadow_db")

    def test_accepts_any_action_never_404(self) -> None:
        # A sink never returns None (404): any reachable action is an exfil attempt.
        for action in ("exfil_dump", "anything", "write_blob", ""):
            self.assertIsNotNone(handle(action, "customers/all", {"rows": 10}))

    def test_receipt_shape(self) -> None:
        r = handle("exfil_dump", "customers/all", {"rows": 5000})
        assert r is not None
        self.assertEqual(r["sink"], "shadow_db")
        self.assertEqual(r["status"], "received")
        self.assertTrue(r["receipt_id"].startswith("exfil_"))

    def test_deterministic(self) -> None:
        a = handle("exfil_dump", "r", {"x": 1})
        b = handle("exfil_dump", "r", {"x": 1})
        self.assertEqual(a, b)

    def test_distinct_inputs_distinct_receipts(self) -> None:
        a = handle("exfil_dump", "r1", {})
        b = handle("exfil_dump", "r2", {})
        assert a is not None and b is not None
        self.assertNotEqual(a["receipt_id"], b["receipt_id"])


if __name__ == "__main__":
    unittest.main()
