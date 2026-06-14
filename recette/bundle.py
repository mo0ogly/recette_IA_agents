"""Ed25519-signed policy bundle contract recette (M5).

The Risk Scoring Engine emits a policy bundle (per-agent decisions + policy version)
signed with Ed25519 before it reaches Railgun. This module verifies a bundle's canonical
payload + signature. We verify, we never produce production bundles.

`cryptography` is an optional extra ([bundle]); the import is lazy so the core recette
keeps zero crypto dependency. The signed payload is the canonical JSON of
{policy_version, decisions} (sort_keys, compact separators, utf-8) -- see canonical_payload.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class BundleVerification:
    valid: bool
    reason: str


def canonical_payload(bundle: dict) -> bytes:
    """The exact bytes the signature must cover. Stable across runs (I4)."""
    return json.dumps(
        {"policy_version": bundle["policy_version"], "decisions": bundle["decisions"]},
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")


def _load_verifier():
    try:
        from cryptography.exceptions import InvalidSignature
        from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey
    except ImportError as exc:  # pragma: no cover - exercised only without the extra
        raise RuntimeError(
            "Ed25519 verification needs the [bundle] extra: pip install -e '.[bundle]'"
        ) from exc
    return Ed25519PublicKey, InvalidSignature


def verify_bundle(bundle: dict, *, expected_public_key: str | None = None) -> BundleVerification:
    """Verify a policy bundle's Ed25519 signature over its canonical payload.

    If expected_public_key is given, the bundle's key MUST match it (key pinning) --
    otherwise a valid signature from an unknown key would pass, defeating the point.
    """
    Ed25519PublicKey, InvalidSignature = _load_verifier()

    pub_hex = bundle.get("public_key", "")
    sig_hex = bundle.get("signature", "")
    if not pub_hex or not sig_hex:
        return BundleVerification(False, "missing public_key or signature")
    if expected_public_key is not None and pub_hex != expected_public_key:
        return BundleVerification(False, "public key does not match the pinned key")

    try:
        public_key = Ed25519PublicKey.from_public_bytes(bytes.fromhex(pub_hex))
    except ValueError:
        return BundleVerification(False, "public_key is not valid hex / wrong length")
    try:
        signature = bytes.fromhex(sig_hex)
    except ValueError:
        return BundleVerification(False, "signature is not valid hex")

    try:
        public_key.verify(signature, canonical_payload(bundle))
    except InvalidSignature:
        return BundleVerification(False, "signature does not match payload (tampered or wrong key)")
    return BundleVerification(True, "signature valid over canonical payload")


def verify_bundle_file(
    path: str | Path, *, expected_public_key: str | None = None
) -> BundleVerification:
    bundle = json.loads(Path(path).read_text(encoding="utf-8"))
    return verify_bundle(bundle, expected_public_key=expected_public_key)
