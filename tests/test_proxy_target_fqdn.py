# tests/test_proxy_target_fqdn.py
"""Task 5: ProxyTrace.target carries the resolved server name (fqdn) for trace
realism, so a trace reads ``api.github.com`` instead of ``127.0.0.1:9101``.

This is realism-only plumbing. The resolver is called with containment OFF, so an
unknown name keeps the exact legacy id-based path. The deny/audit path
(containment ON) is Task 6 and is NOT exercised here.

NOTE (deviation from the task brief, reported in the handoff): in THIS codebase
``LabHttpProxy.execute`` returns an ``ExecutionResult`` (it does not build a
``ProxyTrace``; the ``RingTraceRecorder`` does, from the event + result). The
resolved name is therefore surfaced as ``ExecutionResult.target`` by the proxy
and copied onto ``ProxyTrace.target`` by the recorder (``result.target or
event.target_system``). The assertions below check both layers accordingly.
"""

from __future__ import annotations

import unittest

from recette.platform.events import PlatformActionEvent
from recette.platform.proxy.lab_proxy import LabHttpProxy
from recette.platform.proxy.protocol import ExecutionResult
from recette.platform.proxy.router import resolve_proxy
from recette.platform.proxy.tracing import RingTraceRecorder


def _event(target_system: str = "github") -> PlatformActionEvent:
    return PlatformActionEvent(
        event_id="evt-0001",
        timestamp="2026-06-15T00:00:00Z",
        agent_id="agent-x",
        capability_scope=(),
        role="reader",
        action_type="read_repo",
        target_system=target_system,
        resource="acme/widgets",
        payload={"ref": "main"},
        risk_score=1,
        risk_level="low",
    )


class _StubClient:
    """httpx-style stub matching StdlibHttpClient's surface: a .post returning a
    response with .status and .json(), plus a public .base_url. Mirrors the
    existing lab_proxy tests' introspection pattern (proxy._client)."""

    def __init__(self, base_url: str) -> None:
        self.base_url = base_url
        self.posted: list[tuple[str, dict]] = []

    def post(self, path: str, json: dict):  # noqa: A002 - mirror real signature
        self.posted.append((path, json))
        return _StubResponse()


class _StubResponse:
    status = 200

    def json(self) -> dict:
        return {"success": True, "data": {"ok": True}}


def _proxy_with_stub(base_url: str, *, target_name: str | None = None) -> LabHttpProxy:
    proxy = LabHttpProxy(base_url=base_url, target_name=target_name)
    proxy._client = _StubClient(base_url)  # noqa: SLF001 - test seam, as in test_proxy_router
    return proxy


SERVERS_WITH_FQDN = [
    {
        "id": "gh-mock",
        "system": "github",
        "mode": "mock_local",
        "port": 9101,
        "fqdn": "api.github.com",
    },
    {
        "id": "gh-mock-nofqdn",
        "system": "github",
        "mode": "mock_local",
        "port": 9102,
    },
]


class LabProxyTargetNameTests(unittest.TestCase):
    def test_target_name_surfaces_on_execution_result(self) -> None:
        proxy = _proxy_with_stub("http://127.0.0.1:9101", target_name="api.github.com")
        result = proxy.execute(_event("github"))
        self.assertTrue(result.ok)
        self.assertEqual(result.target, "api.github.com")

    def test_without_target_name_falls_back_to_target_system(self) -> None:
        proxy = _proxy_with_stub("http://127.0.0.1:9101")
        result = proxy.execute(_event("github"))
        self.assertTrue(result.ok)
        # Back-compat: default None -> behaves exactly as today (no fqdn known).
        self.assertIsNone(result.target)

    def test_recorder_uses_target_name_for_trace_target(self) -> None:
        # The recorder builds ProxyTrace.target from result.target or event.target_system.
        proxy = _proxy_with_stub("http://127.0.0.1:9101", target_name="api.github.com")
        result = proxy.execute(_event("github"))
        recorder = RingTraceRecorder()
        recorder.record(_event("github"), result)
        trace = recorder.snapshot()[0]
        self.assertEqual(trace.target, "api.github.com")
        self.assertEqual(trace.to_dict()["target"], "api.github.com")

    def test_recorder_target_falls_back_to_target_system(self) -> None:
        result = ExecutionResult(ok=True, status_code=200)
        recorder = RingTraceRecorder()
        recorder.record(_event("github"), result)
        trace = recorder.snapshot()[0]
        self.assertEqual(trace.target, "github")
        self.assertEqual(trace.to_dict()["target"], "github")


class ResolveProxyFqdnTests(unittest.TestCase):
    def _target_name(self, proxy: LabHttpProxy) -> str | None:
        return proxy._target_name  # noqa: SLF001 - test introspection, as in router tests

    def test_server_with_fqdn_threads_fqdn_as_target_name(self) -> None:
        agent = {"id": "a1", "target_system": "github", "server": "gh-mock"}
        default = LabHttpProxy("http://localhost:8082")
        resolved = resolve_proxy(agent, SERVERS_WITH_FQDN, default)
        self.assertIsInstance(resolved, LabHttpProxy)
        self.assertEqual(self._target_name(resolved), "api.github.com")
        # The resolved entry still drives the base_url (mode/port unchanged).
        self.assertEqual(resolved._client.base_url, "http://127.0.0.1:9101")  # noqa: SLF001

    def test_server_without_fqdn_has_no_target_name(self) -> None:
        agent = {"id": "a1", "target_system": "github", "server": "gh-mock-nofqdn"}
        default = LabHttpProxy("http://localhost:8082")
        resolved = resolve_proxy(agent, SERVERS_WITH_FQDN, default)
        self.assertIsInstance(resolved, LabHttpProxy)
        self.assertIsNone(self._target_name(resolved))
        self.assertEqual(resolved._client.base_url, "http://127.0.0.1:9102")  # noqa: SLF001

    def test_end_to_end_trace_target_is_fqdn(self) -> None:
        agent = {"id": "a1", "target_system": "github", "server": "gh-mock"}
        default = LabHttpProxy("http://localhost:8082")
        resolved = resolve_proxy(agent, SERVERS_WITH_FQDN, default)
        assert isinstance(resolved, LabHttpProxy)
        resolved._client = _StubClient("http://127.0.0.1:9101")  # noqa: SLF001
        result = resolved.execute(_event("github"))
        recorder = RingTraceRecorder()
        recorder.record(_event("github"), result)
        self.assertEqual(recorder.snapshot()[0].target, "api.github.com")


if __name__ == "__main__":
    unittest.main()
