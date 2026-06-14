"""RealSlackProxy: a real-SaaS ExternalSystemProxy over the Slack Web API (I5).

Adapts the I5 proxy protocol to the real Slack Web API (``POST
https://slack.com/api/<method>`` with a Bearer token, response ``{"ok": bool,
...}``). It maps the EXISTING ``slack`` catalog action_types
(catalog/domains/slack.py) to Slack methods -- no invented action.

Safety posture (recette-corpus, R8, failure-modes.md), so a real run can never
spam a production workspace:
- Lab stays the default; this proxy is opt-in (real_saas server with system=slack).
- The bot token comes from ``SLACK_BOT_TOKEN`` (env, R8), held only here, never
  in decision code, never logged.
- A channel allowlist (``INSPECT_IA_AGENTS_SLACK_CHANNEL_ALLOWLIST``) restricts every
  call to test channels; an empty allowlist refuses everything (fail-safe).
- ``enable_writes`` is False by default: write methods are refused unless
  explicitly opted in, and a write also requires the event to be approved (I6,
  defense in depth on top of the gateway).

Failure mode: an unsupported action, an allowlist rejection, a disabled write, a
Slack ``ok:false`` body, a non-JSON body or any transport error is mapped to
``ExecutionResult(ok=False, ...)``. The proxy never raises through the gateway
and never bypasses; the gateway then appends an auditable failure event.
"""

from __future__ import annotations

import os

from ..._http_client import StdlibHttpClient
from ..events import PlatformActionEvent
from .protocol import ExecutionResult, side_effect_hash
from .wire import wire_ca_from_env, wire_proxy_url_from_env

DEFAULT_SLACK_API_URL = "https://slack.com/api"

# Internal status classification for the audit trail (Slack speaks ok:bool, not
# always HTTP status): 200 ok, 403 refused (allowlist/write-gate), 501 action not
# supported by this proxy, 502 Slack-side error, 0 transport failure.
_STATUS_OK = 200
_STATUS_FORBIDDEN = 403
_STATUS_UNSUPPORTED = 501
_STATUS_SLACK_ERROR = 502

# Canonical slack action_type -> Slack Web API method. Split by side: WRITE
# methods mutate the workspace (gated by enable_writes + approval); READ methods
# only observe (allowlist still applies).
_WRITE_METHODS = {
    "send_message_external_channel": "chat.postMessage",
    "publish_company_announcement": "chat.postMessage",
    "create_public_channel": "conversations.create",
    "delete_channel": "conversations.archive",
}
_READ_METHODS = {
    "access_confidential_channel": "conversations.info",
    "export_slack_history": "conversations.history",
}


class ProxyConfigError(RuntimeError):
    """A real proxy is missing required configuration (token/allowlist)."""


def _slack_params(method: str, channel: str, payload: dict) -> dict:
    """Build the Slack method params from the canonical event resource/payload."""
    if method == "chat.postMessage":
        text = payload.get("text") or payload.get("message") or ""
        return {"channel": channel, "text": str(text)}
    if method == "conversations.create":
        # ``resource`` carries the channel NAME to create (allowlisted).
        return {"name": channel, "is_private": False}
    if method == "conversations.archive":
        return {"channel": channel}
    if method == "conversations.info":
        return {"channel": channel}
    if method == "conversations.history":
        limit = payload.get("limit", 100)
        return {"channel": channel, "limit": int(limit) if isinstance(limit, int) else 100}
    return {"channel": channel}  # pragma: no cover - methods are exhaustive above


class RealSlackProxy:
    """ExternalSystemProxy backed by the real Slack Web API."""

    def __init__(
        self,
        *,
        token: str,
        base_url: str = DEFAULT_SLACK_API_URL,
        allowlist: frozenset[str],
        enable_writes: bool = False,
        timeout: float = 10.0,
        proxy_url: str | None = None,
        ca_bundle: str | None = None,
    ) -> None:
        # proxy_url/ca_bundle (optional) route the real Slack HTTPS through the
        # mitmproxy wire overlay so the exchange is captured; None => direct.
        self._client = StdlibHttpClient(
            base_url,
            headers={"Authorization": f"Bearer {token}"},
            timeout=timeout,
            proxy_url=proxy_url,
            ca_bundle=ca_bundle,
        )
        self._allowlist = allowlist
        self._enable_writes = enable_writes

    def execute(self, event: PlatformActionEvent) -> ExecutionResult:
        method = _WRITE_METHODS.get(event.action_type) or _READ_METHODS.get(event.action_type)
        if method is None:
            return ExecutionResult(
                ok=False,
                status_code=_STATUS_UNSUPPORTED,
                error=f"slack proxy: action {event.action_type!r} is not supported",
            )
        channel = event.resource
        if channel not in self._allowlist:
            return ExecutionResult(
                ok=False,
                status_code=_STATUS_FORBIDDEN,
                error=f"slack proxy: channel {channel!r} not in allowlist",
            )
        is_write = event.action_type in _WRITE_METHODS
        if is_write:
            if not self._enable_writes:
                return ExecutionResult(
                    ok=False,
                    status_code=_STATUS_FORBIDDEN,
                    error="slack proxy: writes are disabled (enable_writes=False)",
                )
            if event.approval_state != "approved":
                # Defense in depth on I6: the gateway already blocks, but a write
                # must never go out un-approved even if reached directly.
                return ExecutionResult(
                    ok=False,
                    status_code=_STATUS_FORBIDDEN,
                    error="slack proxy: write requires an approved action (I6)",
                )
        body = _slack_params(method, channel, dict(event.payload))
        try:
            resp = self._client.post(f"/{method}", json=body)
        except Exception as exc:  # noqa: BLE001 - transport errors must not raise through
            return ExecutionResult(
                ok=False, status_code=0, error=f"slack proxy transport error: {exc}"
            )
        try:
            data = resp.json()
        except Exception:  # noqa: BLE001 - a non-JSON body is a Slack-side failure
            return ExecutionResult(
                ok=False, status_code=_STATUS_SLACK_ERROR, error="slack proxy: non-JSON response"
            )
        if not isinstance(data, dict) or not data.get("ok"):
            err = data.get("error") if isinstance(data, dict) else "malformed response"
            return ExecutionResult(
                ok=False,
                status_code=resp.status if resp.status >= 400 else _STATUS_SLACK_ERROR,
                response=data if isinstance(data, dict) else {},
                error=f"slack error: {err}",
            )
        return ExecutionResult(
            ok=True,
            status_code=_STATUS_OK,
            response=data,
            side_effect_hash=side_effect_hash(
                event.target_system, event.action_type, event.resource, data
            ),
        )


def _parse_allowlist(raw: str | None) -> frozenset[str]:
    if not raw:
        return frozenset()
    return frozenset(item.strip() for item in raw.split(",") if item.strip())


def build_slack_proxy_from_env(*, enable_writes: bool = False) -> RealSlackProxy:
    """Build a RealSlackProxy from the environment (R8). Fail-safe: a missing
    token or an empty channel allowlist raises rather than running unrestricted."""
    token = os.environ.get("SLACK_BOT_TOKEN")
    if not token:
        raise ProxyConfigError("RealSlackProxy needs SLACK_BOT_TOKEN in the environment")
    allowlist = _parse_allowlist(os.environ.get("INSPECT_IA_AGENTS_SLACK_CHANNEL_ALLOWLIST"))
    if not allowlist:
        raise ProxyConfigError(
            "RealSlackProxy needs a non-empty INSPECT_IA_AGENTS_SLACK_CHANNEL_ALLOWLIST (fail-safe)"
        )
    base_url = os.environ.get("INSPECT_IA_AGENTS_SLACK_API_URL", DEFAULT_SLACK_API_URL)
    _env_writes = os.environ.get("INSPECT_IA_AGENTS_SLACK_ENABLE_WRITES", "").lower() == "true"
    writes = enable_writes or _env_writes
    return RealSlackProxy(
        token=token,
        base_url=base_url,
        allowlist=allowlist,
        enable_writes=writes,
        proxy_url=wire_proxy_url_from_env(),
        ca_bundle=wire_ca_from_env(),
    )
