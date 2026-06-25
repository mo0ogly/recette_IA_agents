"""Tests for recette/runs/registry.py (Tasks 1-3).

Run:  python3 -m unittest tests.test_runs_registry -v
"""

from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from recette.runs.registry import RunRegistry


class TestRegistryCreateSeal(unittest.TestCase):
    """Task 1: new_group / new_run / write_artifact / seal with sha256 chain."""

    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.root = Path(self._tmp.name)
        self.reg = RunRegistry(self.root)

    def tearDown(self) -> None:
        self._tmp.cleanup()

    def test_new_group_then_run_then_seal_is_hash_stable(self) -> None:
        # eurodate is injected (I4: registry never reads the clock)
        g = self.reg.new_group(
            category="skynet",
            group_id="megacamp",
            eurodate="2026-06-25T14-30-00",
            label="SKYNET mega",
        )
        r = self.reg.new_run(
            group=g, run_id="agent-1", kind="agent", eurodate="2026-06-25T14-30-01"
        )
        self.reg.write_artifact(r, "agents.jsonl", '{"agent_id":"a","ok":true}\n')
        meta = self.reg.seal(r)

        # sealed -> status + per-file sha256 + chained root_hash
        self.assertEqual(meta["status"], "sealed")
        self.assertIn("agents.jsonl", {a["file"] for a in meta["artifacts"]})
        self.assertEqual(len(meta["root_hash"]), 64)

        # byte-stable: same input -> same root_hash on a fresh registry
        reg2 = RunRegistry(Path(self._tmp.name) / "b")
        g2 = reg2.new_group(
            category="skynet",
            group_id="megacamp",
            eurodate="2026-06-25T14-30-00",
            label="SKYNET mega",
        )
        r2 = reg2.new_run(group=g2, run_id="agent-1", kind="agent", eurodate="2026-06-25T14-30-01")
        reg2.write_artifact(r2, "agents.jsonl", '{"agent_id":"a","ok":true}\n')
        self.assertEqual(reg2.seal(r2)["root_hash"], meta["root_hash"])

    def test_write_artifact_rejects_slash(self) -> None:
        g = self.reg.new_group(
            category="agents", group_id="g", eurodate="2026-06-25T10-00-00", label="x"
        )
        r = self.reg.new_run(group=g, run_id="r", kind="agent", eurodate="2026-06-25T10-00-01")
        with self.assertRaises(ValueError):
            self.reg.write_artifact(r, "sub/file.txt", "data")

    def test_write_artifact_rejects_dotdot(self) -> None:
        g = self.reg.new_group(
            category="agents", group_id="g", eurodate="2026-06-25T10-00-00", label="x"
        )
        r = self.reg.new_run(group=g, run_id="r", kind="agent", eurodate="2026-06-25T10-00-01")
        with self.assertRaises(ValueError):
            self.reg.write_artifact(r, "../../evil.txt", "data")

    def test_group_json_records_run_id(self) -> None:
        g = self.reg.new_group(
            category="campaigns",
            group_id="c1",
            eurodate="2026-06-25T09-00-00",
            label="batch",
        )
        self.reg.new_run(group=g, run_id="run-a", kind="campaign", eurodate="2026-06-25T09-00-01")
        gm = json.loads((g.path / "_group.json").read_text())
        self.assertIn("run-a", gm["runs"])

    def test_seal_empty_artifacts_has_deterministic_root(self) -> None:
        g = self.reg.new_group(
            category="agents", group_id="e", eurodate="2026-06-25T08-00-00", label="empty"
        )
        r = self.reg.new_run(group=g, run_id="no-art", kind="agent", eurodate="2026-06-25T08-00-01")
        meta = self.reg.seal(r)
        self.assertEqual(meta["status"], "sealed")
        # Empty artifacts -> root is the chain sentinel ("0"*64 folded zero times)
        self.assertEqual(meta["root_hash"], "0" * 64)


class TestRegistryReadIndex(unittest.TestCase):
    """Task 2: tree / read_run / read_artifact / path-traversal guard."""

    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.root = Path(self._tmp.name)
        self.reg = RunRegistry(self.root)

    def tearDown(self) -> None:
        self._tmp.cleanup()

    def _seed(self) -> tuple:
        g = self.reg.new_group(
            category="campaigns",
            group_id="b1",
            eurodate="2026-06-25T10-00-00",
            label="batch",
        )
        r = self.reg.new_run(group=g, run_id="r1", kind="campaign", eurodate="2026-06-25T10-00-01")
        self.reg.write_artifact(r, "results.jsonl", '{"ok":true}\n')
        self.reg.seal(r)
        return g, r

    def test_tree_groups_by_category(self) -> None:
        self._seed()
        tree = self.reg.tree()
        cats = {n["category"] for n in tree["categories"]}
        self.assertIn("campaigns", cats)

    def test_tree_includes_run_node(self) -> None:
        self._seed()
        tree = self.reg.tree()
        camp_cat = next(c for c in tree["categories"] if c["category"] == "campaigns")
        all_run_ids = [run["id"] for grp in camp_cat["groups"] for run in grp["runs"]]
        self.assertIn("r1", all_run_ids)

    def test_tree_on_empty_root_returns_empty_categories(self) -> None:
        tree = self.reg.tree()
        self.assertEqual(tree["categories"], [])

    def test_read_run_returns_meta_annotations_artifacts(self) -> None:
        _, _ = self._seed()
        doc = self.reg.read_run("r1")
        self.assertEqual(doc["meta"]["status"], "sealed")
        self.assertIn("tags", doc["annotations"])
        self.assertIn("results.jsonl", doc["artifacts"])

    def test_read_run_raises_key_error_for_missing(self) -> None:
        with self.assertRaises(KeyError):
            self.reg.read_run("nonexistent-run-xyz")

    def test_read_artifact_returns_content(self) -> None:
        _, r = self._seed()
        content = self.reg.read_artifact(r, "results.jsonl")
        self.assertIn("ok", content)

    def test_read_artifact_rejects_path_escape(self) -> None:
        g = self.reg.new_group(
            category="agents", group_id="g", eurodate="2026-06-25T10-00-00", label="x"
        )
        r = self.reg.new_run(group=g, run_id="r", kind="agent", eurodate="2026-06-25T10-00-01")
        with self.assertRaises(ValueError):
            self.reg.read_artifact(r, "../../../etc/passwd")

    def test_find_run_returns_none_for_missing(self) -> None:
        self.assertIsNone(self.reg.find_run("does-not-exist"))


class TestRegistryAnnotateDeleteReplay(unittest.TestCase):
    """Task 3: annotate / delete-archive / spawn_replay."""

    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.root = Path(self._tmp.name)
        self.reg = RunRegistry(self.root)

    def tearDown(self) -> None:
        self._tmp.cleanup()

    def _seed_sealed(self, *, category: str = "agents", run_id: str = "r1") -> tuple:
        g = self.reg.new_group(
            category=category,
            group_id="g1",
            eurodate="2026-06-25T10-00-00",
            label="test group",
        )
        r = self.reg.new_run(group=g, run_id=run_id, kind="agent", eurodate="2026-06-25T10-00-01")
        self.reg.write_artifact(r, "out.jsonl", '{"x":1}\n')
        self.reg.seal(r)
        return g, r

    def test_annotate_mutates_only_annotations(self) -> None:
        _, r = self._seed_sealed()

        # Record sha256 of meta.json + artifact before annotating.
        meta_bytes_before = (r.path / "meta.json").read_bytes()
        art_bytes_before = (r.path / "artifacts" / "out.jsonl").read_bytes()

        self.reg.annotate("r1", tags=["reviewed"], comment="looks good", retention="keep")

        # meta.json and artifact bytes MUST be unchanged.
        self.assertEqual((r.path / "meta.json").read_bytes(), meta_bytes_before)
        self.assertEqual((r.path / "artifacts" / "out.jsonl").read_bytes(), art_bytes_before)

        # Only annotations changed.
        ann = json.loads((r.path / "annotations.json").read_text())
        self.assertEqual(ann["tags"], ["reviewed"])
        self.assertEqual(ann["comment"], "looks good")

    def test_annotate_partial_update_preserves_other_fields(self) -> None:
        _, _ = self._seed_sealed()
        self.reg.annotate("r1", tags=["a", "b"])
        self.reg.annotate("r1", comment="updated")
        ann = json.loads(
            (self.reg.find_run("r1").path / "annotations.json").read_text()  # type: ignore[union-attr]
        )
        # tags were set first, then comment; both should be their last value
        self.assertEqual(ann["tags"], ["a", "b"])
        self.assertEqual(ann["comment"], "updated")

    def test_annotate_raises_for_missing_run(self) -> None:
        with self.assertRaises(KeyError):
            self.reg.annotate("no-such-run", tags=["x"])

    def test_delete_archives_then_purges(self) -> None:
        _, _ = self._seed_sealed()
        archive_path = self.reg.delete("r1")

        # Live dir gone.
        self.assertIsNone(self.reg.find_run("r1"))
        # Archive exists.
        self.assertTrue(archive_path.exists())
        self.assertTrue(tarfile.is_tarfile(archive_path))

    def test_delete_raises_for_missing_run(self) -> None:
        with self.assertRaises(KeyError):
            self.reg.delete("ghost")

    def test_spawn_replay_child_links_parent_and_leaves_parent_intact(self) -> None:
        _, parent_ref = self._seed_sealed()
        parent_meta_before = (parent_ref.path / "meta.json").read_bytes()

        child = self.reg.spawn_replay("r1", eurodate="2026-06-25T11-00-00")

        # Parent untouched.
        self.assertEqual((parent_ref.path / "meta.json").read_bytes(), parent_meta_before)

        # Child exists and has replay_of set.
        child_meta = json.loads((child.path / "meta.json").read_text())
        self.assertEqual(child_meta["replay_of"], "r1")
        self.assertEqual(child_meta["status"], "running")

    def test_spawn_replay_raises_for_missing_parent(self) -> None:
        with self.assertRaises(KeyError):
            self.reg.spawn_replay("no-parent", eurodate="2026-06-25T11-00-00")


# Needed for the tarfile assertion in test_delete_archives_then_purges.
import tarfile  # noqa: E402

if __name__ == "__main__":
    unittest.main()
