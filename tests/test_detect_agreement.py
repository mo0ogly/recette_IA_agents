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

from recette.api.routers import detect as detect_router

_REPO_ROOT = Path(__file__).resolve().parents[1]
_CASES = _REPO_ROOT / "corpus" / "detect" / "agreement-cases.json"


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
