"""Live SourceScanAdapter for the Discovery / Enrichment Plane REST API (:8081).

Wires the recette to the colleague's real Discovery service. The exact routes and the
`estimated_risk` JSON shape are ASSUMED here pending the Discovery OpenAPI (see A1/A4 in
the plan); every assumption is isolated in this one module so a change is a one-file edit.

- httpx is imported lazily; the package works without it (the reference adapter does not
  need network).
- Tenant via AGENTRAIL_TENANT (dev mode, arch doc section 9). Token via env, never hardcoded.
- The response envelope is unwrapped explicitly (no raw passthrough).
"""

from __future__ import annotations

import os
from typing import Any

from .adapters import DiscoveryRisk

# Assumed Discovery REST routes (A1) -- confirm against the Discovery OpenAPI.
ROUTE_SOURCES = "/v1/sources"
ROUTE_SCAN = "/v1/sources/{source_id}/scan"
ROUTE_RUN = "/v1/scan-runs/{run_id}"
ROUTE_RISKS = "/v1/sources/{source_id}/risks"

# Terminal scan_run statuses.
_DONE = {"completed", "succeeded", "failed", "error", "timeout"}


def _unwrap(payload: Any) -> Any:
    """Unwrap a {success, data} envelope if present; otherwise return as-is."""
    if (
        isinstance(payload, dict)
        and "data" in payload
        and set(payload).issubset({"success", "data", "error"})
    ):
        return payload["data"]
    return payload


class HttpSourceScanAdapter:
    """Talks to the Discovery service at base_url (default http://127.0.0.1:8081)."""

    def __init__(
        self,
        base_url: str | None = None,
        *,
        tenant: str | None = None,
        token: str | None = None,
        client: Any | None = None,
    ) -> None:
        self.base_url = (
            base_url or os.environ.get("AGENTRAIL_DISCOVERY_URL", "http://127.0.0.1:8081")
        ).rstrip("/")
        self.tenant = tenant or os.environ.get("AGENTRAIL_TENANT", "dev")
        self.token = token or os.environ.get("AGENTRAIL_DISCOVERY_TOKEN")
        self._client = client or self._default_client()

    def _default_client(self) -> Any:
        try:
            import httpx  # type: ignore
        except ImportError as exc:  # pragma: no cover - optional dep
            raise RuntimeError(
                "HttpSourceScanAdapter needs httpx (pip install 'railgun-recette[real]') "
                "or pass an explicit client="
            ) from exc
        headers = {"X-Tenant-Id": self.tenant}
        if self.token:
            headers["Authorization"] = f"Bearer {self.token}"
        return httpx.Client(base_url=self.base_url, headers=headers, timeout=30.0)

    def _post(self, path: str, json_body: dict) -> Any:
        resp = self._client.post(path, json=json_body)
        resp.raise_for_status()
        return _unwrap(resp.json())

    def _get(self, path: str) -> Any:
        resp = self._client.get(path)
        resp.raise_for_status()
        return _unwrap(resp.json())

    def register(self, location: str) -> str:
        body = {
            "adapter": "github",
            "name": location,
            "location": location,
            "tenant_id": self.tenant,
        }
        data = self._post(ROUTE_SOURCES, body)
        return str(data["source_id"])

    def scan(self, source_id: str) -> str:
        data = self._post(ROUTE_SCAN.format(source_id=source_id), {})
        return str(data["run_id"])

    def await_run(self, run_id: str) -> str:
        # Single poll; the caller/harness decides on retry cadence. Returns the status.
        data = self._get(ROUTE_RUN.format(run_id=run_id))
        return str(data.get("status", "unknown"))

    def risks(self, source_id: str) -> list[DiscoveryRisk]:
        data = self._get(ROUTE_RISKS.format(source_id=source_id))
        rows = data if isinstance(data, list) else data.get("risks", [])
        return [
            DiscoveryRisk(
                canonical_agent_id=row["canonical_agent_id"],
                action_pattern=row["action_pattern"],
                target_system=row["target_system"],
                estimated_risk=row.get("estimated_risk") or {},
                generated_policy=row.get("generated_policy"),
            )
            for row in rows
        ]
