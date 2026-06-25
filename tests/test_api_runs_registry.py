"""Tests for /results endpoints (Tasks 4-5).

Requires the [api] extra (fastapi).  Skipped without it.

Run:  .venv/bin/python -m unittest tests.test_api_runs_registry -v
"""

from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

try:
    from fastapi.testclient import TestClient

    from recette.api.app import create_app
    from recette.api.config_store import ConfigStore
    from recette.runs.registry import RunRegistry

    _HAS_FASTAPI = True
except ImportError:  # pragma: no cover - only without the [api] extra
    _HAS_FASTAPI = False


def _make_client(tmp_root: Path) -> TestClient:
    """Build a TestClient with a registry pointing at *tmp_root*."""
    app = create_app(config_store=ConfigStore())
    reg = RunRegistry(tmp_root)
    app.state.runs_registry = reg
    return TestClient(app)


def _seed_sealed_run(reg: RunRegistry) -> str:
    """Create and seal one run; return run_id."""
    g = reg.new_group(
        category="agents",
        group_id="grp1",
        eurodate="2026-06-25T10-00-00",
        label="test group",
    )
    r = reg.new_run(group=g, run_id="run-1", kind="agent", eurodate="2026-06-25T10-00-01")
    reg.write_artifact(r, "agents.jsonl", '{"agent_id":"a","ok":true}\n')
    reg.seal(r)
    return r.run_id


@unittest.skipUnless(_HAS_FASTAPI, "requires the [api] extra (fastapi)")
class TestResultsReadEndpoints(unittest.TestCase):
    """Task 4: read-only /results endpoints."""

    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.root = Path(self._tmp.name)
        self.reg = RunRegistry(self.root)
        self.client = _make_client(self.root)
        self.run_id = _seed_sealed_run(self.reg)

    def tearDown(self) -> None:
        self._tmp.cleanup()

    def test_get_tree_returns_200_with_categories(self) -> None:
        r = self.client.get("/results/tree")
        self.assertEqual(r.status_code, 200)
        body = r.json()
        self.assertIn("categories", body)
        cats = {c["category"] for c in body["categories"]}
        self.assertIn("agents", cats)

    def test_get_run_returns_200_with_meta_and_annotations(self) -> None:
        r = self.client.get(f"/results/{self.run_id}")
        self.assertEqual(r.status_code, 200)
        body = r.json()
        self.assertIn("meta", body)
        self.assertIn("annotations", body)
        self.assertIn("artifacts", body)
        self.assertEqual(body["meta"]["status"], "sealed")

    def test_get_run_404_for_missing(self) -> None:
        r = self.client.get("/results/no-such-run")
        self.assertEqual(r.status_code, 404)

    def test_get_artifact_returns_200_raw_text(self) -> None:
        r = self.client.get(f"/results/{self.run_id}/artifact/agents.jsonl")
        self.assertEqual(r.status_code, 200)
        self.assertIn("agent_id", r.text)

    def test_get_artifact_404_for_missing(self) -> None:
        r = self.client.get(f"/results/{self.run_id}/artifact/no-such.jsonl")
        self.assertEqual(r.status_code, 404)

    def test_get_artifact_path_traversal_rejected_400(self) -> None:
        # URL-encoded path traversal attempt.
        r = self.client.get(f"/results/{self.run_id}/artifact/..%2F..%2Fetc%2Fpasswd")
        self.assertEqual(r.status_code, 400)

    def test_get_artifact_dotdot_rejected(self) -> None:
        # FastAPI normalizes literal "../.." at the routing layer, so the
        # response is either 400 (guard fires) or 404 (route not matched
        # after normalization).  Both reject the traversal -- never 200.
        r = self.client.get(f"/results/{self.run_id}/artifact/../../etc/passwd")
        self.assertIn(r.status_code, {400, 404})


@unittest.skipUnless(_HAS_FASTAPI, "requires the [api] extra (fastapi)")
class TestResultsWriteEndpoints(unittest.TestCase):
    """Task 5: CRUD + replay /results endpoints."""

    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.root = Path(self._tmp.name)
        self.reg = RunRegistry(self.root)
        self.client = _make_client(self.root)
        self.run_id = _seed_sealed_run(self.reg)

    def tearDown(self) -> None:
        self._tmp.cleanup()

    # -- POST /results (register) --

    def test_post_register_creates_run(self) -> None:
        r = self.client.post(
            "/results",
            json={
                "category": "campaigns",
                "group_id": "batch-1",
                "label": "test batch",
                "run_id": "camp-run-1",
                "kind": "campaign",
                "eurodate": "2026-06-25T12-00-00",
                "artifacts": {"scorecard.json": '{"pass":true}'},
                "seal": True,
            },
        )
        self.assertEqual(r.status_code, 201)
        body = r.json()
        self.assertEqual(body["run_id"], "camp-run-1")
        self.assertEqual(body["status"], "sealed")
        self.assertIn("root_hash", body)

    def test_post_register_missing_fields_400(self) -> None:
        r = self.client.post(
            "/results",
            json={"category": "agents"},
        )
        self.assertEqual(r.status_code, 400)

    # -- PATCH /results/{id} (annotations) --

    def test_patch_annotations_updates_only_annotations(self) -> None:
        # Capture meta before.
        meta_before = self.reg.read_run(self.run_id)["meta"]

        r = self.client.patch(
            f"/results/{self.run_id}",
            json={"tags": ["reviewed"], "comment": "looks good"},
        )
        self.assertEqual(r.status_code, 200)
        body = r.json()
        self.assertEqual(body["tags"], ["reviewed"])
        self.assertEqual(body["comment"], "looks good")

        # Meta unchanged.
        meta_after = self.reg.read_run(self.run_id)["meta"]
        self.assertEqual(meta_before, meta_after)

    def test_patch_annotations_404_for_missing(self) -> None:
        r = self.client.patch("/results/no-run", json={"tags": ["x"]})
        self.assertEqual(r.status_code, 404)

    # -- DELETE /results/{id} --

    def test_delete_without_confirm_returns_400(self) -> None:
        r = self.client.delete(f"/results/{self.run_id}")
        self.assertEqual(r.status_code, 400)

    def test_delete_with_confirm_archives_then_404(self) -> None:
        r = self.client.delete(f"/results/{self.run_id}", params={"confirm": "true"})
        self.assertEqual(r.status_code, 200)
        body = r.json()
        self.assertEqual(body["status"], "purged")
        # Subsequent GET returns 404.
        r2 = self.client.get(f"/results/{self.run_id}")
        self.assertEqual(r2.status_code, 404)

    def test_delete_404_for_missing(self) -> None:
        r = self.client.delete("/results/ghost", params={"confirm": "true"})
        self.assertEqual(r.status_code, 404)

    # -- POST /results/{id}/replay --

    def test_replay_replayable_kind_returns_201_with_child_id(self) -> None:
        r = self.client.post(
            f"/results/{self.run_id}/replay",
            json={"eurodate": "2026-06-25T15-00-00"},
        )
        self.assertEqual(r.status_code, 201)
        body = r.json()
        self.assertIn("child_run_id", body)
        self.assertEqual(body["replay_of"], self.run_id)

        # Child run exists and has replay_of set.
        child_id = body["child_run_id"]
        child_ref = self.reg.find_run(child_id)
        self.assertIsNotNone(child_ref)
        child_meta = json.loads(
            (child_ref.path / "meta.json").read_text()  # type: ignore[union-attr]
        )
        self.assertEqual(child_meta["replay_of"], self.run_id)

    def test_replay_parent_not_mutated(self) -> None:
        meta_before = self.reg.read_run(self.run_id)["meta"]
        self.client.post(
            f"/results/{self.run_id}/replay",
            json={"eurodate": "2026-06-25T16-00-00"},
        )
        meta_after = self.reg.read_run(self.run_id)["meta"]
        self.assertEqual(meta_before, meta_after)

    def test_replay_not_replayable_kind_returns_422(self) -> None:
        # Create a run of a non-replayable kind.
        g = self.reg.new_group(
            category="discovery",
            group_id="disc1",
            eurodate="2026-06-25T11-00-00",
            label="disc",
        )
        r = self.reg.new_run(
            group=g, run_id="disc-run-1", kind="discovery", eurodate="2026-06-25T11-00-01"
        )
        self.reg.seal(r)

        r2 = self.client.post(
            "/results/disc-run-1/replay",
            json={"eurodate": "2026-06-25T17-00-00"},
        )
        self.assertEqual(r2.status_code, 422)

    def test_replay_404_for_missing_run(self) -> None:
        r = self.client.post("/results/no-run/replay", json={})
        self.assertEqual(r.status_code, 404)


if __name__ == "__main__":
    unittest.main()
