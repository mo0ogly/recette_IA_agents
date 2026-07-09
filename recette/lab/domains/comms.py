"""comms mock handler -- customer communication double.

A realistic deterministic double of an outbound customer-notification gateway
(the comms domain of the BANQUE fraud-investigation scenario). Every response is
a pure function of (action_type, resource, payload): same input -> identical
bytes, no clock, no random, no cross-call state (I4).

Realism levels (all deterministic, additive on the base envelope):
  1. Per-action business fields -- a notify_customer returns a full dispatch
     receipt (message id, gateway route, template, locale, queue position).
  2. Entity coherence -- the recipient view reuses the shared CRM contact
     entity (``_entities.derive_contact``), so comms and crm agree on the same
     customer (masked email, lifecycle stage) with NO mutable state.
  3. Input validation -- a present-but-unknown ``channel`` is rejected with a
     structured 422 (code + detail), like a real notification API. Validation
     stays lenient on OMITTED fields (a deterministic default is derived).
"""

from __future__ import annotations

from . import _entities
from ._realism import LabActionError, derived_int, digest, envelope, pick, ref

_DOMAIN = "comms"

_KNOWN_ACTIONS = frozenset(("notify_customer",))

#: Delivery channels a real customer-notification gateway would expose.
_CHANNELS = ("email", "sms", "push", "postal")

#: Simulated gateway routes (regional dispatch clusters), picked per input.
_GATEWAY_ROUTES = ("msg-gw-eu-1", "msg-gw-eu-2", "msg-gw-amer-1")

#: Notification templates of the fraud-investigation scenario.
_TEMPLATES = (
    "fraud-alert-card-blocked",
    "fraud-alert-suspicious-login",
    "kyc-document-request",
    "payment-confirmation",
)

_LOCALES = ("fr-FR", "en-GB", "de-DE", "es-ES")


def _masked_email(email: str) -> str:
    """Mask the local part of an address (GDPR-style trace hygiene)."""
    local, _, domain = email.partition("@")
    if not domain:
        return "***"
    return f"{local[:1]}***@{domain}"


def handle(action_type: str, resource: str, payload: dict) -> dict | None:
    """Return a realistic deterministic comms response, ``None`` for an unknown
    action, or raise ``LabActionError`` for a known action with invalid input."""
    if action_type not in _KNOWN_ACTIONS:
        return None
    dig = digest(_DOMAIN, action_type, resource, payload)
    base = envelope(action_type, resource, dig)

    # notify_customer -- strict on a present-but-unknown channel, lenient
    # (deterministic default) when the field is omitted.
    channel = str(payload.get("channel") or pick(dig, _CHANNELS))
    if channel not in _CHANNELS:
        raise LabActionError(
            422,
            f"unknown channel {channel!r}: must be one of {sorted(_CHANNELS)}",
            code="unknown_channel",
            detail={"field": "channel", "got": channel, "expected": sorted(_CHANNELS)},
        )
    contact = _entities.derive_contact(resource or "customer/unknown")
    template = str(payload.get("template") or pick(dig, _TEMPLATES, offset=4))
    response = {
        **base,
        "status": "queued",
        "customer": resource or "customer/unknown",
        "channel": channel,
        "notification_id": ref("ntf_", dig),
        "message_id": ref("msg_", dig, length=12),
        "template": template,
        "locale": pick(dig, _LOCALES, offset=8),
        "gateway_route": pick(dig, _GATEWAY_ROUTES, offset=12),
        "queue_position": derived_int(dig, 1, 250),
        "recipient": {
            "contact_id": contact.contact_id,
            "email_masked": _masked_email(contact.email),
            "lifecycle_stage": contact.lifecycle_stage,
        },
    }
    if channel == "sms":
        # A realistic SMS receipt carries the segment count billed.
        response["segments"] = derived_int(dig, 1, 4, offset=16)
    return response
