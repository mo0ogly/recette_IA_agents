"""Wire-vs-audit reconciliation (allowlist slice).

A legitimate run only talks to MEDIATED targets (the lab, the mock_local servers,
the configured LLM backends). Any wire flow whose target (``host:port``) is
outside that allowlist is an UNMEDIATED path -- the ghost-agent / shadow-AI
signal: traffic on the network with no audit event behind it.

Pure: given the flows and the allowlist, ``reconcile`` returns the same report,
byte for byte (no clock, no network, I4). An empty/garbage host is treated as
SUSPECT (flagged), never allowed (deny-by-default classification). The lab
OBSERVES the unmediated path; it does not ENFORCE a network block.

Targets are keyed on a normalized ``host:port`` (matching the ``WireFlow`` shape,
which carries host and port separately); ``localhost`` and ``::1`` are folded to
``127.0.0.1`` so an allowlisted local server matches however the proxy named it.
"""

from __future__ import annotations

from dataclasses import dataclass

# Host strings (not a bind): the local-loopback aliases a proxy may record for
# the same local target. "0.0.0.0" is here as a host ALIAS to fold onto
# 127.0.0.1, never a bind address. nosec B104 - no socket binds here.
_LOCAL_ALIASES = frozenset(("localhost", "::1", "127.0.0.1", "0.0.0.0"))  # nosec B104


def _normalize_host(host: str) -> str:
    """Fold the local-loopback aliases onto ``127.0.0.1`` so a flow and the
    allowlist agree regardless of how the proxy spelled the local host."""
    return "127.0.0.1" if host in _LOCAL_ALIASES else host


def target_of(flow: dict) -> str:
    """The normalized ``host:port`` of a wire flow, or ``""`` when the host is
    missing (unclassifiable -> suspect)."""
    host = str(flow.get("host", ""))
    if not host:
        return ""
    return f"{_normalize_host(host)}:{flow.get('port', '')}"


@dataclass(frozen=True)
class ReconcileReport:
    """Outcome of one wire-vs-audit reconciliation. ``ok`` is True iff no flow
    fell outside the allowlist; ``bypass_flows`` lists the offending flows in
    seq order. ``audited_run_ids`` is the audit-view context (the runs that
    produced a ProxyTrace) -- empty for the target-only ``reconcile``."""

    ok: bool
    bypass_flows: list[dict]
    audited_run_ids: tuple[str, ...] = ()

    def to_dict(self) -> dict:
        return {
            "ok": self.ok,
            "bypass_flows": self.bypass_flows,
            "audited_run_ids": list(self.audited_run_ids),
        }


def reconcile(wire_flows: list[dict], allowlist: set[str]) -> ReconcileReport:
    """Flag every wire flow whose ``host:port`` is not an allowlisted mediated
    target. A flow with an empty host is flagged too (suspect, never silently
    allowed). Output is ordered by ``seq`` for a stable report (I4)."""
    bypass = [
        f
        for f in sorted(wire_flows, key=lambda flow: flow.get("seq", 0))
        if target_of(f) not in allowlist
    ]
    return ReconcileReport(ok=(bypass == []), bypass_flows=bypass)


def reconcile_run(
    wire_flows: list[dict],
    proxy_traces: list[dict],
    allowlist: set[str],
) -> ReconcileReport:
    """Wire<->audit join (run-scoped): step 4 of the ghost-direct-db scenario.

    A wire flow whose target is a mediated endpoint is EXPLAINED -- the proxy
    records a ``ProxyTrace`` for those side effects. A flow to a non-mediated
    target has no matching audit event (the proxy never traces a target it does
    not mediate), so it is a bypass. ``proxy_traces`` is the audit-view half:
    ``audited_run_ids`` reports which runs produced a genuine, mediated side
    effect, sharpening the signal (an audited run that ALSO made an unaudited
    egress is a stronger ghost indicator than a flow with no run at all).

    Pure and deterministic (I4): same inputs -> same report, byte for byte.
    The discriminator is target-based by decision (the wire carries raw bytes,
    not the canonical ``side_effect_hash``); a per-flow hash join is phase 3.
    """
    base = reconcile(wire_flows, allowlist)
    audited = tuple(sorted({str(t["run_id"]) for t in proxy_traces if t.get("run_id") is not None}))
    return ReconcileReport(ok=base.ok, bypass_flows=base.bypass_flows, audited_run_ids=audited)


def build_allowlist(
    *,
    servers: list[dict],
    lab_host: str,
    llm_hosts: set[str],
) -> set[str]:
    """Allowlisted mediated targets: the lab, every ``mock_local`` server
    (``127.0.0.1:port``), and the configured LLM backend hosts.

    A honeypot (any ``mode`` other than ``mock_local``) is deliberately excluded:
    it is never a legitimate target, so a flow to it is always a bypass. The
    empty string is never in the allowlist, so an unclassifiable flow is flagged.
    """
    allow = {lab_host} | {h for h in llm_hosts if h}
    for server in servers:
        if server.get("mode") == "mock_local" and server.get("port"):
            allow.add(f"127.0.0.1:{server['port']}")
    return allow
