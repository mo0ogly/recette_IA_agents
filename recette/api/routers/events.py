"""Realtime event stream -- the console's live tail of governed events (G4).

GET /events/stream is a Server-Sent Events endpoint bridging the Data Plane
``RealtimeTransport`` (app.state.realtime_transport) to the browser. Every event
appended to the store (executed/denied/requested/resolved/error) is diffused
here. The stream is a derived view: it is NEVER the source of truth (I1) -- a
client that reconnects backfills history from the audit endpoints, not the bus.
"""

from __future__ import annotations

import asyncio
import json
from collections.abc import AsyncIterator

from fastapi import APIRouter, Request
from starlette.responses import JSONResponse, StreamingResponse

router = APIRouter(prefix="/events", tags=["events"])

_POLL_SECONDS = 1.0


@router.get("/stream")
async def stream_events(request: Request) -> StreamingResponse:
    """Stream governed events as SSE. One subscription per connection; closed on
    client disconnect. A keepalive comment is emitted on idle so proxies do not
    time the connection out."""
    transport = request.app.state.realtime_transport

    async def event_source() -> AsyncIterator[str]:
        sub = transport.subscribe()
        try:
            # Greet immediately so EventSource fires `onopen` without waiting.
            yield ": connected\n\n"
            while True:
                if await request.is_disconnected():
                    break
                # The subscription queue is blocking; hop to a worker thread so
                # the event loop stays free while we wait for the next event.
                event = await asyncio.to_thread(sub.get, _POLL_SECONDS)
                if event is None:
                    yield ": keepalive\n\n"
                else:
                    yield f"data: {json.dumps(event, separators=(',', ':'))}\n\n"
        finally:
            sub.close()

    return StreamingResponse(
        event_source(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


@router.get("/status")
def stream_status(request: Request) -> JSONResponse:
    """Lightweight transport health for the console badge: whether the realtime
    backend is degraded (buffering) and how many events are pending retry. The
    in-process transport is never degraded; a wrapped NATS transport may be."""
    transport = request.app.state.realtime_transport
    degraded = bool(getattr(transport, "degraded", False))
    pending = int(getattr(transport, "pending", 0))
    dropped = int(getattr(transport, "dropped", 0))
    return JSONResponse({"degraded": degraded, "pending": pending, "dropped": dropped})
