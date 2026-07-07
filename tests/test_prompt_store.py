"""PromptStore: overrides-only persistence for the assist prompt catalog."""

from __future__ import annotations

import json
import tempfile
import threading
import unittest
from pathlib import Path

from recette.api.prompt_store import MAX_OVERRIDE_CHARS, PromptStore


class TestPromptStore(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.path = Path(self.tmp.name) / "overrides.json"
        self.store = PromptStore(self.path)

    def tearDown(self) -> None:
        self.tmp.cleanup()

    def test_missing_file_reads_as_no_overrides(self) -> None:
        self.assertIsNone(self.store.get_override("chat.system"))
        self.assertEqual(self.store.resolve("chat.system", "default"), "default")
        self.assertEqual(self.store.overridden_ids(), set())

    def test_set_and_resolve_override(self) -> None:
        self.store.set_override("chat.system", "custom prompt")
        self.assertEqual(self.store.resolve("chat.system", "default"), "custom prompt")
        self.assertEqual(self.store.overridden_ids(), {"chat.system"})
        # Persisted shape: {"overrides": {id: value}} (the fixture contract).
        on_disk = json.loads(self.path.read_text(encoding="utf-8"))
        self.assertEqual(on_disk["overrides"]["chat.system"], "custom prompt")

    def test_hot_reload_reads_disk_on_every_resolve(self) -> None:
        self.store.set_override("chat.system", "v1")
        # A second store over the same file sees the override with no restart.
        other = PromptStore(self.path)
        self.assertEqual(other.resolve("chat.system", "default"), "v1")
        other.set_override("chat.system", "v2")
        self.assertEqual(self.store.resolve("chat.system", "default"), "v2")

    def test_delete_is_idempotent_and_resets_default(self) -> None:
        self.store.set_override("chat.system", "custom")
        self.store.delete_override("chat.system")
        self.assertEqual(self.store.resolve("chat.system", "default"), "default")
        # Unknown id: no error, no file churn.
        self.store.delete_override("never.set")

    def test_json_values_round_trip(self) -> None:
        value = {"debutant": "explique tout", "expert": "va aux faits"}
        self.store.set_override("help.levels", value)
        self.assertEqual(self.store.resolve("help.levels", {}), value)

    def test_corrupt_file_is_tolerated(self) -> None:
        self.path.write_text("{not json", encoding="utf-8")
        self.assertIsNone(self.store.get_override("chat.system"))
        self.assertEqual(self.store.resolve("chat.system", "default"), "default")
        # A write after corruption recovers the file.
        self.store.set_override("chat.system", "recovered")
        self.assertEqual(self.store.resolve("chat.system", "default"), "recovered")

    def test_oversized_override_rejected(self) -> None:
        with self.assertRaises(ValueError):
            self.store.set_override("chat.system", "x" * (MAX_OVERRIDE_CHARS + 1))

    def test_concurrent_writers_do_not_lose_overrides(self) -> None:
        # The RLock serializes read-modify-write cycles: two threads writing
        # distinct ids must both land.
        def write(prompt_id: str) -> None:
            for i in range(20):
                self.store.set_override(prompt_id, f"{prompt_id}-{i}")

        threads = [threading.Thread(target=write, args=(f"p{n}",)) for n in range(4)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()
        self.assertEqual(self.store.overridden_ids(), {"p0", "p1", "p2", "p3"})
        for n in range(4):
            self.assertEqual(self.store.get_override(f"p{n}"), f"p{n}-19")


if __name__ == "__main__":
    unittest.main()
