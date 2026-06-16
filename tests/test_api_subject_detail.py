"""Subject detail finder: full manifest + ground-truth by agent_id.

Exercises find_subject_detail against the on-disk corpus so the console explain
modal has a real source. Deterministic. The finder is pure logic, but it lives
in recette.api.routers.subjects which imports fastapi at module level, so the
import is guarded: the suite collects cleanly without the [api] extra (R20) and
the test runs wherever fastapi is installed.
"""

import unittest

try:
    from recette.api.routers.subjects import find_subject_detail

    _HAS_API = True
except ImportError:  # pragma: no cover - depends on the [api] extra (fastapi)
    _HAS_API = False


@unittest.skipUnless(_HAS_API, "requires the [api] extra (fastapi)")
class SubjectDetailTest(unittest.TestCase):
    def test_known_git_subject_returns_manifest_and_ground_truth(self) -> None:
        detail = find_subject_detail("gh-issue-triager")
        self.assertIsNotNone(detail)
        assert detail is not None
        self.assertEqual(detail["agent_id"], "gh-issue-triager")
        self.assertEqual(detail["manifest"]["agent_id"], "gh-issue-triager")
        # capability_scope is part of the declared manifest
        self.assertIn("capability_scope", detail["manifest"])
        # a correct subject carries an expected verdict in its ground-truth
        self.assertEqual(detail["ground_truth"].get("expected_verdict"), "correct")

    def test_incorrect_subject_carries_violation_type(self) -> None:
        detail = find_subject_detail("gh-readonly-overreach")
        self.assertIsNotNone(detail)
        assert detail is not None
        self.assertEqual(detail["ground_truth"].get("violation_type"), "capability_overreach")

    def test_unknown_subject_returns_none(self) -> None:
        self.assertIsNone(find_subject_detail("does-not-exist-xyz"))


if __name__ == "__main__":
    unittest.main()
