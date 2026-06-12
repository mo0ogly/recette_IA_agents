"""Lifecycle tests for the lab mock server: /health probe + JSONL access log.

Boots the real ThreadingHTTPServer in-process on an ephemeral port and talks
to it over HTTP (stdlib urllib only). The access log is driven by the
AGENTRAIL_LAB_ACCESS_LOG env var, read per-request by the server, so tests
set/unset it around requests and restore the original value in tearDown.
"""

from __future__ import annotations

import json
import os
import threading
import unittest
import urllib.error
import urllib.request
from http.server import ThreadingHTTPServer
from pathlib import Path
from tempfile import TemporaryDirectory

from recette.lab.domains import HANDLER_MODULES
from recette.lab.mock_server import _Handler

_ACCESS_LOG_ENV = "AGENTRAIL_LAB_ACCESS_LOG"


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


if __name__ == "__main__":
    unittest.main()
