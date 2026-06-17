"""The Python detector run over the realistic repo fixtures
(corpus/detect/repos/<slug>/) yields each repo's ground-truth detections --
the same fixtures the Rust crate tests, so both agree over multi-file sources.

The fixtures are our OWN small projects using the real public identifiers of
observability tools (package / import / env var), no third-party repo content.
The scan reads SOURCE files only (excluding expected.json, which contains needle
strings) and asserts the detections match the committed ground-truth.
"""

from __future__ import annotations

import json
import unittest
from pathlib import Path

try:
    from recette.api.routers import detect as detect_router

    _HAS_API = True
except ImportError:  # pragma: no cover - depends on the [api] extra (fastapi)
    _HAS_API = False

_REPOS = Path(__file__).resolve().parents[1] / "corpus" / "detect" / "repos"


def _scan_sources(repo: Path) -> str:
    parts = []
    for path in sorted(repo.iterdir()):
        if path.name == "expected.json" or not path.is_file():
            continue
        try:
            parts.append(path.read_text(encoding="utf-8"))
        except OSError:  # pragma: no cover - skip unreadable
            continue
    return "\n".join(parts) + "\n"


@unittest.skipUnless(_HAS_API, "requires the [api] extra (fastapi)")
class TestDetectRepoFixtures(unittest.TestCase):
    def test_every_repo_fixture_matches_its_ground_truth(self) -> None:
        repos = sorted(p for p in _REPOS.iterdir() if p.is_dir())
        self.assertTrue(repos, "expected at least one repo fixture")
        signatures = detect_router._load_signatures()
        for repo in repos:
            expected = json.loads((repo / "expected.json").read_text(encoding="utf-8"))
            got = detect_router._detect(_scan_sources(repo), signatures)
            self.assertEqual(got, expected, f"detection mismatch for repo {repo.name}")


if __name__ == "__main__":
    unittest.main()
