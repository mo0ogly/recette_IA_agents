"""Cross-language behaviour agreement for the observability detector.

The Python API detector must produce exactly the detections in the shared cases
file (corpus/detect/agreement-cases.json), which the Rust reference detector
tests against too -- so the two `detect` algorithms cannot silently diverge
(R20). Table parity is covered by the shared signature JSON; this covers the
ALGORITHM.
"""

from __future__ import annotations

import json
import unittest
from pathlib import Path

try:
    # The detector functions are pure, but recette.api.routers.detect imports
    # fastapi at module level, so collection needs the [api] extra. Guard the
    # import so the suite collects cleanly without it (R20); the test runs
    # wherever fastapi is installed.
    from recette.api.routers import detect as detect_router

    _HAS_API = True
except ImportError:  # pragma: no cover - depends on the [api] extra (fastapi)
    _HAS_API = False

_REPO_ROOT = Path(__file__).resolve().parents[1]
_CASES = _REPO_ROOT / "corpus" / "detect" / "agreement-cases.json"


@unittest.skipUnless(_HAS_API, "requires the [api] extra (fastapi)")
class TestDetectAgreement(unittest.TestCase):
    def test_python_detector_matches_the_shared_cases(self) -> None:
        cases = json.loads(_CASES.read_text(encoding="utf-8"))
        self.assertTrue(cases, "agreement cases must not be empty")
        signatures = detect_router._load_signatures()
        for case in cases:
            got = detect_router._detect(case["text"], signatures)
            self.assertEqual(
                got,
                case["expected"],
                f"python detection diverged on {case['text']!r}",
            )


if __name__ == "__main__":
    unittest.main()
