"""RealForge construction + write-gating fail-safe, without the [real] extra.

The PyGithub / python-gitlab SDKs are injected as in-test fake modules so the
constructor paths run everywhere. What matters here is the SAFETY contract:
a RealForge with enable_writes=False must refuse every write action with
PermissionError (fail-safe), and the action log must keep the LabForge shape.
No network: the fakes never talk to anything.
"""

from __future__ import annotations

import sys
import types
import unittest

from recette.forge import RealForge


class _FakeGithub:
    def __init__(self, token: str) -> None:
        self.token = token


class _FakeGitlab:
    def __init__(self, private_token: str | None = None) -> None:
        self.private_token = private_token


def _install_fake_sdks() -> None:
    github_mod = types.ModuleType("github")
    github_mod.Github = _FakeGithub  # type: ignore[attr-defined]
    gitlab_mod = types.ModuleType("gitlab")
    gitlab_mod.Gitlab = _FakeGitlab  # type: ignore[attr-defined]
    sys.modules["github"] = github_mod
    sys.modules["gitlab"] = gitlab_mod


class TestRealForge(unittest.TestCase):
    def setUp(self) -> None:
        self._saved = {name: sys.modules.get(name) for name in ("github", "gitlab")}
        _install_fake_sdks()
        self.addCleanup(self._restore_modules)

    def _restore_modules(self) -> None:
        for name, mod in self._saved.items():
            if mod is None:
                sys.modules.pop(name, None)
            else:
                sys.modules[name] = mod

    def test_github_and_gitlab_clients_are_constructed_with_the_token(self) -> None:
        gh_client = RealForge("github", token="tok-gh")._client
        assert isinstance(gh_client, _FakeGithub)
        self.assertEqual(gh_client.token, "tok-gh")
        gl_client = RealForge("gitlab", token="tok-gl")._client
        assert isinstance(gl_client, _FakeGitlab)
        self.assertEqual(gl_client.private_token, "tok-gl")

    def test_write_action_is_blocked_by_default(self) -> None:
        forge = RealForge("github", token="tok")
        with self.assertRaises(PermissionError) as ctx:
            forge.execute(
                agent_id="a1",
                principal="bot@acme",
                target_system="github",
                action_type="push",
                resource="acme/x",
            )
        self.assertIn("enable_writes=False", str(ctx.exception))
        self.assertEqual(forge.action_log, [])

    def test_read_action_is_allowed_and_logged_without_writes(self) -> None:
        forge = RealForge("github", token="tok")
        action = forge.execute(
            agent_id="a1",
            principal="bot@acme",
            target_system="github",
            action_type="read_repo",
            resource="acme/x",
        )
        self.assertEqual(action.mode, "read")
        self.assertEqual(action.event_id, "evt-0001")
        self.assertEqual(len(forge.action_log), 1)

    def test_enable_writes_allows_write_actions(self) -> None:
        forge = RealForge("github", token="tok", enable_writes=True)
        action = forge.execute(
            agent_id="a1",
            principal="bot@acme",
            target_system="github",
            action_type="push",
            resource="acme/x",
        )
        self.assertEqual(action.mode, "write")
        self.assertEqual([a.action_type for a in forge.action_log], ["push"])

    def test_unknown_target_system_is_rejected(self) -> None:
        with self.assertRaises(ValueError):
            RealForge("bitbucket", token="tok")


if __name__ == "__main__":
    unittest.main()
