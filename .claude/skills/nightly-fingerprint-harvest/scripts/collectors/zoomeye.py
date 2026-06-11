"""ZoomEye collector. Free tier: 500 queries/month.

Auth: env var ZOOMEYE_API_KEY.
API doc: https://www.zoomeye.org/doc
Endpoint: GET https://api.zoomeye.org/host/search?query=<q>
"""

from __future__ import annotations

import json
import os
import urllib.parse
import urllib.request

from .base import Collector, CollectorRequest, CollectorResult


class ZoomEyeCollector(Collector):
    name = "zoomeye"
    requires_auth = True
    auth_env_keys = ("ZOOMEYE_API_KEY",)

    BASE_URL = "https://api.zoomeye.org/host/search"

    def _build_query(self, request: CollectorRequest) -> str:
        terms: list[str] = []
        if request.product:
            terms.append(f'app:"{request.product}"')
        if request.ports:
            terms.append(f"port:{request.ports[0]}")
        return " ".join(terms) or request.taxonomy_code

    def search(self, request: CollectorRequest) -> list[CollectorResult]:
        api_key = os.environ.get("ZOOMEYE_API_KEY", "")
        if not api_key:
            return [CollectorResult(source=self.name, host="", error="ZOOMEYE_API_KEY missing")]

        params = {"query": self._build_query(request), "page": "1"}
        url = f"{self.BASE_URL}?{urllib.parse.urlencode(params)}"
        req = urllib.request.Request(url, headers={
            "API-KEY": api_key,
            "Accept": "application/json",
        })

        try:
            with urllib.request.urlopen(req, timeout=25) as resp:
                if resp.status != 200:
                    return [CollectorResult(
                        source=self.name, host="",
                        error=f"HTTP {resp.status} from ZoomEye")]
                data = json.loads(resp.read())
        except Exception as exc:
            return [CollectorResult(source=self.name, host="", error=str(exc))]

        results: list[CollectorResult] = []
        for match in data.get("matches", [])[: request.max_hosts]:
            ip = str(match.get("ip", ""))
            port = int(match.get("portinfo", {}).get("port", 0) or 0)
            banner = str(match.get("portinfo", {}).get("banner", "")) or None
            headers_map = match.get("portinfo", {}).get("headers") or {}
            results.append(CollectorResult(
                source=self.name,
                host=ip,
                port=port,
                capture_url=f"zoomeye:{ip}:{port}",
                http_status=0,
                headers=headers_map if isinstance(headers_map, dict) else {},
                body=b"",
                banner=banner,
                raw_record=match,
            ))
        return results
