"""Support desk lab entity: tickets (derived from id)."""

from __future__ import annotations

from dataclasses import dataclass

from ._common import _edigest, _pick

__all__ = [
    "PRIORITIES",
    "SEED_CLOSED_TICKETS",
    "SEED_TICKETS",
    "TICKET_STATES_MUTABLE",
    "Ticket",
    "derive_ticket",
]

PRIORITIES = ("low", "normal", "high", "urgent")
TICKET_STATES_MUTABLE = ("open", "pending", "on_hold", "solved")
SEED_TICKETS = ("support/ticket/t-1001", "support/ticket/t-1002")
SEED_CLOSED_TICKETS = ("support/ticket/closed-1",)


@dataclass(frozen=True)
class Ticket:
    """A support ticket, fully derived from its id."""

    ticket_id: str
    priority: str
    state: str
    requester: str
    vip: bool

    @property
    def mutable(self) -> bool:
        """A closed ticket is immutable; reopen it before changing its status."""
        return self.state != "closed"

    def summary(self) -> dict:
        return {
            "ticket_id": self.ticket_id,
            "priority": self.priority,
            "state": self.state,
            "vip": self.vip,
        }


def derive_ticket(ticket_id: str) -> Ticket:
    tid = ticket_id or "support/ticket/unknown"
    dig = _edigest("ticket", tid)
    state = "closed" if tid in SEED_CLOSED_TICKETS else _pick(dig, TICKET_STATES_MUTABLE, offset=4)
    return Ticket(
        ticket_id=tid,
        priority=_pick(dig, PRIORITIES),
        state=state,
        requester=f"cust_{dig[:8]}",
        vip=tid in SEED_TICKETS,
    )
