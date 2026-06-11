"""LB6 tests: real-mode allowlist guard (no real creds -- LabForge as the wrapped inner)."""

from __future__ import annotations

import os
import unittest

from recette.forge import LabForge
from recette.realmode import (
    ALLOWLIST_ENV,
    AllowlistForge,
    RealModeError,
    build_real_forge,
    is_allowed,
    parse_allowlist,
)


def _exec(forge, resource):
    return forge.execute(
        agent_id="a",
        principal="p",
        target_system="github",
        action_type="read_repo",
        resource=resource,
    )


class TestAllowlist(unittest.TestCase):
    def test_parse_allowlist(self):
        self.assertEqual(parse_allowlist("acme-test/*, demo/*"), ["acme-test/*", "demo/*"])
        self.assertEqual(parse_allowlist(""), [])
        self.assertEqual(parse_allowlist(None), [])

    def test_is_allowed_globs(self):
        self.assertTrue(is_allowed("acme-test/x", ["acme-test/*"]))
        self.assertFalse(is_allowed("prod/x", ["acme-test/*"]))

    def test_empty_allowlist_is_refused(self):
        with self.assertRaises(RealModeError):
            AllowlistForge(LabForge(), [])

    def test_in_list_resource_executes(self):
        forge = AllowlistForge(LabForge(), ["acme-test/*"])
        action = _exec(forge, "acme-test/widgets")
        self.assertEqual(action.resource, "acme-test/widgets")
        self.assertEqual(len(forge.action_log), 1)

    def test_out_of_list_resource_is_blocked(self):
        forge = AllowlistForge(LabForge(), ["acme-test/*"])
        with self.assertRaises(RealModeError):
            _exec(forge, "prod/secret")


class TestBuildRealForge(unittest.TestCase):
    def test_missing_token_raises(self):
        old = os.environ.pop("AGENTRAIL_GITHUB_TOKEN", None)
        try:
            with self.assertRaises(RealModeError):
                build_real_forge("github")
        finally:
            if old is not None:
                os.environ["AGENTRAIL_GITHUB_TOKEN"] = old

    def test_missing_allowlist_raises(self):
        old_t = os.environ.get("AGENTRAIL_GITHUB_TOKEN")
        old_a = os.environ.pop(ALLOWLIST_ENV, None)
        os.environ["AGENTRAIL_GITHUB_TOKEN"] = "dummy-test-token"  # noqa: S105
        try:
            with self.assertRaises(RealModeError):
                build_real_forge("github")
        finally:
            if old_t is None:
                os.environ.pop("AGENTRAIL_GITHUB_TOKEN", None)
            else:
                os.environ["AGENTRAIL_GITHUB_TOKEN"] = old_t
            if old_a is not None:
                os.environ[ALLOWLIST_ENV] = old_a


if __name__ == "__main__":
    unittest.main()
