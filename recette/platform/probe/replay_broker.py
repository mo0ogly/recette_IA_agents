"""A replay stand-in for the privileged discoveryprobe eBPF broker.

Why this exists
---------------
The console Probe view drives ``POST /probe/capture`` -> the API relay ->
the broker Unix socket. The real broker (``discoveryprobe-broker``, Rust) holds
CAP_BPF and emits a LIVE capture. In dev / CI there is no CAP_BPF, so the socket
is unset, ``GET /probe/status`` reports ``configured: false`` and the capture
button is disabled -- the surface looks empty.

This module is a NON-privileged server that speaks the broker's exact wire form
(one JSON ``capture`` command line in, one recording JSON line out) and answers
with a deterministic REPLAY of known surface state. The replayed observations are
re-projected from the committed ``corpus/surface/*/ground-truth.json`` subjects,
so the recording is single-source-of-truth and drift-free. The same
source-agnostic judge (``recette/surface``) then scores it, exactly as it scores
a live eBPF capture (I4). It is labelled ``mode: replay`` end-to-end: it never
claims to be a live eBPF capture (R13/R14).

Determinism (I4): no clock, no random. ``recording_sha256`` is the SHA-256 of the
canonical recordings JSON (tamper-evident, I1). Surfaces are walked in a stable
order.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import logging
import os
import signal
import socket
import threading
import time
from collections.abc import Iterable, Sequence
from pathlib import Path
from types import FrameType

from .address import create_stream_socket, parse_probe_address

logger = logging.getLogger("recette.probe.replay_broker")

# The four observation surfaces, in the stable order the recording lists them.
_SURFACE_ORDER: tuple[str, ...] = ("hook_subprocess", "hook_mcp", "hook_sdk", "ebpf_wire")

_DEFAULT_CORPUS = Path(__file__).resolve().parents[3] / "corpus" / "surface"


def _iter_ground_truths(corpus_dir: Path) -> Iterable[Path]:
    """Every ``ground-truth.json`` under the surface corpus, in sorted order."""
    if not corpus_dir.is_dir():
        return []
    return sorted(corpus_dir.rglob("ground-truth.json"))


def load_reference_surfaces(corpus_dir: Path = _DEFAULT_CORPUS) -> dict[str, dict[str, bool]]:
    """Map each corpus subject's ``agent_id`` to its per-surface visibility.

    The visibility is the subject's ``expected.per_surface`` -- the frozen
    ground-truth of what the probe saw of that agent. A malformed subject is
    skipped with a warning rather than aborting the whole reference (fail-safe).
    """
    reference: dict[str, dict[str, bool]] = {}
    for path in _iter_ground_truths(corpus_dir):
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            logger.warning("skipping unreadable surface subject %s: %s", path, exc)
            continue
        agent_id = data.get("agent_id")
        per_surface = data.get("expected", {}).get("per_surface", {})
        if not isinstance(agent_id, str) or not isinstance(per_surface, dict):
            logger.warning("skipping malformed surface subject %s", path)
            continue
        reference[agent_id] = {
            surface: bool(per_surface.get(surface, False)) for surface in _SURFACE_ORDER
        }
    return reference


def build_recording(
    agents: Sequence[str], reference: dict[str, dict[str, bool]]
) -> dict[str, object]:
    """Project the requested agents onto a broker recording envelope.

    For a known agent, each surface marked visible in the reference yields one
    synthetic visible identifier ``replay:{agent}:{surface}``; an invisible
    surface is omitted. An UNKNOWN requested agent yields an empty ``surfaces``
    map -- a genuine "captured nowhere" / ghost, the thesis failure case.
    """
    recordings: list[dict[str, object]] = []
    for agent in agents:
        per_surface = reference.get(agent, {})
        surfaces: dict[str, list[str]] = {
            surface: [f"replay:{agent}:{surface}"]
            for surface in _SURFACE_ORDER
            if per_surface.get(surface, False)
        }
        recordings.append({"agent_id": agent, "surfaces": surfaces})
    canonical = json.dumps(recordings, sort_keys=True, separators=(",", ":"))
    digest = hashlib.sha256(canonical.encode("utf-8")).hexdigest()
    return {
        "status": "ok",
        "recordings": recordings,
        "recording_sha256": digest,
        "mode": "replay",
    }


def _validated_agents(request: dict) -> list[str] | None:
    """The request's ``agents`` when it is a non-empty list of ids, else None."""
    agents = request.get("agents")
    if not isinstance(agents, list) or not agents or not all(isinstance(a, str) for a in agents):
        return None
    return agents


def parse_request(line: str) -> dict[str, object]:
    """Parse one wire command line into a request dict, or an error envelope.

    Mirrors the real broker's deny-by-default validation: only ``capture`` and
    ``watch`` with a non-empty list of string agent ids are honoured; anything
    else is a structured error recording, never a fabricated success.
    """
    try:
        request = json.loads(line)
    except json.JSONDecodeError:
        return {"status": "error", "reason": "request is not valid JSON"}
    if not isinstance(request, dict) or request.get("command") not in ("capture", "watch"):
        return {"status": "error", "reason": "unsupported command (only 'capture' or 'watch')"}
    if _validated_agents(request) is None:
        return {"status": "error", "reason": "agents must be a non-empty list of ids"}
    return request


def handle_command(line: str, reference: dict[str, dict[str, bool]]) -> dict[str, object]:
    """Parse one ``capture`` command line and return the recording (or an error
    envelope). ``watch`` is handled at the connection level (it streams)."""
    request = parse_request(line)
    if request.get("status") == "error":
        return request
    if request.get("command") != "capture":
        return {"status": "error", "reason": "watch is a streaming command, not a one-shot"}
    agents = _validated_agents(request)
    if agents is None:  # unreachable after parse_request, kept fail-safe
        return {"status": "error", "reason": "agents must be a non-empty list of ids"}
    return build_recording(agents, reference)


class ReplayBroker:
    """A one-command-per-connection stream server speaking the broker wire.

    Binds the canonical Unix socket path, or a loopback TCP endpoint when the
    address is ``tcp:HOST:PORT`` (the Windows fallback -- CPython there has no
    ``socket.AF_UNIX``). ``tcp:HOST:0`` binds an ephemeral port; the actual
    bound address is exposed as :attr:`address`.
    """

    def __init__(self, socket_path: str, corpus_dir: Path = _DEFAULT_CORPUS) -> None:
        self._socket_path = socket_path
        self._reference = load_reference_surfaces(corpus_dir)
        self._family, target = parse_probe_address(socket_path)
        self._sock = create_stream_socket(self._family)
        self._closed = False
        if self._family == "tcp":
            # NB: do NOT set SO_REUSEADDR here. On Windows it has "reuse" (not
            # Linux "reuse TIME_WAIT") semantics: several sockets can bind the
            # SAME port and the OS spreads connections across them, so a stale
            # broker keeps answering alongside a fresh one (observed: 4 zombies
            # on :8093 replying with the old wire, monitor spinning). A clean
            # bind fails loudly if the port is held -- the launcher kills the
            # holder first (R19), so the fresh broker is the only listener.
            self._sock.bind(target)  # type: ignore[arg-type]
            host, port = self._sock.getsockname()[:2]
            self.address = f"tcp:{host}:{port}"
        else:
            if os.path.exists(socket_path):
                os.unlink(socket_path)
            self._sock.bind(socket_path)
            os.chmod(socket_path, 0o600)
            self.address = socket_path
        self._sock.listen(8)
        logger.info(
            "replay broker listening on %s (%d reference subjects)",
            self.address,
            len(self._reference),
        )

    def serve_forever(self) -> None:
        """Accept connections until :meth:`close` is called.

        Each connection is served on its own daemon thread: a long-lived
        ``watch`` stream must never block a concurrent one-shot ``capture``.
        """
        while not self._closed:
            try:
                conn, _ = self._sock.accept()
            except OSError:
                return
            threading.Thread(
                target=self._serve_connection, args=(conn,), daemon=True
            ).start()

    def _serve_connection(self, conn: socket.socket) -> None:
        with conn:
            self._handle_connection(conn)

    def _handle_connection(self, conn: socket.socket) -> None:
        data = b""
        while b"\n" not in data:
            try:
                chunk = conn.recv(65536)
            except OSError:
                return
            if not chunk:
                break
            data += chunk
        line = data.decode("utf-8", errors="replace").strip()
        request = parse_request(line)
        if request.get("command") == "watch":
            self._stream_watch(conn, request)
            return
        response = handle_command(line, self._reference)
        try:
            conn.sendall((json.dumps(response) + "\n").encode("utf-8"))
        except OSError as exc:
            logger.warning("failed to send response: %s", exc)

    def _stream_watch(self, conn: socket.socket, request: dict[str, object]) -> None:
        """Stream one recording line per slice until the client closes.

        Mirrors the real broker's gap-free passive watch wire form (the API
        monitor reads newline-delimited recordings off one connection). Each
        slice re-emits the deterministic replay of the reference surfaces --
        the CONTENT is pure (I4); only the pacing between slices is wall-clock,
        exactly like the live broker's slice cadence (operational, never judged).
        """
        agents = _validated_agents(request)
        if agents is None:  # unreachable after parse_request, kept fail-safe
            return
        duration_ms = request.get("duration_ms")
        if not isinstance(duration_ms, int) or isinstance(duration_ms, bool) or duration_ms <= 0:
            duration_ms = 2000
        pace_s = min(max(duration_ms, 200), 10_000) / 1000.0
        recording = build_recording(agents, self._reference)
        payload = (json.dumps(recording) + "\n").encode("utf-8")
        while not self._closed:
            try:
                conn.sendall(payload)
            except OSError:
                return  # client closed the watch -> stop streaming
            time.sleep(pace_s)

    def close(self) -> None:
        self._closed = True
        try:
            self._sock.close()
        finally:
            if self._family == "unix" and os.path.exists(self._socket_path):
                try:
                    os.unlink(self._socket_path)
                except OSError:
                    pass


def _build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="discoveryprobe replay broker (non-privileged)")
    parser.add_argument(
        "--socket",
        required=True,
        help="Unix socket path to bind, or tcp:HOST:PORT (Windows fallback)",
    )
    parser.add_argument(
        "--corpus",
        default=str(_DEFAULT_CORPUS),
        help="surface corpus directory (default: corpus/surface)",
    )
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(name)s %(levelname)s %(message)s")
    args = _build_arg_parser().parse_args(argv)
    broker = ReplayBroker(args.socket, Path(args.corpus))

    def _stop(_signum: int, _frame: FrameType | None) -> None:
        logger.info("signal received, shutting down replay broker")
        broker.close()

    signal.signal(signal.SIGTERM, _stop)
    signal.signal(signal.SIGINT, _stop)
    try:
        broker.serve_forever()
    finally:
        broker.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
