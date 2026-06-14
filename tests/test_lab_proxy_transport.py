# tests/test_lab_proxy_transport.py
"""LabHttpProxy transport-error legibility: a refused connection (the target
mock_local/declared_url server is stopped) must surface as a readable
"server stopped" message including the base_url, not a raw OS errno. Other
transport faults keep the generic wording. Fail-safe: ok=False, never raises."""

from __future__ import annotations

import socket
import unittest

from recette.platform.events import PlatformActionEvent
from recette.platform.proxy.lab_proxy import LabHttpProxy, _transport_error


def _closed_port() -> int:
    """A port that is guaranteed to refuse connections (bound then released)."""
    s = socket.socket()
    s.bind(("127.0.0.1", 0))
    port = s.getsockname()[1]
    s.close()
    return port


def _event() -> PlatformActionEvent:
    return PlatformActionEvent(
        event_id="evt-0001",
        timestamp="t0",
        agent_id="a1",
        capability_scope=(),
        role="",
        action_type="create_payment",
        target_system="finance",
        resource="accounts-payable-run",
        payload={},
        risk_score=0,
        risk_level="high",
    )


class TestLabProxyTransport(unittest.TestCase):
    def test_refused_connection_says_server_stopped(self) -> None:
        base = f"http://127.0.0.1:{_closed_port()}"
        result = LabHttpProxy(base_url=base, timeout=2.0).execute(_event())
        self.assertFalse(result.ok)
        self.assertEqual(result.status_code, 0)
        self.assertIn("server stopped", result.error)
        # The unreachable target URL is named so the operator knows what to start.
        self.assertIn(base, result.error)

    def test_classifier_refused(self) -> None:
        msg = _transport_error("http://x:1", ConnectionRefusedError(111, "refused"))
        self.assertIn("server stopped", msg)
        self.assertIn("http://x:1", msg)

    def test_classifier_other_transport_fault_keeps_generic(self) -> None:
        msg = _transport_error("http://x:1", TimeoutError("timed out"))
        self.assertEqual(msg, "proxy transport error: timed out")


if __name__ == "__main__":
    unittest.main()
