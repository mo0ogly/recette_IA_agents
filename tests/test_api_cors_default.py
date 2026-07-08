"""DEFAULT_CORS_ORIGINS must cover the canonical console port.

Regression guard: the console canonical port lives in cicd/lib/common.sh
(CONSOLE_PORT default). When it moved 5173 -> 5174, the API CORS default was
not updated and every bare-host console got 'Failed to fetch' (preflight 400
'Disallowed CORS origin'). This test parses the canonical port from
common.sh and asserts the API default allows it on both loopback spellings,
so a future port move fails loudly here instead of silently in the browser.
"""

from __future__ import annotations

import re
import unittest
from pathlib import Path

from recette.api.app import DEFAULT_CORS_ORIGINS

REPO_ROOT = Path(__file__).resolve().parents[1]
COMMON_SH = REPO_ROOT / "cicd" / "lib" / "common.sh"


class TestDefaultCorsOrigins(unittest.TestCase):
    def _canonical_console_port(self) -> str:
        text = COMMON_SH.read_text(encoding="utf-8")
        match = re.search(r"INSPECT_IA_AGENTS_CONSOLE_PORT:-(\d+)", text)
        self.assertIsNotNone(
            match, "CONSOLE_PORT default not found in cicd/lib/common.sh"
        )
        assert match is not None  # narrow for type checkers
        return match.group(1)

    def test_default_allows_canonical_console_origin(self) -> None:
        port = self._canonical_console_port()
        origins = DEFAULT_CORS_ORIGINS.split(",")
        for origin in (f"http://localhost:{port}", f"http://127.0.0.1:{port}"):
            self.assertIn(
                origin,
                origins,
                f"{origin} missing from DEFAULT_CORS_ORIGINS -- the console "
                "canonical port moved without updating the API CORS default",
            )

    def test_no_wildcard(self) -> None:
        self.assertNotIn("*", DEFAULT_CORS_ORIGINS)
