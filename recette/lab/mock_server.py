"""Generic mock lab server (:8082): POST /{target_system}/execute.

LAB DOUBLE of the 11 external systems -- one process, one handler module per
domain (recette/lab/domains/*). Handlers are pure and deterministic (I4):
stable ids derived from sha256 of inputs, no clock, no random, no state.

Run: python -m recette.lab.mock_server   (port via AGENTRAIL_LAB_PORT, R5)
"""

from __future__ import annotations

import importlib
import json
import os
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlparse

from .domains import HANDLER_MODULES

DEFAULT_PORT = 8082


def _load_handlers() -> dict[str, object]:
    handlers: dict[str, object] = {}
    for target_system, module_name in HANDLER_MODULES.items():
        module = importlib.import_module(f"{__package__}.domains.{module_name}")
        handlers[target_system] = module
    return handlers


_HANDLERS = _load_handlers()


def _envelope_ok(data: object) -> bytes:
    return json.dumps({"success": True, "data": data}, sort_keys=True).encode("utf-8")


def _envelope_err(message: str) -> bytes:
    return json.dumps({"success": False, "error": message}, sort_keys=True).encode("utf-8")


def _append_access_log(record: dict) -> None:
    """Append one JSONL line when AGENTRAIL_LAB_ACCESS_LOG is set (R5).

    The env var is read per request: cheap, and honors changes without a
    restart. The server is threaded, but a single open(..., "a") followed by
    one write() of one line is atomic enough for line-grained appends on
    POSIX (O_APPEND), so concurrent handlers do not interleave partial lines.
    No timestamp on purpose: the event_id already orders the trace (I4).
    """
    log_path = os.environ.get("AGENTRAIL_LAB_ACCESS_LOG")
    if not log_path:
        return
    with open(log_path, "a", encoding="utf-8") as log_file:
        log_file.write(json.dumps(record, sort_keys=True) + "\n")


def dispatch(target_system: str, action_type: str, resource: str, payload: dict) -> dict | None:
    """Route to the domain handler. None when target or action is unknown."""
    module = _HANDLERS.get(target_system)
    if module is None:
        return None
    handle = getattr(module, "handle", None)
    if handle is None:
        return None
    result = handle(action_type, resource, payload)
    return result if isinstance(result, dict) else None


class _Handler(BaseHTTPRequestHandler):
    def log_message(self, *args: object) -> None:  # silence default stderr logging
        return

    def _send(self, status: int, body: bytes) -> None:
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _read_body(self) -> dict:
        length = int(self.headers.get("Content-Length", "0") or "0")
        if not length:
            return {}
        parsed = json.loads(self.rfile.read(length).decode("utf-8"))
        return parsed if isinstance(parsed, dict) else {}

    def do_GET(self) -> None:  # noqa: N802 (BaseHTTPRequestHandler API)
        # /healthz kept as a legacy alias (documented in docs/runbooks/recette-sh.md).
        if urlparse(self.path).path in ("/health", "/healthz"):
            self._send(200, _envelope_ok({"status": "up", "systems": sorted(_HANDLERS)}))
            return
        self._send(404, _envelope_err("not found"))

    def do_POST(self) -> None:  # noqa: N802
        path = urlparse(self.path).path
        parts = [p for p in path.split("/") if p]
        if len(parts) != 2 or parts[1] != "execute":
            self._send(404, _envelope_err("not found"))
            return
        target_system = parts[0]
        try:
            body = self._read_body()
        except json.JSONDecodeError:
            body = {}
            status, response = 400, _envelope_err("invalid JSON body")
        else:
            action_type = str(body.get("action_type", ""))
            resource = str(body.get("resource", ""))
            payload = body.get("payload")
            result = dispatch(
                target_system, action_type, resource, payload if isinstance(payload, dict) else {}
            )
            if result is None:
                status, response = 404, _envelope_err(
                    f"unknown action {target_system}/{action_type}"
                )
            else:
                status, response = 200, _envelope_ok(result)
        # Log before sending so a client that has the response can read the line.
        _append_access_log(
            {
                "event_id": body.get("event_id"),
                "target_system": target_system,
                "action_type": str(body.get("action_type", "")),
                "resource": str(body.get("resource", "")),
                "status": status,
            }
        )
        self._send(status, response)


def main() -> None:
    port = int(os.environ.get("AGENTRAIL_LAB_PORT", str(DEFAULT_PORT)))
    server = ThreadingHTTPServer(("0.0.0.0", port), _Handler)  # noqa: S104  # nosec B104 - lab container
    server.serve_forever()


if __name__ == "__main__":
    main()
