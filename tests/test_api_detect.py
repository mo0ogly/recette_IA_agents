"""GET /detect/signatures + POST /detect/scan -- observability-tool detection.

Proves the Python detector over the committed corpus signature table agrees with
the Rust reference (one match per tool, sorted by tool name, first matching
needle as evidence), the catalog shape, the env override, determinism, and the
fail-safe empty result on a missing file. No third-party data.
"""

from __future__ import annotations

import json
import os
import tempfile
import unittest
from pathlib import Path

try:
    from fastapi.testclient import TestClient

    from recette.api.app import create_app

    _HAS_FASTAPI = True
except ImportError:  # pragma: no cover - depends on the [api] extra
    _HAS_FASTAPI = False

_SIGNATURES_ENV = "INSPECT_IA_AGENTS_DETECT_SIGNATURES"


@unittest.skipUnless(_HAS_FASTAPI, "requires the [api] extra (fastapi)")
class TestDetect(unittest.TestCase):
    def setUp(self) -> None:
        self._saved = os.environ.pop(_SIGNATURES_ENV, None)
        self.client = TestClient(create_app())

    def tearDown(self) -> None:
        if self._saved is None:
            os.environ.pop(_SIGNATURES_ENV, None)
        else:
            os.environ[_SIGNATURES_ENV] = self._saved

    def test_signatures_catalog_twelve_tools_and_categories(self) -> None:
        body = self.client.get("/detect/signatures").json()
        tools = body["tools"]
        self.assertEqual(len(tools), 12)
        # every entry carries the documented shape.
        first = tools[0]
        self.assertEqual(set(first.keys()), {"tool", "category", "needles"})
        self.assertEqual(first["tool"], "Langfuse")
        self.assertIn("langfuse", first["needles"])
        # categories are sorted + distinct and cover the documented span.
        categories = body["categories"]
        self.assertEqual(categories, sorted(set(categories)))
        for expected in ("tracing", "gateway", "eval"):
            self.assertIn(expected, categories)

    def test_scan_two_tools_sorted_with_matched_needles(self) -> None:
        text = "from langfuse import observe\nagentops.init()"
        body = self.client.post("/detect/scan", json={"text": text}).json()
        self.assertEqual(
            body["matches"],
            [
                {"tool": "AgentOps", "category": "tracing", "matched": "agentops"},
                {"tool": "Langfuse", "category": "tracing", "matched": "langfuse"},
            ],
        )

    def test_scan_clean_text_no_matches(self) -> None:
        body = self.client.post("/detect/scan", json={"text": "def main():\n    return 0\n"}).json()
        self.assertEqual(body["matches"], [])

    def test_scan_is_deterministic(self) -> None:
        text = "agentops.init()\nLMNR_PROJECT_API_KEY=x\nPHOENIX_API_KEY=y"
        first = self.client.post("/detect/scan", json={"text": text}).json()
        second = self.client.post("/detect/scan", json={"text": text}).json()
        self.assertEqual(
            json.dumps(first, sort_keys=True),
            json.dumps(second, sort_keys=True),
        )

    def test_one_match_per_tool_even_with_repeated_needles(self) -> None:
        # Langfuse hit by two distinct needles in the text -> still one match,
        # the FIRST needle in file order ("langfuse").
        text = "import langfuse\nLANGFUSE_PUBLIC_KEY=pk\nlangfuse.get_client()"
        body = self.client.post("/detect/scan", json={"text": text}).json()
        self.assertEqual(
            body["matches"],
            [{"tool": "Langfuse", "category": "tracing", "matched": "langfuse"}],
        )

    def test_env_override_points_to_temp_signatures(self) -> None:
        table = [
            {"tool": "Solo", "category": "audit", "needles": ["solo_marker", "SOLO_KEY"]},
        ]
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "signatures.json"
            path.write_text(json.dumps(table), encoding="utf-8")
            os.environ[_SIGNATURES_ENV] = str(path)
            client = TestClient(create_app())
            sigs = client.get("/detect/signatures").json()
            self.assertEqual(sigs["tools"], table)
            self.assertEqual(sigs["categories"], ["audit"])
            scan = client.post("/detect/scan", json={"text": "x = solo_marker"}).json()
            self.assertEqual(
                scan["matches"],
                [{"tool": "Solo", "category": "audit", "matched": "solo_marker"}],
            )

    def test_missing_file_is_fail_safe_empty(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            os.environ[_SIGNATURES_ENV] = str(Path(tmp) / "does-not-exist.json")
            client = TestClient(create_app())
            sigs = client.get("/detect/signatures").json()
            self.assertEqual(sigs, {"tools": [], "categories": []})
            scan = client.post("/detect/scan", json={"text": "langfuse"}).json()
            self.assertEqual(scan, {"matches": []})

    def test_malformed_file_is_fail_safe_empty(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "bad.json"
            path.write_text("{ not valid json", encoding="utf-8")
            os.environ[_SIGNATURES_ENV] = str(path)
            client = TestClient(create_app())
            sigs = client.get("/detect/signatures").json()
            self.assertEqual(sigs, {"tools": [], "categories": []})
            self.assertEqual(
                client.post("/detect/scan", json={"text": "langfuse"}).json(),
                {"matches": []},
            )


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
