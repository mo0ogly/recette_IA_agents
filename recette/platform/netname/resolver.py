"""Pure name resolution over the server registry (I4).

A name resolves to a server entry by fqdn -> alias -> id. With containment ON,
an unknown name is DENIED (fail-safe). With containment OFF, an unknown name
returns None so the caller keeps the legacy id-based path (realism-only mode).

Purity: no socket, no clock, no random -- a pure function of (name, servers,
containment). Resolution is deterministic and replay-stable. This module lives
in the Data Plane and is NEVER called from the decision path (decide()).
"""

from __future__ import annotations


class ResolutionDenied(Exception):
    """A name is not in the allowlist and containment is enforced (fail-safe deny)."""

    def __init__(self, name: str) -> None:
        super().__init__(f"name not in private DNS allowlist: {name}")
        self.name = name


def resolve_name(name: str, servers: list[dict], *, containment: bool) -> dict | None:
    """Resolve a name to its server entry, or None (containment off + unknown).

    Raises ResolutionDenied when containment is on and the name is unknown.
    """
    for server in servers:
        if name == server.get("fqdn"):
            return server
    for server in servers:
        if name in (server.get("aliases") or []):
            return server
    for server in servers:
        if name == server.get("id"):
            return server
    if containment:
        raise ResolutionDenied(name)
    return None
