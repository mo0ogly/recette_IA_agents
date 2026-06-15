"""Generic mock lab server (:8082): POST /{target_system}/execute.

LAB DOUBLE of the 11 external systems -- one process, one handler module per
domain (recette/lab/domains/*). Handlers are pure and deterministic (I4):
stable ids derived from sha256 of inputs, no clock, no random, no state.

Run: python -m recette.lab.mock_server   (port via INSPECT_IA_AGENTS_LAB_PORT, R5)
"""

from __future__ import annotations

import importlib
import json
import os
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from types import ModuleType
from urllib.parse import urlparse

from .domains import HANDLER_MODULES
from .errors import LabActionError

DEFAULT_PORT = 8082


def _load_handlers() -> dict[str, ModuleType]:
    handlers: dict[str, ModuleType] = {}
    for target_system, module_name in HANDLER_MODULES.items():
        module = importlib.import_module(f"{__package__}.domains.{module_name}")
        handlers[target_system] = module
    return handlers


_HANDLERS = _load_handlers()

# Dev-only hot-reload state (see _maybe_reload). The lock serialises reloads
# across the threaded server; _MTIMES tracks each domain module's source mtime.
_RELOAD_LOCK = threading.Lock()
_MTIMES: dict[str, float] = {}


def _reload_enabled() -> bool:
    raw = os.environ.get("INSPECT_IA_AGENTS_LAB_RELOAD", "").strip().lower()
    return raw in {"1", "true", "yes", "on"}


def _seed_mtimes() -> None:
    for module in _HANDLERS.values():
        path = getattr(module, "__file__", None)
        if path is None:
            continue
        try:
            _MTIMES[path] = os.path.getmtime(path)
        except OSError:
            pass


_seed_mtimes()


def _maybe_reload() -> None:
    """Reload a domain handler whose source changed, so an edited lab domain is
    served without restarting the long-lived mock_local server.

    Gated by INSPECT_IA_AGENTS_LAB_RELOAD (R5), OFF by default: tests and replay
    keep a static, deterministic lab (I4). The lab is the external target (I5),
    never the decision/judge path, so reloading it is safe. Cheap per request:
    one stat per domain; a reload happens only when an mtime actually changes.
    """
    if not _reload_enabled():
        return
    with _RELOAD_LOCK:
        for target_system, module in list(_HANDLERS.items()):
            path = getattr(module, "__file__", None)
            if path is None:
                continue
            try:
                mtime = os.path.getmtime(path)
            except OSError:
                continue
            if _MTIMES.get(path) != mtime:
                _HANDLERS[target_system] = importlib.reload(module)
                _MTIMES[path] = mtime


def _envelope_ok(data: object) -> bytes:
    return json.dumps({"success": True, "data": data}, sort_keys=True).encode("utf-8")


def _envelope_err(message: str, code: str | None = None, detail: dict | None = None) -> bytes:
    body: dict = {"success": False, "error": message}
    if code is not None:
        body["code"] = code
    if detail is not None:
        body["detail"] = detail
    return json.dumps(body, sort_keys=True).encode("utf-8")


def _append_access_log(record: dict) -> None:
    """Append one JSONL line when INSPECT_IA_AGENTS_LAB_ACCESS_LOG is set (R5).

    The env var is read per request: cheap, and honors changes without a
    restart. The server is threaded, but a single open(..., "a") followed by
    one write() of one line is atomic enough for line-grained appends on
    POSIX (O_APPEND), so concurrent handlers do not interleave partial lines.
    No timestamp on purpose: the event_id already orders the trace (I4).
    """
    log_path = os.environ.get("INSPECT_IA_AGENTS_LAB_ACCESS_LOG")
    if not log_path:
        return
    with open(log_path, "a", encoding="utf-8") as log_file:
        log_file.write(json.dumps(record, sort_keys=True) + "\n")


def dispatch(target_system: str, action_type: str, resource: str, payload: dict) -> dict | None:
    """Route to the domain handler. None when target or action is unknown.

    A handler may raise ``LabActionError`` for a known action with invalid
    input; that propagates to the caller (the HTTP layer maps it to its status).
    """
    _maybe_reload()
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
            try:
                result = dispatch(
                    target_system,
                    action_type,
                    resource,
                    payload if isinstance(payload, dict) else {},
                )
            except LabActionError as err:
                status = err.status_code
                response = _envelope_err(err.message, err.code, err.detail)
            else:
                if result is None:
                    status, response = (
                        404,
                        _envelope_err(f"unknown action {target_system}/{action_type}"),
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
    port = int(os.environ.get("INSPECT_IA_AGENTS_LAB_PORT", str(DEFAULT_PORT)))
    server = ThreadingHTTPServer(("0.0.0.0", port), _Handler)  # noqa: S104  # nosec B104 - lab container
    server.serve_forever()


if __name__ == "__main__":
    main()
