"""Netlas.io collector. Free tier: 50 queries/day.

Auth: env var NETLAS_API_KEY.
API doc: https://docs.netlas.io/api/responses/
Endpoint: GET https://app.netlas.io/api/responses/?q=<query>&size=<n>

Query examples:
  "product:nginx port:443"
  "tag:wordpress"
  'http.headers.server:"nginx/1.24"'
"""

from __future__ import annotations

import json
import os
import time
import urllib.parse
import urllib.request
from typing import Optional

from .base import Collector, CollectorRequest, CollectorResult


class NetlasCollector(Collector):
    name = "netlas"
    requires_auth = True
    auth_env_keys = ("NETLAS_API_KEY",)

    BASE_URL = "https://app.netlas.io/api/responses/"
    USER_AGENT = "LIA-SEC liaprobe-harvest/1.0"

    def _build_query(self, request: CollectorRequest) -> str:
        # Netlas full-text search is more reliable than narrow product:
        # filters (many fingerprint rules have vendor/product strings that
        # don't exactly match Netlas's product taxonomy). Use the seed as
        # a plain phrase. Add a port filter only if the rule is bound to
        # one specific port.
        seed = request.product or request.query_seed or request.taxonomy_code
        if not seed:
            return "*"
        # Quote the seed to keep multi-word product names intact.
        quoted = seed.replace('"', "")
        query = f'"{quoted}"'
        if request.ports and len(request.ports) == 1 and request.ports[0] not in (80, 443):
            query += f" AND port:{request.ports[0]}"
        return query

    def _http_get(self, url: str, headers: dict) -> tuple[int, dict, bytes]:
        req = urllib.request.Request(url, headers=headers)
        with urllib.request.urlopen(req, timeout=20) as resp:
            return (
                resp.status,
                dict(resp.headers.items()),
                resp.read(),
            )

    def search(self, request: CollectorRequest) -> list[CollectorResult]:
        api_key = os.environ.get("NETLAS_API_KEY", "")
        if not api_key:
            return [CollectorResult(source=self.name, host="", error="NETLAS_API_KEY missing")]

        query = self._build_query(request)
        params = {
            "q": query,
            "size": str(request.max_hosts),
        }
        url = f"{self.BASE_URL}?{urllib.parse.urlencode(params)}"
        headers = {
            "X-API-Key": api_key,
            "Accept": "application/json",
            "User-Agent": self.USER_AGENT,
        }

        try:
            status, _, body = self._http_get(url, headers)
            if status != 200:
                return [CollectorResult(
                    source=self.name, host="",
                    error=f"HTTP {status} from Netlas search")]
            data = json.loads(body)
        except Exception as exc:
            return [CollectorResult(source=self.name, host="", error=str(exc))]

        results: list[CollectorResult] = []
        for item in data.get("items", []):
            doc = item.get("data", item)
            host = str(doc.get("host", ""))
            port = int(doc.get("port", 0) or 0)
            http_block = doc.get("http") or {}
            response_headers = http_block.get("headers") or {}
            body_text = (http_block.get("body") or "").encode("utf-8", errors="replace")
            status_code = int(http_block.get("status_code") or 0)
            results.append(CollectorResult(
                source=self.name,
                host=host,
                port=port,
                capture_url=f"netlas:{host}:{port}",
                http_status=status_code,
                headers=response_headers,
                body=body_text,
                banner=str(http_block.get("banner", "")) or None,
                raw_record=doc,
            ))
            if len(results) >= request.max_hosts:
                break
        # Polite spacing in case caller loops several queries
        time.sleep(0.2)
        return results
