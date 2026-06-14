"""finance mock handler -- W4 Finance / payments (13 actions).

A realistic deterministic double of a finance/payments API. Every response is
a pure function of (action_type, resource, payload): same input -> identical
response bytes, no clock, no random, no cross-call state (I4). Replays are
byte-stable.

Three levels of realism, all deterministic:
  1. Per-action business fields -- a create_payment returns a payment object
     (payment_id, payee, amount, currency, status), a modify_iban returns the
     masked IBANs, etc. -- not a generic blob.
  2. Input validation -- a known action called with explicitly invalid input is
     rejected with the status the real system would use (422), via
     ``LabActionError``. Validation is lenient on MISSING optional fields
     (a deterministic value is derived) and strict only on values that are
     present and wrong, so existing scenarios that omit fields still succeed.
  3. Deterministic coherence -- references are format-derived, not stored. A
     ``payee_id`` is valid iff it has the exact shape ``add_payee`` returns
     (``payee_<10 hex>``); a create_payment to a fabricated payee is rejected.
     This gives add_payee -> create_payment coherence WITHOUT mutable state
     (which would leak across runs and break replay).
"""

from __future__ import annotations

import hashlib
import json

from ..errors import LabActionError

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
    )
)

# ISO 4217 subset the double accepts; a present-but-unknown currency is rejected.
_CURRENCIES = frozenset(("EUR", "USD", "GBP", "CHF", "JPY", "CAD", "AUD"))
_INVOICE_STATES = ("paid", "pending", "overdue", "disputed")
_PAYEE_PREFIX = "payee_"


def _digest(action_type: str, resource: str, payload: dict) -> str:
    """64-hex stable digest of the full input (the determinism anchor, I4)."""
    material = f"finance:{action_type}:{resource}:{json.dumps(payload, sort_keys=True)}"
    return hashlib.sha256(material.encode("utf-8")).hexdigest()


def _ref(prefix: str, digest: str) -> str:
    """A realistic, stable identifier derived from the input digest."""
    return f"{prefix}{digest[:10]}"


def _derived_amount(digest: str) -> str:
    """A plausible decimal amount in [10.00, 9999.99], derived from the digest."""
    cents = 1000 + (int(digest[:8], 16) % 998999)
    return f"{cents // 100}.{cents % 100:02d}"


def _pick(digest: str, choices: tuple[str, ...]) -> str:
    """A deterministic choice from a tuple (stable per input)."""
    return choices[int(digest[8:12], 16) % len(choices)]


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
                422, f"invalid amount {payload['amount']!r}: must be a positive number"
            )
        return f"{value:.2f}"
    return _derived_amount(digest)


def _currency(payload: dict) -> str:
    """Validated currency: reject a present-but-unknown code (422); default EUR."""
    if "currency" in payload:
        cur = str(payload["currency"]).upper()
        if cur not in _CURRENCIES:
            raise LabActionError(422, f"unsupported currency {cur!r}")
        return cur
    return "EUR"


def _iban_field(payload: dict, key: str, digest: str) -> str:
    """Validated IBAN: reject a present-but-malformed IBAN (422); derive a valid
    masked one when absent."""
    if key in payload and str(payload[key]).strip():
        iban = str(payload[key])
        if not _valid_iban(iban):
            raise LabActionError(422, f"invalid IBAN in {key!r}")
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
      Wire transfers and one-off payments name a beneficiary string, not a
      registered id, so they must not be rejected.
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
            raise LabActionError(422, f"unknown payee {text!r}")
        return text
    free = payload.get("payee")
    return str(free) if free is not None else None


def _pct(payload: dict, digest: str) -> str:
    """Validated percentage in (0, 100]; reject out-of-range when present."""
    if "discount_pct" in payload:
        raw = payload["discount_pct"]
        if isinstance(raw, bool) or not isinstance(raw, (int, float)) or not 0 < raw <= 100:
            raise LabActionError(422, f"invalid discount_pct {raw!r}: must be in (0, 100]")
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
        return {
            **base,
            "status": "ok",
            "invoice_id": resource or _ref("inv_", digest),
            "invoice_status": _pick(digest, _INVOICE_STATES),
            "amount_due": _amount(payload, digest),
            "currency": _currency(payload),
        }
    if action_type == "trigger_refund":
        return {
            **base,
            "status": "refunded",
            "refund_id": _ref("rfnd_", digest),
            "invoice_id": resource,
            "amount": _amount(payload, digest),
            "currency": _currency(payload),
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
        return {
            **base,
            "status": "submitted",
            "wire_id": _ref("wire_", digest),
            "beneficiary": _require_payee(payload) or resource,
            "beneficiary_iban": _iban_field(payload, "iban", digest),
            "amount": _amount(payload, digest),
            "currency": _currency(payload),
        }
    if action_type == "modify_iban":
        return {
            **base,
            "status": "updated",
            "account": resource,
            "iban": _iban_field(payload, "iban", digest),
        }
    if action_type == "modify_supplier_bank_details":
        return {
            **base,
            "status": "updated",
            "supplier": resource,
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
        return {**base, "status": "validated", "invoice_id": resource}
    if action_type == "create_credit_note":
        return {
            **base,
            "status": "issued",
            "credit_note_id": _ref("cn_", digest),
            "invoice_id": resource,
            "amount": _amount(payload, digest),
            "currency": _currency(payload),
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
            "row_count": 1 + int(digest[16:22], 16) % 1000000,
        }
    # modify_billing_rule
    return {**base, "status": "updated", "rule_id": resource or _ref("rule_", digest)}
