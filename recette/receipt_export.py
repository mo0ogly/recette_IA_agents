"""Signed, transferable export of context receipts (Ed25519).

Wraps a hash-chained list of content-free receipts into an export envelope and
signs its canonical payload with Ed25519 -- the same mechanism the policy bundle
uses (recette/bundle.py): ``cryptography`` is the optional ``[bundle]`` extra,
lazily imported, so the core recette keeps zero crypto dependency (R20). The
signing key comes from the environment (R8), never hardcoded; with no key the
export is returned UNSIGNED (``signed: false``), fail-safe -- never a fake
signature.

The signed payload is the canonical JSON of ``{chain_head, receipts}`` (sorted
keys, compact separators, utf-8) -- deterministic (I4). The receipts are already
content-free, so the export carries no bodies; signing makes the audit trail
verifiable OFF-platform by anyone holding the public key.
"""

from __future__ import annotations

import json
import os

#: Env var holding the Ed25519 signing key (hex, 32-byte seed). R8: never
#: hardcoded, never logged. Absent -> the export is unsigned (fail-safe).
SIGNING_KEY_ENV = "INSPECT_IA_AGENTS_RECEIPT_SIGNING_KEY"


def canonical_payload(chain_head: str, receipts: list[dict]) -> bytes:
    """Exact bytes the signature covers. Stable across runs (I4)."""
    return json.dumps(
        {"chain_head": chain_head, "receipts": receipts},
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
    ).encode("utf-8")


def _signing_key_hex() -> str | None:
    key = os.environ.get(SIGNING_KEY_ENV)
    return key or None


def export_receipts(receipts: list[dict]) -> dict:
    """Build a (possibly signed) export envelope over the chained receipts.

    ``chain_head`` is the last receipt's hash (the tip of the integrity chain),
    or "" when empty. When a signing key resolves from the env, the envelope is
    signed with Ed25519 and carries ``signed: true`` + ``public_key`` +
    ``signature`` (hex). With no key it is returned unsigned (fail-safe)."""
    chain_head = receipts[-1].get("hash", "") if receipts else ""
    envelope: dict = {
        "schema": "inspect_ia_agents-receipt-export-v1",
        "count": len(receipts),
        "chain_head": chain_head,
        "receipts": receipts,
        "signed": False,
    }
    key_hex = _signing_key_hex()
    if key_hex is None:
        return envelope
    try:
        from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
    except ImportError:  # pragma: no cover - only without the [bundle] extra
        envelope["sign_error"] = "Ed25519 signing needs the [bundle] extra"
        return envelope
    try:
        private_key = Ed25519PrivateKey.from_private_bytes(bytes.fromhex(key_hex))
    except ValueError:
        envelope["sign_error"] = "signing key is not valid hex / wrong length"
        return envelope
    signature = private_key.sign(canonical_payload(chain_head, receipts))
    public_key = private_key.public_key()
    from cryptography.hazmat.primitives import serialization

    pub_raw = public_key.public_bytes(
        encoding=serialization.Encoding.Raw, format=serialization.PublicFormat.Raw
    )
    envelope["signed"] = True
    envelope["public_key"] = pub_raw.hex()
    envelope["signature"] = signature.hex()
    return envelope


def verify_export(envelope: dict, *, expected_public_key: str | None = None) -> dict:
    """Verify a signed receipt export. Returns ``{valid, reason}``.

    Mirrors recette.bundle.verify_bundle: optional key pinning, lazy import.
    An unsigned envelope is reported invalid (nothing to verify)."""
    if not envelope.get("signed"):
        return {"valid": False, "reason": "export is not signed"}
    try:
        from cryptography.exceptions import InvalidSignature
        from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey
    except ImportError:  # pragma: no cover
        return {"valid": False, "reason": "Ed25519 verification needs the [bundle] extra"}
    pub_hex = envelope.get("public_key", "")
    sig_hex = envelope.get("signature", "")
    if not pub_hex or not sig_hex:
        return {"valid": False, "reason": "missing public_key or signature"}
    if expected_public_key is not None and pub_hex != expected_public_key:
        return {"valid": False, "reason": "public key does not match the pinned key"}
    try:
        public_key = Ed25519PublicKey.from_public_bytes(bytes.fromhex(pub_hex))
        signature = bytes.fromhex(sig_hex)
    except ValueError:
        return {"valid": False, "reason": "public_key or signature is not valid hex"}
    payload = canonical_payload(envelope.get("chain_head", ""), envelope.get("receipts", []))
    try:
        public_key.verify(signature, payload)
    except InvalidSignature:
        return {"valid": False, "reason": "signature does not match payload (tampered/wrong key)"}
    return {"valid": True, "reason": "signature valid over canonical payload"}
