"""comms mock handler -- customer communication double.

Deterministic double for the comms domain (outbound customer notifications).
Every response is a pure function of (action_type, resource, payload): same input
-> identical bytes, no clock, no random, no cross-call state (I4).
"""

from __future__ import annotations

from ._realism import digest, envelope, ref

_DOMAIN = "comms"

_KNOWN_ACTIONS = frozenset(("notify_customer",))


def handle(action_type: str, resource: str, payload: dict) -> dict | None:
    """Return a realistic deterministic comms response, or None for an unknown action."""
    if action_type not in _KNOWN_ACTIONS:
        return None
    dig = digest(_DOMAIN, action_type, resource, payload)
    base = envelope(action_type, resource, dig)
    # notify_customer
    return {
        **base,
        "status": "queued",
        "customer": resource or "customer/unknown",
        "channel": str(payload.get("channel") or "email"),
        "notification_id": ref("ntf_", dig),
    }
