"""HTTP verification helpers for capture URL provenance.

Provides curl-based Server header analysis and a disk-backed cache so
repeated runs do not re-fetch the same hosts.
"""

import json
import re
import subprocess
import time
from datetime import datetime, timezone
from pathlib import Path

HTTP_TIMEOUT_SEC = 8
HTTP_DELAY_SEC = 0.5
HTTP_VERIFICATION_MAX_REDIRECTS = 3

_CDN_SIGNATURES = [
    "cloudflare",
    "varnish",
    "github.com",
    "fastly",
    "vercel",
    "akamai",
    "netlify",
    "amazons3",
    "amazonaws",
    "pantheon",
    "ghs.googlehosted",
    "cowboy",
    "openresty edge",
]

_GENERIC_SERVER_MAP = {
    "nginx": "nginx",
    "apache": "apache",
    "iis": "microsoft",
    "openresty": "openresty",
}


def load_http_cache(cache_path: Path) -> dict:
    """Load the persistent HTTP verification cache from disk."""
    if cache_path.exists():
        try:
            return json.loads(cache_path.read_text(encoding="utf-8"))
        except Exception:
            return {}
    return {}


def save_http_cache(cache: dict, cache_path: Path) -> None:
    """Flush the HTTP verification cache to disk."""
    cache_path.parent.mkdir(parents=True, exist_ok=True)
    cache_path.write_text(
        json.dumps(cache, indent=2, sort_keys=True), encoding="utf-8"
    )


def fetch_server_header(url: str) -> tuple:
    """Issue a HEAD request and return (server_header_lower, http_status).

    Returns (None, 0) on network error or timeout.
    """
    if not url:
        return None, 0
    try:
        result = subprocess.run(
            [
                "curl", "-sI", "-L",
                "--max-redirs", str(HTTP_VERIFICATION_MAX_REDIRECTS),
                "--max-time", str(HTTP_TIMEOUT_SEC),
                url,
            ],
            capture_output=True,
            text=True,
            timeout=HTTP_TIMEOUT_SEC + 2,
        )
        if result.returncode != 0:
            return None, 0
        out = result.stdout
        status = 0
        m = re.search(r"^HTTP/[\d.]+ (\d+)", out, re.MULTILINE)
        if m:
            status = int(m.group(1))
        srv = None
        m = re.search(r"^Server:\s*(.+)$", out, re.IGNORECASE | re.MULTILINE)
        if m:
            srv = m.group(1).strip().lower()
        return srv, status
    except (subprocess.TimeoutExpired, FileNotFoundError, Exception):
        return None, 0


def verify_vendor_self_host(rule_id: str, vendor_website: str, cache: dict) -> tuple:
    """Classify a vendor URL based on its Server response header.

    Returns (verdict, server_header, http_status).

    Verdicts:
        vendor_self_host      -- Server header contains the rule_id slug
        SUSPECT_MARKETING     -- CDN/PaaS hosting or generic server
        UNREACHABLE           -- HTTP error or connection timeout
        INDETERMINATE         -- Server header present but inconclusive
    """
    if not vendor_website:
        return "INDETERMINATE", None, 0

    cache_key = vendor_website.lower().rstrip("/")
    if cache_key in cache:
        cached = cache[cache_key]
        return (
            cached.get("verdict", "INDETERMINATE"),
            cached.get("server"),
            cached.get("status", 0),
        )

    server, status = fetch_server_header(vendor_website)
    time.sleep(HTTP_DELAY_SEC)

    if status == 0 or status >= 500:
        verdict = "UNREACHABLE"
    elif server is None:
        verdict = "INDETERMINATE"
    else:
        rule_slug = rule_id.lower().replace("_", "").replace("-", "").replace(" ", "")
        srv_slug = server.lower().replace("_", "").replace("-", "").replace(" ", "")

        if rule_slug and rule_slug in srv_slug:
            verdict = "vendor_self_host"
        elif any(cdn in server.lower() for cdn in _CDN_SIGNATURES):
            verdict = "SUSPECT_MARKETING"
        elif server.lower() in _GENERIC_SERVER_MAP:
            expected = _GENERIC_SERVER_MAP[server.lower()]
            verdict = "vendor_self_host" if expected in rule_slug else "SUSPECT_MARKETING"
        else:
            verdict = "INDETERMINATE"

    cache[cache_key] = {
        "verdict": verdict,
        "server": server,
        "status": status,
        "checked_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
    }
    return verdict, server, status
