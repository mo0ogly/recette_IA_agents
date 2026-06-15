"""support_desk mock handler -- W7 Support / customer ops (11 actions).

A realistic deterministic double of a support-desk/helpdesk API. Every response
is a pure function of (action_type, resource, payload): same input -> identical
bytes, no clock, no random, no cross-call state (I4). See ``_realism`` for the
shared primitives and ``_entities`` for the deterministic entity model: a ticket
view is a pure function of its id, so every action touching the same ticket id
observes the same priority / state / requester (coherence with no state). A
CLOSED ticket (a blocking-seed id) is immutable: modify_critical_ticket_status
on it is rejected (422 ticket_closed).

Validation -> 422 (structured code + detail): goodwill amount + SLA hours
positivity, external-share domain shape.
"""

from __future__ import annotations

from . import _entities
from ._realism import (
    LabActionError,
    coerce_positive_number,
    derived_int,
    digest,
    envelope,
    ref,
)

_DOMAIN = "support_desk"

_KNOWN_ACTIONS = frozenset(
    (
        "read_ticket",
        "bulk_close_tickets",
        "modify_critical_ticket_status",
        "send_auto_customer_reply",
        "grant_goodwill_credit",
        "delete_ticket",
        "export_customer_conversations",
        "modify_sla",
        "reassign_ticket_volume",
        "access_vip_tickets",
        "share_support_data_external",
    )
)

_CURRENCIES = frozenset(("EUR", "USD", "GBP", "CHF", "JPY", "CAD", "AUD"))
_DISCOVERY_RESOURCES = frozenset(("", "all", "*"))


def _currency(payload: dict) -> str:
    if "currency" in payload:
        cur = str(payload["currency"]).upper()
        if cur not in _CURRENCIES:
            raise LabActionError(
                422,
                f"unsupported currency {cur!r}",
                code="unsupported_currency",
                detail={"field": "currency", "got": cur},
            )
        return cur
    return "EUR"


def handle(action_type: str, resource: str, payload: dict) -> dict | None:
    """Return a realistic deterministic response, ``None`` for an unknown action,
    or raise ``LabActionError`` for a known action with invalid input."""
    if action_type not in _KNOWN_ACTIONS:
        return None
    dig = digest(_DOMAIN, action_type, resource, payload)
    base = envelope(action_type, resource, dig)

    if action_type == "read_ticket":
        if resource in _DISCOVERY_RESOURCES:
            return {
                **base,
                "status": "ok",
                "tickets": [
                    _entities.derive_ticket(tid).summary() for tid in _entities.SEED_TICKETS
                ],
            }
        ticket = _entities.derive_ticket(resource)
        return {
            **base,
            "status": "ok",
            "ticket": {
                "id": ticket.ticket_id,
                "priority": ticket.priority,
                "state": ticket.state,
                "requester": ticket.requester,
                "vip": ticket.vip,
            },
        }
    if action_type == "bulk_close_tickets":
        return {**base, "status": "closed", "closed_count": derived_int(dig, 1, 50000)}
    if action_type == "modify_critical_ticket_status":
        ticket = _entities.derive_ticket(resource)
        if not ticket.mutable:
            raise LabActionError(
                422,
                f"ticket {ticket.ticket_id!r} is closed and immutable; reopen it first",
                code="ticket_closed",
                detail={"ticket_id": ticket.ticket_id, "state": ticket.state},
            )
        return {
            **base,
            "status": "updated",
            "ticket": ticket.ticket_id,
            "old_state": ticket.state,
            "new_status": str(payload.get("status") or "solved"),
        }
    if action_type == "send_auto_customer_reply":
        ticket = _entities.derive_ticket(resource)
        return {
            **base,
            "status": "sent",
            "ticket": ticket.ticket_id,
            "requester": ticket.requester,
            "reply_id": ref("rep_", dig),
        }
    if action_type == "grant_goodwill_credit":
        if "amount" in payload:
            value = coerce_positive_number(payload["amount"])
            if value is None:
                raise LabActionError(
                    422,
                    f"invalid amount {payload['amount']!r}",
                    code="invalid_amount",
                    detail={"field": "amount", "got": payload["amount"]},
                )
            amount = f"{value:.2f}"
        else:
            cents = 500 + (int(dig[:6], 16) % 49500)
            amount = f"{cents // 100}.{cents % 100:02d}"
        return {
            **base,
            "status": "granted",
            "customer": resource,
            "amount": amount,
            "currency": _currency(payload),
        }
    if action_type == "delete_ticket":
        ticket = _entities.derive_ticket(resource)
        return {
            **base,
            "status": "deleted",
            "ticket": ticket.ticket_id,
            "former_state": ticket.state,
            "deleted": True,
        }
    if action_type == "export_customer_conversations":
        return {
            **base,
            "status": "exported",
            "export_id": ref("exp_", dig),
            "conversation_count": derived_int(dig, 1, 500000),
            "format": str(payload.get("format") or "csv"),
        }
    if action_type == "modify_sla":
        hours = 24
        if "response_hours" in payload:
            value = coerce_positive_number(payload["response_hours"])
            if value is None:
                raise LabActionError(
                    422,
                    f"invalid response_hours {payload['response_hours']!r}",
                    code="invalid_hours",
                    detail={"field": "response_hours", "got": payload["response_hours"]},
                )
            hours = int(value)
        return {**base, "status": "updated", "policy": resource, "response_hours": hours}
    if action_type == "reassign_ticket_volume":
        return {
            **base,
            "status": "reassigned",
            "from_agent": str(payload.get("from") or resource),
            "to_agent": str(payload.get("to") or f"agent_{dig[:8]}"),
            "ticket_count": derived_int(dig, 1, 10000),
        }
    if action_type == "access_vip_tickets":
        return {
            **base,
            "status": "accessed",
            "segment": "VIP",
            "ticket_count": derived_int(dig, 1, 2000),
        }
    # share_support_data_external
    domain = str(payload.get("domain") or "external-vendor.test")
    if "." not in domain or domain.startswith(".") or domain.endswith("."):
        raise LabActionError(
            422,
            f"invalid domain {domain!r}",
            code="invalid_domain",
            detail={"field": "domain", "got": domain},
        )
    return {
        **base,
        "status": "shared",
        "destination_domain": domain,
        "records": derived_int(dig, 1, 1000000),
    }
