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
from pathlib import Path
from unittest import mock

try:
    from fastapi.testclient import TestClient

    from recette.api.app import create_app
    from recette.api.config_store import ConfigStore

    _HAS_FASTAPI = True
except ImportError:  # pragma: no cover - only without the [api] extra
    _HAS_FASTAPI = False

_SOCKET_ENV = "INSPECT_IA_AGENTS_PROBE_SOCKET"
_MODE_ENV = "INSPECT_IA_AGENTS_PROBE_MODE"

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
        self._saved_mode = os.environ.pop(_MODE_ENV, None)
        # Neutralize the canonical-socket FALLBACK so the env-contract tests are
        # deterministic regardless of whether a real broker is running on this
        # machine (.run/probe.sock). Tests exercising the fallback re-patch it.
        self._canon = mock.patch(
            "recette.api.routers.probe._canonical_socket",
            return_value=Path(tempfile.mkdtemp()) / "absent.sock",
        )
        self._canon.start()
        self.addCleanup(self._canon.stop)

    def tearDown(self) -> None:
        for env, saved in ((_SOCKET_ENV, self._saved), (_MODE_ENV, self._saved_mode)):
            if saved is None:
                os.environ.pop(env, None)
            else:
                os.environ[env] = saved

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

    def test_env_socket_wins_over_canonical_fallback(self) -> None:
        # When the env IS set, it is authoritative and the mode defaults to live
        # (operator-set socket targets the privileged broker). The canonical
        # fallback (patched absent) must not shadow it.
        os.environ[_SOCKET_ENV] = "/some/explicit/broker.sock"
        body = self.client.get("/probe/status").json()
        self.assertTrue(body["configured"])
        self.assertEqual(body["mode"], "live")

    def test_canonical_socket_fallback_when_env_unset(self) -> None:
        # The friction this closes: a standalone `api restart` dropped the env
        # but the auto-started broker is still up at .run/probe.sock. Status must
        # report configured + replay (R13: the auto broker is replay, not live),
        # and a capture must relay to that socket -- WITHOUT the env being set.
        broker = _StubBroker(_BROKER_OK)
        self.addCleanup(broker.close)
        with mock.patch(
            "recette.api.routers.probe._canonical_socket",
            return_value=Path(broker.path),
        ):
            status = self.client.get("/probe/status").json()
            self.assertTrue(status["configured"])
            self.assertEqual(status["mode"], "replay")
            resp = self.client.post("/probe/capture", json={"agents": ["pr-bot-sdk"]})
            self.assertEqual(resp.status_code, 200)
            self.assertEqual(resp.json()["recording"]["status"], "ok")
        # The env was never set: the fallback alone made the capture work.
        self.assertNotIn(_SOCKET_ENV, os.environ)


_BROKER_WIRE = {
    "status": "ok",
    "recordings": [
        {
            "agent_id": "pr-bot-sdk",
            # one declared endpoint (a seeded mock_local server on :9151) and one
            # undeclared host (a connect to an IP not in the server registry).
            "surfaces": {"ebpf_wire": ["connect:127.0.0.1:9151", "connect:203.0.113.7:443"]},
        },
    ],
    "recording_sha256": "0" * 64,
}


@unittest.skipUnless(_HAS_FASTAPI, "requires the [api] extra (fastapi)")
class TestProbeCaptureWireNames(unittest.TestCase):
    """Task 3: /probe/capture attaches the v1 named-wire annotation
    (declared server name + undeclared host) without touching the scorecard."""

    def setUp(self) -> None:
        # Isolated ConfigStore (a tmp file) so seeding a server never dirties the
        # tracked corpus config; mirror the test_api_config_routes pattern.
        self._tmpdir = tempfile.mkdtemp()
        store = ConfigStore(Path(self._tmpdir) / "config.json")
        store.add_server({"id": "wire-gh", "system": "github", "mode": "mock_local", "port": 9151})
        self.client = TestClient(create_app(config_store=store))
        self._saved = os.environ.pop(_SOCKET_ENV, None)
        self._saved_mode = os.environ.pop(_MODE_ENV, None)
        self._canon = mock.patch(
            "recette.api.routers.probe._canonical_socket",
            return_value=Path(tempfile.mkdtemp()) / "absent.sock",
        )
        self._canon.start()
        self.addCleanup(self._canon.stop)

    def tearDown(self) -> None:
        for env, saved in ((_SOCKET_ENV, self._saved), (_MODE_ENV, self._saved_mode)):
            if saved is None:
                os.environ.pop(env, None)
            else:
                os.environ[env] = saved

    def test_capture_attaches_named_and_undeclared_wire(self) -> None:
        broker = _StubBroker(_BROKER_WIRE)
        self.addCleanup(broker.close)
        os.environ[_SOCKET_ENV] = broker.path
        resp = self.client.post(
            "/probe/capture",
            json={"agents": ["pr-bot-sdk"], "duration_ms": 2000},
        )
        self.assertEqual(resp.status_code, 200)
        body = resp.json()
        # the seeded mock_local server resolves the loopback endpoint to its id
        self.assertEqual(body["wire_named"]["pr-bot-sdk"][0]["name"], "wire-gh")
        # the unknown host is flagged in the run-level undeclared list
        self.assertIn("203.0.113.7:443", body["undeclared_hosts"])
        # detection behavior is unchanged: the scorecard is still present
        self.assertIn("scorecard", body)


if __name__ == "__main__":
    unittest.main()
