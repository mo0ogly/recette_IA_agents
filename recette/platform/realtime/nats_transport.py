"""NatsJetStreamTransport -- Phase 2 realtime transport (opt-in, [nats] extra).

Diffuses governed events over a NATS JetStream subject so the realtime fan-out
survives a multi-host deployment (the in-process transport is mono-host only).
JetStream is NEVER the source of truth (I1): it carries a derived copy of events
already persisted in the event store, so retention/purge of the stream can never
lose a governed event -- it is replayable from the durable log.

nats-py is asyncio; the gateway/store path is synchronous. This adapter owns a
dedicated background event loop in a daemon thread and bridges sync calls onto
it with ``run_coroutine_threadsafe``. ``publish`` raises on a downstream failure;
it is meant to be wrapped by ``BoundedRetryBuffer`` (the factory does this) so a
degraded bus buffers and retries instead of ever raising into the gateway
(failure-modes.md). Credentials/URL come from the environment (R5/R8), never code.
"""

from __future__ import annotations

import asyncio
import json
import queue
import threading

import nats
import nats.js

from .protocol import RealtimeEvent

_CONNECT_TIMEOUT = 10.0
_PUBLISH_TIMEOUT = 5.0
_SUBSCRIBER_BUFFER = 1024


class _NatsSubscription:
    """A live JetStream consumer bridged into a thread-safe bounded queue."""

    def __init__(self, transport: NatsJetStreamTransport) -> None:
        self._transport = transport
        self._queue: queue.Queue[RealtimeEvent] = queue.Queue(maxsize=_SUBSCRIBER_BUFFER)
        self._lagged = 0
        self._sub = None  # set by the transport after async subscribe
        self._closed = False

    def _offer(self, event: RealtimeEvent) -> None:
        try:
            self._queue.put_nowait(event)
        except queue.Full:
            try:
                self._queue.get_nowait()
                self._lagged += 1
                self._queue.put_nowait(event)
            except queue.Empty:  # pragma: no cover - racing drain
                self._queue.put_nowait(event)

    def get(self, timeout: float | None = None) -> RealtimeEvent | None:
        try:
            return self._queue.get(timeout=timeout)
        except queue.Empty:
            return None

    @property
    def lagged(self) -> int:
        return self._lagged

    def close(self) -> None:
        if not self._closed:
            self._closed = True
            self._transport._unsubscribe(self)


class NatsJetStreamTransport:
    """Synchronous facade over an asyncio NATS JetStream client."""

    def __init__(
        self, url: str, *, subject: str = "agentrail.events", stream: str = "AGENTRAIL_EVENTS"
    ) -> None:
        self._url = url
        self._subject = subject
        self._stream = stream
        self._loop = asyncio.new_event_loop()
        self._thread = threading.Thread(target=self._run_loop, daemon=True)
        self._thread.start()
        self._nc: nats.NATS | None = None
        self._js: nats.js.JetStreamContext | None = None
        self._run(self._connect(), timeout=_CONNECT_TIMEOUT)

    def _jetstream(self) -> nats.js.JetStreamContext:
        if self._js is None:  # pragma: no cover - connect() runs in __init__
            raise RuntimeError("NATS transport is not connected")
        return self._js

    def _run_loop(self) -> None:
        asyncio.set_event_loop(self._loop)
        self._loop.run_forever()

    def _run(self, coro, *, timeout: float):  # type: ignore[no-untyped-def]
        """Schedule a coroutine on the background loop and block for its result."""
        return asyncio.run_coroutine_threadsafe(coro, self._loop).result(timeout)

    async def _connect(self) -> None:
        self._nc = await nats.connect(self._url, connect_timeout=int(_CONNECT_TIMEOUT))
        self._js = self._nc.jetstream()
        # Idempotent stream provisioning: add, tolerate an already-existing stream.
        try:
            await self._jetstream().add_stream(name=self._stream, subjects=[self._subject])
        except Exception:
            # Stream already exists (possibly created by another host). The
            # subject set is owned by deployment config, not this process.
            pass

    def publish(self, event: RealtimeEvent) -> None:
        data = json.dumps(event, separators=(",", ":")).encode("utf-8")
        self._run(self._jetstream().publish(self._subject, data), timeout=_PUBLISH_TIMEOUT)

    def subscribe(self) -> _NatsSubscription:
        sub = _NatsSubscription(self)

        async def _on_message(msg) -> None:  # type: ignore[no-untyped-def]
            try:
                event = json.loads(msg.data.decode("utf-8"))
            except (ValueError, UnicodeDecodeError):
                return  # malformed message on the wire: drop, never crash the loop
            sub._offer(event)
            await msg.ack()

        # Ephemeral push consumer delivering only NEW messages: a live tail.
        # Historical backfill is the event store's job (replay), not the bus.
        js_sub = self._run(
            self._jetstream().subscribe(self._subject, cb=_on_message, ordered_consumer=False),
            timeout=_CONNECT_TIMEOUT,
        )
        sub._sub = js_sub
        return sub

    def _unsubscribe(self, sub: _NatsSubscription) -> None:
        if sub._sub is not None:
            try:
                self._run(sub._sub.unsubscribe(), timeout=_PUBLISH_TIMEOUT)
            except Exception:  # pragma: no cover - best-effort teardown
                pass

    def close(self) -> None:
        if self._nc is not None:
            try:
                self._run(self._nc.drain(), timeout=_CONNECT_TIMEOUT)
            except Exception:  # pragma: no cover - best-effort teardown
                pass
            self._nc = None
        self._loop.call_soon_threadsafe(self._loop.stop)
