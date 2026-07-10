"""Live multi-agent orchestration -- drive a team, track it, judge it (Phase 9).

Pulls the orchestrator out of the dark: the console can DRIVE a declared team
(team.json) through real per-instance LLM backends and see the resulting run,
its four-dimension verdict, and the multi-session tracking receipts -- the same
SessionTracker whose session_id/instance_id the wire panel already filters on.

- ``POST /orchestrate/run`` builds one LlmBackend per participant via
  ``build_llm`` (live; keys resolved from the env/secret store, R8), drives the
  team through the shared app-state SessionTracker, and returns the run +
  verdict + the session's tracked instances.
- ``GET /orchestrate/sessions`` / ``GET /orchestrate/sessions/{id}`` expose the
  tracker: the sessions seen, and per session the content-free chained receipts
  plus the chain-verify verdict and the acting instances.

Determinism (I4): the judge stays a pure function of (team, run); all
non-determinism lives in the backends. The endpoint never touches the audit log
(the tracker is a separate content-free receipt chain). Fail-safe (R7): an
unknown provider, a missing key, or an unroutable handoff is an explicit 4xx,
never a silent partial run.
"""

from __future__ import annotations

import logging

from fastapi import APIRouter, HTTPException, Request

router = APIRouter(prefix="/orchestrate", tags=["orchestrate"])

_LOG = logging.getLogger("recette.orchestrate")

# Bound the fan-out so a malformed team cannot ask for an unbounded run.
_MAX_STEPS_CEILING = 64


def _resolve_backends(participants: list[dict], providers: dict, proxy_url: str | None) -> dict:
    """One LlmBackend per acting participant, routed through the wire overlay.

    ``providers`` maps participant_id -> {provider, model, base_url?}. A single
    ``{provider, model}`` (no per-participant keys) backs every participant. A
    participant with no resolvable provider is a 422 (fail-loud, never a silent
    default model). ``proxy_url`` (the active wire overlay, when up) forces every
    backend's HTTP client through the mitmproxy seam so the run's LLM bytes are
    captured on the wire -- the "instance -> its flows" deep-link then resolves."""
    from ...llm import build_llm

    ids = [p["agent_id"] for p in participants]
    default = None
    if "provider" in providers and "model" in providers:
        default = providers
    backends: dict = {}
    for pid in ids:
        spec = providers.get(pid, default)
        if not isinstance(spec, dict) or "provider" not in spec or "model" not in spec:
            raise HTTPException(
                status_code=422,
                detail=(
                    f"participant {pid!r} has no provider/model (give a per-id spec or a default)"
                ),
            )
        try:
            backends[pid] = build_llm(
                spec["provider"],
                spec["model"],
                base_url=spec.get("base_url"),
                proxy_url=proxy_url,
            )
        except ValueError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc
    return backends


@router.post("/run")
def run_orchestration(request: Request, body: dict) -> dict:
    """Drive a declared team live and return the tracked, judged run.

    Body: ``{team: <team doc>, providers: {<id>: {provider, model, base_url?}}
    | {provider, model}, session_id: str, max_steps?: int}``. The team is
    schema-validated; a bad team, an unknown provider, or an out-of-set handoff
    is a 4xx (fail-safe). On success the run is tracked under ``session_id`` in
    the shared SessionTracker so the console can follow the instances across the
    wire capture."""
    from ...maf_orchestration import judge_orchestration
    from ...manifest import validate
    from ...orchestrate import drive

    team = body.get("team")
    if not isinstance(team, dict):
        raise HTTPException(status_code=422, detail="body.team (object) is required")
    session_id = body.get("session_id")
    if not isinstance(session_id, str) or not session_id:
        raise HTTPException(
            status_code=422, detail="body.session_id (non-empty string) is required"
        )
    providers = body.get("providers")
    if not isinstance(providers, dict):
        raise HTTPException(status_code=422, detail="body.providers (object) is required")
    max_steps = body.get("max_steps", 32)
    if not isinstance(max_steps, int) or not 1 <= max_steps <= _MAX_STEPS_CEILING:
        raise HTTPException(
            status_code=422, detail=f"body.max_steps must be an int in 1..{_MAX_STEPS_CEILING}"
        )
    # Schema-validate the team (fail-safe: a malformed team never drives a run).
    errors = validate("maf_orchestration", team)
    if errors:
        raise HTTPException(status_code=422, detail=f"invalid team: {errors[0]}")

    # Force the wire route when the overlay is up: the run's LLM bytes then flow
    # through mitmproxy and land in the wire capture, so the returned instances
    # deep-link to real flows. None (overlay off) => direct, unchanged (I4).
    wire_proxy_url = request.app.state.wire_proxy_url
    backends = _resolve_backends(team.get("participants", []), providers, wire_proxy_url)
    tracker = request.app.state.orchestration_tracker
    try:
        run = drive(team, backends, max_steps=max_steps, session_id=session_id, tracker=tracker)
    except ValueError as exc:
        # Out-of-set handoff / unknown target / uncovered participant: fail-safe.
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    _LOG.info(
        "orchestration run session=%s hops=%d calls=%d", session_id, len(run.hops), len(run.calls)
    )
    result = judge_orchestration(team, run)
    return {
        "session_id": session_id,
        "verdict": result.verdict,
        "dimensions": {
            "identity_match": result.identity_match,
            "capabilities_conform": result.capabilities_conform,
            "policy_compliant": result.policy_compliant,
            "behavior_expected": result.behavior_expected,
        },
        "run": {
            "hops": [
                {"seq": h.seq, "from": h.source, "to": h.target, "reason": h.reason}
                for h in run.hops
            ],
            "order": list(run.order),
            "actions": [
                {
                    "seq": c.seq,
                    "agent_id": c.agent_id,
                    "provider": c.provider,
                    "model": c.model,
                    "target": c.target,
                    "tool_kind": c.tool_kind,
                    "approved": c.approved,
                }
                for c in run.calls
            ],
        },
        "instances": tracker.instances_of(session_id),
        # True when the run's LLM bytes were routed through the wire overlay
        # (so the wire capture holds this session's flows); False = direct run,
        # the instance deep-links will find no flows for this session.
        "wire_captured": wire_proxy_url is not None,
    }


@router.get("/sessions")
def list_sessions(request: Request) -> dict:
    """Every orchestration session the tracker holds, with its instance roster."""
    tracker = request.app.state.orchestration_tracker
    return {
        "sessions": [
            {
                "session_id": sid,
                "instances": tracker.instances_of(sid),
                "receipts": len(tracker.receipts(sid)),
            }
            for sid in tracker.sessions()
        ],
    }


@router.get("/sessions/{session_id}")
def get_session(request: Request, session_id: str) -> dict:
    """One session's content-free chained receipts + chain-verify verdict.

    404 when the session is unknown (never a silent empty chain that would read
    as a verified-but-empty session)."""
    tracker = request.app.state.orchestration_tracker
    receipts = tracker.receipts(session_id)
    if not receipts:
        raise HTTPException(status_code=404, detail=f"unknown session {session_id!r}")
    return {
        "session_id": session_id,
        "instances": tracker.instances_of(session_id),
        "receipts": receipts,
        "verify": tracker.verify(session_id),
    }
