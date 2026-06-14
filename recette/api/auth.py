"""Identity binding for the API (I3): stdlib HS256 JWT, zero new dependency.

The console/API exposes governed routes (/actions/execute, /config/*, /policies,
/rag/*, ...). Without authentication a caller can claim any ``agent_id`` -- I3
(every action bound to a verified identity) is not enforced. This module provides
a minimal, auditable JWT verifier so the transport layer can resolve a principal
before any handler runs, and the gateway can bind the acting identity.

Why stdlib, not PyJWT: the project keeps a near-zero hard-dependency surface
(jsonschema only). HS256 is a symmetric HMAC over ``header.payload`` -- implementable
with ``hmac``/``hashlib`` and fully auditable. No asymmetric keys are used, so there
is no reason to pull a JWT library and its transitive deps.

Security posture:
- the algorithm is PINNED to HS256; ``none`` and any asymmetric ``alg`` (RS*/ES*/PS*)
  are rejected before any signature work -- this defeats the classic alg-confusion
  and ``alg:none`` forgeries;
- the signature is compared in constant time (``hmac.compare_digest``);
- ``exp`` and ``nbf`` are enforced (with an explicit, caller-chosen leeway);
- a ``sub`` claim is required (no anonymous principal);
- token size is bounded (a cheap DoS guard before any base64 work);
- the signing key comes from ``INSPECT_IA_AGENTS_JWT_SIGNING_KEY`` (R8), never hardcoded.

The clock is read at the boundary only (token mint / verify), never inside the
policy decision path, so I4 (deterministic replay) is untouched.
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
import time
from dataclasses import dataclass

# A signed compact JWT well above this length is not a credential we mint; reject
# early to avoid spending HMAC/base64 work on adversarial input.
_MAX_TOKEN_BYTES = 8192
# The ONLY accepted algorithm. Pinning here is the anti-alg-confusion control.
_ALG = "HS256"
_MIN_KEY_BYTES = 16


class AuthError(Exception):
    """A token is missing, malformed, mis-signed, expired, or claims no identity."""


@dataclass(frozen=True)
class Principal:
    """The verified caller: a subject id, a kind, and (for agents) the bound agent_id."""

    sub: str
    kind: str  # "agent" | "operator"
    agent_id: str | None = None


def _b64url_encode(raw: bytes) -> str:
    return base64.urlsafe_b64encode(raw).rstrip(b"=").decode("ascii")


def _b64url_decode(segment: str) -> bytes:
    pad = "=" * (-len(segment) % 4)
    try:
        return base64.urlsafe_b64decode(segment + pad)
    except (ValueError, TypeError) as exc:  # malformed base64
        raise AuthError("malformed token segment") from exc


def _json_segment(segment: str) -> object:
    """Decode a base64url JWT segment to JSON, mapping any decode error to AuthError."""
    try:
        return json.loads(_b64url_decode(segment) or b"{}")
    except ValueError as exc:  # JSONDecodeError and UnicodeDecodeError are ValueError
        raise AuthError("malformed token segment") from exc


def _key_bytes(key: str) -> bytes:
    if not key or len(key.encode("utf-8")) < _MIN_KEY_BYTES:
        raise AuthError("signing key missing or too short")
    return key.encode("utf-8")


def _sign(signing_input: bytes, key: bytes) -> str:
    return _b64url_encode(hmac.new(key, signing_input, hashlib.sha256).digest())


def decode_token(token: str, key: str, *, now: float | None = None, leeway: int = 0) -> dict:
    """Verify a compact HS256 JWT and return its claims, or raise AuthError.

    Pins alg=HS256 (rejects none/asymmetric), compares the signature in constant
    time, enforces exp/nbf with the given leeway, and requires a non-empty sub.
    """
    if not isinstance(token, str) or not token:
        raise AuthError("empty token")
    if len(token.encode("utf-8")) > _MAX_TOKEN_BYTES:
        raise AuthError("token too large")
    parts = token.split(".")
    if len(parts) != 3:
        raise AuthError("token must have three segments")
    header_b64, payload_b64, sig_b64 = parts

    header = _json_segment(header_b64)
    if not isinstance(header, dict) or header.get("alg") != _ALG:
        # Anything other than the pinned HS256 (incl. "none") is refused here.
        raise AuthError("unexpected token algorithm")

    expected_sig = _sign(f"{header_b64}.{payload_b64}".encode("ascii"), _key_bytes(key))
    if not hmac.compare_digest(expected_sig, sig_b64):
        raise AuthError("bad signature")

    claims = _json_segment(payload_b64)
    if not isinstance(claims, dict):
        raise AuthError("claims must be an object")

    clock = time.time() if now is None else now
    exp = claims.get("exp")
    if exp is not None and clock > float(exp) + leeway:
        raise AuthError("token expired")
    nbf = claims.get("nbf")
    if nbf is not None and clock < float(nbf) - leeway:
        raise AuthError("token not yet valid")

    sub = claims.get("sub")
    if not isinstance(sub, str) or not sub:
        raise AuthError("token carries no subject (sub)")
    return claims


def principal_from_claims(claims: dict) -> Principal:
    """Map verified claims to a Principal. kind defaults to operator; an agent
    principal carries the agent_id it is allowed to act as (defaults to sub)."""
    kind = claims.get("kind", "operator")
    if kind not in ("agent", "operator"):
        raise AuthError(f"unknown principal kind: {kind!r}")
    sub = str(claims["sub"])
    agent_id = claims.get("agent_id")
    if kind == "agent":
        agent_id = str(agent_id) if agent_id else sub
    return Principal(sub=sub, kind=kind, agent_id=agent_id)


def issue_token(
    claims: dict, key: str, *, ttl_seconds: int = 3600, now: float | None = None
) -> str:
    """Mint a compact HS256 JWT. For operator/agent provisioning and tests; the
    server only ever verifies. iat/exp are stamped from the boundary clock."""
    issued = int(time.time() if now is None else now)
    body = {"iat": issued, "exp": issued + int(ttl_seconds), **claims}
    header_b64 = _b64url_encode(json.dumps({"alg": _ALG, "typ": "JWT"}).encode("utf-8"))
    payload_b64 = _b64url_encode(json.dumps(body, separators=(",", ":")).encode("utf-8"))
    sig = _sign(f"{header_b64}.{payload_b64}".encode("ascii"), _key_bytes(key))
    return f"{header_b64}.{payload_b64}.{sig}"
