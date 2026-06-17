"""GET /catalog/summary -- invariant projection of the declarative catalog registry.

The summary mirrors the Rust catalog crate's DiscoverySummary (total, unique,
entries-with-tools, sorted+deduped tags). This proves the Python projection over
the committed corpus registry, the env override, the fail-safe empty catalog on
a missing file, and determinism (two calls byte-identical). No third-party data.
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

_REGISTRY_ENV = "INSPECT_IA_AGENTS_CATALOG_REGISTRY"


@unittest.skipUnless(_HAS_FASTAPI, "requires the [api] extra (fastapi)")
class TestCatalogSummary(unittest.TestCase):
    def setUp(self) -> None:
        self._saved = os.environ.pop(_REGISTRY_ENV, None)
        self.client = TestClient(create_app())

    def tearDown(self) -> None:
        if self._saved is None:
            os.environ.pop(_REGISTRY_ENV, None)
        else:
            os.environ[_REGISTRY_ENV] = self._saved

    def test_corpus_registry_invariants(self) -> None:
        body = self.client.get("/catalog/summary").json()
        self.assertEqual(body["version"], "1.0")
        summary = body["summary"]
        self.assertEqual(summary["total"], 5)
        self.assertEqual(summary["unique"], 5)
        self.assertEqual(summary["with_tools"], 4)
        # tags are sorted and de-duplicated across the registry.
        self.assertEqual(summary["tags"], sorted(set(summary["tags"])))
        self.assertEqual(
            summary["tags"],
            [
                "finance",
                "github",
                "handoff",
                "identity",
                "okta",
                "pr",
                "read",
                "support",
                "write",
            ],
        )

    def test_agents_preserve_order_and_tool_count(self) -> None:
        body = self.client.get("/catalog/summary").json()
        agents = body["agents"]
        self.assertEqual(len(agents), 5)
        # registry order preserved.
        self.assertEqual(
            [a["name"] for a in agents],
            [
                "github-pr-bot",
                "okta-provisioner",
                "finance-reconciler",
                "support-triage",
                "silent-scanner",
            ],
        )
        first = agents[0]
        self.assertEqual(first["version"], "1.0.0")
        self.assertEqual(first["publisher_name"], "recette")
        self.assertEqual(first["tool_count"], 2)
        # okta-provisioner: 1 associated + 1 foundry = 2.
        self.assertEqual(agents[1]["tool_count"], 2)
        # silent-scanner declares no tools.
        silent = agents[-1]
        self.assertEqual(silent["tool_count"], 0)
        self.assertEqual(silent["tags"], [])

    def test_env_override_points_to_temp_registry(self) -> None:
        registry = {
            "version": "9.9",
            "generated_at": None,
            "entries": [
                {
                    "name": "solo-agent",
                    "type": "agent",
                    "version": "0.0.1",
                    "publisher_name": "recette",
                    "description": "single declared agent",
                    "tags": ["beta", "beta", "alpha"],
                    "associated_tools": ["tools/x"],
                }
            ],
        }
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "registry.json"
            path.write_text(json.dumps(registry), encoding="utf-8")
            os.environ[_REGISTRY_ENV] = str(path)
            client = TestClient(create_app())
            body = client.get("/catalog/summary").json()
        self.assertEqual(body["version"], "9.9")
        self.assertEqual(body["summary"]["total"], 1)
        self.assertEqual(body["summary"]["unique"], 1)
        self.assertEqual(body["summary"]["with_tools"], 1)
        # tags sorted + de-duplicated even from a duplicate-bearing entry.
        self.assertEqual(body["summary"]["tags"], ["alpha", "beta"])
        self.assertEqual(body["agents"][0]["name"], "solo-agent")
        self.assertEqual(body["agents"][0]["tool_count"], 1)

    def test_missing_file_is_fail_safe_empty(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            os.environ[_REGISTRY_ENV] = str(Path(tmp) / "does-not-exist.json")
            client = TestClient(create_app())
            body = client.get("/catalog/summary").json()
        self.assertEqual(body["version"], "")
        self.assertEqual(
            body["summary"],
            {"total": 0, "unique": 0, "with_tools": 0, "tags": []},
        )
        self.assertEqual(body["agents"], [])

    def test_malformed_json_is_fail_safe_empty(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "bad.json"
            path.write_text("{ not valid json", encoding="utf-8")
            os.environ[_REGISTRY_ENV] = str(path)
            client = TestClient(create_app())
            body = client.get("/catalog/summary").json()
        self.assertEqual(body, _empty())

    def test_determinism_two_calls_identical(self) -> None:
        first = self.client.get("/catalog/summary").json()
        second = self.client.get("/catalog/summary").json()
        self.assertEqual(json.dumps(first, sort_keys=True), json.dumps(second, sort_keys=True))


def _empty() -> dict:
    return {
        "version": "",
        "summary": {"total": 0, "unique": 0, "with_tools": 0, "tags": []},
        "agents": [],
    }


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
