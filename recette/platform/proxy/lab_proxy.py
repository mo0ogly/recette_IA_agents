"""Lab proxy: routes side effects to the simulated lab over HTTP (I5).

Base URL comes from configuration (R5): INSPECT_IA_AGENTS_LAB_URL or constructor arg.
Failure mode: proxy/lab unreachable or non-2xx -> ok=False; the gateway
appends an auditable failure event and never bypasses.
"""

from __future__ import annotations

import errno
import os

from ..._http_client import StdlibHttpClient
from ..events import PlatformActionEvent
from .protocol import ExecutionResult, side_effect_hash

DEFAULT_LAB_URL = "http://localhost:8082"


def lab_url_from_env() -> str:
    return os.environ.get("INSPECT_IA_AGENTS_LAB_URL", DEFAULT_LAB_URL)


def _transport_error(base_url: str, exc: Exception) -> str:
    """Classify a connect failure into a legible message. A refused connection
    (ECONNREFUSED) means nothing is listening at the target -- almost always the
    mock_local/declared_url server is stopped -- so say so instead of leaking the
    raw OS errno. Other transport faults keep the generic wording."""
    reason = getattr(exc, "reason", exc)
    refused = isinstance(reason, ConnectionRefusedError) or (
        getattr(reason, "errno", None) == errno.ECONNREFUSED
    )
    if refused:
        return f"target server stopped or unreachable at {base_url} (start it): {exc}"
    return f"proxy transport error: {exc}"


def _error_from_envelope(resp: object) -> str:
    """Build a legible error from a 4xx lab envelope.

    The double answers a rejected action with ``{success:false, error, code?,
    detail?}`` (a structured error). Surface ``code: message`` so the failure is
    legible in the ProxyTrace, falling back to the bare status when the body is
    not the expected shape."""
    status = getattr(resp, "status", 0)
    fallback = f"lab returned HTTP {status}"
    try:
        body = resp.json()  # type: ignore[attr-defined]
    except Exception:
        return fallback
    if not isinstance(body, dict):
        return fallback
    message = str(body.get("error") or fallback)
    code = body.get("code")
    # Keep the HTTP status in the string (callers/tests rely on it) while adding
    # the structured code + message so the failure is legible in the ProxyTrace.
    detail = f"{code}: {message}" if code else message
    return f"lab HTTP {status}: {detail}"


class LabHttpProxy:
    def __init__(
        self, base_url: str | None = None, *, timeout: float = 10.0, proxy_url: str | None = None
    ) -> None:
        # ``proxy_url`` (optional) routes the side effect through the mitmproxy
        # wire overlay; None (default) talks to the lab directly (I4 unchanged).
        self._client = StdlibHttpClient(
            base_url or lab_url_from_env(), timeout=timeout, proxy_url=proxy_url
        )

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
            return ExecutionResult(
                ok=False, status_code=0, error=_transport_error(self._client.base_url, exc)
            )
        if resp.status >= 400:
            return ExecutionResult(
                ok=False, status_code=resp.status, error=_error_from_envelope(resp)
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
