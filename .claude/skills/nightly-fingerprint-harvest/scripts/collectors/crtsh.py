"""crt.sh collector. No auth, no hard quota.

Use case: discover hosts that present a TLS cert mentioning the product
vendor. Returns hostnames (no body/banner). Orchestrator must invoke a
live HTTP fetch separately if it wants to capture a payload.

Endpoint: GET https://crt.sh/?q=<vendor>&output=json
"""

from __future__ import annotations

import json
import re
import urllib.parse
import urllib.request

from .base import Collector, CollectorRequest, CollectorResult

# A crt.sh name_value line can be a SAN dNSName (a real host) OR a certificate
# CN that is an organization string ("AFP Confia S.A."), an email, or a bare
# wildcard. Only real DNS hostnames are fetchable; everything else produces an
# invalid URL ("https://AFP Confia S.A./" -> http_status 0). Validate before
# emitting so the orchestrator never tries to fetch a non-host.
_HOSTNAME_RE = re.compile(
    r"^(?=.{1,253}$)(?!-)[A-Za-z0-9-]{1,63}(?<!-)(?:\.(?!-)[A-Za-z0-9-]{1,63}(?<!-))+$"
)


def _valid_hostname(host: str) -> bool:
    if not host or " " in host or "@" in host or "*" in host or "_" in host:
        return False
    if host.endswith("."):
        host = host[:-1]
    return bool(_HOSTNAME_RE.match(host))


# Sandbox / preview-deploy suffixes: the host is ephemeral (per-branch, per-PR)
# and almost never the canonical product deployment. Capturing them wastes a
# fetch and pollutes evidence with throwaway DNS that frequently fails.
_EPHEMERAL_SUFFIXES = (
    ".code.run", ".repl.co", ".replit.dev", ".ngrok.io", ".ngrok-free.app",
    ".vercel.app", ".netlify.app", ".pages.dev", ".workers.dev", ".onrender.com",
    ".sawa.rocks",
)


def _is_ephemeral(host: str) -> bool:
    if host.endswith(_EPHEMERAL_SUFFIXES):
        return True
    # A label containing '--' is a preview/branch hash (e.g.
    # 'devvvv-jira--k59c8gpxtg52'); keep punycode IDN labels ('xn--...').
    for label in host.split("."):
        if "--" in label and not label.startswith("xn--"):
            return True
    return False


def _pick_seed(request: CollectorRequest) -> str:
    """Pick the most specific cert search seed. vendor/product are precise;
    the query_seed fallback (rule_id-as-words) is noisy, so require >=4 chars
    there to avoid ambiguous short-token substring matches on crt.sh."""
    for cand in (request.vendor, request.product):
        c = (cand or "").strip()
        if len(c) >= 3:
            return c
    qs = (request.query_seed or "").strip()
    return qs if len(qs) >= 4 else ""


class CrtShCollector(Collector):
    name = "crtsh"
    requires_auth = False

    BASE_URL = "https://crt.sh/"

    def search(self, request: CollectorRequest) -> list[CollectorResult]:
        seed = _pick_seed(request)
        if not seed:
            return [CollectorResult(source=self.name, host="",
                                    error="vendor/product seed too short for cert search")]
        # exclude=expired drops dead certs whose hosts no longer resolve.
        params = {"q": seed, "output": "json", "exclude": "expired"}
        url = f"{self.BASE_URL}?{urllib.parse.urlencode(params)}"
        req = urllib.request.Request(url, headers={
            "User-Agent": "LIA-SEC liaprobe-harvest/1.0",
            "Accept": "application/json",
        })

        try:
            with urllib.request.urlopen(req, timeout=30) as resp:
                if resp.status != 200:
                    return [CollectorResult(source=self.name, host="",
                                            error=f"HTTP {resp.status} from crt.sh")]
                raw = resp.read()
        except Exception as exc:
            return [CollectorResult(source=self.name, host="", error=str(exc))]

        try:
            entries = json.loads(raw)
        except json.JSONDecodeError:
            return [CollectorResult(source=self.name, host="",
                                    error="crt.sh returned non-JSON payload")]

        seen: set[str] = set()
        results: list[CollectorResult] = []
        for entry in entries:
            name_val = (entry.get("name_value") or "").strip()
            for hostname in name_val.split("\n"):
                hostname = hostname.strip().lstrip("*.").lower()
                if not hostname or hostname in seen:
                    continue
                if not _valid_hostname(hostname):
                    continue
                if _is_ephemeral(hostname):
                    continue
                seen.add(hostname)
                results.append(CollectorResult(
                    source=self.name,
                    host=hostname,
                    port=443,
                    capture_url=f"https://{hostname}/",
                    http_status=0,
                    headers={},
                    body=b"",
                    banner=None,
                    raw_record=entry,
                ))
                if len(results) >= request.max_hosts:
                    return results
        return results
