"""GET /discovery/overview -- unified discovery overview for the console.

Proves the overview aggregates BOTH discovery sources over the committed corpus:
the agent-catalog registry (total / with_tools / tags) and the
observability-signature table (tools, by_category primary counts, by_capability
coverage counts where audit/replay surface). Also proves determinism (two calls
byte-identical) and the fail-safe collapse to zeros on an empty source. The sister
passthrough -- /detect/signatures now carrying ``capabilities`` -- is checked here
too so the console fixtures stay coherent. No third-party data.
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
_SIGNATURES_ENV = "INSPECT_IA_AGENTS_DETECT_SIGNATURES"


@unittest.skipUnless(_HAS_FASTAPI, "requires the [api] extra (fastapi)")
class TestDiscoveryOverview(unittest.TestCase):
    def setUp(self) -> None:
        self._saved_registry = os.environ.pop(_REGISTRY_ENV, None)
        self._saved_signatures = os.environ.pop(_SIGNATURES_ENV, None)
        self.client = TestClient(create_app())

    def tearDown(self) -> None:
        for env, saved in (
            (_REGISTRY_ENV, self._saved_registry),
            (_SIGNATURES_ENV, self._saved_signatures),
        ):
            if saved is None:
                os.environ.pop(env, None)
            else:
                os.environ[env] = saved

    def test_overview_aggregates_both_corpus_sources(self) -> None:
        body = self.client.get("/discovery/overview").json()

        # Catalog totals match the committed corpus registry.
        self.assertEqual(body["catalog"]["total"], 5)
        self.assertEqual(body["catalog"]["with_tools"], 4)
        self.assertGreater(body["catalog"]["tags"], 0)

        # Detect side: 12 signatures, capability coverage, primary-category count.
        detect = body["detect"]
        self.assertEqual(detect["tools"], 12)
        # audit/replay surface via the capability lists (Langfuse + LangSmith).
        self.assertGreaterEqual(detect["by_capability"]["audit"], 2)
        self.assertGreaterEqual(detect["by_capability"]["replay"], 2)
        # by_category counts each tool's PRIMARY category; exactly one gateway.
        self.assertEqual(detect["by_category"]["gateway"], 1)

    def test_overview_keys_are_sorted(self) -> None:
        detect = self.client.get("/discovery/overview").json()["detect"]
        self.assertEqual(list(detect["by_category"].keys()), sorted(detect["by_category"].keys()))
        self.assertEqual(
            list(detect["by_capability"].keys()), sorted(detect["by_capability"].keys())
        )

    def test_signatures_passthrough_carries_capabilities(self) -> None:
        tools = self.client.get("/detect/signatures").json()["tools"]
        langfuse = next(t for t in tools if t["tool"] == "Langfuse")
        self.assertEqual(langfuse["capabilities"], ["audit", "replay", "tracing"])

    def test_overview_is_deterministic(self) -> None:
        first = self.client.get("/discovery/overview").json()
        second = self.client.get("/discovery/overview").json()
        self.assertEqual(
            json.dumps(first, sort_keys=True),
            json.dumps(second, sort_keys=True),
        )

    def test_overview_includes_the_surface_corpus_pillar(self) -> None:
        client = TestClient(create_app())
        surfaces = client.get("/discovery/overview").json()["surfaces"]
        # 4 green subjects in corpus/surface/: pr-bot-sdk + ghost-direct-db,
        # then exfil-to-sink + hook-only-mock (added by the 4-pattern thesis wave).
        self.assertEqual(surfaces["total_agents"], 4)
        self.assertTrue(surfaces["ok"])
        self.assertEqual(surfaces["ghosts"], 0)
        self.assertIn("ebpf_wire", surfaces["detected_per_surface"])

    def test_overview_fail_safe_on_empty_sources(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            os.environ[_REGISTRY_ENV] = str(Path(tmp) / "no-registry.json")
            os.environ[_SIGNATURES_ENV] = str(Path(tmp) / "no-signatures.json")
            client = TestClient(create_app())
            body = client.get("/discovery/overview").json()
            # The neutralised sources (catalog + detect via env) collapse to
            # zeros; the surface corpus is a separate real source, so assert the
            # neutralised sections precisely and only the surfaces SHAPE.
            self.assertEqual(body["catalog"], {"total": 0, "with_tools": 0, "tags": 0})
            self.assertEqual(body["detect"], {"tools": 0, "by_category": {}, "by_capability": {}})
            self.assertEqual(
                set(body["surfaces"]),
                {"total_agents", "detected_per_surface", "ghosts", "ok"},
            )


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
