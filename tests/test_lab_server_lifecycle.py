"""Lifecycle tests for the lab mock server: /health probe + JSONL access log.

Boots the real ThreadingHTTPServer in-process on an ephemeral port and talks
to it over HTTP (stdlib urllib only). The access log is driven by the
INSPECT_IA_AGENTS_LAB_ACCESS_LOG env var, read per-request by the server, so tests
set/unset it around requests and restore the original value in tearDown.
"""

from __future__ import annotations

import json
import os
import socket
import threading
import unittest
import urllib.error
import urllib.request
from http.server import ThreadingHTTPServer
from pathlib import Path
from tempfile import TemporaryDirectory

from recette.api.server_manager import ServerManager
from recette.lab.domains import HANDLER_MODULES
from recette.lab.mock_server import _Handler

_ACCESS_LOG_ENV = "INSPECT_IA_AGENTS_LAB_ACCESS_LOG"


class LabServerLifecycleTest(unittest.TestCase):
    def setUp(self) -> None:
        self._original_access_log = os.environ.pop(_ACCESS_LOG_ENV, None)
        self.server = ThreadingHTTPServer(("127.0.0.1", 0), _Handler)
        self.port = self.server.server_address[1]
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()

    def tearDown(self) -> None:
        self.server.shutdown()
        self.server.server_close()
        self.thread.join(timeout=5)
        os.environ.pop(_ACCESS_LOG_ENV, None)
        if self._original_access_log is not None:
            os.environ[_ACCESS_LOG_ENV] = self._original_access_log

    def _url(self, path: str) -> str:
        return f"http://127.0.0.1:{self.port}{path}"

    def _get(self, path: str) -> tuple[int, dict]:
        try:
            with urllib.request.urlopen(self._url(path)) as response:
                return response.status, json.loads(response.read().decode("utf-8"))
        except urllib.error.HTTPError as error:
            return error.code, json.loads(error.read().decode("utf-8"))

    def _post(self, path: str, body: dict) -> tuple[int, dict]:
        request = urllib.request.Request(
            self._url(path),
            data=json.dumps(body).encode("utf-8"),
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        try:
            with urllib.request.urlopen(request) as response:
                return response.status, json.loads(response.read().decode("utf-8"))
        except urllib.error.HTTPError as error:
            return error.code, json.loads(error.read().decode("utf-8"))

    def test_health_reports_up_and_systems(self) -> None:
        status, body = self._get("/health")
        self.assertEqual(status, 200)
        self.assertTrue(body["success"])
        self.assertEqual(body["data"]["status"], "up")
        self.assertEqual(body["data"]["systems"], sorted(HANDLER_MODULES))
        self.assertIn("github", body["data"]["systems"])
        self.assertIn("okta", body["data"]["systems"])

    def test_get_unknown_path_is_404(self) -> None:
        status, body = self._get("/no/such/path")
        self.assertEqual(status, 404)
        self.assertFalse(body["success"])
        self.assertIn("error", body)

    def test_access_log_line_written(self) -> None:
        with TemporaryDirectory() as tmp_dir:
            log_path = Path(tmp_dir) / "access.jsonl"
            os.environ[_ACCESS_LOG_ENV] = str(log_path)
            status, body = self._post(
                "/github/execute",
                {
                    "event_id": "e1",
                    "action_type": "delete_repository",
                    "resource": "acme/x",
                    "payload": {},
                },
            )
            self.assertEqual(status, 200)
            self.assertTrue(body["success"])

            lines = log_path.read_text(encoding="utf-8").splitlines()
            self.assertEqual(len(lines), 1)
            record = json.loads(lines[0])
            self.assertEqual(
                set(record),
                {"event_id", "target_system", "action_type", "resource", "status"},
            )
            self.assertEqual(record["event_id"], "e1")
            self.assertEqual(record["target_system"], "github")
            self.assertEqual(record["action_type"], "delete_repository")
            self.assertEqual(record["resource"], "acme/x")
            self.assertEqual(record["status"], status)

    def test_invalid_action_input_maps_to_422(self) -> None:
        # A known action with invalid input is rejected by the handler
        # (LabActionError) and surfaced as HTTP 422 with an error envelope,
        # not a generic 200 -- the realistic-double error protocol end to end.
        status, body = self._post(
            "/finance/execute",
            {"action_type": "create_payment", "resource": "acct-1", "payload": {"amount": -10}},
        )
        self.assertEqual(status, 422)
        self.assertFalse(body["success"])
        self.assertIn("amount", body["error"])

    def test_access_log_records_failed_dispatch(self) -> None:
        with TemporaryDirectory() as tmp_dir:
            log_path = Path(tmp_dir) / "access.jsonl"
            os.environ[_ACCESS_LOG_ENV] = str(log_path)
            status, body = self._post(
                "/no_such_system/execute",
                {"action_type": "delete_repository", "resource": "acme/x", "payload": {}},
            )
            self.assertEqual(status, 404)
            self.assertFalse(body["success"])

            lines = log_path.read_text(encoding="utf-8").splitlines()
            self.assertEqual(len(lines), 1)
            record = json.loads(lines[0])
            self.assertIsNone(record["event_id"])
            self.assertEqual(record["target_system"], "no_such_system")
            self.assertEqual(record["status"], 404)

    def test_no_access_log_when_env_unset(self) -> None:
        with TemporaryDirectory() as tmp_dir:
            log_path = Path(tmp_dir) / "access.jsonl"
            self.assertNotIn(_ACCESS_LOG_ENV, os.environ)
            status, _ = self._post(
                "/github/execute",
                {
                    "event_id": "e1",
                    "action_type": "delete_repository",
                    "resource": "acme/x",
                    "payload": {},
                },
            )
            self.assertEqual(status, 200)
            self.assertFalse(log_path.exists())


def _free_port() -> int:
    """Find an ephemeral free port by binding port 0 then closing."""
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]


class ServerManagerTests(unittest.TestCase):
    """Lifecycle of mock_local lab servers via recette.api.server_manager."""

    def setUp(self) -> None:
        tmp = TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.base_dir = Path(tmp.name) / "data" / "lab"
        self.manager = ServerManager(base_dir=self.base_dir)
        # Cleanup runs even when the test body fails: no leaked subprocess.
        self.addCleanup(self._shutdown_and_assert_no_children)

    def _shutdown_and_assert_no_children(self) -> None:
        tracked = list(self.manager._procs.values())
        self.manager.shutdown()
        for proc in tracked:
            self.assertIsNotNone(proc.poll(), "leftover child process after shutdown")
        self.assertEqual(self.manager._procs, {})

    def _health_status(self, port: int) -> int:
        with urllib.request.urlopen(f"http://127.0.0.1:{port}/health", timeout=2) as response:
            return response.status

    def test_start_creates_live_process_and_health_answers(self) -> None:
        port = _free_port()
        result = self.manager.start({"id": "s1", "mode": "mock_local", "port": port})
        self.assertEqual(result, {"status": "up"})
        self.assertEqual(self._health_status(port), 200)
        self.assertEqual(self.manager.status("s1"), "up")

    def test_start_on_busy_port_fails_explicitly(self) -> None:
        blocker = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.addCleanup(blocker.close)
        blocker.bind(("127.0.0.1", 0))
        port = blocker.getsockname()[1]
        result = self.manager.start({"id": "s1", "mode": "mock_local", "port": port})
        self.assertEqual(result["status"], "down")
        self.assertIn(str(port), result["error"])
        self.assertEqual(self.manager.status("s1"), "down")
        self.assertEqual(self.manager._procs, {}, "no process may be spawned on a busy port")

    def test_stop_terminates_process(self) -> None:
        port = _free_port()
        result = self.manager.start({"id": "s1", "mode": "mock_local", "port": port})
        self.assertEqual(result, {"status": "up"})
        self.assertEqual(self.manager.stop("s1"), {"status": "down"})
        self.assertEqual(self.manager.status("s1"), "down")
        with self.assertRaises(urllib.error.URLError):
            urllib.request.urlopen(f"http://127.0.0.1:{port}/health", timeout=2)
        # Stop is idempotent: stopping an already-stopped server stays "down".
        self.assertEqual(self.manager.stop("s1"), {"status": "down"})

    def test_status_down_for_never_started(self) -> None:
        self.assertEqual(self.manager.status("nope"), "down")

    def test_start_rejects_non_mock_local(self) -> None:
        with self.assertRaises(ValueError):
            self.manager.start({"id": "x", "mode": "declared_url", "base_url": "http://h"})

    def test_start_accepts_honeypot_sink(self) -> None:
        # A honeypot reuses the same mock_server process (port-bound sink); only
        # its mode (and thus its exclusion from build_allowlist) differs.
        port = _free_port()
        result = self.manager.start({"id": "sink", "mode": "honeypot", "port": port})
        self.assertEqual(result, {"status": "up"})
        self.assertEqual(self._health_status(port), 200)
        self.assertEqual(self.manager.status("sink"), "up")

    def test_access_log_path_under_data_lab(self) -> None:
        path = self.manager.access_log_path("s1")
        self.assertTrue(path.as_posix().endswith("data/lab/s1.access.jsonl"))

    def test_start_requires_a_non_empty_id(self) -> None:
        no_id = {"mode": "mock_local", "port": 9101}
        empty_id = {"id": "", "mode": "mock_local", "port": 9101}
        for entry in (no_id, empty_id):
            with self.subTest(entry=entry), self.assertRaises(ValueError):
                self.manager.start(entry)

    def test_start_rejects_non_integer_port(self) -> None:
        # bool is an int subclass in Python: it must be rejected too.
        for bad_port in ("9101", None, 9.5, True):
            with self.subTest(port=bad_port), self.assertRaises(ValueError):
                self.manager.start({"id": "x", "mode": "mock_local", "port": bad_port})

    def test_immediate_restart_on_same_port_succeeds(self) -> None:
        """Regression: the start() preflight probe must not refuse a port that
        only holds TIME_WAIT leftovers from the server just stopped (the probe
        binds with SO_REUSEADDR, matching http.server semantics)."""
        port = _free_port()
        entry = {"id": "s1", "mode": "mock_local", "port": port}
        self.assertEqual(self.manager.start(entry), {"status": "up"})
        self._health_status(port)  # leave at least one closed connection behind
        self.assertEqual(self.manager.stop("s1"), {"status": "down"})
        self.assertEqual(self.manager.start(entry), {"status": "up"})
        self.assertEqual(self.manager.status("s1"), "up")

    def test_status_detects_an_externally_died_process(self) -> None:
        port = _free_port()
        self.assertEqual(
            self.manager.start({"id": "s1", "mode": "mock_local", "port": port}), {"status": "up"}
        )
        proc = self.manager._procs["s1"]
        proc.kill()
        proc.wait(timeout=5)
        self.assertEqual(self.manager.status("s1"), "down")

    def test_manager_started_server_writes_its_access_log(self) -> None:
        """The manager injects INSPECT_IA_AGENTS_LAB_ACCESS_LOG: traffic to a managed
        server lands in {base_dir}/{id}.access.jsonl (runtime capture trace)."""
        port = _free_port()
        self.assertEqual(
            self.manager.start({"id": "s1", "mode": "mock_local", "port": port}), {"status": "up"}
        )
        request = urllib.request.Request(
            f"http://127.0.0.1:{port}/github/execute",
            data=json.dumps(
                {
                    "event_id": "e1",
                    "action_type": "delete_repository",
                    "resource": "acme/x",
                    "payload": {},
                }
            ).encode("utf-8"),
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with urllib.request.urlopen(request, timeout=2) as response:
            self.assertEqual(response.status, 200)
        lines = self.manager.access_log_path("s1").read_text(encoding="utf-8").splitlines()
        self.assertEqual(len(lines), 1)
        record = json.loads(lines[0])
        self.assertEqual(record["event_id"], "e1")
        self.assertEqual(record["target_system"], "github")
        self.assertEqual(record["status"], 200)


if __name__ == "__main__":
    unittest.main()
