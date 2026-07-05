"""Rust/Python attestation equivalence: the Python oracle mirrors `passport verify`.

Task 11 adds a pure Python attestation ORACLE (`recette.adapters.attest_passport`)
that reproduces the frozen semantics of the Rust `agent-passport` crate. This test
pins the equivalence on THREE fronts for every corpus subject carrying a signed
``.inspect_ia_agents/passport.json``:

1. Python oracle status/reasons == the Rust ``passport verify`` verdict (driven via
   subprocess on the built ``discoveryprobe-inventory`` binary). If the release
   binary is absent, that leg is skipped (like the other live-binary checks).
2. Python oracle status == the subject's committed ground-truth
   ``attestation_status`` (the corpus is the third, independent oracle).

CRITICAL (reviewer-flagged): ``--declared`` is applied on BOTH sides for EVERY
subject, set to the manifest's declared action families. Without it the Rust side
would report ``trusted`` for ``gh-passport-scope-overreach`` while the Python oracle
(which always cross-checks the declared families) reports ``untrusted`` -- a false
divergence. Both sides must do the same declared cross-check.

The Ed25519 signature check needs the ``cryptography`` (``[bundle]``) extra; without
it the oracle raises ``ImportError`` and the crypto-dependent asserts are skipped
explicitly -- never silently treated as trusted (I4 fail-safe).
"""

from __future__ import annotations

import json
import os
import subprocess  # nosec B404 - drives the trusted, locally-built release binary
import unittest
from pathlib import Path

from recette.adapters import attest_passport

_REPO_ROOT = Path(__file__).resolve().parents[1]
_REPOS = _REPO_ROOT / "corpus" / "repos"
_TRUST = _REPO_ROOT / "corpus" / "keys" / "test-authority.trust.json"

#: Injected clock (I4): the same fixed reference the ground-truth notes cite and
#: the ReferenceSourceScanAdapter defaults to. Never the wall clock.
_NOW = "2027-01-01T00:00:00Z"

#: The compiled verifier (env override, else the release build). Absent -> the
#: Rust equivalence leg is skipped (the binary is built by ./recette.sh discovery-build).
_INVENTORY_BIN = Path(
    os.environ.get("INSPECT_IA_AGENTS_INVENTORY_BIN")
    or (_REPO_ROOT / "discoveryprobe" / "target" / "release" / "discoveryprobe-inventory")
)
_HAS_BIN = _INVENTORY_BIN.is_file()

try:  # the Ed25519 verify needs the [bundle] extra
    import cryptography  # noqa: F401

    _HAS_CRYPTO = True
except ImportError:  # pragma: no cover - only without the [bundle] extra
    _HAS_CRYPTO = False


def _subjects() -> list[str]:
    """Every corpus repo carrying a signed passport.json, sorted (deterministic)."""
    out = []
    for passport in _REPOS.glob("*/repo/.inspect_ia_agents/passport.json"):
        out.append(passport.parents[2].name)
    return sorted(out)


def _declared_families(slug: str) -> list[str]:
    """The manifest's declared action families, sorted -- the cross-check scope."""
    manifest = json.loads(
        (_REPOS / slug / "repo" / ".inspect_ia_agents" / "manifest.json").read_text("utf-8")
    )
    return sorted({cap["action"] for cap in manifest["agent"]["capabilities"]})


def _load_trust() -> dict[str, str]:
    return json.loads(_TRUST.read_text("utf-8"))


def _oracle_verdict(status: str, reasons: list[dict]) -> dict:
    """Shape the oracle output like the Rust ``Verdict`` serde JSON for comparison."""
    if status == "trusted":
        return {"kind": "trusted"}
    if status == "untrusted":
        return {"kind": "untrusted", "reasons": reasons}
    return {"kind": status}  # unsigned / malformed have no Rust verdict


def _rust_verify(slug: str, declared: list[str]) -> dict:
    """Run the release binary's ``passport verify`` and parse the stdout verdict."""
    cmd = [
        str(_INVENTORY_BIN),
        "passport",
        "verify",
        str(_REPOS / slug / "repo"),
        "--trust",
        str(_TRUST),
        "--now",
        _NOW,
        "--declared",
        ",".join(declared),
    ]
    proc = subprocess.run(cmd, capture_output=True, text=True, check=False)  # nosec B603
    # Exit 0 (trusted) or 3 (untrusted) both print the verdict; anything else is a bug.
    assert proc.returncode in (0, 3), f"{slug}: unexpected exit {proc.returncode}: {proc.stderr}"
    return json.loads(proc.stdout)


@unittest.skipUnless(_HAS_CRYPTO, "attestation crypto needs the [bundle] extra (cryptography)")
class TestPassportEquivalence(unittest.TestCase):
    def test_at_least_the_seven_passport_subjects_present(self):
        subjects = _subjects()
        self.assertGreaterEqual(len(subjects), 7, subjects)

    def test_oracle_matches_ground_truth_attestation_status(self):
        trust = _load_trust()
        for slug in _subjects():
            with self.subTest(slug=slug):
                passport = json.loads(
                    (_REPOS / slug / "repo" / ".inspect_ia_agents" / "passport.json").read_text(
                        "utf-8"
                    )
                )
                status, _reasons = attest_passport(passport, trust, _NOW, _declared_families(slug))
                gt = json.loads((_REPOS / slug / "discovery-ground-truth.json").read_text("utf-8"))
                self.assertEqual(
                    status,
                    gt["attestation_status"],
                    f"{slug}: oracle {status} != ground-truth {gt['attestation_status']}",
                )

    @unittest.skipUnless(_HAS_BIN, f"release binary not built at {_INVENTORY_BIN}")
    def test_oracle_matches_rust_verify_verdict(self):
        trust = _load_trust()
        for slug in _subjects():
            with self.subTest(slug=slug):
                declared = _declared_families(slug)
                passport = json.loads(
                    (_REPOS / slug / "repo" / ".inspect_ia_agents" / "passport.json").read_text(
                        "utf-8"
                    )
                )
                status, reasons = attest_passport(passport, trust, _NOW, declared)
                rust = _rust_verify(slug, declared)
                self.assertEqual(
                    _oracle_verdict(status, reasons),
                    rust,
                    f"{slug}: oracle diverges from Rust verify",
                )

    def test_coverage_both_trusted_and_untrusted_are_exercised(self):
        # The equivalence suite covers the attestation dimension only if both
        # verdict classes appear across the corpus (positives + negatives).
        trust = _load_trust()
        seen = set()
        for slug in _subjects():
            passport = json.loads(
                (_REPOS / slug / "repo" / ".inspect_ia_agents" / "passport.json").read_text("utf-8")
            )
            status, _ = attest_passport(passport, trust, _NOW, _declared_families(slug))
            seen.add(status)
        self.assertIn("trusted", seen, seen)
        self.assertIn("untrusted", seen, seen)

    def test_multi_reason_sort_canonical_order(self):
        """Multi-reason untrust verdicts must be sorted by canonical order (I4 determinism).

        The corpus subjects are all single-reason, so this test directly constructs a
        passport with multiple defects:
        - expired (exp <= now)
        - empty_delegation (delegation is [])
        - unknown_key_id (key_id not in trust)
        - scope_overreach (declared family not in scope)

        These trigger reasons with priorities [1, 2, 5, 4] in _UNTRUST_ORDER.
        After sort, they must be [1, 2, 4, 5] = [expired, empty_delegation, scope_overreach, unknown_key_id].
        """
        # Construct a minimal passport with multiple defects (no crypto needed).
        passport = {
            "id": "test-agent-id",
            "tenant": "test-tenant",
            "exp": "2020-01-01T00:00:00Z",  # past, triggers expired
            "signature": "0000000000000000000000000000000000000000000000000000000000000000",
            "key_id": "nonexistent-key",  # not in trust, triggers unknown_key_id
            "delegation": [],  # empty, triggers empty_delegation
            "scope": ["read"],
        }
        trust = _load_trust()
        declared = ["read", "write"]  # write is declared but not in scope, triggers scope_overreach

        status, reasons = attest_passport(passport, trust, _NOW, declared)

        self.assertEqual(status, "untrusted", "multi-reason passport must be untrusted")
        self.assertEqual(len(reasons), 4, f"expected 4 reasons, got {len(reasons)}: {reasons}")

        # Extract reason kinds in order.
        kinds = [r["kind"] for r in reasons]

        # The canonical sort order is: expired(1) < empty_delegation(2) < scope_overreach(4) < unknown_key_id(5).
        expected_kinds = ["expired", "empty_delegation", "scope_overreach", "unknown_key_id"]
        self.assertEqual(kinds, expected_kinds, f"reasons not in canonical order: {kinds}")


if __name__ == "__main__":
    unittest.main()
