"""Data Plane realtime transport (Phase 1 in-process, Phase 2 NATS opt-in).

The transport diffuses governed events to live consumers (the console) but is
NEVER the source of truth (I1): the append-only event store is. Selection is
env-driven, mirroring the event-store Phase 1/2 switch (event-store-decision.md):

    INSPECT_IA_AGENTS_REALTIME=inproc (default) -> InProcessTransport (mono-host, real)
    INSPECT_IA_AGENTS_REALTIME=nats   -> NatsJetStreamTransport at INSPECT_IA_AGENTS_NATS_URL
                                           (R5/R8), wrapped in a BoundedRetryBuffer
                                           (failure-modes.md). Extra [nats].
"""

from __future__ import annotations

import os

from .buffer import BoundedRetryBuffer
from .inproc import InProcessTransport
from .protocol import RealtimeEvent, RealtimeTransport, Subscription
from .publishing_store import PublishingEventStore

__all__ = [
    "BoundedRetryBuffer",
    "InProcessTransport",
    "PublishingEventStore",
    "RealtimeEvent",
    "RealtimeTransport",
    "RealtimeTransportConfigError",
    "Subscription",
    "build_realtime_transport_from_env",
]


class RealtimeTransportConfigError(RuntimeError):
    """The configured realtime backend is unknown or missing required config."""


def build_realtime_transport_from_env() -> RealtimeTransport:
    """Construct the realtime transport selected by INSPECT_IA_AGENTS_REALTIME."""
    backend = os.environ.get("INSPECT_IA_AGENTS_REALTIME", "inproc").strip().lower()
    if backend == "inproc":
        return InProcessTransport()
    if backend == "nats":
        url = os.environ.get("INSPECT_IA_AGENTS_NATS_URL")
        if not url:
            raise RealtimeTransportConfigError(
                "INSPECT_IA_AGENTS_REALTIME=nats requires INSPECT_IA_AGENTS_NATS_URL"
            )
        subject = os.environ.get("INSPECT_IA_AGENTS_NATS_SUBJECT", "inspect_ia_agents.events")
        stream = os.environ.get("INSPECT_IA_AGENTS_NATS_STREAM", "INSPECT_IA_AGENTS_EVENTS")
        try:
            from .nats_transport import NatsJetStreamTransport
        except ImportError as exc:  # nats-py not installed
            raise RealtimeTransportConfigError(
                "nats backend needs the [nats] extra (nats-py)"
            ) from exc
        # A network transport is fallible: wrap it so a degraded bus buffers and
        # retries instead of ever raising into the gateway (failure-modes.md).
        return BoundedRetryBuffer(NatsJetStreamTransport(url, subject=subject, stream=stream))
    raise RealtimeTransportConfigError(f"unknown INSPECT_IA_AGENTS_REALTIME backend: {backend!r}")
