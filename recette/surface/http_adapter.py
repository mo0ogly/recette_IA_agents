"""Live SurfaceDiscoveryAdapter for a real discovery probe detection endpoint (HTTP).

Wires the per-surface detection recette to a real discovery probe. The harness depends
only on the ``SurfaceDiscoveryAdapter`` protocol (``recette/surface/detect.py``);
this is the HTTP implementation, mirroring ``recette/http_adapter.py`` (which
wires the ``SourceScanAdapter``). The route and the response JSON shape are
ASSUMED here pending the discovery probe detection API; every assumption is isolated in
this one module so a change is a one-file edit.

- httpx is imported lazily; the package works without it (the reference adapter
  needs no network). The zero-dependency stdlib client is the fallback.
- Base URL via ``INSPECT_IA_AGENTS_RAILNODE_URL``; token via env, never hardcoded (R8).
- The response envelope is unwrapped explicitly (no raw passthrough).
"""

from __future__ import annotations

import os
from typing import Any

from recette.adapters import DiscoveryResult

from .surfaces import SurfaceObservation

# Assumed discovery probe detection route -- confirm against the discovery probe API.
ROUTE_DETECT = "/v1/detect"


def _unwrap(payload: Any) -> Any:
    """Unwrap a {success, data} envelope if present; otherwise return as-is."""
    if (
        isinstance(payload, dict)
        and "data" in payload
        and set(payload).issubset({"success", "data", "error"})
    ):
        return payload["data"]
    return payload


class HttpSurfaceDiscoveryAdapter:
    """Talks to a discovery probe detection endpoint (default http://127.0.0.1:8085).

    ``detect_on`` POSTs one surface observation and reads back the detection
    verdict for that surface. A real discovery probe answers ``{detected: bool, signals:
    [...]}`` (optionally inside a ``{success, data}`` envelope).
    """

    def __init__(
        self,
        base_url: str | None = None,
        *,
        tenant: str | None = None,
        token: str | None = None,
        client: Any | None = None,
    ) -> None:
        self.base_url = (
            base_url or os.environ.get("INSPECT_IA_AGENTS_RAILNODE_URL", "http://127.0.0.1:8085")
        ).rstrip("/")
        self.tenant = tenant or os.environ.get("INSPECT_IA_AGENTS_TENANT", "dev")
        self.token = token or os.environ.get("INSPECT_IA_AGENTS_RAILNODE_TOKEN")
        self._client = client or self._default_client()

    def _default_client(self) -> Any:
        headers = {"X-Tenant-Id": self.tenant}
        if self.token:
            headers["Authorization"] = f"Bearer {self.token}"
        try:
            import httpx  # type: ignore

            return httpx.Client(base_url=self.base_url, headers=headers, timeout=30.0)
        except ImportError:
            from recette._http_client import StdlibHttpClient

            return StdlibHttpClient(self.base_url, headers=headers)

    def detect_on(self, observation: SurfaceObservation) -> DiscoveryResult:
        body = {"surface": observation.surface.value, "visible": list(observation.visible)}
        resp = self._client.post(ROUTE_DETECT, json=body)
        resp.raise_for_status()
        data = _unwrap(resp.json())
        return DiscoveryResult(
            detected=bool(data.get("detected", False)),
            signals=list(data.get("signals", [])),
        )
