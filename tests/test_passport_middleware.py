"""Task 4 (unit): PassportAdmissionMiddleware -- per-action re-attestation.

Pins the middleware contract independently of the Gateway (a plain object with
`before`/`after`): observe never vetoes, enforce denies a non-trusted passport,
the veto reason lists only reason KINDS (no key/signature material, R8), the
passport FILE is cached per agent_id, and -- the point of this middleware -- the
VERDICT is recomputed per action against `request.timestamp`, so a passport that
expires mid-run is caught (I4: the clock is the captured input, not the wall clock).

Driven by the REAL corpus subjects (signed passports + real keyring) so the
oracle reuse is proven end-to-end (Ed25519 verify, [bundle] extra).
"""

from __future__ import annotations

import json
import shutil
import tempfile
import unittest
from pathlib import Path

from recette.platform import passport_middleware
from recette.platform.gateway import ActionRequest
from recette.platform.passport_middleware import PassportAdmissionMiddleware

_REPO_ROOT = Path(__file__).resolve().parents[1]
_TRUST_PATH = _REPO_ROOT / "corpus" / "keys" / "test-authority.trust.json"
_PRBOT_PASSPORT = (
    _REPO_ROOT / "corpus" / "repos" / "gh-pr-bot" / "repo" / ".inspect_ia_agents" / "passport.json"
)
_EXPIRED_PASSPORT = (
    _REPO_ROOT
    / "corpus"
    / "repos"
    / "gh-passport-expired"
    / "repo"
    / ".inspect_ia_agents"
    / "passport.json"
)

#: gh-pr-bot's passport carries exp = 2030-01-01T00:00:00Z, scope
#: ["read_repo", "open_pr"]. These two clocks straddle that exp.
_BEFORE_EXP = "2029-01-01T00:00:00Z"
_AFTER_EXP = "2031-01-01T00:00:00Z"


def _load(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def _request(agent_id: str, timestamp: str) -> ActionRequest:
    return ActionRequest(
        agent_id=agent_id,
        action_type="read_repo",
        target_system="github",
        resource="github/acme/repo",
        payload={},
        timestamp=timestamp,
    )


class _PassportDir:
    """A temp passport directory holding one `<agent_id>.json` per agent."""

    def __init__(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.path = Path(self._tmp.name)

    def place(self, agent_id: str, source: Path) -> None:
        shutil.copyfile(source, self.path / f"{agent_id}.json")

    def close(self) -> None:
        self._tmp.cleanup()


class PassportMiddlewareTest(unittest.TestCase):
    def setUp(self) -> None:
        self.trust = _load(_TRUST_PATH)
        self.dir = _PassportDir()
        self.addCleanup(self.dir.close)
        self.prbot_scope = list(_load(_PRBOT_PASSPORT)["scope"])

    def _mw(
        self, *, enforce: bool, declared: list[str] | None = None
    ) -> PassportAdmissionMiddleware:
        scope = self.prbot_scope if declared is None else declared
        return PassportAdmissionMiddleware(
            trust=self.trust,
            passport_dir=self.dir.path,
            enforce=enforce,
            declared_for=lambda _aid: scope,
        )

    def test_enforce_untrusted_expired_passport_vetoes(self) -> None:
        # gh-passport-expired: signed but past its exp -> untrusted at any now.
        self.dir.place("expired-bot", _EXPIRED_PASSPORT)
        mw = self._mw(enforce=True, declared=list(_load(_EXPIRED_PASSPORT)["scope"]))
        reason = mw.before(_request("expired-bot", _BEFORE_EXP))
        self.assertIsNotNone(reason)
        assert reason is not None  # narrow for type-checkers
        self.assertIn("untrusted_passport", reason)
        self.assertIn("expired", reason)

    def test_observe_never_vetoes(self) -> None:
        # Even an untrusted passport is NOT vetoed in observe mode.
        self.dir.place("expired-bot", _EXPIRED_PASSPORT)
        mw = self._mw(enforce=False, declared=list(_load(_EXPIRED_PASSPORT)["scope"]))
        self.assertIsNone(mw.before(_request("expired-bot", _BEFORE_EXP)))

    def test_enforce_trusted_before_exp_passes(self) -> None:
        self.dir.place("pr-bot", _PRBOT_PASSPORT)
        mw = self._mw(enforce=True)
        self.assertIsNone(mw.before(_request("pr-bot", _BEFORE_EXP)))

    def test_mid_run_expiry_same_passport_two_timestamps(self) -> None:
        # SAME passport file, cached once; the VERDICT is recomputed per action.
        # timestamp < exp -> trusted (None); timestamp > exp -> expired veto.
        self.dir.place("pr-bot", _PRBOT_PASSPORT)
        mw = self._mw(enforce=True)
        self.assertIsNone(mw.before(_request("pr-bot", _BEFORE_EXP)))
        reason = mw.before(_request("pr-bot", _AFTER_EXP))
        self.assertIsNotNone(reason)
        assert reason is not None
        self.assertIn("untrusted_passport", reason)
        self.assertIn("expired", reason)

    def test_scope_overreach_when_declared_has_extra_family(self) -> None:
        # Declared scope adds a family absent from the signed passport scope.
        self.dir.place("pr-bot", _PRBOT_PASSPORT)
        overreach = [*self.prbot_scope, "push"]
        mw = self._mw(enforce=True, declared=overreach)
        reason = mw.before(_request("pr-bot", _BEFORE_EXP))
        self.assertIsNotNone(reason)
        assert reason is not None
        self.assertIn("untrusted_passport", reason)
        self.assertIn("scope_overreach", reason)
        # R8: only reason KINDS surface; the extra family list is not leaked.
        self.assertNotIn("push", reason)

    def test_passport_file_cached_verdict_recomputed(self) -> None:
        # The FILE is loaded once per agent_id; the verdict still recomputes per
        # action (proven by the mid-run expiry flip on a single cached load).
        self.dir.place("pr-bot", _PRBOT_PASSPORT)
        calls: list[str] = []
        original = passport_middleware.load_agent_passport

        def _counting(agent_id: str, base_dir: object) -> object:
            calls.append(agent_id)
            return original(agent_id, base_dir)

        passport_middleware.load_agent_passport = _counting  # type: ignore[assignment]
        try:
            mw = self._mw(enforce=True)
            self.assertIsNone(mw.before(_request("pr-bot", _BEFORE_EXP)))
            self.assertIsNotNone(mw.before(_request("pr-bot", _AFTER_EXP)))
            self.assertIsNone(mw.before(_request("pr-bot", _BEFORE_EXP)))
        finally:
            passport_middleware.load_agent_passport = original  # type: ignore[assignment]
        # Three before() calls, one cached file load for the single agent_id.
        self.assertEqual(calls, ["pr-bot"])


if __name__ == "__main__":
    unittest.main()
