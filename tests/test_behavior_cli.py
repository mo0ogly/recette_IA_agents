"""CLI surface for `recette analyze` (wave / replay). Builds the real parser and
drives the handlers over a temp evidence bundle -- proves the wiring + the
human/JSON rendering + the replay byte-equality path. Pure, zero install.
"""

from __future__ import annotations

import io
import json
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path

from recette.behavior import EvidenceBundle
from recette.cli.behavior_cmds import _cmd_analyze_replay, _cmd_analyze_wave
from recette.cli.parser import build_parser

_RECORDING = {
    "recordings": [
        {
            "agent_id": "exfil-bot",
            "surfaces": {
                "ebpf_wire": [
                    "connect:127.0.0.1:9101",
                    "open:/home/bot/.aws/credentials",
                    "connect:8.8.8.8:443",
                ]
            },
        }
    ]
}


def _write_bundle(folder: str) -> str:
    EvidenceBundle.from_dict(
        {
            "recording": _RECORDING,
            "servers": [{"id": "gh-mock", "mode": "mock_local", "port": 9101}],
            "declared": {
                "exfil-bot": {"scope": ["read_repo"], "systems": ["gh-mock"], "decided": []}
            },
        }
    ).save(folder)
    return folder


class TestAnalyzeParser(unittest.TestCase):
    def test_parser_accepts_wave_and_replay(self) -> None:
        parser = build_parser()
        a = parser.parse_args(["analyze", "wave", "--evidence", "x", "--threat", "exfil"])
        self.assertEqual((a.command, a.analyze_cmd, a.threat), ("analyze", "wave", "exfil"))
        b = parser.parse_args(["analyze", "replay", "--evidence", "x", "--report", "r.json"])
        self.assertEqual((b.command, b.analyze_cmd, b.report), ("analyze", "replay", "r.json"))


class TestAnalyzeHandlers(unittest.TestCase):
    def test_wave_summary_then_replay_ok(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            folder = _write_bundle(tmp)
            # JSON wave -> file
            buf = io.StringIO()
            with redirect_stdout(buf):
                rc = _cmd_analyze_wave(folder, None, "exfil", True)
            self.assertEqual(rc, 0)
            report = json.loads(buf.getvalue())
            self.assertEqual(report["threat"], "exfil")
            report_path = Path(tmp) / "report.json"
            report_path.write_text(json.dumps(report), encoding="utf-8")
            # replay against that report -> byte identical
            buf2 = io.StringIO()
            with redirect_stdout(buf2):
                rc2 = _cmd_analyze_replay(folder, None, "exfil", str(report_path))
            self.assertEqual(rc2, 0)
            self.assertIn("REPLAY OK", buf2.getvalue())

    def test_replay_mismatch_returns_1(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            folder = _write_bundle(tmp)
            bogus = Path(tmp) / "bogus.json"
            bogus.write_text(json.dumps({"agents": []}), encoding="utf-8")
            buf = io.StringIO()
            with redirect_stdout(buf):
                rc = _cmd_analyze_replay(folder, None, "exfil", str(bogus))
            self.assertEqual(rc, 1)
            self.assertIn("MISMATCH", buf.getvalue())

    def test_bad_evidence_returns_2(self) -> None:
        rc = _cmd_analyze_wave("/nonexistent/path", None, None, False)
        self.assertEqual(rc, 2)


if __name__ == "__main__":
    unittest.main()
