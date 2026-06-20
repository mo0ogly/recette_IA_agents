"""Passive, continuous eBPF monitor -- flag any watched agent the moment it runs.

The bounded ``/probe/capture`` answers "did the kernel see X during this window".
This monitor turns that into a PASSIVE watch: a background thread opens ONE
gap-free broker ``watch`` stream (the eBPF probe stays attached, emitting a
recording line per slice -- nothing lost between slices) and accumulates live
sightings, so an operator who just launches an agent sees it appear on the wire
in near-real-time, no per-capture click. The console polls ``GET /probe/monitor``.

This is live measurement, NOT a decision path: it uses threads + the wall clock
and is non-deterministic by nature (I4 governs the pure judge, not this probe).
Fail-safe: a broker error degrades the monitor (recorded in ``last_error``) and
the loop keeps trying; it never fabricates a sighting.
"""

from __future__ import annotations

import json
import socket
import threading

from .probe_relay import ProbeUnavailable, open_watch


class ProbeMonitor:
    """Background loop of broker captures -> a rolling map of live sightings."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._thread: threading.Thread | None = None
        self._stop = threading.Event()
        self._running = False
        self._socket_path = ""
        self._agents: list[str] = []
        self._window_ms = 2000
        self._last_error: str | None = None
        self._windows = 0
        # agent_id -> {"surfaces": set[str], "windows_seen": int, "last_window": int}
        self._sightings: dict[str, dict] = {}

    def start(self, *, socket_path: str, agents: list[str], window_ms: int = 2000) -> bool:
        """Start the watch loop. Idempotent: a no-op (returns False) if already
        running. ``agents`` must be in the broker manifest (its allowlist)."""
        with self._lock:
            if self._running:
                return False
            self._socket_path = socket_path
            self._agents = list(agents)
            self._window_ms = max(200, min(window_ms, 10000))
            self._last_error = None
            self._windows = 0
            self._sightings = {}
            self._stop.clear()
            self._running = True
            self._thread = threading.Thread(target=self._loop, daemon=True)
            self._thread.start()
            return True

    def _loop(self) -> None:
        # Gap-free passive stream: ONE broker connection keeps the eBPF probe
        # attached and emits a recording line per slice (no re-attach, nothing
        # lost between slices). Reconnect on drop; back off on broker error.
        while not self._stop.is_set():
            try:
                sock = open_watch(
                    socket_path=self._socket_path,
                    agents=self._agents,
                    duration_ms=self._window_ms,
                )
            except ProbeUnavailable as exc:
                with self._lock:
                    self._last_error = str(exc)
                self._stop.wait(1.0)
                continue
            try:
                self._read_stream(sock)
            finally:
                sock.close()

    def _read_stream(self, sock: socket.socket) -> None:
        """Read newline-delimited recording lines off one watch stream, merging
        each, until stop or the broker closes the connection."""
        buf = b""
        while not self._stop.is_set():
            try:
                data = sock.recv(65536)
            except TimeoutError:
                continue  # periodic wake so stop is honoured
            except OSError as exc:
                with self._lock:
                    self._last_error = str(exc)
                return
            if not data:
                return  # broker closed -> reconnect
            buf += data
            while b"\n" in buf:
                raw, buf = buf.split(b"\n", 1)
                raw = raw.strip()
                if not raw:
                    continue
                try:
                    self._merge(json.loads(raw.decode("utf-8")))
                except ValueError:
                    pass

    def _merge(self, recording: dict) -> None:
        with self._lock:
            self._windows += 1
            if recording.get("status") != "ok":
                self._last_error = (
                    f"broker: {recording.get('status')} {recording.get('reason', '')}".strip()
                )
                return
            self._last_error = None
            for rec in recording.get("recordings", []):
                aid = rec.get("agent_id")
                if not aid:
                    continue
                seen = {surface for surface, ids in (rec.get("surfaces") or {}).items() if ids}
                if not seen:
                    continue
                entry = self._sightings.setdefault(
                    aid, {"surfaces": set(), "windows_seen": 0, "last_window": 0}
                )
                entry["surfaces"] |= seen
                entry["windows_seen"] += 1
                entry["last_window"] = self._windows

    def stop(self) -> None:
        with self._lock:
            if not self._running:
                return
            self._stop.set()
            thread = self._thread
            self._running = False
        if thread is not None:
            thread.join(timeout=5)

    def snapshot(self) -> dict:
        """Current monitor state + the live sightings (sorted, JSON-ready)."""
        with self._lock:
            return {
                "running": self._running,
                "window_ms": self._window_ms,
                "agents": list(self._agents),
                "windows": self._windows,
                "last_error": self._last_error,
                "sightings": [
                    {
                        "agent_id": aid,
                        "surfaces": sorted(e["surfaces"]),
                        "windows_seen": e["windows_seen"],
                        "last_window": e["last_window"],
                    }
                    for aid, e in sorted(self._sightings.items())
                ],
            }
