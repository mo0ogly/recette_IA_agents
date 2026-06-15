"""Lifecycle of mock_local lab servers -- one subprocess per server entry.

Failure mode (fail-safe): a server that cannot bind its port stays "down"
and start() reports the error; nothing is retried silently and no traffic
is rerouted. Status is probed live (process poll), never cached.
"""

from __future__ import annotations

import os
import socket
import subprocess
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

_HEALTH_PROBE_ATTEMPTS = 30
_HEALTH_PROBE_INTERVAL_S = 0.1
_STOP_TIMEOUT_S = 5
# Repo root (this file lives at recette/api/server_manager.py): the mock
# server subprocess runs with cwd here so "python -m recette.lab.mock_server"
# resolves the package regardless of the caller's working directory.
_REPO_ROOT = Path(__file__).resolve().parents[2]


class ServerManager:
    """Supervises one ``python -m recette.lab.mock_server`` process per entry.

    A "server" entry is the console-facing dict, e.g.
    ``{"id": "gh-mock", "system": "github", "mode": "mock_local", "port": 9101}``.
    Only ``mode == "mock_local"`` is startable here; other modes are rejected
    with ``ValueError`` (no silent fallback, fail-safe).
    """

    def __init__(self, base_dir: Path | str = "data/lab") -> None:
        self._base_dir = Path(base_dir)
        self._procs: dict[str, subprocess.Popen[bytes]] = {}

    def access_log_path(self, server_id: str) -> Path:
        """JSONL access log of one server, under the manager base dir."""
        return self._base_dir / f"{server_id}.access.jsonl"

    # Port-bound modes share the same mock_server process; only build_allowlist
    # tells them apart (honeypot is excluded -> a sink that flags any traffic).
    _STARTABLE_MODES = frozenset(("mock_local", "honeypot"))

    def start(self, server: dict) -> dict:
        """Start one port-bound lab server; return {"status": "up"} or a down+error.

        Handles ``mock_local`` (a mediated lab double) and ``honeypot`` (a sink
        an agent must never reach directly) -- both run the same mock_server.
        Fail-fast preflight: bind the port once before spawning, so a busy
        port yields an explicit error and zero child process. The server
        stays "down"; nothing is retried and no traffic is rerouted.
        """
        mode = server.get("mode")
        if mode not in self._STARTABLE_MODES:
            raise ValueError(
                f"ServerManager only starts modes {sorted(self._STARTABLE_MODES)}, got {mode!r}"
            )
        server_id = server.get("id")
        if not server_id:
            raise ValueError("server entry requires a non-empty 'id'")
        port = server.get("port")
        # bool is an int subclass: reject it explicitly (same rule as config_store).
        if not isinstance(port, int) or isinstance(port, bool):
            raise ValueError(f"port-bound server {server_id!r} requires an integer 'port'")

        probe = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        # SO_REUSEADDR matches the mock server's own bind semantics
        # (http.server sets allow_reuse_address): an immediate stop->start on
        # the same port must not fail on TIME_WAIT leftovers, while a live
        # listener still yields EADDRINUSE.
        probe.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        try:
            probe.bind(("127.0.0.1", port))
        except OSError as exc:
            return {"status": "down", "error": f"port {port} already in use: {exc}"}
        finally:
            probe.close()

        self._base_dir.mkdir(parents=True, exist_ok=True)
        env = {
            **os.environ,
            "INSPECT_IA_AGENTS_LAB_PORT": str(port),
            "INSPECT_IA_AGENTS_LAB_ACCESS_LOG": str(self.access_log_path(server_id)),
        }
        proc = subprocess.Popen(
            [sys.executable, "-m", "recette.lab.mock_server"],
            env=env,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            cwd=_REPO_ROOT,
        )
        # Wall-clock sleeps are acceptable here: this is process supervision,
        # not a decision path, so I4 (deterministic replay) does not apply.
        for _ in range(_HEALTH_PROBE_ATTEMPTS):
            if proc.poll() is not None:
                return {
                    "status": "down",
                    "error": f"mock server exited with code {proc.returncode}",
                }
            try:
                # fixed localhost health probe to a server we spawned
                with urllib.request.urlopen(  # noqa: S310  # nosec B310
                    f"http://127.0.0.1:{port}/health", timeout=1
                ) as response:
                    if response.status == 200:
                        self._procs[server_id] = proc
                        return {"status": "up"}
            except (urllib.error.URLError, OSError):
                time.sleep(_HEALTH_PROBE_INTERVAL_S)
        self._terminate(proc)
        return {"status": "down", "error": "health probe timeout"}

    def stop(self, server_id: str) -> dict:
        """Stop one server; idempotent (unknown id is already "down")."""
        proc = self._procs.pop(server_id, None)
        if proc is not None:
            self._terminate(proc)
        return {"status": "down"}

    def status(self, server_id: str) -> str:
        """Live status: "up" only when a tracked process is still running."""
        proc = self._procs.get(server_id)
        return "up" if proc is not None and proc.poll() is None else "down"

    def shutdown(self) -> None:
        """Stop every tracked server (app shutdown hook)."""
        for server_id in list(self._procs):
            self.stop(server_id)

    @staticmethod
    def _terminate(proc: subprocess.Popen[bytes]) -> None:
        if proc.poll() is not None:
            return
        proc.terminate()
        try:
            proc.wait(timeout=_STOP_TIMEOUT_S)
        except subprocess.TimeoutExpired:
            proc.kill()
            proc.wait(timeout=_STOP_TIMEOUT_S)
