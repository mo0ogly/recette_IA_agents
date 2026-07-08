# tests/test_lab_proxy_transport.py
"""LabHttpProxy transport-error legibility: a refused connection (the target
mock_local/declared_url server is stopped) must surface as a readable
"server stopped" message including the base_url, not a raw OS errno. Other
transport faults keep the generic wording. Fail-safe: ok=False, never raises."""

from __future__ import annotations

import errno
import unittest
from urllib.error import URLError

from recette.platform.events import PlatformActionEvent
from recette.platform.proxy.lab_proxy import LabHttpProxy, _transport_error


def _raise(exc: Exception):  # type: ignore[no-untyped-def]
    """A callable that raises ``exc`` regardless of arguments (stub for _client.post)."""

    def _stub(*_args: object, **_kwargs: object) -> object:
        raise exc

    return _stub


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
        # Inject the exact exception urllib raises on a refused connect (URLError
        # wrapping ECONNREFUSED). This proves the execute -> _transport_error ->
        # ExecutionResult wiring deterministically on every platform, instead of
        # relying on OS loopback behaviour: a bound-then-closed port refuses on
        # POSIX but can TIME OUT on Windows, which would misclassify the fault.
        base = "http://127.0.0.1:9"
        proxy = LabHttpProxy(base_url=base, timeout=2.0)
        refused = URLError(ConnectionRefusedError(errno.ECONNREFUSED, "refused"))
        proxy._client.post = _raise(refused)  # type: ignore[method-assign]
        result = proxy.execute(_event())
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
