"""compliance mock handler -- KYC / regulatory workflow double.

Deterministic double for the compliance domain (KYC review workflows). Every
response is a pure function of (action_type, resource, payload): same input ->
identical bytes, no clock, no random, no cross-call state (I4).
"""

from __future__ import annotations

from ._realism import digest, envelope, ref

_DOMAIN = "compliance"

_KNOWN_ACTIONS = frozenset(("open_kyc_review",))


def handle(action_type: str, resource: str, payload: dict) -> dict | None:
    """Return a realistic deterministic compliance response, or None for an unknown action."""
    if action_type not in _KNOWN_ACTIONS:
        return None
    dig = digest(_DOMAIN, action_type, resource, payload)
    base = envelope(action_type, resource, dig)
    # open_kyc_review
    return {
        **base,
        "status": "opened",
        "subject": resource or "subject/unknown",
        "review_id": ref("kyc_", dig),
        "review_state": "pending",
    }
