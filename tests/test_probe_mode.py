"""/probe/status reports the broker mode truthfully from .run/probe.mode.

The launcher records which broker it started (live|replay) in a mode file next
to the canonical socket; the API reads it so a launcher-started LIVE broker on
the canonical socket reports live, the replay broker reports replay, and an
operator-set INSPECT_IA_AGENTS_PROBE_SOCKET still wins (R13/R14 -- never claim
live for a replay broker, never hide a real one).
"""

from __future__ import annotations

import os
import socket
import tempfile
import unittest
from pathlib import Path
from unittest import mock

try:
    from recette.api.routers import probe

    _HAS_FASTAPI = True
except ImportError:  # pragma: no cover - depends on the [api] extra
    _HAS_FASTAPI = False


_HAS_AF_UNIX = hasattr(socket, "AF_UNIX")


@unittest.skipUnless(_HAS_FASTAPI, "requires the [api] extra (fastapi)")
@unittest.skipUnless(_HAS_AF_UNIX, "requires AF_UNIX (absent on Windows CPython)")
class ProbeModeResolveTest(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self._sock_path = Path(self._tmp.name) / "probe.sock"
        # A real bound AF_UNIX socket so Path.is_socket() is true (the canonical
        # broker socket the API falls back to).
        self._srv = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        self._srv.bind(str(self._sock_path))
        self.addCleanup(self._srv.close)
        # Neutralize any ambient env so the canonical-fallback branch is exercised.
        self._env = mock.patch.dict(os.environ, {}, clear=False)
        self._env.start()
        os.environ.pop(probe._SOCKET_ENV, None)
        os.environ.pop(probe._MODE_ENV, None)
        self.addCleanup(self._env.stop)
        self._patch = mock.patch.object(probe, "_canonical_socket", return_value=self._sock_path)
        self._patch.start()
        self.addCleanup(self._patch.stop)

    def _write_mode(self, value: str) -> None:
        (self._sock_path.with_name("probe.mode")).write_text(value, encoding="utf-8")

    def test_live_mode_file_reports_live(self) -> None:
        self._write_mode("live\n")
        path, mode = probe._resolve_socket()
        self.assertEqual(path, str(self._sock_path))
        self.assertEqual(mode, "live")

    def test_replay_mode_file_reports_replay(self) -> None:
        self._write_mode("replay")
        self.assertEqual(probe._resolve_socket()[1], "replay")

    def test_absent_mode_file_defaults_replay(self) -> None:
        # No marker (a hand-started broker) -> the safe default, never live.
        self.assertEqual(probe._resolve_socket()[1], "replay")

    def test_garbage_mode_file_defaults_replay(self) -> None:
        self._write_mode("bogus")
        self.assertEqual(probe._resolve_socket()[1], "replay")

    def test_env_socket_wins_over_canonical(self) -> None:
        os.environ[probe._SOCKET_ENV] = "/run/operator-broker.sock"
        path, mode = probe._resolve_socket()
        self.assertEqual(path, "/run/operator-broker.sock")
        self.assertEqual(mode, "live")  # operator socket defaults to live


@unittest.skipUnless(_HAS_FASTAPI, "requires the [api] extra (fastapi)")
class ProbeAddrFallbackTest(unittest.TestCase):
    """The tcp: probe.addr marker (Windows fallback) resolves like the canonical
    socket: mode from probe.mode, safe default replay, garbage ignored."""

    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        # No unix socket exists at the canonical path (Windows situation).
        self._sock_path = Path(self._tmp.name) / "probe.sock"
        self._env = mock.patch.dict(os.environ, {}, clear=False)
        self._env.start()
        os.environ.pop(probe._SOCKET_ENV, None)
        os.environ.pop(probe._MODE_ENV, None)
        self.addCleanup(self._env.stop)
        self._patch = mock.patch.object(probe, "_canonical_socket", return_value=self._sock_path)
        self._patch.start()
        self.addCleanup(self._patch.stop)

    def _write_addr(self, value: str) -> None:
        (self._sock_path.with_name("probe.addr")).write_text(value, encoding="utf-8")

    def test_tcp_addr_marker_resolves_with_replay_default(self) -> None:
        self._write_addr("tcp:127.0.0.1:8093\n")
        path, mode = probe._resolve_socket()
        self.assertEqual(path, "tcp:127.0.0.1:8093")
        self.assertEqual(mode, "replay")

    def test_tcp_addr_marker_mode_from_mode_file(self) -> None:
        self._write_addr("tcp:127.0.0.1:8093")
        (self._sock_path.with_name("probe.mode")).write_text("live", encoding="utf-8")
        self.assertEqual(probe._resolve_socket()[1], "live")

    def test_non_tcp_addr_marker_is_ignored(self) -> None:
        self._write_addr("/some/stale/path.sock")
        self.assertEqual(probe._resolve_socket(), (None, "off"))

    def test_absent_marker_is_off(self) -> None:
        self.assertEqual(probe._resolve_socket(), (None, "off"))


if __name__ == "__main__":
    unittest.main()
