"""StdlibHttpClient: default User-Agent + override, against a local stub server.

A default User-Agent is required because some provider edges (Cloudflare-fronted
api.groq.com) reject the urllib default agent with HTTP 403 code 1010. These
tests hit a local ThreadingHTTPServer (no network) and read back the headers it
received, so the agent behavior is asserted on real HTTP, not mocked.
"""

from __future__ import annotations

import threading
import unittest
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from recette._http_client import DEFAULT_USER_AGENT, StdlibHttpClient

_RECEIVED: dict[str, str] = {}


class _CaptureHandler(BaseHTTPRequestHandler):
    def log_message(self, *args: object) -> None:  # silence stderr logging
        return

    def _capture_and_reply(self) -> None:
        _RECEIVED.clear()
        for key, value in self.headers.items():
            _RECEIVED[key.lower()] = value
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.end_headers()
        self.wfile.write(b'{"ok": true}')

    def do_GET(self) -> None:
        self._capture_and_reply()

    def do_POST(self) -> None:
        length = int(self.headers.get("Content-Length", "0"))
        self.rfile.read(length)
        self._capture_and_reply()


class StdlibHttpClientUserAgentTests(unittest.TestCase):
    def setUp(self) -> None:
        self.server = ThreadingHTTPServer(("127.0.0.1", 0), _CaptureHandler)
        self.port = self.server.server_address[1]
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()

    def tearDown(self) -> None:
        self.server.shutdown()
        self.server.server_close()
        self.thread.join(timeout=5)

    def _client(self, headers: dict[str, str] | None = None) -> StdlibHttpClient:
        return StdlibHttpClient(f"http://127.0.0.1:{self.port}", headers=headers)

    def test_default_user_agent_is_sent_on_get(self) -> None:
        self._client().get("/")
        self.assertEqual(_RECEIVED.get("user-agent"), DEFAULT_USER_AGENT)

    def test_default_user_agent_is_sent_on_post(self) -> None:
        self._client().post("/", json={"k": "v"})
        self.assertEqual(_RECEIVED.get("user-agent"), DEFAULT_USER_AGENT)

    def test_default_user_agent_is_not_the_urllib_default(self) -> None:
        self._client().get("/")
        self.assertNotIn("python-urllib", _RECEIVED.get("user-agent", "").lower())

    def test_caller_supplied_user_agent_overrides_default(self) -> None:
        self._client(headers={"User-Agent": "custom/9.9"}).get("/")
        self.assertEqual(_RECEIVED.get("user-agent"), "custom/9.9")


if __name__ == "__main__":
    unittest.main()
