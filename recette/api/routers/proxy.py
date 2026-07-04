"""Side-effect proxy debug endpoints (I5 observability).

Two altitudes over the SAME side effects:
- ``/proxy/traces`` -- the APPLICATION view (ProxyTrace), recorded by the
  gateway's TracingProxy at the ExternalSystemProxy boundary.
- ``/proxy/wire`` -- the NETWORK view (WireFlow), the bytes on the wire, fed by
  the OPTIONAL mitmproxy Docker overlay (``POST /proxy/wire`` ingest).

Both buffers are jettable views persisted in the SQLite proxy store (I1 keeps
the durable truth in the append-only audit log), so a ``clear`` is allowed -- it
discards the debug buffer, never the log. The ingest is the only mutating route
here and it only appends to the bounded debug store; it never touches the event
store.
"""

from __future__ import annotations

import logging
import os
import subprocess
from pathlib import Path

from fastapi import APIRouter, HTTPException, Request

from ...platform.proxy.reconcile import wire_flow_side_effect_hash
from ...platform.proxy.redact import redact_mapping, redaction_enabled


def _redacted_view(d: dict) -> dict:
    """Redact secret shapes in an emitted VIEW dict, preserving the integrity hash.

    Best-effort masking for the console (default ON, ``INSPECT_IA_AGENTS_PROXY_REDACT``
    to disable). Transforms the emitted dict only -- never the recorded
    WireFlow/ProxyTrace objects or the audit log (I1). ``side_effect_hash`` is
    restored verbatim so the integrity value is never altered."""
    if not redaction_enabled():
        return d
    seh = d.get("side_effect_hash")
    out = {k: redact_mapping(v) for k, v in d.items()}
    out["side_effect_hash"] = seh  # never redact the integrity hash
    return out


router = APIRouter(prefix="/proxy", tags=["proxy"])


@router.get("/debug")
def get_debug_status(request: Request) -> dict:
    """Whether proxy debug tracing is on, and how many traces are buffered.

    ``store_error`` surfaces the last storage failure of the SQLite debug
    store (``None`` when healthy) so the console can flag a degraded buffer."""
    recorder = request.app.state.proxy_trace_recorder
    return {
        "debug_enabled": bool(request.app.state.proxy_debug_enabled),
        "trace_count": len(recorder.snapshot()),
        "store_error": recorder.store_error,
    }


@router.post("/debug")
def set_debug(request: Request, body: dict) -> dict:
    """Toggle side-effect trace recording at runtime (operator action).

    Flips both the app flag (surfaced to the console) and the live TracingProxy
    so the change takes effect immediately, no restart. Fail-safe: a non-bool
    ``enabled`` is a 422 (never silently keep the old state). Logged via tracing
    as an operator action; NOT appended to the canonical event store (it is an
    ops action, not an agent action)."""
    enabled = body.get("enabled")
    if not isinstance(enabled, bool):
        raise HTTPException(status_code=422, detail="body.enabled (bool) is required")
    request.app.state.proxy_debug_enabled = enabled
    proxy = getattr(request.app.state, "tracing_proxy", None)
    if proxy is not None and hasattr(proxy, "set_enabled"):
        proxy.set_enabled(enabled)
    logging.getLogger("recette.proxy").info("operator set proxy debug enabled=%s", enabled)
    return {"debug_enabled": enabled}


@router.get("/traces")
def list_traces(request: Request, tail: int | None = None, run_id: str | None = None) -> dict:
    """Recorded side-effect traces in monotone seq order (oldest first).

    ``run_id`` narrows the view to the traces of one run (F3 run <-> traces
    link); applied before ``tail``. ``tail`` keeps only the last N traces
    (live-console backfill). Stays read-only.
    """
    traces = request.app.state.proxy_trace_recorder.snapshot()
    if run_id is not None:
        traces = [t for t in traces if t.run_id == run_id]
    if tail is not None and tail >= 0:
        traces = traces[-tail:]
    return {
        "debug_enabled": bool(request.app.state.proxy_debug_enabled),
        "traces": [_redacted_view(t.to_dict()) for t in traces],
    }


@router.get("/receipts")
def list_receipts(request: Request, tail: int | None = None, run_id: str | None = None) -> dict:
    """Content-free context receipts of the recorded side effects.

    Same selection as ``/traces`` (run_id then tail) but each entry is the
    privacy-safe receipt: intent metadata + body byte-size + SHA-256, NEVER the
    request/response bodies. Lets an auditor prove what crossed the boundary and
    that it is unchanged without the platform exposing the content (RSSI-safe).
    """
    from ...context_receipt import chain_receipts

    traces = request.app.state.proxy_trace_recorder.snapshot()
    if run_id is not None:
        traces = [t for t in traces if t.run_id == run_id]
    if tail is not None and tail >= 0:
        traces = traces[-tail:]
    return {"receipts": chain_receipts([t.to_dict() for t in traces])}


@router.get("/receipts/verify")
def verify_receipts(request: Request, run_id: str | None = None) -> dict:
    """Verify the receipt hash chain (sequence-integrity proof, like I1).

    Recomputes every chained hash from genesis over the same selection; ``ok``
    false reports the first break. Read-only, content-free."""
    from ...context_receipt import chain_receipts, verify_chain

    traces = request.app.state.proxy_trace_recorder.snapshot()
    if run_id is not None:
        traces = [t for t in traces if t.run_id == run_id]
    return verify_chain(chain_receipts([t.to_dict() for t in traces]))


@router.get("/receipts/export")
def export_receipts_route(request: Request, run_id: str | None = None) -> dict:
    """A transferable, Ed25519-signed export of the chained receipts.

    The envelope carries the content-free chained receipts + their chain head,
    signed when a signing key is configured (fail-safe unsigned otherwise). Lets
    an auditor verify the trail OFF-platform with the public key alone."""
    from ...context_receipt import chain_receipts
    from ...receipt_export import export_receipts

    traces = request.app.state.proxy_trace_recorder.snapshot()
    if run_id is not None:
        traces = [t for t in traces if t.run_id == run_id]
    return export_receipts(chain_receipts([t.to_dict() for t in traces]))


@router.get("/receipts/root-attestation")
def receipts_root_attestation_route(request: Request, run_id: str | None = None) -> dict:
    """A tiny, Ed25519-signed commitment to the receipts: chain head + count +
    Merkle root, NO receipts. Pair it with GET /proxy/receipts/merkle/proof to
    attest that ONE side effect crossed the boundary without disclosing the
    others (selective disclosure). Unsigned (fail-safe) when no key is set."""
    from ...context_receipt import chain_receipts
    from ...receipt_export import export_root_attestation

    traces = request.app.state.proxy_trace_recorder.snapshot()
    if run_id is not None:
        traces = [t for t in traces if t.run_id == run_id]
    return export_root_attestation(chain_receipts([t.to_dict() for t in traces]))


@router.get("/receipts/merkle")
def receipts_merkle_route(request: Request, run_id: str | None = None) -> dict:
    """The Merkle root committing to the current chained receipts (+ count).

    A single value that commits to the whole batch; pair it with an inclusion
    proof (below) to attest that ONE receipt is committed without disclosing the
    others (selective disclosure). Pure given the snapshot (I4), content-free."""
    from ...context_receipt import chain_receipts
    from ...receipt_merkle import merkle_root

    traces = request.app.state.proxy_trace_recorder.snapshot()
    if run_id is not None:
        traces = [t for t in traces if t.run_id == run_id]
    receipts = chain_receipts([t.to_dict() for t in traces])
    return {"root": merkle_root(receipts), "count": len(receipts)}


@router.get("/receipts/merkle/proof")
def receipts_merkle_proof_route(request: Request, seq: int, run_id: str | None = None) -> dict:
    """Inclusion proof that the receipt with ``seq`` is committed under the root.

    Returns ``{leaf, index, count, root, path}`` -- the disclosed leaf plus the
    sibling-hash audit path; a verifier reconstructs the root from these alone,
    never the other receipts. A ``seq`` absent from the (run-scoped) selection is
    a 404. Pure given the snapshot (I4), content-free."""
    from ...context_receipt import chain_receipts
    from ...receipt_merkle import inclusion_proof

    traces = request.app.state.proxy_trace_recorder.snapshot()
    if run_id is not None:
        traces = [t for t in traces if t.run_id == run_id]
    receipts = chain_receipts([t.to_dict() for t in traces])
    index = next((i for i, r in enumerate(receipts) if r.get("seq") == seq), None)
    if index is None:
        raise HTTPException(status_code=404, detail=f"no receipt with seq {seq} in selection")
    return inclusion_proof(receipts, index)


@router.post("/receipts/verify-import")
def verify_import_route(request: Request, envelope: dict) -> dict:
    """Cross-verify a third-party receipt export envelope (off-platform proof).

    Stateless and pure (I4): takes ANY ``inspect_ia_agents-receipt-export-v1`` envelope
    (exported here or elsewhere) and checks the Ed25519 signature over its
    canonical payload, plus the receipt hash chain. Returns ``signature`` (the
    verify_export verdict) and ``chain`` (the chain-integrity verdict). Never
    touches the audit log or the buffers; nothing is trusted, the envelope
    crosses a process boundary and is fully re-verified. ``expected_public_key``
    (optional query) pins the signer."""
    from ...context_receipt import verify_chain
    from ...receipt_export import verify_export

    if not isinstance(envelope, dict):
        raise HTTPException(status_code=422, detail="body must be an export envelope object")
    expected = request.query_params.get("expected_public_key") or None
    signature = verify_export(envelope, expected_public_key=expected)
    receipts = envelope.get("receipts")
    chain = verify_chain(receipts if isinstance(receipts, list) else [])
    return {"signature": signature, "chain": chain}


@router.delete("/traces")
def clear_traces(request: Request) -> dict:
    """Discard the debug trace buffer (the audit log is untouched, I1)."""
    request.app.state.proxy_trace_recorder.clear()
    return {"cleared": True}


@router.get("/wire/status")
def get_wire_status(request: Request) -> dict:
    """Whether the wire overlay is active, its proxy URL, and buffered flow count.

    ``enabled`` reflects configuration (INSPECT_IA_AGENTS_WIRE_PROXY set): it says the
    overlay is wired, not that a container is currently reachable -- liveness is
    observed through arriving flows, not asserted here (fail-safe, no probe in a
    read path)."""
    proxy_url = request.app.state.wire_proxy_url
    recorder = request.app.state.wire_flow_recorder
    return {
        "enabled": proxy_url is not None,
        "proxy_url": proxy_url,
        "flow_count": len(recorder.snapshot()),
    }


@router.post("/wire/overlay")
def control_wire_overlay(request: Request, body: dict) -> dict:
    """Start/stop the OPTIONAL mitmproxy wire overlay (operator action).

    Deny-by-default: the API spawns docker only when
    INSPECT_IA_AGENTS_ALLOW_WIRE_CONTROL is truthy (fail-safe, R5). The script only
    STARTS/STOPS the container; routing agent traffic through it still needs the
    API restarted with INSPECT_IA_AGENTS_WIRE_PROXY set and the CA trusted --
    reported back in ``next_step``. Logged via tracing (ops action), never
    appended to the canonical event store."""
    action = body.get("action")
    if action not in {"up", "down"}:
        raise HTTPException(status_code=422, detail='body.action must be "up" or "down"')
    allowed = os.environ.get("INSPECT_IA_AGENTS_ALLOW_WIRE_CONTROL", "").strip().lower()
    if allowed not in {"1", "true", "yes", "on"}:
        raise HTTPException(
            status_code=403,
            detail="wire overlay control disabled (set INSPECT_IA_AGENTS_ALLOW_WIRE_CONTROL=1)",
        )
    logging.getLogger("recette.proxy").info("operator wire overlay action=%s", action)
    # Resolve the repo root from this module's path so the launcher is found
    # regardless of the API process cwd (recette/api/routers/proxy.py -> repo root).
    repo_root = Path(__file__).resolve().parents[3]
    try:
        result = subprocess.run(
            ["./recette.sh", "wire", action],
            capture_output=True,
            text=True,
            timeout=120,
            check=False,
            cwd=str(repo_root),
        )
    except (OSError, subprocess.SubprocessError) as exc:
        raise HTTPException(status_code=502, detail=f"wire control failed: {exc}") from exc
    ok = result.returncode == 0
    return {
        "ok": ok,
        "action": action,
        "returncode": result.returncode,
        "next_step": (
            "set INSPECT_IA_AGENTS_WIRE_PROXY + trust the CA, then ./recette.sh api restart"
            if action == "up"
            else None
        ),
    }


@router.post("/wire", status_code=201)
def ingest_wire_flow(request: Request, payload: dict) -> dict:
    """Ingest one normalized flow from the mitmproxy overlay addon.

    Appends to the bounded wire debug buffer only; never the audit log. A non-object
    payload is a malformed ingest -> 422 (the addon controls the shape, but the
    body crosses a process boundary, so it is validated, not trusted)."""
    try:
        flow = request.app.state.wire_flow_recorder.record(payload)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return {"recorded": True, "seq": flow.seq}


@router.get("/wire")
def list_wire_flows(request: Request, tail: int | None = None, run_id: str | None = None) -> dict:
    """Recorded wire flows in monotone seq order (oldest first).

    ``run_id`` narrows to one run's flows (applied before ``tail``); ``tail``
    keeps only the last N. Read-only."""
    flows = request.app.state.wire_flow_recorder.snapshot()
    if run_id is not None:
        flows = [f for f in flows if f.run_id == run_id]
    if tail is not None and tail >= 0:
        flows = flows[-tail:]

    def _enrich(flow_dict: dict) -> dict:
        # Derived VIEW field: canonical side_effect_hash recomputed from the bytes
        # so the console can join a wire flow to its app-level exchange (None when
        # the flow is not a governed-action shape). Recorded WireFlow stays pure;
        # computed read-only here (I1/I4).
        return {**flow_dict, "side_effect_hash": wire_flow_side_effect_hash(flow_dict)}

    return {
        "enabled": request.app.state.wire_proxy_url is not None,
        "proxy_url": request.app.state.wire_proxy_url,
        "flows": [_redacted_view(_enrich(f.to_dict())) for f in flows],
    }


@router.delete("/wire")
def clear_wire_flows(request: Request) -> dict:
    """Discard the wire flow buffer (the audit log is untouched, I1)."""
    request.app.state.wire_flow_recorder.clear()
    return {"cleared": True}


@router.get("/route")
def get_proxy_route(request: Request) -> dict:
    """The selectable transport targets (direct vs wire overlay) + the active one.

    Transport selection only -- it changes how a side effect reaches the target,
    never the decision (I4). Surfaced in the network-debug consoles."""
    registry = request.app.state.proxy_route_registry
    return {
        "active": registry.active(),
        "targets": [t.to_dict() for t in registry.targets()],
    }


@router.post("/route")
def set_proxy_route(request: Request, body: dict) -> dict:
    """Select the active transport target. Applies to runs started afterwards.

    A missing/unknown target is a 422 (fail-safe: never silently keep the old
    route on a bad selection)."""
    target = body.get("target")
    if not isinstance(target, str) or not target:
        raise HTTPException(status_code=422, detail="body.target (string) is required")
    try:
        chosen = request.app.state.proxy_route_registry.set_active(target)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return {"active": chosen.id, "proxy_url": chosen.proxy_url}


def _build_run_allowlist(request: Request, run_id: str | None):
    """The run's flows + traces (as dicts) and the mediated-target allowlist.

    Shared by reconciliation and the discovery-exchange overlay so both see the
    exact same recorder snapshots and allowlist. Pure given the snapshots (I4);
    no side effect. Returns ``(allow, flow_dicts, trace_dicts)``."""
    from urllib.parse import urlparse

    from ...llm import provider_host
    from ...platform.proxy.lab_proxy import lab_url_from_env
    from ...platform.proxy.reconcile import build_allowlist, target_of

    flows = request.app.state.wire_flow_recorder.snapshot()
    traces = request.app.state.proxy_trace_recorder.snapshot()
    if run_id is not None:
        flows = [f for f in flows if f.run_id == run_id]
        traces = [t for t in traces if t.run_id == run_id]
    lab = urlparse(lab_url_from_env())
    # Normalize through target_of so "localhost:8082" matches a flow recorded as
    # "127.0.0.1:8082" (and vice versa).
    lab_host = target_of({"host": lab.hostname or "127.0.0.1", "port": lab.port or 8082})
    # A configured LLM backend is a mediated target: a real-mode run's traffic to
    # its host must not be mistaken for an unmediated path (task C).
    config_store = request.app.state.config_store
    llm_hosts = {
        host
        for backend in config_store.read().get("ai_backends", [])
        if (host := provider_host(backend.get("provider", ""), backend.get("base_url")))
    }
    allow = build_allowlist(
        servers=config_store.list_servers(),
        lab_host=lab_host,
        llm_hosts=llm_hosts,
    )
    return allow, [f.to_dict() for f in flows], [t.to_dict() for t in traces]


def _reconcile_report(request: Request, run_id: str | None, *, strict: bool = False):
    """Compute the run-scoped wire<->audit reconciliation over the live recorders.

    Shared by the read endpoint and the raise endpoint so both see the exact
    same join. ``strict`` selects the phase-3 per-flow side_effect_hash join
    (catches a ghost via an allowlisted target); the default is the phase-2
    target/run join. Pure given the recorder snapshots (I4); no side effect."""
    from ...platform.proxy.reconcile import reconcile_run, reconcile_strict

    allow, flow_dicts, trace_dicts = _build_run_allowlist(request, run_id)
    join = reconcile_strict if strict else reconcile_run
    return join(flow_dicts, trace_dicts, allow)


@router.get("/discovery-exchange")
def get_discovery_exchange(
    request: Request, run_id: str | None = None, strict: bool = True
) -> dict:
    """Overlay the discovery verdict onto the real exchange (run-scoped).

    Joins the two real-exchange views (ProxyTrace hook + WireFlow wire) with what
    the surface discovery oracle SAW: per-agent detection (hook grouped by
    agent_id, wire run-scoped) with the ghost agents in
    ``scorecard.false_negatives``, plus a per-exchange verdict (hook = identified;
    wire = corroborated, or a ghost exchange via ``reconcile_strict``). Pure given
    the recorder snapshots (I4); read-only. The eBPF source is the separate POST
    /probe/capture; this endpoint is the always-available deterministic oracle.
    Fail-safe: empty recorders -> an empty report, never a 500."""
    from ...surface.exchange import build_exchange_report

    allow, flow_dicts, trace_dicts = _build_run_allowlist(request, run_id)
    report = build_exchange_report(
        proxy_traces=trace_dicts,
        wire_flows=flow_dicts,
        allowlist=allow,
        run_id=run_id,
    )
    return {"debug_enabled": bool(request.app.state.proxy_debug_enabled), **report.to_dict()}


@router.get("/reconcile")
def get_reconcile(request: Request, run_id: str | None = None, strict: bool = False) -> dict:
    """Wire-vs-audit reconciliation (run-scoped join).

    Joins the wire view (WireFlow) with the audit view (ProxyTrace) by run_id.
    A wire flow whose target (host:port) is a mediated endpoint (the lab, a
    mock_local server) is EXPLAINED; a flow to a non-mediated target (e.g. the
    shadow-db honeypot :9113) has no matching audit event -- the ghost-agent
    signal. ``audited_run_ids`` reports which runs produced a genuine mediated
    side effect. With ``strict=true`` (phase 3) every governed-action flow to a
    mediated target must also carry a matching ``side_effect_hash``, so a ghost
    hitting an allowlisted server directly is caught too (``bypass_reason``
    distinguishes ``non_mediated_target`` from ``no_audit_event``). The lab
    OBSERVES the unmediated path; it does not ENFORCE a network block. Read-only;
    POST /proxy/reconcile/raise records the bypass as a compensatory event."""
    report = _reconcile_report(request, run_id, strict=strict)
    return {"run_id": run_id, "strict": strict, **report.to_dict()}


@router.get("/reconcile/status")
def get_reconcile_status(request: Request, run_id: str | None = None, strict: bool = False) -> dict:
    """Lightweight reconciliation verdict for the source-menu badge.

    Same run-scoped join as GET /proxy/reconcile (pure given the recorder
    snapshots, I4) but returns only the verdict and the bypass count -- the Proxy
    console menu shows a live reconciliation badge without shipping (or
    rendering) the full ``bypass_flows`` payload, and without the panel being
    open. Read-only."""
    report = _reconcile_report(request, run_id, strict=strict)
    data = report.to_dict()
    return {"ok": bool(data["ok"]), "bypass_count": len(data["bypass_flows"])}


@router.post("/reconcile/raise")
def raise_reconcile(request: Request, run_id: str | None = None, strict: bool = False) -> dict:
    """Record each detected bypass as a compensatory ``bypass_detected`` event
    in the append-only audit log (I1) -- the Control Plane alert (scenario step 5).

    Idempotent: a bypass already recorded (same side_effect_hash) is not appended
    twice, so polling the raise endpoint never spams the log. The decision
    (reconcile) is pure; the event ``timestamp`` is a wall-clock value captured
    HERE at the boundary as an INPUT (I4), never read inside the join. Because
    the result is a normal canonical event, replaying the stream reproduces it
    (step 6)."""
    from datetime import UTC, datetime

    from ...platform.events import EventKind
    from ...platform.proxy.bypass_event import raise_bypass_events
    from ..app import RestartSafeIdGenerator

    store = request.app.state.event_store
    report = _reconcile_report(request, run_id, strict=strict)
    already = {
        e.payload.get("side_effect_hash")
        for e in store.read_from(kind=EventKind.BYPASS_DETECTED)
        if e.payload.get("side_effect_hash")
    }
    ids = RestartSafeIdGenerator(store)
    timestamp = datetime.now(UTC).isoformat()
    events = raise_bypass_events(
        report, next_event_id=ids.next_id, timestamp=timestamp, already_raised=already
    )
    for event in events:
        store.append(
            event_id=event.event_id,
            kind=EventKind.BYPASS_DETECTED,
            payload=event.to_dict(),
            schema_version=event.schema_version,
        )
    return {"raised": len(events), "event_ids": [e.event_id for e in events]}
