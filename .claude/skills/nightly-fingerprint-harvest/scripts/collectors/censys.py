"""Censys collector. Free tier: 250 queries/month.

Auth: env var CENSYS_API_TOKEN (Personal Access Token, Bearer auth).
Legacy env vars CENSYS_API_ID + CENSYS_API_SECRET still accepted as
fallback (HTTP Basic) for older accounts.
API doc: https://search.censys.io/api
Endpoint v2: POST https://search.censys.io/api/v2/hosts/search

Query examples:
  'services.software.product:"nginx"'
  'services.banner:"OpenSSH_9.0"'
"""

from __future__ import annotations

import base64
import json
import os
import urllib.request
from typing import Optional

from .base import Collector, CollectorRequest, CollectorResult


class CensysCollector(Collector):
    name = "censys"
    requires_auth = True
    auth_env_keys = ("CENSYS_API_TOKEN",)

    BASE_URL = "https://search.censys.io/api/v2/hosts/search"

    def is_configured(self) -> bool:
        if os.environ.get("CENSYS_API_TOKEN"):
            return True
        return bool(os.environ.get("CENSYS_API_ID") and os.environ.get("CENSYS_API_SECRET"))

    def _auth_header(self) -> str:
        token = os.environ.get("CENSYS_API_TOKEN", "")
        if token:
            return f"Bearer {token}"
        api_id = os.environ.get("CENSYS_API_ID", "")
        api_secret = os.environ.get("CENSYS_API_SECRET", "")
        encoded = base64.b64encode(f"{api_id}:{api_secret}".encode()).decode()
        return f"Basic {encoded}"

    def _build_query(self, request: CollectorRequest) -> str:
        terms: list[str] = []
        if request.product:
            terms.append(f'services.software.product: "{request.product}"')
        if request.vendor and len(request.vendor) > 2:
            terms.append(f'services.software.vendor: "{request.vendor}"')
        if request.ports:
            terms.append(f"services.port: {request.ports[0]}")
        return " and ".join(terms) or f'services.banner: "{request.taxonomy_code or request.query_seed}"'

    def search(self, request: CollectorRequest) -> list[CollectorResult]:
        if not self.is_configured():
            return [CollectorResult(source=self.name, host="",
                                    error="CENSYS_API_TOKEN (or legacy ID+SECRET) missing")]

        payload = json.dumps({
            "q": self._build_query(request),
            "per_page": request.max_hosts,
        }).encode()
        req = urllib.request.Request(
            self.BASE_URL,
            data=payload,
            method="POST",
            headers={
                "Authorization": self._auth_header(),
                "Content-Type": "application/json",
                "Accept": "application/json",
            },
        )

        try:
            with urllib.request.urlopen(req, timeout=25) as resp:
                if resp.status != 200:
                    return [CollectorResult(
                        source=self.name, host="",
                        error=f"HTTP {resp.status} from Censys")]
                data = json.loads(resp.read())
        except Exception as exc:
            return [CollectorResult(source=self.name, host="", error=str(exc))]

        results: list[CollectorResult] = []
        for host in data.get("result", {}).get("hits", []):
            ip = str(host.get("ip", ""))
            services = host.get("services") or []
            for svc in services[:1]:  # one service per host
                port = int(svc.get("port", 0) or 0)
                banner = str(svc.get("banner", "")) or None
                http_block = svc.get("http") or {}
                response = http_block.get("response") or {}
                response_headers = response.get("headers") or {}
                body = (response.get("body") or "").encode("utf-8", errors="replace")
                results.append(CollectorResult(
                    source=self.name,
                    host=ip,
                    port=port,
                    capture_url=f"censys:{ip}:{port}",
                    http_status=int(response.get("status_code") or 0),
                    headers=response_headers,
                    body=body,
                    banner=banner,
                    raw_record=host,
                ))
            if len(results) >= request.max_hosts:
                break
        return results
