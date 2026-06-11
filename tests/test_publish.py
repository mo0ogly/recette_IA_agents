"""Tests for the repo publisher -- dry-run logic only, no network."""

from __future__ import annotations

import subprocess
import unittest

from recette.publish import build_plan, publish_repo


class TestPublishPlan(unittest.TestCase):
    def test_plan_targets_owner_and_lists_files(self):
        plan = build_plan("gh-pr-bot", "acme-test")
        self.assertEqual(plan.repo_name, "gh-pr-bot")
        self.assertEqual(plan.remote_url, "https://github.com/acme-test/gh-pr-bot.git")
        self.assertEqual(plan.visibility, "private")
        self.assertIn(".agentrail/manifest.json", plan.files)
        self.assertIn("agent/main.py", plan.files)
        self.assertFalse(plan.applied)

    def test_unknown_slug_raises(self):
        with self.assertRaises(FileNotFoundError):
            build_plan("does-not-exist", "acme-test")

    def test_dry_run_touches_nothing(self):
        calls = []

        def spy(cmd):
            calls.append(cmd)
            return ""

        plan = publish_repo("gh-pr-bot", "acme-test", dry_run=True, runner=spy)
        self.assertFalse(plan.applied)
        self.assertEqual(calls, [], "dry-run must not invoke any command")

    def test_apply_refuses_existing_repo(self):
        # runner that reports the repo already exists (gh repo view succeeds).
        def runner(cmd):
            if cmd[:3] == ["gh", "repo", "view"]:
                return "exists"
            return ""

        with self.assertRaises(RuntimeError):
            publish_repo("gh-pr-bot", "acme-test", dry_run=False, runner=runner)

    def test_apply_creates_when_absent(self):
        calls = []

        def runner(cmd):
            calls.append(cmd)
            if cmd[:3] == ["gh", "repo", "view"]:
                raise subprocess.CalledProcessError(1, cmd)  # not found
            return ""

        plan = publish_repo("gh-pr-bot", "acme-test", dry_run=False, runner=runner)
        self.assertTrue(plan.applied)
        # must create with gh and must NOT use --force anywhere
        joined = [" ".join(c) for c in calls]
        self.assertTrue(any(j.startswith("gh repo create acme-test/gh-pr-bot") for j in joined))
        self.assertFalse(any("--force" in j for j in joined))


if __name__ == "__main__":
    unittest.main()
