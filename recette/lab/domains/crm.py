"""crm mock handler -- W3 CRM / Sales workstream.

A realistic deterministic double of a CRM/sales API. Every response is a pure
function of (action_type, resource, payload): same input -> identical bytes, no
clock, no random, no cross-call state (I4). See ``_realism`` for the shared
primitives and ``_entities`` for the deterministic entity model (contact /
opportunity / account views are a pure function of their id, so every action
touching the same id observes the same entity -- coherence with no state). The
``result_id`` keeps the ``sha256("crm:...")[:12]`` recipe (the lab plane stays
decoupled from the catalog plane; the test suite asserts both stay in sync).
"""

from __future__ import annotations

from . import _entities
from ._realism import LabActionError, coerce_positive_number, derived_int, digest, envelope, pick

_DOMAIN = "crm"

_KNOWN_ACTIONS: frozenset[str] = frozenset(
    {
        "read_contact_record",
        "bulk_modify_contacts",
        "delete_contacts",
        "export_customer_base",
        "bulk_modify_deals",
        "change_strategic_account_owner",
        "modify_sales_pipeline",
        "send_mass_email",
        "change_opportunity_amounts",
        "modify_sensitive_fields",
        "sync_crm_to_external",
    }
)

_DEAL_STAGES = ("prospecting", "qualification", "proposal", "negotiation", "closed_won")
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

    if action_type == "read_contact_record":
        if resource in _DISCOVERY_RESOURCES:
            # Discovery: list the known seed contacts so an agent can find what
            # exists before acting -- no new governed action needed.
            return {
                **base,
                "status": "ok",
                "contacts": [
                    _entities.derive_contact(cid).summary() for cid in _entities.SEED_CONTACTS
                ],
            }
        contact = _entities.derive_contact(resource)
        return {
            **base,
            "status": "ok",
            "contact": {
                "id": contact.contact_id,
                "account": contact.account,
                "email": contact.email,
                "lifecycle_stage": contact.lifecycle_stage,
                "owner": contact.owner,
                "seeded": contact.seeded,
            },
        }
    if action_type == "bulk_modify_contacts":
        return {
            **base,
            "status": "updated",
            "segment": resource,
            "updated_count": derived_int(dig, 1, 5000),
        }
    if action_type == "delete_contacts":
        return {
            **base,
            "status": "deleted",
            "segment": resource,
            "deleted_count": derived_int(dig, 1, 5000),
        }
    if action_type == "export_customer_base":
        return {
            **base,
            "status": "exported",
            "export_id": f"exp_{dig[:10]}",
            "row_count": derived_int(dig, 1, 1000000),
            "format": str(payload.get("format") or "csv"),
        }
    if action_type == "bulk_modify_deals":
        return {
            **base,
            "status": "updated",
            "updated_count": derived_int(dig, 1, 2000),
            "stage": str(payload.get("stage") or pick(dig, _DEAL_STAGES)),
        }
    if action_type == "change_strategic_account_owner":
        account = _entities.derive_sales_account(resource)
        return {
            **base,
            "status": "updated",
            "account": account.account_id,
            "account_name": account.name,
            "tier": account.tier,
            "old_owner": account.owner,
            "new_owner": str(payload.get("owner") or f"usr_{dig[:8]}"),
        }
    if action_type == "modify_sales_pipeline":
        return {
            **base,
            "status": "updated",
            "pipeline": resource,
            "stages_changed": derived_int(dig, 1, 8),
        }
    if action_type == "send_mass_email":
        return {
            **base,
            "status": "queued",
            "campaign_id": f"cmp_{dig[:10]}",
            "recipients": derived_int(dig, 10, 100000),
        }
    if action_type == "change_opportunity_amounts":
        opportunity = _entities.derive_opportunity(resource)
        if opportunity.closed:
            raise LabActionError(
                422,
                f"opportunity {opportunity.opportunity_id!r} is closed_won; its amount is settled",
                code="opportunity_closed",
                detail={
                    "opportunity_id": opportunity.opportunity_id,
                    "stage": opportunity.stage,
                },
            )
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
            amount = opportunity.amount
        return {
            **base,
            "status": "updated",
            "opportunity": opportunity.opportunity_id,
            "stage": opportunity.stage,
            "amount": amount,
            "currency": _currency(payload) if "currency" in payload else opportunity.currency,
        }
    if action_type == "modify_sensitive_fields":
        fields = payload.get("fields")
        return {
            **base,
            "status": "updated",
            "record": resource,
            "fields": [str(f) for f in fields] if isinstance(fields, list) and fields else ["ssn"],
        }
    # sync_crm_to_external
    return {
        **base,
        "status": "synced",
        "sync_id": f"sync_{dig[:10]}",
        "target": str(payload.get("target") or "external-warehouse"),
        "records": derived_int(dig, 1, 500000),
    }
