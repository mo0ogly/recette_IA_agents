"""PublicWWW collector. Free tier: 50 queries/day via web UI (HTML scrape).

PublicWWW exposes a paid REST API; the free path is the public HTML
results page at https://publicwww.com/websites/<query>/.

We do a polite single-page fetch + naive HTML parse to extract host
listings. No JS execution. Quota tracker is responsible for the daily cap.
"""

from __future__ import annotations

import re
import urllib.parse
import urllib.request

from .base import Collector, CollectorRequest, CollectorResult


class PublicWwwCollector(Collector):
    name = "publicwww"
    requires_auth = False

    BASE_URL = "https://publicwww.com/websites/"
    HOST_PATTERN = re.compile(
        r'<a[^>]+href="https?://([^"/]+)/?"[^>]*class="extlink"',
        re.IGNORECASE,
    )

    def _build_query(self, request: CollectorRequest) -> str:
        # PublicWWW expects raw HTML / JS fragments. Prefer a literal
        # needle (extracted from the rule's regex/contains matchers).
        if request.literal_needles:
            return request.literal_needles[0]
        return request.product or request.taxonomy_code or request.query_seed

    def search(self, request: CollectorRequest) -> list[CollectorResult]:
        needle = self._build_query(request)
        if not needle:
            return [CollectorResult(source=self.name, host="",
                                    error="empty needle for publicwww search")]
        encoded = urllib.parse.quote(needle, safe="")
        url = f"{self.BASE_URL}{encoded}/"
        req = urllib.request.Request(url, headers={
            "User-Agent": "Mozilla/5.0 LIA-SEC liaprobe-harvest/1.0",
            "Accept": "text/html",
        })

        try:
            with urllib.request.urlopen(req, timeout=20) as resp:
                if resp.status != 200:
                    return [CollectorResult(source=self.name, host="",
                                            error=f"HTTP {resp.status} from publicwww")]
                html = resp.read().decode("utf-8", errors="replace")
        except Exception as exc:
            return [CollectorResult(source=self.name, host="", error=str(exc))]

        seen: set[str] = set()
        results: list[CollectorResult] = []
        for match in self.HOST_PATTERN.finditer(html):
            host = match.group(1).strip().lower()
            if not host or host in seen:
                continue
            seen.add(host)
            results.append(CollectorResult(
                source=self.name,
                host=host,
                port=443,
                capture_url=f"https://{host}/",
                http_status=0,
                headers={},
                body=b"",
                banner=None,
                raw_record={"needle": needle},
            ))
            if len(results) >= request.max_hosts:
                break
        return results
