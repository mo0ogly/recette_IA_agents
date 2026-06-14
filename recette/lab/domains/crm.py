"""crm mock handler -- W3 CRM / Sales workstream.

A realistic deterministic double of a CRM/sales API. Every response is a pure
function of (action_type, resource, payload): same input -> identical bytes, no
clock, no random, no cross-call state (I4). See ``_realism`` for the shared
primitives and the validation contract. The ``result_id`` keeps the
``sha256("crm:...")[:12]`` recipe (the lab plane stays decoupled from the
catalog plane; the test suite asserts both stay in sync).
"""

from __future__ import annotations

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

_LIFECYCLE = ("lead", "mql", "sql", "customer", "churned")
_DEAL_STAGES = ("prospecting", "qualification", "proposal", "negotiation", "closed_won")
_CURRENCIES = frozenset(("EUR", "USD", "GBP", "CHF", "JPY", "CAD", "AUD"))


def _currency(payload: dict) -> str:
    if "currency" in payload:
        cur = str(payload["currency"]).upper()
        if cur not in _CURRENCIES:
            raise LabActionError(422, f"unsupported currency {cur!r}")
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
        local = (resource.split(":")[-1] or "contact").replace(" ", ".").lower()[:24]
        return {
            **base,
            "status": "ok",
            "contact": {
                "id": f"cnt_{dig[:10]}",
                "account": resource,
                "email": f"{local}.{dig[:6]}@example-corp.test",
                "lifecycle_stage": pick(dig, _LIFECYCLE),
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
        return {
            **base,
            "status": "updated",
            "account": resource,
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
        if "amount" in payload:
            value = coerce_positive_number(payload["amount"])
            if value is None:
                raise LabActionError(422, f"invalid amount {payload['amount']!r}")
            amount = f"{value:.2f}"
        else:
            cents = 100000 + (int(dig[:8], 16) % 9900000)
            amount = f"{cents // 100}.{cents % 100:02d}"
        return {
            **base,
            "status": "updated",
            "opportunity": resource,
            "amount": amount,
            "currency": _currency(payload),
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
