"""Overlay the discovery verdict onto the REAL agent<->server exchange (pure, I4).

The console double-console shows the real exchange of a run as two views over the
same side effects: the HOOK view (``ProxyTrace`` -- the mediated/structured call)
and the WIRE view (``WireFlow`` -- the bytes on the network). This module answers,
for that same exchange, what the DISCOVERY core SAW:

- per agent: did discovery detect it on each observation surface, or is it a
  ghost (seen nowhere). Reuses the surface judge (``detect_agent`` +
  ``score_detections``) -- the SAME source-agnostic oracle the surface recette
  and the eBPF broker capture feed.
- per exchange: a hook ``ProxyTrace`` is an IDENTIFIED action (its structured
  intent is visible on the hook surface); a ``WireFlow`` is CORROBORATED when it
  joins back to an audited side effect, and a GHOST exchange (wire-only, not
  identified) when it does not -- exactly a ``reconcile_strict`` bypass.

``WireFlow`` carries no ``agent_id`` by design (that absence is what makes a ghost
detectable: wire-seen, hook-blind). A live buffer therefore cannot reconstruct a
ghost AGENT (there is no id to attribute an unmediated flow to) -- so per-agent
detection here is HOOK-attributable only (the 3 hook surfaces; ``ebpf_wire`` is
run-scoped, never claimed per agent). The ghost signal lives at the EXCHANGE
level instead: ``ghost_exchanges`` counts the wire-only flows with no audited
side effect (the run saw network traffic it could not attribute to any identified
agent). Pure function of (proxy_traces, wire_flows, allowlist): no clock, no
random, sorted output, replay-stable (I4).
"""

from __future__ import annotations

from dataclasses import dataclass

from recette.platform.proxy.reconcile import reconcile_strict, target_of

from .detect import AgentDetection, ReferenceSurfaceDiscoveryAdapter, detect_agent
from .scorecard import DetectionScorecard, score_detections


@dataclass(frozen=True)
class ExchangeVerdict:
    """One exchange of the run, annotated with what discovery saw of it.

    ``kind`` is ``"hook"`` (a mediated ``ProxyTrace``) or ``"wire"`` (a
    ``WireFlow``). ``identified`` is True for every hook exchange (its structured
    intent is visible) and for a wire flow that joins back to an audited side
    effect; a wire flow that does not is a GHOST exchange (``identified`` False,
    ``reason`` = the ``reconcile_strict`` bypass reason). ``agent_id`` is the
    agent for a hook exchange and ``None`` for a wire flow (not attributable).
    """

    seq: int
    kind: str
    identified: bool
    reason: str | None
    agent_id: str | None
    target: str
    action_type: str | None
    run_id: str | None

    def to_dict(self) -> dict:
        return {
            "seq": self.seq,
            "kind": self.kind,
            "identified": self.identified,
            "reason": self.reason,
            "agent_id": self.agent_id,
            "target": self.target,
            "action_type": self.action_type,
            "run_id": self.run_id,
        }


@dataclass(frozen=True)
class ExchangeReport:
    """The discovery-vs-exchange overlay for one run (or the whole buffer).

    ``agents`` is the per-agent detection (hook grouped by ``agent_id``, wire
    run-scoped); ``scorecard.false_negatives`` are the ghost agents; ``exchanges``
    is the per-exchange drill-down (hook identified + wire corroborated/ghost).
    """

    run_id: str | None
    agents: tuple[AgentDetection, ...]
    scorecard: DetectionScorecard
    exchanges: tuple[ExchangeVerdict, ...]
    ghost_exchanges: int

    def to_dict(self) -> dict:
        return {
            "run_id": self.run_id,
            "ghost_exchanges": self.ghost_exchanges,
            "agents": [
                {
                    "agent_id": a.agent_id,
                    "detected_anywhere": a.detected_anywhere,
                    "per_surface": [
                        {"surface": d.surface.value, "detected": d.detected} for d in a.per_surface
                    ],
                }
                for a in self.agents
            ],
            "scorecard": {
                "ok": self.scorecard.ok,
                "total_agents": self.scorecard.total_agents,
                "detected_per_surface": dict(self.scorecard.detected_per_surface),
                "false_negatives": list(self.scorecard.false_negatives),
            },
            "exchanges": [e.to_dict() for e in self.exchanges],
        }


def _hook_target(trace: dict) -> str:
    """Human target of a mediated call: ``target_system/resource``."""
    return f"{trace.get('target_system', '')}/{trace.get('resource', '')}"


def _wire_target(flow: dict) -> str:
    """Human target of a network flow: ``method host:port path``."""
    return f"{flow.get('method', '')} {target_of(flow)}{flow.get('path', '')}".strip()


def build_exchange_report(
    *,
    proxy_traces: list[dict],
    wire_flows: list[dict],
    allowlist: set[str],
    run_id: str | None = None,
) -> ExchangeReport:
    """Compose the per-agent detection and per-exchange verdict (pure, I4).

    Reuses ``detect_agent`` (one detection per distinct ``agent_id`` of the hook
    traces, wire passed whole = run-scoped), ``score_detections`` (ghosts), and
    ``reconcile_strict`` (which wire flows join back to an audited side effect).
    Output is sorted (agents by id, exchanges by (kind, seq)) so the same inputs
    yield a byte-stable report.
    """
    adapter = ReferenceSurfaceDiscoveryAdapter()
    agent_ids = sorted({str(t.get("agent_id", "")) for t in proxy_traces})
    # Per-agent detection is HOOK-attributable only: wire flows carry no agent_id,
    # so passing them per agent would falsely claim every agent was seen on the
    # wire. Wire flows go through the exchange-level ghost join below instead.
    detections = [
        detect_agent(
            agent_id=agent_id,
            proxy_traces=[t for t in proxy_traces if str(t.get("agent_id", "")) == agent_id],
            wire_flows=[],
            adapter=adapter,
        )
        for agent_id in agent_ids
    ]
    scorecard = score_detections(detections)

    # reconcile_strict marks every wire flow that does NOT join back to an audited
    # side effect as a bypass (= a ghost exchange) with its reason.
    bypass = reconcile_strict(wire_flows, proxy_traces, allowlist).bypass_flows
    bypass_reason: dict[int, str] = {
        int(f.get("seq", 0)): str(f.get("bypass_reason", "")) for f in bypass
    }

    exchanges: list[ExchangeVerdict] = []
    for trace in proxy_traces:
        exchanges.append(
            ExchangeVerdict(
                seq=int(trace.get("seq", 0)),
                kind="hook",
                identified=True,
                reason=None,
                agent_id=str(trace.get("agent_id", "")) or None,
                target=_hook_target(trace),
                action_type=trace.get("action_type"),
                run_id=trace.get("run_id"),
            )
        )
    for flow in wire_flows:
        seq = int(flow.get("seq", 0))
        reason = bypass_reason.get(seq)
        exchanges.append(
            ExchangeVerdict(
                seq=seq,
                kind="wire",
                identified=reason is None,
                reason=reason,
                agent_id=None,
                target=_wire_target(flow),
                action_type=None,
                run_id=flow.get("run_id"),
            )
        )
    exchanges.sort(key=lambda e: (e.kind, e.seq))
    ghost_exchanges = sum(1 for e in exchanges if not e.identified)

    return ExchangeReport(
        run_id=run_id,
        agents=tuple(detections),
        scorecard=scorecard,
        exchanges=tuple(exchanges),
        ghost_exchanges=ghost_exchanges,
    )
