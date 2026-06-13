"""CI guard: the system recette must pass (coherence + live smoke + flow).

This is the test that catches "green unit tests but the running app is an
incoherent patchwork": it runs scripts/run_system_recette.py end to end (no live
LLM) and asserts exit 0. A frontend route with no backend, a duplicate route, a
500 on a simple GET, or a broken RAG/campaign/agent flow turns this red.
"""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

_SCRIPTS = Path(__file__).resolve().parent.parent / "scripts"
if str(_SCRIPTS) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS))

try:
    import fastapi  # noqa: F401

    _HAS_FASTAPI = True
except ImportError:  # pragma: no cover
    _HAS_FASTAPI = False


@unittest.skipUnless(_HAS_FASTAPI, "requires the [api] extra (fastapi)")
class TestSystemRecette(unittest.TestCase):
    def test_system_recette_passes(self) -> None:
        from run_system_recette import main

        self.assertEqual(main([]), 0, "system recette reported failures")


if __name__ == "__main__":
    unittest.main()
