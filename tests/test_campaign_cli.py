"""CLI surface of recette.campaign: report rendering, list, main dispatch.

The runner itself (CampaignRunner against the API) is covered by the gateway
harness tests; this file hardens the previously untested CLI layer: report
rendering for every verdict shape, directory listing incl. invalid files, and
main() error paths.
"""

from __future__ import annotations

import argparse
import contextlib
import io
import json
import tempfile
import unittest
from pathlib import Path

from recette.campaign import (
    ActionResult,
    CampaignError,
    CampaignReport,
    _cmd_list,
    _render_report,
    main,
    validate_campaign,
)


def _result(**overrides: object) -> ActionResult:
    base: dict = {
        "index": 0,
        "agent_id": "bot",
        "target_system": "okta",
        "action_type": "list_users",
        "resource": "org/acme",
        "verdict": "allow",
        "approval_state": "none",
        "executed": True,
        "event_id": "EV01",
        "side_effect_hash": "abc",
        "expected_verdict": "allow",
        "matches_expectation": True,
        "rationale": None,
    }
    base.update(overrides)
    return ActionResult(**base)


class TestRenderReport(unittest.TestCase):
    def test_pass_report_renders_ok_lines_and_intact_chain(self) -> None:
        report = CampaignReport(name="demo", objective="prove allow", teaching="reads pass")
        report.results.append(_result())
        report.chain_ok = True
        text = _render_report(report)
        self.assertIn("campaign: demo", text)
        self.assertIn("objective: prove allow", text)
        self.assertIn("[OK] #0 bot okta/list_users -> allow/none", text)
        self.assertIn("audit chain: intact", text)
        self.assertIn("teaching: reads pass", text)
        self.assertIn("result: PASS", text)

    def test_mismatch_renders_expected_suffix_and_fail(self) -> None:
        report = CampaignReport(name="demo")
        report.results.append(
            _result(verdict="allow", expected_verdict="deny", matches_expectation=False)
        )
        report.chain_ok = True
        text = _render_report(report)
        self.assertIn("[MISMATCH]", text)
        self.assertIn("expected=deny", text)
        self.assertIn("result: FAIL", text)

    def test_pending_approvals_and_rationale_are_listed(self) -> None:
        report = CampaignReport(name="demo")
        report.results.append(
            _result(
                verdict="escalate",
                approval_state="pending",
                executed=False,
                event_id="EV99",
                expected_verdict="escalate",
                rationale="high blast radius",
            )
        )
        report.chain_ok = True
        text = _render_report(report)
        self.assertIn("pending approvals: 1", text)
        self.assertIn("EV99", text)
        self.assertIn("why: high blast radius", text)

    def test_broken_chain_renders_broken_and_fails(self) -> None:
        report = CampaignReport(name="demo")
        report.results.append(_result())
        report.chain_ok = False
        text = _render_report(report)
        self.assertIn("audit chain: BROKEN", text)
        self.assertIn("result: FAIL", text)


_ACTION: dict = {
    "agent_id": "bot",
    "target_system": "okta",
    "action_type": "list_users",
    "resource": "org/acme",
    "expect": "allow",
}

VALID_DOC: dict = {
    "name": "demo",
    "objective": "obj",
    "agents": [{"id": "bot", "runtime": "lab"}],
    "actions": [_ACTION],
}


class TestValidateCampaign(unittest.TestCase):
    def test_valid_document_passes(self) -> None:
        validate_campaign(json.loads(json.dumps(VALID_DOC)))

    def test_rejections(self) -> None:
        cases: list[tuple[str, dict]] = [
            ("missing name", {**VALID_DOC, "name": ""}),
            ("non-string objective", {**VALID_DOC, "objective": 3}),
            ("agents not a list", {**VALID_DOC, "agents": "x"}),
            ("agent without runtime", {**VALID_DOC, "agents": [{"id": "a"}]}),
            ("empty actions", {**VALID_DOC, "actions": []}),
            ("action missing fields", {**VALID_DOC, "actions": [{"agent_id": "a"}]}),
            ("bad expect", {**VALID_DOC, "actions": [{**_ACTION, "expect": "maybe"}]}),
            ("non-string rationale", {**VALID_DOC, "actions": [{**_ACTION, "rationale": 1}]}),
        ]
        for label, doc in cases:
            with self.subTest(case=label), self.assertRaises(CampaignError):
                validate_campaign(doc)


class TestCliList(unittest.TestCase):
    def test_lists_valid_and_flags_invalid_files(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            good = Path(tmp) / "good.campaign.json"
            good.write_text(json.dumps(VALID_DOC), encoding="utf-8")
            bad = Path(tmp) / "bad.campaign.json"
            bad.write_text("{not json", encoding="utf-8")
            out = io.StringIO()
            with contextlib.redirect_stdout(out):
                code = main(["list", "--dir", tmp])
            self.assertEqual(code, 0)
            text = out.getvalue()
            self.assertIn("good.campaign.json: demo (1 actions)", text)
            self.assertIn("obj", text)
            self.assertIn("bad.campaign.json: INVALID", text)

    def test_empty_directory_says_so(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            out = io.StringIO()
            with contextlib.redirect_stdout(out):
                code = _cmd_list(argparse.Namespace(dir=tmp))
            self.assertEqual(code, 0)
            self.assertIn("no campaign files", out.getvalue())


class TestMainErrors(unittest.TestCase):
    def test_run_with_missing_file_exits_2(self) -> None:
        err = io.StringIO()
        with contextlib.redirect_stderr(err):
            code = main(["run", "/nonexistent/file.campaign.json", "--api", "http://x"])
        self.assertEqual(code, 2)
        self.assertIn("error:", err.getvalue())

    def test_run_with_malformed_campaign_exits_2(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "bad.campaign.json"
            path.write_text(json.dumps({"name": "x", "actions": []}), encoding="utf-8")
            err = io.StringIO()
            with contextlib.redirect_stderr(err):
                code = main(["run", str(path), "--api", "http://x"])
            self.assertEqual(code, 2)
            self.assertIn("actions", err.getvalue())


if __name__ == "__main__":
    unittest.main()
