"""Lab proxy: routes side effects to the simulated lab over HTTP (I5).

Base URL comes from configuration (R5): AGENTRAIL_LAB_URL or constructor arg.
Failure mode: proxy/lab unreachable or non-2xx -> ok=False; the gateway
appends an auditable failure event and never bypasses.
"""

from __future__ import annotations

import os

from ..._http_client import StdlibHttpClient
from ..events import PlatformActionEvent
from .protocol import ExecutionResult, side_effect_hash

DEFAULT_LAB_URL = "http://localhost:8082"


def lab_url_from_env() -> str:
    return os.environ.get("AGENTRAIL_LAB_URL", DEFAULT_LAB_URL)


class LabHttpProxy:
    def __init__(self, base_url: str | None = None, *, timeout: float = 10.0) -> None:
        self._client = StdlibHttpClient(base_url or lab_url_from_env(), timeout=timeout)

    def execute(self, event: PlatformActionEvent) -> ExecutionResult:
        body = {
            "event_id": event.event_id,
            "action_type": event.action_type,
            "resource": event.resource,
            "payload": event.payload,
        }
        try:
            resp = self._client.post(f"/{event.target_system}/execute", json=body)
        except Exception as exc:  # urllib raises URLError on connect failure
            return ExecutionResult(ok=False, status_code=0, error=f"proxy transport error: {exc}")
        if resp.status >= 400:
            return ExecutionResult(
                ok=False, status_code=resp.status, error=f"lab returned HTTP {resp.status}"
            )
        envelope = resp.json()
        if not isinstance(envelope, dict) or not envelope.get("success"):
            return ExecutionResult(
                ok=False, status_code=resp.status, error="lab envelope missing success=true"
            )
        data = envelope.get("data")
        response = data if isinstance(data, dict) else {"data": data}
        return ExecutionResult(
            ok=True,
            status_code=resp.status,
            response=response,
            side_effect_hash=side_effect_hash(
                event.target_system, event.action_type, event.resource, response
            ),
        )
