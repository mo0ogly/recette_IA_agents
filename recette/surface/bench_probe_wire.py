"""Bench: precision/recall of the eBPF discovery probe against the wire truth.

Two independent observers watch the same agent egress at two altitudes:

* the **wire** overlay (mitmproxy) is the GROUND TRUTH of the real outbound
  HTTP(S) connections -- since the layered decode, every flow carries the real
  destination ``ip:port`` (``layers.l3l4``) and the client ``ja3`` (``layers.tls``);
* the **eBPF probe** (discoveryprobe) is the DETECTOR under test -- its broker
  emits one ``connect:ip:port`` surface token per outbound connect it saw.

This module joins the two by real ``ip:port`` (the only key both sides carry at
the network level) and scores the detector:

* **TP** -- endpoint seen by BOTH: the probe correctly detected a real egress.
* **FN** -- endpoint on the wire but NOT in the probe: a real egress the probe
  MISSED (the load-bearing failure for an agent-discovery tool).
* **FP** -- endpoint in the probe but NOT on the wire: a connect the wire did not
  record. The wire only sees PROXIED HTTP(S), so an FP here is not necessarily a
  probe error (DNS resolver, non-proxied egress); the console frames it as such.

``recall = TP/(TP+FN)`` is the headline (did the scanner miss any real egress);
``precision = TP/(TP+FP)`` is the softer companion given the coverage asymmetry.
JA3 is wire-only (eBPF at connect() never sees the ClientHello), so it LABELS the
wire endpoints, it is never a match key.

Pure and deterministic (I4): same inputs -> same report, byte for byte. No
wall-clock, no I/O -- the endpoint (probe.py) feeds it the live snapshots.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass

_CONNECT_PREFIX = "connect:"


@dataclass(frozen=True)
class BenchEndpoint:
    """One ``ip:port`` endpoint and how the two observers saw it."""

    endpoint: str  # "ip:port"
    ip: str
    port: int | None
    in_wire: bool
    in_probe: bool
    verdict: str  # "tp" | "fn" | "fp"
    # Wire-side labels (None when the endpoint is probe-only or unlabelled).
    host: str | None = None
    ja3: str | None = None

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass(frozen=True)
class BenchReport:
    """Detector scorecard: counts, the three rates, and the per-endpoint rows."""

    tp: int
    fp: int
    fn: int
    precision: float | None
    recall: float | None
    f1: float | None
    wire_endpoints: int
    probe_endpoints: int
    # Wire flows the overlay captured but that carry no L3/L4 IP (legacy addon):
    # surfaced so a partial-coverage bench is never silently reported as complete.
    wire_flows_without_ip: int
    endpoints: tuple[BenchEndpoint, ...]

    def to_dict(self) -> dict:
        blob = asdict(self)
        blob["endpoints"] = [e.to_dict() for e in self.endpoints]
        return blob


def _port_of(raw: str) -> int | None:
    try:
        return int(raw)
    except (TypeError, ValueError):
        return None


def wire_endpoints(wire_flows: list[dict]) -> tuple[dict[str, dict], int]:
    """Map ``ip:port`` -> {host, ja3} from wire flows carrying an L3/L4 IP.

    Returns the map plus the count of flows that had no ``layers.l3l4.dst_ip``
    (legacy rows), so the caller can report partial coverage honestly. When the
    same endpoint appears on several flows, the first non-empty host/ja3 wins
    (stable: flows arrive in monotone ``seq`` order)."""
    out: dict[str, dict] = {}
    without_ip = 0
    for flow in wire_flows:
        layers = flow.get("layers") if isinstance(flow, dict) else None
        l3l4 = layers.get("l3l4") if isinstance(layers, dict) else None
        dst_ip = l3l4.get("dst_ip") if isinstance(l3l4, dict) else None
        if not dst_ip:
            without_ip += 1
            continue
        dst_port = l3l4.get("dst_port")
        endpoint = f"{dst_ip}:{dst_port}" if dst_port is not None else str(dst_ip)
        tls = layers.get("tls") if isinstance(layers.get("tls"), dict) else {}
        label = out.setdefault(endpoint, {"host": None, "ja3": None})
        if not label["host"] and flow.get("host"):
            label["host"] = str(flow["host"])
        if not label["ja3"] and tls.get("ja3"):
            label["ja3"] = str(tls["ja3"])
    return out, without_ip


def probe_endpoints(recordings: list[dict]) -> set[str]:
    """Set of ``ip:port`` from every ``connect:ip:port`` ebpf_wire token."""
    endpoints: set[str] = set()
    for rec in recordings or []:
        surfaces = rec.get("surfaces") if isinstance(rec, dict) else None
        tokens = surfaces.get("ebpf_wire") if isinstance(surfaces, dict) else None
        for token in tokens or []:
            text = str(token)
            if text.startswith(_CONNECT_PREFIX):
                endpoints.add(text[len(_CONNECT_PREFIX) :])
    return endpoints


def _rate(numerator: int, denominator: int) -> float | None:
    """Ratio, or None when undefined (empty denominator) -- never a fake 0."""
    if denominator <= 0:
        return None
    return round(numerator / denominator, 4)


def build_bench_report(wire_flows: list[dict], probe_recordings: list[dict]) -> BenchReport:
    """Score the probe against the wire truth by real ``ip:port``. Pure (I4)."""
    wire_map, without_ip = wire_endpoints(wire_flows)
    probe_set = probe_endpoints(probe_recordings)
    wire_set = set(wire_map)

    rows: list[BenchEndpoint] = []
    for ep in sorted(wire_set | probe_set):
        ip, _, port_raw = ep.partition(":")
        in_wire = ep in wire_set
        in_probe = ep in probe_set
        verdict = "tp" if (in_wire and in_probe) else ("fn" if in_wire else "fp")
        label = wire_map.get(ep, {})
        rows.append(
            BenchEndpoint(
                endpoint=ep,
                ip=ip,
                port=_port_of(port_raw),
                in_wire=in_wire,
                in_probe=in_probe,
                verdict=verdict,
                host=label.get("host"),
                ja3=label.get("ja3"),
            )
        )

    tp = sum(1 for r in rows if r.verdict == "tp")
    fn = sum(1 for r in rows if r.verdict == "fn")
    fp = sum(1 for r in rows if r.verdict == "fp")
    precision = _rate(tp, tp + fp)
    recall = _rate(tp, tp + fn)
    # F1 = harmonic mean of precision and recall; None when either is undefined
    # or both are zero (no detections on either side to reconcile).
    if precision and recall and (precision + recall) > 0:
        f1 = round(2 * precision * recall / (precision + recall), 4)
    else:
        f1 = None

    return BenchReport(
        tp=tp,
        fp=fp,
        fn=fn,
        precision=precision,
        recall=recall,
        f1=f1,
        wire_endpoints=len(wire_set),
        probe_endpoints=len(probe_set),
        wire_flows_without_ip=without_ip,
        endpoints=tuple(rows),
    )
