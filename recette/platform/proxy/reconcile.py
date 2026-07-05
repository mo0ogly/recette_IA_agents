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

import json
from dataclasses import dataclass

from .protocol import side_effect_hash

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


def wire_flow_side_effect_hash(flow: dict) -> str | None:
    """Recompute the ``side_effect_hash`` of a governed action from its wire flow.

    Mirrors exactly what ``LabHttpProxy.execute`` hashes: target_system from the
    ``/{target_system}/execute`` path, ``action_type``/``resource`` from the
    request body, and the unwrapped ``data`` of the lab envelope as the response.
    Returns ``None`` when the flow is not a governed-action call (a different
    path, a non-JSON body) -- such traffic (health checks, etc.) is benign and is
    not correlated. Pure/deterministic (I4)."""
    parts = [p for p in str(flow.get("path", "")).split("/") if p]
    if len(parts) != 2 or parts[1] != "execute":
        return None
    target_system = parts[0]
    try:
        request = json.loads(flow.get("request_body") or "{}")
        envelope = json.loads(flow.get("response_body") or "{}")
    except (TypeError, ValueError):
        return None
    if not isinstance(request, dict) or not isinstance(envelope, dict):
        return None
    data = envelope.get("data")
    response = data if isinstance(data, dict) else {"data": data}
    return side_effect_hash(
        target_system,
        str(request.get("action_type", "")),
        str(request.get("resource", "")),
        response,
    )


def reconcile_strict(
    wire_flows: list[dict],
    proxy_traces: list[dict],
    allowlist: set[str],
) -> ReconcileReport:
    """Phase-3 reconciliation: per-flow ``side_effect_hash`` join (I4).

    Stronger than ``reconcile_run``: it also catches a ghost that hits an
    ALLOWLISTED target directly (e.g. a raw write to a mock_local server,
    bypassing the gateway). Every governed-action flow (``/{ts}/execute``) to a
    mediated target MUST have a matching ``ProxyTrace`` (same recomputed hash);
    one that does not is an unaudited side effect -- a ghost via an allowlisted
    target. Each bypass carries a ``bypass_reason``:

    - ``non_mediated_target`` -- the target is not mediated at all (phase 1/2);
    - ``no_audit_event`` -- a governed-action flow to a mediated target with no
      matching audit event.

    Non-``/execute`` traffic to a mediated target (health probes, etc.) is benign
    and never flagged.

    Per-flow hash source: when a flow dict carries the ``side_effect_hash`` KEY
    (the persisted column served by ``snapshot_dicts``/``query``), that value is
    used as-is -- no JSON re-parse. Key present with value ``None`` means a
    non-governed flow persisted as NULL: benign, same as a computed ``None``.
    Key ABSENT means a legacy dict: the hash is recomputed from the bytes
    (back-compat). Pure: same inputs -> same report, byte for byte."""
    audited_hashes = {t["side_effect_hash"] for t in proxy_traces if t.get("side_effect_hash")}
    bypass: list[dict] = []
    for flow in sorted(wire_flows, key=lambda f: f.get("seq", 0)):
        if target_of(flow) not in allowlist:
            bypass.append({**flow, "bypass_reason": "non_mediated_target"})
            continue
        digest = (
            flow["side_effect_hash"]
            if "side_effect_hash" in flow
            else wire_flow_side_effect_hash(flow)
        )
        if digest is None:
            continue  # not a governed-action call to a mediated target -> benign
        if digest not in audited_hashes:
            bypass.append({**flow, "bypass_reason": "no_audit_event"})
    audited_runs = tuple(
        sorted({str(t["run_id"]) for t in proxy_traces if t.get("run_id") is not None})
    )
    return ReconcileReport(ok=(bypass == []), bypass_flows=bypass, audited_run_ids=audited_runs)


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
