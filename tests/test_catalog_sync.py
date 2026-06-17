"""The catalog sync refreshes the local registry from a configurable source.

Exercised entirely offline via a `file://` source (R20: no network in tests);
proves the round-trip + every fail-safe branch.
"""

from __future__ import annotations

import json
import os
import tempfile
import unittest
from pathlib import Path

from recette.catalog_sync import CatalogSyncError, sync_catalog

_REGISTRY = {
    "version": "1.0",
    "entries": [
        {"name": "github-pr-bot", "version": "1.0.0", "associated_tools": ["t"]},
        {"name": "silent-scanner", "version": "0.1.0"},
    ],
}


class TestCatalogSync(unittest.TestCase):
    def test_syncs_from_a_file_url_to_the_destination(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            src = Path(tmp) / "source.json"
            src.write_text(json.dumps(_REGISTRY), encoding="utf-8")
            dest = Path(tmp) / "nested" / "agent-registry.json"
            written = sync_catalog(url=src.as_uri(), dest=dest)
            self.assertEqual(written, dest)
            data = json.loads(dest.read_text(encoding="utf-8"))
            self.assertEqual(len(data["entries"]), 2)
            self.assertEqual(data["entries"][0]["name"], "github-pr-bot")

    def test_unset_source_raises(self) -> None:
        saved = os.environ.pop("INSPECT_IA_AGENTS_CATALOG_REGISTRY_URL", None)
        try:
            with self.assertRaises(CatalogSyncError):
                sync_catalog(url=None)
        finally:
            if saved is not None:
                os.environ["INSPECT_IA_AGENTS_CATALOG_REGISTRY_URL"] = saved

    def test_unsupported_scheme_raises(self) -> None:
        with self.assertRaises(CatalogSyncError):
            sync_catalog(url="ftp://example.invalid/registry.json")

    def test_non_catalog_json_does_not_overwrite(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            src = Path(tmp) / "bad.json"
            src.write_text(json.dumps({"version": "1.0"}), encoding="utf-8")  # no entries
            dest = Path(tmp) / "out.json"
            dest.write_text("PRESERVED", encoding="utf-8")
            with self.assertRaises(CatalogSyncError):
                sync_catalog(url=src.as_uri(), dest=dest)
            # The good local file was left untouched.
            self.assertEqual(dest.read_text(encoding="utf-8"), "PRESERVED")

    def test_invalid_json_raises(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            src = Path(tmp) / "broken.json"
            src.write_text("{not json", encoding="utf-8")
            with self.assertRaises(CatalogSyncError):
                sync_catalog(url=src.as_uri(), dest=Path(tmp) / "out.json")


if __name__ == "__main__":
    unittest.main()
