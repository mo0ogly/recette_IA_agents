"""Mock Discovery / Enrichment Plane service (:8081) for the local lab.

A stdlib HTTP server implementing the assumed Discovery REST routes
(sources / scan-runs / risks), backed by the ReferenceSourceScanAdapter so it returns
exactly what a correct GitHubScanner should. Lets the full loop
`recette discovery --adapter http` run end-to-end in Docker against a real HTTP service,
WITHOUT the colleague's real service.

This is a LAB DOUBLE, not the product. Routes mirror recette/http_adapter.py (A1).
"""

from __future__ import annotations

import json
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlparse

from .adapters import ReferenceSourceScanAdapter

# Shared oracle-backed state across requests (single-process lab).
_ADAPTER = ReferenceSourceScanAdapter()
_RUN_TO_SOURCE: dict[str, str] = {}


def _envelope(data: object) -> bytes:
    return json.dumps({"success": True, "data": data}).encode("utf-8")


class _Handler(BaseHTTPRequestHandler):
    def log_message(self, *args):  # silence default stderr logging
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
        return json.loads(self.rfile.read(length).decode("utf-8"))

    # POST /v1/sources ; POST /v1/sources/{id}/scan
    def do_POST(self) -> None:  # noqa: N802 (BaseHTTPRequestHandler API)
        path = urlparse(self.path).path
        if path == "/v1/sources":
            body = self._read_body()
            source_id = _ADAPTER.register(body["location"])
            self._send(200, _envelope({"source_id": source_id}))
            return
        if path.startswith("/v1/sources/") and path.endswith("/scan"):
            source_id = path[len("/v1/sources/") : -len("/scan")]
            run_id = _ADAPTER.scan(source_id)
            _RUN_TO_SOURCE[run_id] = source_id
            self._send(200, _envelope({"run_id": run_id}))
            return
        self._send(404, _envelope({"error": "not found"}))

    # GET /v1/scan-runs/{id} ; GET /v1/sources/{id}/risks
    def do_GET(self) -> None:  # noqa: N802
        path = urlparse(self.path).path
        if path.startswith("/v1/scan-runs/"):
            self._send(200, _envelope({"status": "completed"}))
            return
        if path.startswith("/v1/sources/") and path.endswith("/risks"):
            source_id = path[len("/v1/sources/") : -len("/risks")]
            risks = [
                {
                    "canonical_agent_id": r.canonical_agent_id,
                    "action_pattern": r.action_pattern,
                    "target_system": r.target_system,
                    "estimated_risk": r.estimated_risk,
                    "generated_policy": r.generated_policy,
                    "passport_status": r.passport_status,
                }
                for r in _ADAPTER.risks(source_id)
            ]
            self._send(200, _envelope(risks))
            return
        if path == "/healthz":
            self._send(200, _envelope({"status": "ok"}))
            return
        self._send(404, _envelope({"error": "not found"}))


def make_server(host: str = "0.0.0.0", port: int = 8081) -> ThreadingHTTPServer:  # noqa: S104  # nosec B104
    # Binds all interfaces on purpose: the lab mock must be reachable across containers.
    return ThreadingHTTPServer((host, port), _Handler)


def main() -> None:
    server = make_server()
    host, port = server.server_address[0], server.server_address[1]
    print(f"discovery-mock listening on {host!r}:{port} (oracle-backed)")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        server.shutdown()


if __name__ == "__main__":
    main()
