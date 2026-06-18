"""GET /catalog/rust-summary bridges the native Rust discovery engine into the API.

Two properties matter: it is FAIL-SAFE (an unbuilt binary yields available=false,
never a 500), and when the binary IS built it AGREES with the Python projection
(the cross-engine invariant guarantee). The real-engine test is skipped when the
binary is absent (CI without the Rust toolchain) -- never a false failure (R18).
"""

from __future__ import annotations

import os
import unittest
from pathlib import Path

try:
    from fastapi.testclient import TestClient

    from recette.api.app import create_app

    _HAS_FASTAPI = True
except ImportError:  # pragma: no cover - only without the [api] extra
    _HAS_FASTAPI = False

_BIN_ENV = "INSPECT_IA_AGENTS_CATALOG_RUST_BIN"
_REPO_ROOT = Path(__file__).resolve().parents[1]
_DEFAULT_BIN = _REPO_ROOT / "discoveryprobe" / "target" / "release" / "discoveryprobe-catalog"


@unittest.skipUnless(_HAS_FASTAPI, "requires the [api] extra (fastapi)")
class TestCatalogRustBridge(unittest.TestCase):
    def setUp(self) -> None:
        self.client = TestClient(create_app())
        self._saved = os.environ.pop(_BIN_ENV, None)

    def tearDown(self) -> None:
        if self._saved is None:
            os.environ.pop(_BIN_ENV, None)
        else:
            os.environ[_BIN_ENV] = self._saved

    def test_failsafe_when_binary_absent(self) -> None:
        os.environ[_BIN_ENV] = "/nonexistent/discoveryprobe-catalog"
        resp = self.client.get("/catalog/rust-summary")
        self.assertEqual(resp.status_code, 200)
        body = resp.json()
        self.assertFalse(body["available"])
        self.assertIn("reason", body)
        self.assertNotIn("summary", body)

    @unittest.skipUnless(_DEFAULT_BIN.is_file(), "rust catalog binary not built")
    def test_real_engine_agrees_with_python(self) -> None:
        os.environ[_BIN_ENV] = str(_DEFAULT_BIN)
        resp = self.client.get("/catalog/rust-summary")
        self.assertEqual(resp.status_code, 200)
        body = resp.json()
        self.assertTrue(body["available"], body.get("reason"))
        # the Rust engine produces the invariant summary shape
        self.assertEqual(set(body["summary"]), {"total", "unique", "with_tools", "tags"})
        # and it AGREES with the Python projection (cross-engine invariant)
        self.assertTrue(body["agreement"])
        self.assertEqual(body["summary"], body["python_summary"])


if __name__ == "__main__":
    unittest.main()
