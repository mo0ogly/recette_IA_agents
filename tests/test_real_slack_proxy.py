"""G5 RealSlackProxy: verified end-to-end against a faithful local Slack Web API
emulator over REAL HTTP sockets (mirror of the docker Postgres/NATS approach in
G3/G4). The proxy code is production-real -- real urllib request, real Bearer
header, real JSON parse, real side_effect_hash; only the Slack endpoint is a
local stand-in. A live test against the real Slack is separate (skip-unless)."""

from __future__ import annotations

import json
import threading
import unittest
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from recette.platform.events import ApprovalState, PlatformActionEvent
from recette.platform.proxy.real_slack_proxy import (
    ProxyConfigError,
    RealSlackProxy,
    build_slack_proxy_from_env,
)

TOKEN = "xoxb-test-token"
ALLOWED = "C0ALLOWED"


class _SlackEmulator(BaseHTTPRequestHandler):
    """Faithful-enough Slack Web API: checks the Bearer token, echoes the method,
    returns {"ok": true, ...} -- except for a channel named 'C0ERROR' which
    returns {"ok": false, "error": "channel_not_found"}."""

    captured: list[dict] = []

    def log_message(self, *args: object) -> None:  # silence the test server
        pass

    def do_POST(self) -> None:  # noqa: N802 - http.server API
        length = int(self.headers.get("Content-Length", "0"))
        raw = self.rfile.read(length) if length else b"{}"
        body = json.loads(raw.decode("utf-8"))
        method = self.path.lstrip("/")
        type(self).captured.append(
            {"method": method, "auth": self.headers.get("Authorization"), "body": body}
        )
        channel = body.get("channel") or body.get("name")
        if channel == "C0ERROR":
            payload = {"ok": False, "error": "channel_not_found"}
        else:
            payload = {"ok": True, "channel": channel, "ts": "1620000000.000100", "method": method}
        data = json.dumps(payload).encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)


def _event(action_type: str, resource: str, *, payload: dict | None = None, approved: bool = True):
    return PlatformActionEvent(
        event_id="EV1",
        timestamp="2026-06-13T00:00:00Z",
        agent_id="agent-x",
        capability_scope=("slack",),
        role="workspace_admin",
        action_type=action_type,
        target_system="slack",
        resource=resource,
        payload=payload or {},
        risk_score=3,
        risk_level="high",
        approval_state=ApprovalState.APPROVED if approved else ApprovalState.PENDING,
    )


class RealSlackProxyTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.server = ThreadingHTTPServer(("127.0.0.1", 0), _SlackEmulator)
        cls.port = cls.server.server_address[1]
        cls.thread = threading.Thread(target=cls.server.serve_forever, daemon=True)
        cls.thread.start()

    @classmethod
    def tearDownClass(cls) -> None:
        cls.server.shutdown()

    def setUp(self) -> None:
        _SlackEmulator.captured = []
        self.base = f"http://127.0.0.1:{self.port}"

    def _proxy(self, *, enable_writes: bool = True) -> RealSlackProxy:
        return RealSlackProxy(
            token=TOKEN,
            base_url=self.base,
            allowlist=frozenset({ALLOWED, "C0ERROR"}),
            enable_writes=enable_writes,
        )

    def test_write_post_message_hits_real_http_with_bearer(self) -> None:
        result = self._proxy().execute(
            _event("send_message_external_channel", ALLOWED, payload={"text": "hi"})
        )
        self.assertTrue(result.ok, result.error)
        self.assertEqual(result.status_code, 200)
        self.assertIsNotNone(result.side_effect_hash)
        sent = _SlackEmulator.captured[-1]
        self.assertEqual(sent["method"], "chat.postMessage")
        self.assertEqual(sent["auth"], f"Bearer {TOKEN}")
        self.assertEqual(sent["body"], {"channel": ALLOWED, "text": "hi"})

    def test_side_effect_hash_is_deterministic_for_same_response(self) -> None:
        a = self._proxy().execute(_event("delete_channel", ALLOWED))
        b = self._proxy().execute(_event("delete_channel", ALLOWED))
        self.assertTrue(a.ok and b.ok)
        self.assertEqual(a.side_effect_hash, b.side_effect_hash)

    def test_read_allowed_without_writes(self) -> None:
        result = self._proxy(enable_writes=False).execute(
            _event("access_confidential_channel", ALLOWED)
        )
        self.assertTrue(result.ok, result.error)
        self.assertEqual(_SlackEmulator.captured[-1]["method"], "conversations.info")

    def test_allowlist_rejection_never_calls_slack(self) -> None:
        result = self._proxy().execute(_event("delete_channel", "C0NOPE"))
        self.assertFalse(result.ok)
        self.assertEqual(result.status_code, 403)
        self.assertEqual(_SlackEmulator.captured, [])

    def test_write_disabled_is_refused_and_never_calls_slack(self) -> None:
        result = self._proxy(enable_writes=False).execute(_event("delete_channel", ALLOWED))
        self.assertFalse(result.ok)
        self.assertEqual(result.status_code, 403)
        self.assertIn("writes are disabled", result.error or "")
        self.assertEqual(_SlackEmulator.captured, [])

    def test_unapproved_write_is_refused_i6(self) -> None:
        result = self._proxy().execute(_event("create_public_channel", ALLOWED, approved=False))
        self.assertFalse(result.ok)
        self.assertEqual(result.status_code, 403)
        self.assertIn("approved", result.error or "")
        self.assertEqual(_SlackEmulator.captured, [])

    def test_unsupported_action_is_refused(self) -> None:
        result = self._proxy().execute(_event("modify_workspace_permissions", ALLOWED))
        self.assertFalse(result.ok)
        self.assertEqual(result.status_code, 501)
        self.assertEqual(_SlackEmulator.captured, [])

    def test_slack_ok_false_maps_to_failure(self) -> None:
        result = self._proxy().execute(_event("delete_channel", "C0ERROR"))
        self.assertFalse(result.ok)
        self.assertIn("channel_not_found", result.error or "")

    def test_resolve_proxy_router_seam_end_to_end(self) -> None:
        # Full I5 router path: an agent bound to a real_saas/slack server resolves
        # to a RealSlackProxy via the injected factory and reaches the emulator.
        import os

        from recette.platform.proxy.real_proxy import build_real_proxy_factory
        from recette.platform.proxy.router import resolve_proxy

        saved = {
            k: os.environ.get(k)
            for k in (
                "SLACK_BOT_TOKEN",
                "INSPECT_IA_AGENTS_SLACK_CHANNEL_ALLOWLIST",
                "INSPECT_IA_AGENTS_SLACK_API_URL",
                "INSPECT_IA_AGENTS_SLACK_ENABLE_WRITES",
            )
        }
        os.environ.update(
            {
                "SLACK_BOT_TOKEN": TOKEN,
                "INSPECT_IA_AGENTS_SLACK_CHANNEL_ALLOWLIST": ALLOWED,
                "INSPECT_IA_AGENTS_SLACK_API_URL": self.base,
                "INSPECT_IA_AGENTS_SLACK_ENABLE_WRITES": "true",
            }
        )
        try:
            from recette.platform.proxy.lab_proxy import LabHttpProxy

            agent = {"id": "a", "server": "slack-test"}
            servers = [{"id": "slack-test", "mode": "real_saas", "system": "slack"}]
            proxy = resolve_proxy(
                agent, servers, LabHttpProxy(), real_proxy_factory=build_real_proxy_factory()
            )
            self.assertIsInstance(proxy, RealSlackProxy)
            result = proxy.execute(
                _event("send_message_external_channel", ALLOWED, payload={"text": "seam"})
            )
            self.assertTrue(result.ok, result.error)
            self.assertEqual(_SlackEmulator.captured[-1]["method"], "chat.postMessage")
        finally:
            for k, v in saved.items():
                if v is None:
                    os.environ.pop(k, None)
                else:
                    os.environ[k] = v

    def test_transport_error_is_failsafe(self) -> None:
        proxy = RealSlackProxy(
            token=TOKEN,
            base_url="http://127.0.0.1:1",  # nothing listening
            allowlist=frozenset({ALLOWED}),
            enable_writes=True,
        )
        result = proxy.execute(_event("delete_channel", ALLOWED))
        self.assertFalse(result.ok)
        self.assertEqual(result.status_code, 0)
        self.assertIn("transport error", result.error or "")


class BuildSlackProxyFromEnvTest(unittest.TestCase):
    def setUp(self) -> None:
        import os

        self._saved = {
            k: os.environ.get(k)
            for k in (
                "SLACK_BOT_TOKEN",
                "INSPECT_IA_AGENTS_SLACK_CHANNEL_ALLOWLIST",
                "INSPECT_IA_AGENTS_SLACK_API_URL",
            )
        }
        for k in self._saved:
            os.environ.pop(k, None)

    def tearDown(self) -> None:
        import os

        for k, v in self._saved.items():
            if v is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = v

    def test_missing_token_raises(self) -> None:
        import os

        os.environ["INSPECT_IA_AGENTS_SLACK_CHANNEL_ALLOWLIST"] = ALLOWED
        with self.assertRaises(ProxyConfigError):
            build_slack_proxy_from_env()

    def test_empty_allowlist_raises_failsafe(self) -> None:
        import os

        os.environ["SLACK_BOT_TOKEN"] = TOKEN
        with self.assertRaises(ProxyConfigError):
            build_slack_proxy_from_env()

    def test_happy_build(self) -> None:
        import os

        os.environ["SLACK_BOT_TOKEN"] = TOKEN
        os.environ["INSPECT_IA_AGENTS_SLACK_CHANNEL_ALLOWLIST"] = f"{ALLOWED}, C0OTHER"
        proxy = build_slack_proxy_from_env()
        self.assertIsInstance(proxy, RealSlackProxy)


class FactoryDispatchTest(unittest.TestCase):
    def test_factory_builds_slack_proxy_for_system_slack(self) -> None:
        import os

        from recette.platform.proxy.real_proxy import build_real_proxy_factory

        saved = (
            os.environ.get("SLACK_BOT_TOKEN"),
            os.environ.get("INSPECT_IA_AGENTS_SLACK_CHANNEL_ALLOWLIST"),
        )
        os.environ["SLACK_BOT_TOKEN"] = TOKEN
        os.environ["INSPECT_IA_AGENTS_SLACK_CHANNEL_ALLOWLIST"] = ALLOWED
        try:
            factory = build_real_proxy_factory()
            proxy = factory({"id": "s1", "system": "slack"})
            self.assertIsInstance(proxy, RealSlackProxy)
        finally:
            for k, v in zip(
                ("SLACK_BOT_TOKEN", "INSPECT_IA_AGENTS_SLACK_CHANNEL_ALLOWLIST"), saved, strict=True
            ):
                if v is None:
                    os.environ.pop(k, None)
                else:
                    os.environ[k] = v


if __name__ == "__main__":
    unittest.main()
