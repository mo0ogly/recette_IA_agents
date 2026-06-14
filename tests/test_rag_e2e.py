"""The deterministic RAG poisoning e2e (scripts/run_rag_poisoning_e2e.py) is the
living proof of the recette loop: reset -> apply scenario -> every injected poison
is blocked by the gateway (executed=False) -> reset -> KB == baseline byte-identical.

The script needs the [api] extra (it drives the real gateway over TestClient), so
the suite skips when fastapi is absent -- same idiom as the other API tests."""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

_SCRIPTS = Path(__file__).resolve().parent.parent / "scripts"
if str(_SCRIPTS) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS))

try:
    import run_rag_poisoning_e2e as e2e

    _HAS_FASTAPI = True
except ImportError:  # pragma: no cover -- exercised only without the [api] extra
    _HAS_FASTAPI = False


@unittest.skipUnless(_HAS_FASTAPI, "requires the [api] extra (fastapi)")
class TestRagPoisoningE2e(unittest.TestCase):
    def test_exfil_finance_loop_holds(self) -> None:
        # Every poisoned doc blocked, baseline restored, audit chain intact -> exit 0.
        self.assertEqual(e2e.main(["--scenario", "exfil-finance"]), 0)

    def test_invalid_command_ops_loop_holds(self) -> None:
        self.assertEqual(e2e.main(["--scenario", "invalid-command-ops"]), 0)

    def test_unknown_scenario_returns_2(self) -> None:
        self.assertEqual(e2e.main(["--scenario", "no-such-scenario"]), 2)

    def test_run_is_deterministic_baseline_restored(self) -> None:
        # Two runs in a row both hold: reset() restores the baseline exactly (I4),
        # so the second run starts from the same clean state as the first.
        self.assertEqual(e2e.main(["--scenario", "exfil-finance"]), 0)
        self.assertEqual(e2e.main(["--scenario", "exfil-finance"]), 0)


if __name__ == "__main__":
    unittest.main()
