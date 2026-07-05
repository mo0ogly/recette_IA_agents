"""Task 1: the admission primitive `admit_agent` reusing the attestation ORACLE.

`recette.platform.admission.admit_agent` wraps `recette.adapters.attest_passport`
into an `AdmissionVerdict` and adds the observe/enforce gate + fail-safe. This
test suite is written FIRST (TDD): it pins the observe/enforce semantics, the
fail-safe (an oracle exception NEVER yields trusted/admitted-in-enforce), the
loaders' I/O behaviour, and replay determinism (I4: `now` is an INPUT).

The trusted case is driven by the REAL corpus subject `gh-pr-bot` (a signed,
in-date passport) against the REAL corpus keyring, so the reuse of the oracle is
proven end-to-end (Ed25519 verify included, [bundle] extra).
"""

from __future__ import annotations

import json
import os
import tempfile
import unittest
from pathlib import Path

from recette.platform import admission
from recette.platform.admission import (
    AdmissionVerdict,
    admit_agent,
    enforce_from_env,
    load_agent_passport,
    load_trust,
)

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

#: Injected clock (I4): a fixed reference BEFORE gh-pr-bot's exp (2030) and AFTER
#: gh-passport-expired's exp (2020). Never the wall clock.
_NOW = "2027-01-01T00:00:00Z"


def _load(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


class UnsignedAdmissionTest(unittest.TestCase):
    """No passport -> unsigned; the gate decides admission."""

    def setUp(self) -> None:
        self.trust = _load(_TRUST_PATH)

    def test_unsigned_observe_admits(self) -> None:
        verdict = admit_agent(None, ["read_repo"], self.trust, _NOW, enforce=False)
        self.assertEqual(verdict.status, "unsigned")
        self.assertTrue(verdict.admitted)
        self.assertEqual(verdict.mode, "observe")
        self.assertEqual(verdict.reasons, [])

    def test_unsigned_enforce_denies(self) -> None:
        verdict = admit_agent(None, ["read_repo"], self.trust, _NOW, enforce=True)
        self.assertEqual(verdict.status, "unsigned")
        self.assertFalse(verdict.admitted)
        self.assertEqual(verdict.mode, "enforce")


class TrustedAdmissionTest(unittest.TestCase):
    """Real corpus subject gh-pr-bot: signed, in-date, declared within scope."""

    def setUp(self) -> None:
        self.trust = _load(_TRUST_PATH)
        self.passport = _load(_PRBOT_PASSPORT)
        self.declared = list(self.passport["scope"])

    def test_trusted_admitted_in_both_modes(self) -> None:
        for enforce in (False, True):
            with self.subTest(enforce=enforce):
                verdict = admit_agent(
                    self.passport, self.declared, self.trust, _NOW, enforce=enforce
                )
                self.assertEqual(verdict.status, "trusted")
                self.assertTrue(verdict.admitted)
                self.assertEqual(verdict.reasons, [])


class ExpiredAdmissionTest(unittest.TestCase):
    """Real corpus subject gh-passport-expired: signed but past its exp."""

    def setUp(self) -> None:
        self.trust = _load(_TRUST_PATH)
        self.passport = _load(_EXPIRED_PASSPORT)
        self.declared = list(self.passport["scope"])

    def test_untrusted_expired_gate(self) -> None:
        observe = admit_agent(self.passport, self.declared, self.trust, _NOW, enforce=False)
        enforce = admit_agent(self.passport, self.declared, self.trust, _NOW, enforce=True)
        for verdict in (observe, enforce):
            self.assertEqual(verdict.status, "untrusted")
            self.assertIn({"kind": "expired"}, verdict.reasons)
        self.assertTrue(observe.admitted)
        self.assertFalse(enforce.admitted)


class EnforceFromEnvTest(unittest.TestCase):
    """The env toggle: only the exact string "enforce" (case-insensitive) is True."""

    def setUp(self) -> None:
        self._saved = os.environ.get(admission.ENFORCE_ENV)
        os.environ.pop(admission.ENFORCE_ENV, None)

    def tearDown(self) -> None:
        if self._saved is None:
            os.environ.pop(admission.ENFORCE_ENV, None)
        else:
            os.environ[admission.ENFORCE_ENV] = self._saved

    def test_unset_is_false(self) -> None:
        self.assertFalse(enforce_from_env())

    def test_enforce_is_true(self) -> None:
        os.environ[admission.ENFORCE_ENV] = "enforce"
        self.assertTrue(enforce_from_env())

    def test_enforce_case_insensitive_and_padded(self) -> None:
        os.environ[admission.ENFORCE_ENV] = "  ENFORCE  "
        self.assertTrue(enforce_from_env())

    def test_observe_is_false(self) -> None:
        os.environ[admission.ENFORCE_ENV] = "observe"
        self.assertFalse(enforce_from_env())

    def test_garbage_is_false(self) -> None:
        os.environ[admission.ENFORCE_ENV] = "garbage"
        self.assertFalse(enforce_from_env())


class LoadAgentPassportTest(unittest.TestCase):
    """The loader does the I/O; admit_agent never touches disk."""

    def test_present_returns_dict(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            payload = {"id": "agent-x[bot]", "scope": ["read_repo"]}
            path = Path(tmp) / "agent-x.json"
            path.write_text(json.dumps(payload), encoding="utf-8")
            self.assertEqual(load_agent_passport("agent-x", tmp), payload)

    def test_absent_returns_none(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            self.assertIsNone(load_agent_passport("missing", tmp))

    def test_corrupt_returns_empty_dict_maps_to_malformed(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "broken.json"
            path.write_text("{not valid json", encoding="utf-8")
            corrupt = load_agent_passport("broken", tmp)
            self.assertEqual(corrupt, {})
            # An empty dict is a passport missing every required field -> malformed.
            verdict = admit_agent(corrupt, ["read_repo"], {}, _NOW, enforce=False)
            self.assertEqual(verdict.status, "malformed")


class LoadTrustTest(unittest.TestCase):
    """Fail-safe keyring load: a missing path yields {} (never a raise)."""

    def test_missing_path_returns_empty(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            self.assertEqual(load_trust(Path(tmp) / "nope.json"), {})

    def test_real_keyring_returns_dict(self) -> None:
        trust = load_trust(_TRUST_PATH)
        self.assertIn("test-authority-1", trust)
        self.assertIsInstance(trust["test-authority-1"], str)


class FailSafeTest(unittest.TestCase):
    """An oracle exception NEVER yields trusted; enforce denies, observe admits."""

    def setUp(self) -> None:
        self._saved = admission.attest_passport

        def _boom(*_args: object, **_kwargs: object) -> object:
            raise RuntimeError("oracle blew up")

        admission.attest_passport = _boom  # type: ignore[assignment]

    def tearDown(self) -> None:
        admission.attest_passport = self._saved  # type: ignore[assignment]

    def test_exception_is_untrusted_never_trusted(self) -> None:
        for enforce in (False, True):
            with self.subTest(enforce=enforce):
                verdict = admit_agent(None, ["read_repo"], {}, _NOW, enforce=enforce)
                self.assertEqual(verdict.status, "untrusted")
                self.assertEqual(verdict.reasons, [{"kind": "oracle_error"}])
                self.assertEqual(verdict.admitted, not enforce)
                self.assertNotEqual(verdict.status, "trusted")


class ReplayDeterminismTest(unittest.TestCase):
    """I4: same inputs -> equal verdict (frozen dataclass value equality)."""

    def test_two_calls_are_equal(self) -> None:
        trust = _load(_TRUST_PATH)
        passport = _load(_PRBOT_PASSPORT)
        declared = list(passport["scope"])
        first = admit_agent(passport, declared, trust, _NOW, enforce=True)
        second = admit_agent(passport, declared, trust, _NOW, enforce=True)
        self.assertEqual(first, second)
        self.assertIsInstance(first, AdmissionVerdict)


if __name__ == "__main__":
    unittest.main()
