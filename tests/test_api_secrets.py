"""BackendSecretStore: per-backend AI keys in a gitignored file (R8).

The store keeps API keys OUT of the versioned config. These tests cover the
set/get/delete roundtrip, validation, idempotent delete, and that an atomic
write survives a reload (a fresh store instance reads the same file).
"""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from recette.api.secret_store import BackendSecretStore


class TestBackendSecretStore(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.path = Path(self.tmp.name) / "backend_secrets.json"
        self.store = BackendSecretStore(self.path)

    def tearDown(self) -> None:
        self.tmp.cleanup()

    def test_set_get_delete_roundtrip(self) -> None:
        self.store.set_secret("b1", "sk-test-123")
        self.assertEqual(self.store.get_secret("b1"), "sk-test-123")
        self.store.delete_secret("b1")
        self.assertIsNone(self.store.get_secret("b1"))

    def test_empty_api_key_raises_value_error(self) -> None:
        with self.assertRaises(ValueError):
            self.store.set_secret("b1", "")
        with self.assertRaises(ValueError):
            self.store.set_secret("b1", "   ")
        self.assertFalse(self.store.is_configured("b1"))

    def test_get_unknown_is_none(self) -> None:
        self.assertIsNone(self.store.get_secret("nope"))

    def test_is_configured(self) -> None:
        self.assertFalse(self.store.is_configured("b1"))
        self.store.set_secret("b1", "k")
        self.assertTrue(self.store.is_configured("b1"))

    def test_delete_is_idempotent(self) -> None:
        # Deleting an unknown id does not raise.
        self.store.delete_secret("nope")
        self.store.set_secret("b1", "k")
        self.store.delete_secret("b1")
        self.store.delete_secret("b1")
        self.assertFalse(self.store.is_configured("b1"))

    def test_configured_ids(self) -> None:
        self.assertEqual(self.store.configured_ids(), set())
        self.store.set_secret("b1", "k1")
        self.store.set_secret("b2", "k2")
        self.assertEqual(self.store.configured_ids(), {"b1", "b2"})

    def test_atomic_write_survives_reload(self) -> None:
        self.store.set_secret("b1", "persisted-key")
        reloaded = BackendSecretStore(self.path)
        self.assertEqual(reloaded.get_secret("b1"), "persisted-key")
        self.assertTrue(reloaded.is_configured("b1"))

    def test_missing_file_is_empty(self) -> None:
        # No file written yet: reads return empty, never raise.
        self.assertIsNone(self.store.get_secret("b1"))
        self.assertEqual(self.store.configured_ids(), set())
        self.assertFalse(self.path.exists())


if __name__ == "__main__":
    unittest.main()
