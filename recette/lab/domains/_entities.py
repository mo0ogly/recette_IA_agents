"""Deterministic entity model for lab doubles.

An entity (an invoice, a payee, an account, a supplier) is a PURE function of
its id: ``derive_invoice("inv/9")`` returns the same Invoice for every action
that touches ``inv/9``, this run and every replay. Cross-call coherence
therefore needs no mutable state (I4): two actions referencing the same id
observe the same entity because both recompute it from the id alone.

No clock, no random, no stored state. Time is expressed as a relative ordinal
(``due_in_days``), never a wall-clock date, so the model stays byte-stable under
replay. The same id always yields the same entity.

Seed tuples (``SEED_INVOICES`` ...) are a small set of KNOWN ids the doubles can
surface for discovery. They are not state -- they are constants. An arbitrary id
still derives a valid entity (any id works), seed ids just derive a richer one.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass

INVOICE_STATES = ("paid", "pending", "overdue", "disputed")
CURRENCIES = ("EUR", "USD", "GBP", "CHF")

# Known ids surfaced for discovery (read with an empty/"all" resource lists them).
SEED_INVOICES = ("inv/2024-0001", "inv/2024-0002", "inv/2024-0003")
SEED_SUPPLIERS = ("supplier/acme", "supplier/globex", "supplier/initech")


def _edigest(kind: str, entity_id: str) -> str:
    """64-hex digest keyed ONLY on (kind, id) -- the coherence anchor.

    Independent of action_type/payload so every action touching the same entity
    derives the identical view (I4)."""
    return hashlib.sha256(f"entity:{kind}:{entity_id}".encode()).hexdigest()


def _pick(dig: str, choices: tuple[str, ...], *, offset: int = 0) -> str:
    window = dig[offset : offset + 4] or dig[:4]
    return choices[int(window, 16) % len(choices)]


def _int(dig: str, lo: int, hi: int, *, offset: int = 0) -> int:
    window = dig[offset : offset + 8] or dig[:8]
    return lo + (int(window, 16) % (hi - lo))


def _money(cents: int) -> str:
    """Format an integer number of cents as a fixed 2-decimal string."""
    return f"{cents // 100}.{cents % 100:02d}"


def _masked_iban(dig: str) -> str:
    """A deterministic masked IBAN placeholder (never a real account)."""
    return f"DE**{'*' * 14}{dig[:4].upper()}"


@dataclass(frozen=True)
class Invoice:
    """A finance invoice, fully derived from its id."""

    invoice_id: str
    status: str
    amount: str
    currency: str
    payee: str
    due_in_days: int
    lines: tuple[dict, ...]
    seeded: bool

    @property
    def refundable(self) -> bool:
        """A paid invoice is closed (refunds go through the credit-note flow)."""
        return self.status != "paid"

    def summary(self) -> dict:
        """A compact view for discovery listings."""
        return {
            "invoice_id": self.invoice_id,
            "invoice_status": self.status,
            "amount_due": self.amount,
            "currency": self.currency,
            "payee": self.payee,
        }


def _invoice_lines(dig: str, currency: str, count: int) -> tuple[tuple[dict, ...], int]:
    """Derive line items and the coherent total (in cents) they sum to."""
    lines: list[dict] = []
    total = 0
    for i in range(count):
        offset = 16 + i * 8
        qty = _int(dig, 1, 12, offset=offset)
        unit_cents = 500 + _int(dig, 0, 49500, offset=offset + 2)
        subtotal = qty * unit_cents
        total += subtotal
        lines.append(
            {
                "sku": f"SKU-{dig[offset : offset + 6].upper()}",
                "qty": qty,
                "unit_price": _money(unit_cents),
                "subtotal": _money(subtotal),
                "currency": currency,
            }
        )
    return tuple(lines), total


def derive_invoice(invoice_id: str) -> Invoice:
    """The Invoice for an id -- identical across actions and replays."""
    iid = invoice_id or "inv/unknown"
    dig = _edigest("invoice", iid)
    seeded = iid in SEED_INVOICES
    status = _pick(dig, INVOICE_STATES)
    currency = _pick(dig, CURRENCIES, offset=4)
    line_count = _int(dig, 2, 5, offset=8) if seeded else _int(dig, 1, 3, offset=8)
    lines, total = _invoice_lines(dig, currency, line_count)
    payee = f"{_pick(dig, ('ACME Ltd', 'Globex SA', 'Initech', 'Umbrella Corp'), offset=12)}"
    return Invoice(
        invoice_id=iid,
        status=status,
        amount=_money(total),
        currency=currency,
        payee=payee,
        due_in_days=_int(dig, 0, 60, offset=20),
        lines=lines,
        seeded=seeded,
    )


@dataclass(frozen=True)
class Account:
    """A finance account, fully derived from its id."""

    account_id: str
    holder: str
    iban: str
    currency: str
    balance: str

    def to_dict(self) -> dict:
        return {
            "account_id": self.account_id,
            "holder": self.holder,
            "iban": self.iban,
            "currency": self.currency,
            "balance": self.balance,
        }


def derive_account(account_id: str) -> Account:
    aid = account_id or "acct/unknown"
    dig = _edigest("account", aid)
    return Account(
        account_id=aid,
        holder=_pick(dig, ("Treasury", "Payroll", "Operations", "Reserve")),
        iban=_masked_iban(dig),
        currency=_pick(dig, CURRENCIES, offset=4),
        balance=_money(100000 + _int(dig, 0, 99000000, offset=8)),
    )


@dataclass(frozen=True)
class Supplier:
    """A finance supplier, fully derived from its id."""

    supplier_id: str
    name: str
    iban: str
    category: str
    seeded: bool

    def to_dict(self) -> dict:
        return {
            "supplier_id": self.supplier_id,
            "name": self.name,
            "iban": self.iban,
            "category": self.category,
        }


def derive_supplier(supplier_id: str) -> Supplier:
    sid = supplier_id or "supplier/unknown"
    dig = _edigest("supplier", sid)
    return Supplier(
        supplier_id=sid,
        name=_pick(dig, ("ACME Ltd", "Globex SA", "Initech", "Umbrella Corp")),
        iban=_masked_iban(dig),
        category=_pick(dig, ("hardware", "services", "logistics", "software"), offset=4),
        seeded=sid in SEED_SUPPLIERS,
    )
