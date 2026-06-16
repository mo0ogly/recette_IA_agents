"""Section 12.5: POST /probe/capture relays to the broker (non-privileged) and
scores the recording.

The API never holds CAP_BPF; it relays a `capture` command to the broker's Unix
socket and scores the returned recording with the same source-agnostic judge. A
stub Unix-socket broker stands in for the privileged daemon, so the relay wiring
is proven for real without privilege. No socket / unreachable broker -> 503
(fail-safe, never a fabricated capture).
"""

from __future__ import annotations

import json
import os
import socket
import tempfile
import threading
import unittest

try:
    from fastapi.testclient import TestClient

    from recette.api.app import create_app

    _HAS_FASTAPI = True
except ImportError:  # pragma: no cover - only without the [api] extra
    _HAS_FASTAPI = False

_SOCKET_ENV = "INSPECT_IA_AGENTS_PROBE_SOCKET"

_BROKER_OK = {
    "status": "ok",
    "recordings": [
        {"agent_id": "pr-bot-sdk", "surfaces": {"ebpf_wire": ["exec:pr-bot:42"]}},
        {"agent_id": "ghost-direct-db", "surfaces": {}},
    ],
    "recording_sha256": "0" * 64,
}


class _StubBroker:
    """A one-command Unix-socket server mimicking the real broker's wire form."""

    def __init__(self, response: dict) -> None:
        self.dir = tempfile.mkdtemp()
        self.path = os.path.join(self.dir, "broker.sock")
        self.response = response
        self.requests: list[str] = []
        self._sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        self._sock.bind(self.path)
        self._sock.listen(8)
        self._thread = threading.Thread(target=self._serve, daemon=True)
        self._thread.start()

    def _serve(self) -> None:
        while True:
            try:
                conn, _ = self._sock.accept()
            except OSError:
                return
            with conn:
                data = b""
                while b"\n" not in data:
                    chunk = conn.recv(4096)
                    if not chunk:
                        break
                    data += chunk
                self.requests.append(data.decode("utf-8").strip())
                conn.sendall((json.dumps(self.response) + "\n").encode("utf-8"))

    def close(self) -> None:
        try:
            self._sock.close()
        except OSError:
            pass


@unittest.skipUnless(_HAS_FASTAPI, "requires the [api] extra (fastapi)")
class TestProbeApi(unittest.TestCase):
    def setUp(self) -> None:
        self.client = TestClient(create_app())
        self._saved = os.environ.pop(_SOCKET_ENV, None)

    def tearDown(self) -> None:
        if self._saved is None:
            os.environ.pop(_SOCKET_ENV, None)
        else:
            os.environ[_SOCKET_ENV] = self._saved

    def test_status_reports_unconfigured_without_env(self) -> None:
        resp = self.client.get("/probe/status")
        self.assertEqual(resp.status_code, 200)
        self.assertFalse(resp.json()["configured"])

    def test_capture_without_socket_is_503(self) -> None:
        resp = self.client.post("/probe/capture", json={"agents": ["pr-bot-sdk"]})
        self.assertEqual(resp.status_code, 503)

    def test_capture_relays_and_scores(self) -> None:
        broker = _StubBroker(_BROKER_OK)
        self.addCleanup(broker.close)
        os.environ[_SOCKET_ENV] = broker.path
        resp = self.client.post(
            "/probe/capture",
            json={"agents": ["pr-bot-sdk", "ghost-direct-db"], "duration_ms": 2000},
        )
        self.assertEqual(resp.status_code, 200)
        payload = resp.json()
        # the relayed request reached the broker verbatim
        sent = json.loads(broker.requests[0])
        self.assertEqual(sent["command"], "capture")
        self.assertEqual(sent["agents"], ["pr-bot-sdk", "ghost-direct-db"])
        self.assertEqual(sent["duration_ms"], 2000)
        # the recording is returned and scored: ghost = false negative
        self.assertEqual(payload["recording"]["status"], "ok")
        self.assertFalse(payload["scorecard"]["ok"])
        self.assertEqual(payload["scorecard"]["false_negatives"], ["ghost-direct-db"])

    def test_capture_rejects_empty_agents(self) -> None:
        os.environ[_SOCKET_ENV] = "/nonexistent/broker.sock"
        resp = self.client.post("/probe/capture", json={"agents": []})
        self.assertEqual(resp.status_code, 400)

    def test_unreachable_broker_is_503(self) -> None:
        os.environ[_SOCKET_ENV] = os.path.join(tempfile.mkdtemp(), "absent.sock")
        resp = self.client.post("/probe/capture", json={"agents": ["pr-bot-sdk"]})
        self.assertEqual(resp.status_code, 503)


if __name__ == "__main__":
    unittest.main()
