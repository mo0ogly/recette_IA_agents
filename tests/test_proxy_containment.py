# tests/test_proxy_containment.py
"""Task 6: the CONTAINMENT gate.

When containment is enforced, an agent that references an UNDECLARED server name
must be DENIED fail-safe: resolve_proxy raises ResolutionDenied (NO proxy built),
and the impure call-site emits an audited ``resolution_denied`` event before
failing the run -- NO proxy is built, NO HTTP call is made (I2/I5 fail-safe).

resolve_proxy stays PURE (I4): it only RAISES; the caller decides to audit.

Router-level tests (pure):
- unknown name + containment ON  -> ResolutionDenied, no proxy.
- known fqdn  + containment ON  -> resolves (allowlisted).
- known id    + containment OFF -> resolves (legacy / realism-only path).

Call-site test:
- on ResolutionDenied the gateway records a ``resolution_denied`` event and NO
  proxy is built / NO HTTP call is made.
"""

from __future__ import annotations

import unittest

from recette.platform.events import EventKind
from recette.platform.netname.resolver import ResolutionDenied
from recette.platform.proxy.lab_proxy import LabHttpProxy
from recette.platform.proxy.router import resolve_proxy

SERVERS = [
    {
        "id": "gh-mock",
        "system": "github",
        "mode": "mock_local",
        "port": 9101,
        "fqdn": "api.github.com",
    }
]


class ContainmentRouterTests(unittest.TestCase):
    def test_unknown_name_with_containment_on_is_denied(self) -> None:
        agent = {"id": "a1", "target_system": "github", "server": "evil.example.com"}
        default = LabHttpProxy("http://localhost:8082")
        with self.assertRaises(ResolutionDenied) as ctx:
            resolve_proxy(agent, SERVERS, default, containment=True)
        self.assertEqual(ctx.exception.name, "evil.example.com")

    def test_known_fqdn_with_containment_on_resolves(self) -> None:
        agent = {"id": "a1", "target_system": "github", "server": "api.github.com"}
        default = LabHttpProxy("http://localhost:8082")
        resolved = resolve_proxy(agent, SERVERS, default, containment=True)
        self.assertIsInstance(resolved, LabHttpProxy)
        self.assertEqual(resolved._target_name, "api.github.com")  # noqa: SLF001
        self.assertEqual(resolved._client.base_url, "http://127.0.0.1:9101")  # noqa: SLF001

    def test_known_id_with_containment_off_resolves_legacy(self) -> None:
        agent = {"id": "a1", "target_system": "github", "server": "gh-mock"}
        default = LabHttpProxy("http://localhost:8082")
        resolved = resolve_proxy(agent, SERVERS, default, containment=False)
        self.assertIsInstance(resolved, LabHttpProxy)
        self.assertEqual(resolved._client.base_url, "http://127.0.0.1:9101")  # noqa: SLF001

    def test_unknown_name_with_containment_off_keeps_dangling_valueerror(self) -> None:
        # Back-compat: containment OFF + unknown name -> the legacy dangling-ref
        # ValueError, NOT ResolutionDenied (no behaviour change off the gate).
        agent = {"id": "a1", "target_system": "github", "server": "nope"}
        default = LabHttpProxy("http://localhost:8082")
        with self.assertRaises(ValueError):
            resolve_proxy(agent, SERVERS, default, containment=False)

    def test_default_containment_is_off(self) -> None:
        # Omitting the kwarg keeps the exact previous behaviour (fail-open NOT
        # introduced: unknown -> dangling ValueError, never a silent allow).
        agent = {"id": "a1", "target_system": "github", "server": "nope"}
        default = LabHttpProxy("http://localhost:8082")
        with self.assertRaises(ValueError):
            resolve_proxy(agent, SERVERS, default)


class _RecordingProxy:
    """A proxy whose execute() must NEVER be called on a denied resolution."""

    def __init__(self) -> None:
        self.calls = 0

    def execute(self, event):  # noqa: ANN001
        self.calls += 1
        raise AssertionError("proxy.execute must not run on a denied resolution")


class ContainmentCallSiteTests(unittest.TestCase):
    """The gateway seam emits the audited event and builds NO proxy (fail-safe)."""

    def _gateway(self):
        import tempfile
        from pathlib import Path

        from recette.platform.catalog import Catalog
        from recette.platform.eventstore.memory_store import InMemoryEventStore
        from recette.platform.gateway import AgentResolver, Gateway
        from recette.platform.ids import SequenceIdGenerator
        from recette.platform.policy.store import PolicyStore

        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        store = InMemoryEventStore()
        proxy = _RecordingProxy()
        gw = Gateway(
            catalog=Catalog(()),
            policy_store=PolicyStore(Path(self._tmp.name) / "policies"),
            event_store=store,
            proxy=proxy,  # type: ignore[arg-type]
            id_generator=SequenceIdGenerator(),
            agent_resolver=AgentResolver(lambda _id: None),
        )
        return gw, store, proxy

    def test_record_resolution_denied_emits_event_and_no_execution(self) -> None:
        gw, store, proxy = self._gateway()
        outcome = gw.record_resolution_denied(
            agent_id="agent-x",
            name="evil.example.com",
            reason="not_in_allowlist",
        )
        # Fail-safe: no proxy execution happened.
        self.assertEqual(proxy.calls, 0)
        # An audited resolution_denied event was appended (I1).
        events = list(store.read_from(0))
        denied = [e for e in events if e.kind == EventKind.RESOLUTION_DENIED]
        self.assertEqual(len(denied), 1)
        self.assertEqual(denied[0].payload["name"], "evil.example.com")
        self.assertEqual(denied[0].payload["agent_id"], "agent-x")
        self.assertEqual(denied[0].payload["reason"], "not_in_allowlist")
        # The outcome is a controlled deny (no execution, no result).
        self.assertFalse(outcome.executed)
        self.assertEqual(outcome.verdict, "deny")


if __name__ == "__main__":
    unittest.main()
