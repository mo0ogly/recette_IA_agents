"""Rapid7 Open Data Sonar offline collector.

No quota. No live API call. Iterates a local ndjson.gz dump (one record
per line) and yields matches against the rule's product/banner pattern.

Dump must be downloaded manually beforehand from
https://opendata.rapid7.com/sonar.http/ or the scans.io archive and placed
at env var RAPID7_SONAR_PATH.

Each line shape is dataset-specific. We support the common Sonar HTTP layout:
  {"ip":"1.2.3.4","port":443,"data":"HTTP/1.1 200 OK\\r\\nServer: nginx ..."}
"""

from __future__ import annotations

import gzip
import json
import os
import re
from pathlib import Path

from .base import Collector, CollectorRequest, CollectorResult


def _split_http_response(blob: str) -> tuple[int, dict, bytes, str | None]:
    """Parse a raw HTTP response into (status, headers, body, banner)."""
    parts = blob.split("\r\n\r\n", 1)
    head = parts[0]
    body = parts[1].encode("utf-8", errors="replace") if len(parts) == 2 else b""

    lines = head.splitlines()
    status_code = 0
    headers: dict[str, str] = {}
    banner = None
    if lines:
        m = re.match(r"HTTP/\d\.\d\s+(\d{3})", lines[0])
        if m:
            status_code = int(m.group(1))
        banner = lines[0]
        for line in lines[1:]:
            if ": " in line:
                k, v = line.split(": ", 1)
                headers[k.strip()] = v.strip()
    return status_code, headers, body, banner


class Rapid7SonarCollector(Collector):
    name = "rapid7_sonar"
    requires_auth = False

    def _candidate_patterns(self, request: CollectorRequest) -> list[re.Pattern]:
        seeds = [s for s in (request.product, request.vendor) if s and len(s) >= 3]
        return [re.compile(re.escape(s), re.IGNORECASE) for s in seeds]

    def search(self, request: CollectorRequest) -> list[CollectorResult]:
        dump_path = os.environ.get("RAPID7_SONAR_PATH", "")
        if not dump_path:
            return [CollectorResult(source=self.name, host="",
                                    error="RAPID7_SONAR_PATH env var not set")]
        path = Path(dump_path)
        if not path.exists():
            return [CollectorResult(source=self.name, host="",
                                    error=f"sonar dump not found at {dump_path}")]

        patterns = self._candidate_patterns(request)
        if not patterns:
            return [CollectorResult(source=self.name, host="",
                                    error="no product/vendor seed for sonar scan")]

        results: list[CollectorResult] = []
        opener = gzip.open if path.suffix == ".gz" else open
        try:
            with opener(path, "rt", encoding="utf-8", errors="replace") as fh:
                for line in fh:
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        rec = json.loads(line)
                    except json.JSONDecodeError:
                        continue
                    blob = rec.get("data") or ""
                    if not any(p.search(blob) for p in patterns):
                        continue
                    status, headers, body, banner = _split_http_response(blob)
                    results.append(CollectorResult(
                        source=self.name,
                        host=str(rec.get("ip", "")),
                        port=int(rec.get("port", 0) or 0),
                        capture_url=f"rapid7-sonar:{rec.get('ip')}:{rec.get('port')}",
                        http_status=status,
                        headers=headers,
                        body=body,
                        banner=banner,
                        raw_record={"timestamp": rec.get("timestamp")},
                    ))
                    if len(results) >= request.max_hosts:
                        break
        except OSError as exc:
            return [CollectorResult(source=self.name, host="", error=str(exc))]
        return results
