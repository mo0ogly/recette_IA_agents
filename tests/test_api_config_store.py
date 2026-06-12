"""U1: versioned config store for Lane B agents + AI backends."""

from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from recette.api.config_store import ConfigStore


class TestConfigStore(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.path = Path(self.tmp.name) / "cfg.json"
        self.store = ConfigStore(self.path)

    def tearDown(self) -> None:
        self.tmp.cleanup()

    def test_missing_file_reads_empty_default(self) -> None:
        cfg = self.store.read()
        self.assertEqual(cfg["schema_version"], "1.0")
        self.assertEqual(cfg["agents"], [])
        self.assertEqual(cfg["ai_backends"], [])
        self.assertFalse(self.path.exists())  # read never creates

    def test_add_agent_persists_and_roundtrips(self) -> None:
        agent = {
            "id": "a1",
            "principal": "acme-bot@github",
            "target_system": "github",
            "goal": "bump deps",
            "capability_scope": ["read_repo", "open_pr"],
            "ai_backend_id": "b1",
            "runtime": "lab",
        }
        self.store.add_agent(agent)
        on_disk = json.loads(self.path.read_text())
        self.assertEqual(on_disk["agents"], [agent])
        # a fresh store over the same file sees it
        self.assertEqual(ConfigStore(self.path).get_agent("a1"), agent)

    def test_add_ai_backend_rejects_key_fields(self) -> None:
        with self.assertRaises(ValueError):
            self.store.add_ai_backend(
                {"id": "b1", "provider": "anthropic", "model": "x", "api_key": "sekret"}
            )

    def test_duplicate_id_rejected(self) -> None:
        self.store.add_ai_backend({"id": "b1", "provider": "openai", "model": "gpt"})
        with self.assertRaises(ValueError):
            self.store.add_ai_backend({"id": "b1", "provider": "openai", "model": "gpt"})

    def test_update_and_delete_agent(self) -> None:
        self.store.add_agent(
            {
                "id": "a1",
                "principal": "p",
                "target_system": "github",
                "goal": "g",
                "capability_scope": [],
                "ai_backend_id": "b1",
                "runtime": "lab",
            }
        )
        self.store.update_agent("a1", {"goal": "g2"})
        self.assertEqual(self.store.get_agent("a1")["goal"], "g2")
        self.store.delete_agent("a1")
        self.assertIsNone(self.store.get_agent("a1"))
