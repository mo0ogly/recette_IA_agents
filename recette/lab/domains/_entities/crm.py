"""CRM lab entities: contacts, opportunities, sales accounts.

A behavioural state is assigned ONLY to ids in an explicit "blocking seed" set,
so an arbitrary id (a probe, a fresh scenario id) is always actionable; the
state-machine rejection is demonstrated through the seed ids.
"""

from __future__ import annotations

from dataclasses import dataclass

from ._common import _edigest, _money, _pick

__all__ = [
    "ACCOUNT_TIERS",
    "CONTACT_LIFECYCLE",
    "DEAL_STAGES_OPEN",
    "SEED_CLOSED_OPPORTUNITIES",
    "SEED_CONTACTS",
    "Contact",
    "Opportunity",
    "SalesAccount",
    "derive_contact",
    "derive_opportunity",
    "derive_sales_account",
]

CONTACT_LIFECYCLE = ("lead", "mql", "sql", "customer", "churned")
DEAL_STAGES_OPEN = ("prospecting", "qualification", "proposal", "negotiation")
ACCOUNT_TIERS = ("smb", "mid", "enterprise", "strategic")
SEED_CONTACTS = ("crm/contact/alice", "crm/contact/bob", "crm/contact/carol")
SEED_CLOSED_OPPORTUNITIES = ("crm/opp/closed-1",)


@dataclass(frozen=True)
class Contact:
    """A CRM contact, fully derived from its id."""

    contact_id: str
    account: str
    email: str
    lifecycle_stage: str
    owner: str
    seeded: bool

    def summary(self) -> dict:
        return {
            "contact_id": self.contact_id,
            "account": self.account,
            "email": self.email,
            "lifecycle_stage": self.lifecycle_stage,
        }


def _local_part(entity_id: str) -> str:
    tail = entity_id.split(":")[-1].split("/")[-1] or "contact"
    return tail.replace(" ", ".").lower()[:24]


def derive_contact(contact_id: str) -> Contact:
    cid = contact_id or "crm/contact/unknown"
    dig = _edigest("contact", cid)
    return Contact(
        contact_id=f"cnt_{dig[:10]}",
        account=cid,
        email=f"{_local_part(cid)}.{dig[:6]}@example-corp.test",
        lifecycle_stage=_pick(dig, CONTACT_LIFECYCLE),
        owner=f"usr_{dig[10:18]}",
        seeded=cid in SEED_CONTACTS,
    )


@dataclass(frozen=True)
class Opportunity:
    """A CRM opportunity, fully derived from its id."""

    opportunity_id: str
    stage: str
    amount: str
    currency: str
    account: str

    @property
    def closed(self) -> bool:
        """A closed-won opportunity is settled; its amount cannot be changed."""
        return self.stage == "closed_won"


def derive_opportunity(opportunity_id: str) -> Opportunity:
    oid = opportunity_id or "crm/opp/unknown"
    dig = _edigest("opportunity", oid)
    stage = "closed_won" if oid in SEED_CLOSED_OPPORTUNITIES else _pick(dig, DEAL_STAGES_OPEN)
    cents = 100000 + int(dig[:8], 16) % 9900000
    return Opportunity(
        opportunity_id=oid,
        stage=stage,
        amount=_money(cents),
        currency=_pick(dig, ("EUR", "USD", "GBP", "CHF"), offset=8),
        account=f"acct_{dig[10:16]}",
    )


@dataclass(frozen=True)
class SalesAccount:
    """A CRM account, fully derived from its id (current owner + tier)."""

    account_id: str
    name: str
    owner: str
    tier: str


def derive_sales_account(account_id: str) -> SalesAccount:
    aid = account_id or "crm/account/unknown"
    dig = _edigest("sales_account", aid)
    return SalesAccount(
        account_id=aid,
        name=_pick(dig, ("ACME Ltd", "Globex SA", "Initech", "Umbrella Corp")),
        owner=f"usr_{dig[:8]}",
        tier=_pick(dig, ACCOUNT_TIERS, offset=4),
    )
