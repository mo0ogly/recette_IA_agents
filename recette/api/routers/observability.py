"""Observability traces/spans -- a read-only span-tree view over persisted runs.

The console debug view needs to see a run as a hierarchy of spans (a root
agent invocation, one tool execution per action) with logical timings, not
only the flat audit log. This router renders that tree from the recordings the
runners persist, reusing the deterministic GenAI span builder in
``recette.otel`` (I4: same recording -> byte-identical spans). It never
mutates anything (I1): traces are a derived, read-only projection.

Endpoints:
- ``GET /observability/traces``            -- one row per recording (trace id + summary)
- ``GET /observability/traces/{trace_id}`` -- the full span tree of a recording
- ``GET /observability/spans/{span_id}``   -- a single span across all recordings
"""

from __future__ import annotations

from fastapi import APIRouter, HTTPException, Request

from ...otel import _trace_id, recording_spans, span_to_dict

router = APIRouter(prefix="/observability", tags=["observability"])


def _store(request: Request) -> object:
    return request.app.state.recording_store


@router.get("/traces")
def list_traces(request: Request) -> list[dict]:
    """One trace per persisted recording, keyed by a deterministic trace id."""
    store = _store(request)
    rows: list[dict] = []
    for rec in store.list():  # type: ignore[attr-defined]
        recording_id = str(rec.get("recording_id", ""))
        # Count spans accurately (a final answer carries no tool span), by
        # rendering the tree; recordings are small and the build is pure (I4).
        recording = store.get(recording_id)  # type: ignore[attr-defined]
        rows.append(
            {
                "trace_id": _trace_id(recording_id),
                "recording_id": recording_id,
                "agent_id": rec.get("agent_id"),
                "target_system": rec.get("target_system"),
                "provider": rec.get("provider"),
                "span_count": len(recording_spans(recording, recording_id)),
            }
        )
    return rows


def _spans_for(store: object, trace_id: str) -> tuple[str, list]:
    """Return (recording_id, spans) for the recording whose trace id matches."""
    for rec in store.list():  # type: ignore[attr-defined]
        recording_id = str(rec.get("recording_id", ""))
        if _trace_id(recording_id) == trace_id:
            recording = store.get(recording_id)  # type: ignore[attr-defined]
            return recording_id, recording_spans(recording, recording_id)
    raise HTTPException(status_code=404, detail=f"no trace {trace_id!r}")


@router.get("/traces/{trace_id}")
def get_trace(request: Request, trace_id: str) -> dict:
    """The full span tree of one recording (flat spans; parent_span_id links)."""
    recording_id, spans = _spans_for(_store(request), trace_id)
    return {
        "trace_id": trace_id,
        "recording_id": recording_id,
        "spans": [span_to_dict(s) for s in spans],
    }


@router.get("/spans/{span_id}")
def get_span(request: Request, span_id: str) -> dict:
    """A single span looked up across every recording's span tree."""
    store = _store(request)
    for rec in store.list():  # type: ignore[attr-defined]
        recording_id = str(rec.get("recording_id", ""))
        recording = store.get(recording_id)  # type: ignore[attr-defined]
        for span in recording_spans(recording, recording_id):
            if span.span_id == span_id:
                return span_to_dict(span)
    raise HTTPException(status_code=404, detail=f"no span {span_id!r}")
