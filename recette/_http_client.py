"""Minimal stdlib HTTP client so the HTTP adapter works without httpx.

Keeps the recette dependency-light (zero hard deps beyond jsonschema). Implements just
the surface HttpSourceScanAdapter needs: .post(path, json=...) and .get(path), each
returning a response object exposing .raise_for_status() and .json().
"""

from __future__ import annotations

import json as _json
import urllib.error
import urllib.request
from typing import Any


class _Response:
    def __init__(self, status: int, body: bytes) -> None:
        self.status = status
        self._body = body

    def raise_for_status(self) -> None:
        if self.status >= 400:
            raise RuntimeError(f"HTTP {self.status}: {self._body.decode('utf-8', 'replace')[:200]}")

    def json(self) -> Any:
        return _json.loads(self._body.decode("utf-8"))


# Some provider edges (e.g. Cloudflare-fronted api.groq.com) reject the default
# "Python-urllib/x.y" agent with HTTP 403 code 1010. Send an explicit agent so
# live provider calls are not blocked on the client signature.
DEFAULT_USER_AGENT = "inspect_ia_agents-recette/0.1"


class StdlibHttpClient:
    """Tiny urllib-based client with a base_url and default headers."""

    def __init__(self, base_url: str, headers: dict[str, str] | None = None, timeout: float = 30.0):
        self.base_url = base_url.rstrip("/")
        self.headers = headers or {}
        self.timeout = timeout

    def _request(self, method: str, path: str, body: dict | None) -> _Response:
        url = f"{self.base_url}{path}"
        data = _json.dumps(body).encode("utf-8") if body is not None else None
        headers = dict(self.headers)
        headers.setdefault("User-Agent", DEFAULT_USER_AGENT)
        if data is not None:
            headers["Content-Type"] = "application/json"
        req = urllib.request.Request(url, data=data, headers=headers, method=method)
        try:
            # url is built from a caller-supplied base_url (http/https), not user input
            with urllib.request.urlopen(req, timeout=self.timeout) as resp:  # noqa: S310  # nosec B310
                return _Response(resp.status, resp.read())
        except urllib.error.HTTPError as exc:
            return _Response(exc.code, exc.read())

    def post(self, path: str, json: dict | None = None) -> _Response:
        return self._request("POST", path, json if json is not None else {})

    def get(self, path: str) -> _Response:
        return self._request("GET", path, None)
