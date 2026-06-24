"""The `surface` CLI subcommand prints the detection scorecard and exits 0 when
the corpus has no false negative."""

from __future__ import annotations

import io
import json
import unittest
from contextlib import redirect_stdout

from recette.__main__ import _cmd_surface


class TestSurfaceCli(unittest.TestCase):
    def test_cmd_surface_prints_scorecard_and_exits_zero(self) -> None:
        buf = io.StringIO()
        with redirect_stdout(buf):
            rc = _cmd_surface()
        self.assertEqual(rc, 0)
        payload = json.loads(buf.getvalue())
        self.assertTrue(payload["ok"])
        self.assertEqual(payload["total_agents"], 4)  # thesis corpus broadened (#9)


if __name__ == "__main__":
    unittest.main()
