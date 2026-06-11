#!/usr/bin/env python3
# a137b_probe.py
#
# A137b live-probe harness -- HOST-ALLOWLIST GATED (R14 enforced IN
# CODE, defence-in-depth). Consumes A137B_TARGET_MANIFEST_*.json,
# fetches each target's `website`, captures evidence (reachable /
# status / body_sha256 / final_url / a declared discriminator
# HEURISTIC) so the A135b promoter can later upgrade WEAK->STRONG
# provenance + behaviorally validate.
#
# SAFETY (the whole point -- hardened by the A137b-HARNESS adversarial
# critique 2026-05-16):
#   * --live REQUIRES --allow-hosts ; without it the tool refuses to
#     touch the network (exit 2).
#   * Redirects are NOT auto-followed. EVERY hop (initial URL, each
#     HTTP 3xx Location, each meta-refresh) is host-rechecked against
#     the allowlist BEFORE the socket is opened. A redirect/refresh to
#     a non-allowlisted host is REFUSED (CRITICAL finding A: urllib
#     default opener silently followed 30x to any host = gate bypass).
#   * Default (no --live) = PLAN mode: zero network.
#   * The opener is injectable -> the redirect/meta-refresh recheck
#     path is offline-unit-tested (it previously had ZERO coverage).
#
# The discriminator check is a declared HEURISTIC: a bounded substring
# OR a Python-`re` search (NOT RE2 -- linear-time is not guaranteed;
# the value is team-authored rule data, sliced to 200 chars). It is
# NOT the engine; authoritative rule-firing stays the Go recette
# engine fed the captured bodies (R4 -- no matcher.go reimpl here).
#
# Usage:
#   python3 a137b_probe.py --manifest M.json --allow-hosts hosts.txt
#   python3 a137b_probe.py --manifest M.json --allow-hosts a.com,b.io --live

import argparse
import hashlib
import importlib.util
import json
import re
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path
from urllib.parse import urlparse

_s = importlib.util.spec_from_file_location(
    "vva2", Path("/opt/lia-sec/dev/scripts/verify_vendor_alive_v2.py"))
_vva2 = importlib.util.module_from_spec(_s)
_s.loader.exec_module(_vva2)
absolutize = _vva2.absolutize                 # A127-fixed
NoRedirectHandler = _vva2.NoRedirectHandler   # reuse (R4)

UA = "liaprobe-a137b/1.0 (+fingerprint liveness validation)"
META_RE = re.compile(
    r'<meta[^>]+http-equiv=["\']?refresh["\']?[^>]+content=["\']?'
    r'\s*\d+\s*;\s*url=([^"\'>\s]+)', re.I)
MAX_HOPS = 5


def norm_host(h: str) -> str:
    """Lowercase, strip a single leading 'www.' and a trailing dot.
    Critique-C: 43% of manifest hosts are www.-prefixed; allowlist and
    manifest MUST normalize identically or ~half is silently skipped."""
    h = (h or "").strip().lower().rstrip(".")
    return h[4:] if h.startswith("www.") else h


def host_of(url: str) -> str:
    try:
        p = urlparse(url if "://" in url else "http://" + url)
        return norm_host(p.hostname or "")
    except ValueError:
        return ""


def load_allowlist(spec: str) -> set:
    """spec = file path (one host/line, # comments) OR comma list.
    Normalized identically to manifest hosts (norm_host)."""
    p = Path(spec)
    raw = (p.read_text().splitlines() if p.is_file()
           else spec.split(","))
    return {norm_host(x) for x in raw
            if x.strip() and not x.strip().startswith("#")}


def _default_open(req, timeout):
    return urllib.request.build_opener(NoRedirectHandler()).open(
        req, timeout=timeout)


def real_fetch(url: str, allow: set, timeout: int = 12,
                _open=_default_open) -> dict:
    """Manual hop-by-hop fetch. NEVER opens a socket to a host not in
    `allow` (defence-in-depth: the gate lives INSIDE the fetcher, on
    every hop, not only on the manifest's declared host). Returns an
    error dict, never raises (except KeyboardInterrupt/SystemExit)."""
    cur = url
    for _ in range(MAX_HOPS):
        h = host_of(cur)
        if h not in allow:
            return {"ok": False, "status": 0, "body": "", "headers": {},
                    "final_url": cur,
                    "error": f"refused_offlist_host:{h}"}
        try:
            req = urllib.request.Request(cur, headers={"User-Agent": UA})
            with _open(req, timeout) as r:
                status = getattr(r, "status", 200)
                hdrs = {k.lower(): v for k, v in r.headers.items()}
                if 300 <= status < 400:
                    loc = hdrs.get("location")
                    if not loc:
                        return {"ok": False, "status": status, "body": "",
                                "headers": hdrs, "final_url": cur,
                                "error": "3xx_no_location"}
                    cur = absolutize(cur, loc)   # re-loop -> rechecked
                    continue
                body = r.read(262144).decode("utf-8", "replace")
        except (urllib.error.URLError, ValueError, OSError,
                TimeoutError) as e:
            return {"ok": False, "status": 0, "body": "", "headers": {},
                    "final_url": cur, "error": str(e)[:160]}
        # 2xx body in hand -- check ONE meta-refresh hop (rechecked at
        # loop top after we set cur).
        m = META_RE.search(body)
        if m:
            cur = absolutize(cur, m.group(1).strip())
            continue
        return {"ok": True, "status": status, "body": body,
                "headers": hdrs, "final_url": cur}
    return {"ok": False, "status": 0, "body": "", "headers": {},
            "final_url": cur, "error": "max_hops_exceeded"}


def discriminator_present(disc: dict, resp: dict) -> bool:
    """Declared HEURISTIC (NOT the engine, NOT RE2 -- Python re, NFA).
    value is team-authored rule data sliced to 200 chars."""
    val = disc.get("value") or ""
    if not val:
        return disc.get("match_type") == "exists" and resp.get("ok")
    hay = resp.get("body", "") + "\n" + "\n".join(
        f"{k}: {v}" for k, v in resp.get("headers", {}).items())
    if disc.get("match_type") == "regex":
        try:
            return re.search(val, hay) is not None
        except re.error:
            return False
    return val.lower() in hay.lower()


def run(manifest: dict, allow: set, live: bool, rate: float,
        fetcher=real_fetch, total_budget: float = 0.0) -> dict:
    out = {"probed": 0, "skipped_host": 0, "plan_only": 0,
           "reachable": 0, "disc_present": 0, "refused_offlist_hop": 0,
           "allow_hosts_unused": [], "results": {}}
    matched_hosts = set()
    last, start = {}, time.time()
    for key, e in manifest.get("entries", {}).items():
        host = norm_host(e.get("host", ""))
        if host not in allow:
            out["skipped_host"] += 1
            out["results"][key] = {"status": "skipped_host", "host": host}
            continue
        matched_hosts.add(host)
        if not live:
            out["plan_only"] += 1
            out["results"][key] = {"status": "would_probe",
                                   "host": host, "url": e.get("website")}
            continue
        if total_budget and (time.time() - start) > total_budget:
            out["results"][key] = {"status": "budget_exceeded"}
            continue
        if rate > 0 and host in last:
            d = rate - (time.time() - last[host])
            if d > 0:
                time.sleep(d)
        resp = fetcher(e.get("website", ""), allow)
        last[host] = time.time()
        out["probed"] += 1
        if str(resp.get("error", "")).startswith("refused_offlist_host"):
            out["refused_offlist_hop"] += 1
        dp = discriminator_present(e.get("discriminator", {}), resp)
        if resp.get("ok"):
            out["reachable"] += 1
        if dp:
            out["disc_present"] += 1
        out["results"][key] = {
            "status": "reachable" if resp.get("ok") else "unreachable",
            "http_status": resp.get("status"),
            "final_url": resp.get("final_url"),
            "body_sha256": hashlib.sha256(
                resp.get("body", "").encode()).hexdigest(),
            "discriminator_present_heuristic": dp,
            "error": resp.get("error")}
    # Critique-C: warn about allowlisted hosts that matched no target
    out["allow_hosts_unused"] = sorted(allow - matched_hosts)[:50]
    return out


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--manifest", required=True)
    ap.add_argument("--allow-hosts", default=None,
                    help="file (host/line) OR comma list, www.-normalized. "
                         "REQUIRED for --live")
    ap.add_argument("--live", action="store_true",
                    help="actually fetch (else PLAN). Requires --allow-hosts")
    ap.add_argument("--rate", type=float, default=2.0,
                    help="min seconds between requests to the same host")
    ap.add_argument("--timeout-total", type=float, default=0.0,
                    help="global wall-clock budget seconds (0=none)")
    ap.add_argument("--out", default=None)
    a = ap.parse_args()

    if a.live and not a.allow_hosts:
        print("REFUSED: --live requires --allow-hosts (R14 ROE gate). "
              "No network touched.", file=sys.stderr)
        return 2
    allow = load_allowlist(a.allow_hosts) if a.allow_hosts else set()
    manifest = json.loads(Path(a.manifest).read_text())
    res = run(manifest, allow, a.live, a.rate,
              total_budget=a.timeout_total)
    print(json.dumps({k: v for k, v in res.items()
                      if k != "results"}, indent=2))
    if a.out:
        Path(a.out).write_text(
            json.dumps(res, indent=2, ensure_ascii=False))
        print(f"detail: {a.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
