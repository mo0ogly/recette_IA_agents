"""finance mock handler -- W4 Finance / payments (14 actions).

A realistic deterministic double of a finance/payments API. Every response is
a pure function of (action_type, resource, payload): same input -> identical
response bytes, no clock, no random, no cross-call state (I4). Replays are
byte-stable.

Four levels of realism, all deterministic:
  1. Per-action business fields -- a create_payment returns a payment object,
     a launch_wire_transfer the beneficiary + masked IBAN, etc.
  2. A shared ENTITY MODEL (``_entities``) -- invoice/account/supplier views are
     a pure function of their id, so every action touching the same id observes
     the same entity (read_invoice_status and trigger_refund of ``inv/9`` agree
     on status/amount/currency/payee). Coherence with NO mutable state.
  3. Input validation -- a known action called with explicitly invalid input is
     rejected with the status a real system would use (422) AND a structured
     error (code + detail) so the trace explains why. Validation is lenient on
     MISSING optional fields (a deterministic value is derived) and strict only
     on values that are present and wrong.
  4. Seed discovery -- a read with an empty/"all" resource lists the known seed
     invoices, so an agent can discover what exists before acting.

Format-derived coherence (no stored state): a ``payee_id`` is valid iff it has
the exact shape ``add_payee`` returns (``payee_<10 hex>``); a create_payment to
a fabricated payee is rejected.
"""

from __future__ import annotations

import hashlib
import json

from ..errors import LabActionError
from . import _entities

_KNOWN_ACTIONS = frozenset(
    (
        "read_invoice_status",
        "trigger_refund",
        "create_payment",
        "modify_iban",
        "add_payee",
        "validate_invoice",
        "modify_supplier_bank_details",
        "create_credit_note",
        "modify_price",
        "apply_mass_discount",
        "export_financial_data",
        "launch_wire_transfer",
        "modify_billing_rule",
        "freeze_operation",
    )
)

# ISO 4217 subset the double accepts; a present-but-unknown currency is rejected.
_CURRENCIES = frozenset(("EUR", "USD", "GBP", "CHF", "JPY", "CAD", "AUD"))
_PAYEE_PREFIX = "payee_"
_DISCOVERY_RESOURCES = frozenset(("", "all", "*"))


def _digest(action_type: str, resource: str, payload: dict) -> str:
    """64-hex stable digest of the full input (the per-action determinism anchor,
    I4). Drives ``result_id`` and amounts derived when a field is omitted."""
    material = f"finance:{action_type}:{resource}:{json.dumps(payload, sort_keys=True)}"
    return hashlib.sha256(material.encode("utf-8")).hexdigest()


def _ref(prefix: str, digest: str) -> str:
    """A realistic, stable identifier derived from the input digest."""
    return f"{prefix}{digest[:10]}"


def _derived_amount(digest: str) -> str:
    """A plausible decimal amount in [10.00, 9999.99], derived from the digest."""
    cents = 1000 + (int(digest[:8], 16) % 998999)
    return f"{cents // 100}.{cents % 100:02d}"


def _valid_iban(iban: str) -> bool:
    """ISO 13616 mod-97 check. Pure: a structurally valid IBAN passes, always."""
    s = iban.replace(" ", "").upper()
    if not (15 <= len(s) <= 34) or not s[:2].isalpha() or not s[2:4].isdigit():
        return False
    rearranged = s[4:] + s[:4]
    if not rearranged.isalnum():
        return False
    digits = "".join(str(int(c, 36)) if c.isalpha() else c for c in rearranged)
    return int(digits) % 97 == 1


def _mask_iban(iban: str) -> str:
    """Mask all but the country code and the last four characters."""
    s = iban.replace(" ", "").upper()
    return f"{s[:2]}{'*' * (len(s) - 6)}{s[-4:]}" if len(s) > 6 else s


def _coerce_amount(raw: object) -> float | None:
    """A positive number, accepting a numeric string ("5000", "5000.00") as LLMs
    often emit. Returns None for anything that is not a positive number (a bool,
    a placeholder like "payment_amount", a non-positive value)."""
    if isinstance(raw, bool):
        return None
    if isinstance(raw, (int, float)):
        return float(raw) if raw > 0 else None
    if isinstance(raw, str):
        try:
            value = float(raw.replace(",", "").strip())
        except ValueError:
            return None
        return value if value > 0 else None
    return None


def _amount(payload: dict, digest: str) -> str:
    """Validated amount: reject a present-but-invalid amount (422); derive a
    plausible one when absent (lenient on omission)."""
    if "amount" in payload:
        value = _coerce_amount(payload["amount"])
        if value is None:
            raise LabActionError(
                422,
                f"invalid amount {payload['amount']!r}: must be a positive number",
                code="invalid_amount",
                detail={
                    "field": "amount",
                    "got": payload["amount"],
                    "expected": "a positive number",
                },
            )
        return f"{value:.2f}"
    return _derived_amount(digest)


def _currency(payload: dict) -> str:
    """Validated currency: reject a present-but-unknown code (422); default EUR."""
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


def _iban_field(payload: dict, key: str, digest: str) -> str:
    """Validated IBAN: reject a present-but-malformed IBAN (422); derive a valid
    masked one when absent."""
    if key in payload and str(payload[key]).strip():
        iban = str(payload[key])
        if not _valid_iban(iban):
            raise LabActionError(
                422,
                f"invalid IBAN in {key!r}",
                code="invalid_iban",
                detail={"field": key},
            )
        return _mask_iban(iban)
    # Derived placeholder (already masked); never a real account.
    return f"DE**{'*' * 14}{digest[:4].upper()}"


def _require_payee(payload: dict) -> str | None:
    """Resolve the beneficiary, enforcing deterministic coherence ONLY on an
    explicit registered-payee reference.

    - ``payee_id`` is a reference to a payee created by add_payee: it MUST have
      the exact shape add_payee returns (``payee_<10 hex>``); a fabricated one is
      rejected (422). This gives add_payee -> create_payment coherence with no
      stored state.
    - ``payee`` (or absence) is a free-form one-off beneficiary: accepted as-is.
    """
    ref = payload.get("payee_id")
    if ref is not None:
        text = str(ref)
        suffix = text[len(_PAYEE_PREFIX) :]
        ok = text.startswith(_PAYEE_PREFIX) and len(suffix) == 10
        if ok:
            try:
                int(suffix, 16)
            except ValueError:
                ok = False
        if not ok:
            raise LabActionError(
                422,
                f"unknown payee {text!r}",
                code="unknown_payee",
                detail={"field": "payee_id", "got": text},
            )
        return text
    free = payload.get("payee")
    return str(free) if free is not None else None


def _pct(payload: dict, digest: str) -> str:
    """Validated percentage in (0, 100]; reject out-of-range when present."""
    if "discount_pct" in payload:
        raw = payload["discount_pct"]
        if isinstance(raw, bool) or not isinstance(raw, (int, float)) or not 0 < raw <= 100:
            raise LabActionError(
                422,
                f"invalid discount_pct {raw!r}: must be in (0, 100]",
                code="invalid_discount",
                detail={"field": "discount_pct", "got": raw, "expected": "(0, 100]"},
            )
        return f"{float(raw):.2f}"
    return f"{5 + int(digest[:2], 16) % 25}.00"


def handle(action_type: str, resource: str, payload: dict) -> dict | None:
    """Return a realistic deterministic response, ``None`` for an unknown action,
    or raise ``LabActionError`` for a known action with invalid input."""
    if action_type not in _KNOWN_ACTIONS:
        return None
    digest = _digest(action_type, resource, payload)
    base = {"action": action_type, "resource": resource, "result_id": digest[:12]}

    if action_type == "read_invoice_status":
        if resource in _DISCOVERY_RESOURCES:
            # Discovery: list the known seed invoices so an agent can find what
            # exists before acting -- no new governed action needed.
            return {
                **base,
                "status": "ok",
                "invoices": [
                    _entities.derive_invoice(iid).summary() for iid in _entities.SEED_INVOICES
                ],
            }
        invoice = _entities.derive_invoice(resource)
        return {
            **base,
            "status": "ok",
            "invoice_id": invoice.invoice_id,
            "invoice_status": invoice.status,
            "amount_due": invoice.amount,
            "currency": invoice.currency,
            "payee": invoice.payee,
            "due_in_days": invoice.due_in_days,
            "line_items": list(invoice.lines),
            "seeded": invoice.seeded,
        }
    if action_type == "trigger_refund":
        invoice = _entities.derive_invoice(resource)
        if not invoice.refundable:
            raise LabActionError(
                422,
                f"invoice {invoice.invoice_id!r} is paid and closed; issue a credit_note",
                code="invoice_paid",
                detail={
                    "invoice_id": invoice.invoice_id,
                    "status": invoice.status,
                    "hint": "paid invoices are closed; use create_credit_note",
                },
            )
        # Coherent with the invoice: a no-amount refund is a full refund; an
        # explicit amount is honoured (validated); currency follows the invoice
        # unless one is explicitly provided (and then validated).
        amount = _amount(payload, digest) if "amount" in payload else invoice.amount
        currency = _currency(payload) if "currency" in payload else invoice.currency
        return {
            **base,
            "status": "refunded",
            "refund_id": _ref("rfnd_", digest),
            "invoice_id": invoice.invoice_id,
            "invoice_status": invoice.status,
            "amount": amount,
            "currency": currency,
        }
    if action_type == "create_payment":
        payee = _require_payee(payload)
        return {
            **base,
            "status": "pending_approval",
            "payment_id": _ref("pay_", digest),
            "payee": payee or resource,
            "amount": _amount(payload, digest),
            "currency": _currency(payload),
        }
    if action_type == "launch_wire_transfer":
        amount = _amount(payload, digest)
        fee_cents = 1500 + int(digest[22:28], 16) % 8500
        return {
            **base,
            "status": "submitted",
            "wire_id": _ref("wire_", digest),
            "beneficiary": _require_payee(payload) or resource,
            "beneficiary_iban": _iban_field(payload, "iban", digest),
            "amount": amount,
            "currency": _currency(payload),
            "fee": f"{fee_cents // 100}.{fee_cents % 100:02d}",
            "value_seq": int(digest[28:34], 16),
        }
    if action_type == "modify_iban":
        account = _entities.derive_account(resource)
        return {
            **base,
            "status": "updated",
            "account": account.account_id,
            "holder": account.holder,
            "old_iban": account.iban,
            "iban": _iban_field(payload, "iban", digest),
        }
    if action_type == "modify_supplier_bank_details":
        supplier = _entities.derive_supplier(resource)
        return {
            **base,
            "status": "updated",
            "supplier": supplier.supplier_id,
            "supplier_name": supplier.name,
            "old_iban": supplier.iban,
            "iban": _iban_field(payload, "iban", digest),
        }
    if action_type == "add_payee":
        return {
            **base,
            "status": "created",
            "payee_id": _ref(_PAYEE_PREFIX, digest),
            "name": str(payload.get("name") or resource or "supplier"),
            "iban": _iban_field(payload, "iban", digest),
        }
    if action_type == "validate_invoice":
        invoice = _entities.derive_invoice(resource)
        return {
            **base,
            "status": "validated",
            "invoice_id": invoice.invoice_id,
            "invoice_status": invoice.status,
            "amount_due": invoice.amount,
            "currency": invoice.currency,
        }
    if action_type == "create_credit_note":
        invoice = _entities.derive_invoice(resource)
        amount = _amount(payload, digest) if "amount" in payload else invoice.amount
        currency = _currency(payload) if "currency" in payload else invoice.currency
        return {
            **base,
            "status": "issued",
            "credit_note_id": _ref("cn_", digest),
            "invoice_id": invoice.invoice_id,
            "amount": amount,
            "currency": currency,
        }
    if action_type == "modify_price":
        return {
            **base,
            "status": "updated",
            "sku": resource,
            "new_price": _amount(payload, digest),
            "currency": _currency(payload),
        }
    if action_type == "apply_mass_discount":
        return {
            **base,
            "status": "applied",
            "scope": resource,
            "discount_pct": _pct(payload, digest),
            "affected_items": 1 + int(digest[12:16], 16) % 5000,
        }
    if action_type == "export_financial_data":
        return {
            **base,
            "status": "exported",
            "export_id": _ref("exp_", digest),
            "dataset": resource,
            "format": str(payload.get("format") or "csv"),
            "columns": ["date", "account", "counterparty", "amount", "currency", "status"],
            "row_count": 1 + int(digest[16:22], 16) % 1000000,
        }
    if action_type == "freeze_operation":
        return {
            **base,
            "status": "frozen",
            "operation": resource or "operation/unknown",
            "freeze_id": _ref("frz_", digest),
        }
    # modify_billing_rule
    return {**base, "status": "updated", "rule_id": resource or _ref("rule_", digest)}
