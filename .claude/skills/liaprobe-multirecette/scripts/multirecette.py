#!/usr/bin/env python3
"""Multi-source recette of a LiaProbe fingerprint rule.

Validates ONE rule against several independent evidence sources at once and
reports a consolidated verdict:

  OFFLINE  match the rule's matchers against real Onyphe banner corpora
           (no network) -> corroboration count + per-matcher hits.
  LIVE     fetch real host URL(s) (user-provided / dork-discovered), capture
           status+headers+body, reconstruct the engine targets (header values
           vs body), score = base_confidence + sum(fired matcher deltas),
           verdict DETECT/MISS vs confidence_threshold, sha256 the capture.
  SUGGEST  scan captured headers for a product/vendor token the rule does NOT
           already key on (e.g. an `X-Jenkins` header the rule ignores) and
           propose a high-signal matcher. Detection-content advice only -- it
           does NOT edit matchers (R4: matcher edits go through the
           fingerprint-rebuild recette-onyphe gate).

  --apply  (evidence injection, R4-safe) ONLY when a LIVE host scored >=
           threshold: set _lia_independent_authoring.http_gate.verified=true
           and add a capture artifact (capture_url, html_sha256, headers_sha256,
           capture_date). NEVER fabricated: a MISS refuses --apply and explains.

Pure stdlib (urllib). Read-only unless --apply.
"""
import argparse
import hashlib
import json
import os
import re
import ssl
import sys
import urllib.request
import urllib.error
from datetime import datetime, timezone

# dev root = five levels up from this file (.../dev/.claude/skills/liaprobe-multirecette/scripts/x.py)
_DEV_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(
    os.path.dirname(os.path.abspath(__file__))))))
sys.path.insert(0, os.path.join(
    _DEV_ROOT, "_alire", "tracking", "liaprobe-legal-provenance", "tooling"))
try:
    from onyphe_match import (load_matchers, split_banner, target_text,
                              banners, parse_headers, matcher_fires)
except Exception:  # pragma: no cover - fallback if path differs
    load_matchers = split_banner = target_text = banners = None
    parse_headers = matcher_fires = None


WORKROOT = os.path.join(_DEV_ROOT, "_alire", "tracking", "liaprobe-multirecette",
                        "rules")
# Durable, multi-session store for USER contributions (marker models). A single
# contribution doc may cover MANY rules (e.g. a multi-CMS empreinte/CVE corpus),
# so contributions live in a shared store and are BOUND to rule ids via a
# manifest. Every multirecette run auto-loads the contributions bound to the
# current rule -> the user's markers persist across sessions and frame the audit.
CONTRIB_ROOT = os.path.join(_DEV_ROOT, "_alire", "tracking",
                            "liaprobe-multirecette", "contributions")
CONTRIB_MANIFEST = os.path.join(CONTRIB_ROOT, "manifest.json")


def workdir_for(rule: dict, rule_path: str) -> str:
    """Per-rule durable working directory (NEVER _alire/temp). Holds the OODA
    PLAN, the multi-session SESSION journal, verdicts, captures, recette runs.
    Resolved from the rule id so every session for the same rule converges on
    one directory -> multi-session resume."""
    rid = str(rule.get("id") or os.path.splitext(os.path.basename(rule_path))[0])
    rid = re.sub(r"[^A-Za-z0-9._-]", "_", rid)
    d = os.path.join(WORKROOT, rid)
    os.makedirs(os.path.join(d, "captures"), exist_ok=True)
    os.makedirs(os.path.join(d, "recette"), exist_ok=True)
    return d


# Recette status ladder -- mirrors tooling/rule_recette_status.py so the rule
# JSON stamp is the authoritative source the ledger reads first.
_RECETTE_LEVEL_ORDER = {"NONE": 0, "DOCUMENTED": 1, "LIVE_VERIFIED": 2}


def stamp_recette_level(rule: dict, rule_path: str, verdict: dict, workdir: str) -> str | None:
    """Write the recette status INTO the rule JSON so the level is visible in the
    rule itself, not only in the tracking dir. Leak-safe: the stamp carries the
    level + UTC timestamp + tool + a dev-private evidence_ref (the per-rule
    workdir relpath) -- NEVER a third-party host, IP, or body. Never downgrades
    an already-stamped higher level. Returns the written level, or None if the
    run produced no durable evidence (level NONE) or would downgrade.
    """
    # A durable verdict is always written by this run, so the rule is at least
    # DOCUMENTED (matches the ledger derive: any verdict -> DOCUMENTED). A live
    # DETECT lifts it to LIVE_VERIFIED.
    live = verdict.get("live") or []
    level = "LIVE_VERIFIED" if any(r.get("detected") for r in live) else "DOCUMENTED"

    # Evidence block (sha256) -- the PROOF, written into the rule (not only the
    # tracking dir). Two verdict shapes carry it: the detected live[] entry
    # (html_sha256 + headers_sha256 + favicon.sha256) and/or the top-level
    # evidence block (body_hashes/headers_hashes). Prefer the detected entry.
    detected = next((r for r in live if isinstance(r, dict) and r.get("detected")),
                    live[0] if live else {})
    top = verdict.get("evidence") or {}
    body = (detected.get("html_sha256")
            or (top.get("body_hashes") or {}).get("sha256"))
    headers = (detected.get("headers_sha256")
               or (top.get("headers_hashes") or {}).get("sha256"))
    fav = detected.get("favicon") if isinstance(detected.get("favicon"), dict) else top.get("favicon")
    favicon = fav.get("sha256") if isinstance(fav, dict) else None
    evidence = None
    if body or headers or favicon:
        evidence = {"body_sha256": body, "headers_sha256": headers,
                    "favicon_sha256": favicon}

    # GATE (no level claim without proof): a LIVE_VERIFIED stamp REQUIRES a
    # signed evidence hash block. A live DETECT with no captured hash cannot
    # claim LIVE_VERIFIED -- demote to DOCUMENTED rather than lie (R18/R26).
    if level == "LIVE_VERIFIED" and evidence is None:
        level = "DOCUMENTED"

    lia = rule.get("_lia_independent_authoring")
    if not isinstance(lia, dict):
        lia = {}
        rule["_lia_independent_authoring"] = lia
    cur = lia.get("recette") if isinstance(lia.get("recette"), dict) else {}
    cur_level = cur.get("level", "NONE")
    if _RECETTE_LEVEL_ORDER.get(level, 0) < _RECETTE_LEVEL_ORDER.get(cur_level, 0):
        return None  # never downgrade

    recette = {
        "level": level,
        "verified_at": datetime.now(timezone.utc).isoformat(),
        "tool": "multirecette",
        # dev-private tracking path (NOT a host) -- where the proof lives.
        "evidence_ref": os.path.relpath(workdir, _DEV_ROOT),
    }
    if evidence is not None:
        recette["evidence"] = evidence
    # version (from the live capture) -> stamp it so version->CPE->CVE is durable
    vblock = verdict.get("version") if isinstance(verdict.get("version"), dict) else {}
    vstr = vblock.get("version")
    if vstr:
        recette["version"] = vstr
        if vblock.get("candidates"):
            recette["version_via"] = vblock["candidates"][0].get("via")
    lia["recette"] = recette
    tmp = rule_path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as fh:
        json.dump(rule, fh, indent=2, ensure_ascii=False)
        fh.write("\n")
    os.replace(tmp, rule_path)
    return level


def append_session(workdir: str, verdict: dict) -> None:
    """Append a multi-session journal entry (resumable state for the rule)."""
    path = os.path.join(workdir, "SESSION.md")
    live = verdict.get("live") or []
    det = [r for r in live if r.get("detected")]
    miss = [r for r in live if r.get("ok") and not r.get("detected")]
    ver = (verdict.get("version") or {}).get("version")
    cve = verdict.get("cve") or {}
    lines = [
        f"\n## {verdict.get('generated_at')}",
        f"- rule: {verdict.get('rule')} (matchers={verdict.get('matchers')})",
    ]
    contribs = verdict.get("contributions") or []
    if contribs:
        names = ", ".join(
            (c.get("doc") or "?") + (f"#{c['section']}" if c.get("section") else "")
            for c in contribs)
        lines.append(f"- contribution(s): {len(contribs)} ({names})")
    for r in verdict.get("offline", []):
        lines.append(f"- offline {r['corpus']}: {r['matched']}/{r['scanned']} ({r['rate_pct']}%)")
    for r in live:
        if r.get("ok"):
            tag = "DETECT" if r.get("detected") else "MISS"
            lines.append(f"- live {r['url']} -> {tag} score={r.get('score')}/{r.get('threshold')}")
    if ver:
        lines.append(f"- version: {ver}")
    if cve.get("ok"):
        lines.append(f"- cve: {cve['count']} ({cve['kev_count']} KEV) [{'exact' if cve.get('version_pinned') else 'product'}]")
    if verdict.get("suggestions"):
        lines.append(f"- suggestions: {len(verdict['suggestions'])} missing high-signal header(s)")
    if verdict.get("discovery_dorks"):
        lines.append(f"- discovery_dorks: {verdict['discovery_dorks']} (passive)")
    ev = verdict.get("evidence") or {}
    if ev.get("body_hashes"):
        bh = ev["body_hashes"]
        lines.append(f"- hashes: body sha256={bh['sha256'][:16]} md5={bh['md5'][:12]}")
    fav = ev.get("favicon") or {}
    if fav.get("ok"):
        lines.append(f"- favicon: sha256={fav['sha256'][:16]} md5={fav['md5'][:12]} mmh3={fav.get('mmh3')}")
    eg = verdict.get("engine_test") or {}
    if eg.get("ok"):
        d = eg.get("delta") or {}
        verdict_str = "REGRESSION" if eg.get("regression") else "zero-regression"
        lines.append(f"- engine-gate: {verdict_str} "
                     f"(CORRECT {d.get('CORRECT', 0):+d} WRONG {d.get('WRONG', 0):+d} "
                     f"MISS {d.get('MISS', 0):+d})")
    if verdict.get("todo"):
        lines.append(f"- todo: {len(verdict['todo'])} audit gap(s) (see TODO.md)")
    evo = verdict.get("evolve")
    if evo:
        d = evo.get("delta")
        if d:
            lines.append(f"- evolve: {evo.get('status', '?')} "
                         f"(CORRECT {d['CORRECT']:+d} WRONG {d['WRONG']:+d} MISS {d['MISS']:+d})")
        else:
            lines.append(f"- evolve: {evo.get('status', '?')}")
    lines.append(f"- next: {'capture evidence (--apply)' if det else ('fix coverage then re-run' if miss else 'corroborate on a live host')}")
    header = "" if os.path.exists(path) else f"# Multirecette SESSION journal -- {verdict.get('rule')}\n\nMulti-session resumable state. Newest entries at the bottom.\n"
    with open(path, "a", encoding="utf-8") as fh:
        if header:
            fh.write(header)
        fh.write("\n".join(lines) + "\n")


def _load_manifest() -> dict:
    """Read the contributions manifest (bindings + ingested docs). Tolerant of
    a missing/corrupt file -> empty manifest."""
    try:
        with open(CONTRIB_MANIFEST, encoding="utf-8") as fh:
            m = json.load(fh)
        if isinstance(m, dict):
            m.setdefault("docs", {})
            m.setdefault("bindings", [])
            return m
    except Exception:  # noqa: BLE001
        pass
    return {"docs": {}, "bindings": []}


def _save_manifest(m: dict) -> None:
    os.makedirs(CONTRIB_ROOT, exist_ok=True)
    tmp = CONTRIB_MANIFEST + ".tmp"
    with open(tmp, "w", encoding="utf-8") as fh:
        json.dump(m, fh, indent=2, ensure_ascii=False)
        fh.write("\n")
    os.replace(tmp, CONTRIB_MANIFEST)


def ingest_contribution(src_path: str, rule_id: str, section: str | None) -> dict:
    """Persist a USER contribution doc (the marker model) into the durable
    contributions store and BIND it to rule_id (optionally to a named section
    of a multi-CMS doc). Idempotent: re-ingesting the same content + same
    binding does not duplicate. Returns the binding record.

    The raw doc is copied verbatim into CONTRIB_ROOT (sha-stamped name) so the
    contribution survives even if the original source path vanishes (the
    durable-work-in-temp loss class the user flagged)."""
    if not os.path.isfile(src_path):
        raise FileNotFoundError(src_path)
    with open(src_path, "rb") as fh:
        data = fh.read()
    sha = hashlib.sha256(data).hexdigest()
    base = re.sub(r"[^A-Za-z0-9._-]", "_", os.path.basename(src_path))
    os.makedirs(CONTRIB_ROOT, exist_ok=True)
    stored_name = base
    stored_path = os.path.join(CONTRIB_ROOT, stored_name)
    # If a different file already owns this name, disambiguate with the sha.
    if os.path.isfile(stored_path):
        with open(stored_path, "rb") as fh:
            if hashlib.sha256(fh.read()).hexdigest() != sha:
                root, ext = os.path.splitext(base)
                stored_name = f"{root}_{sha[:8]}{ext}"
                stored_path = os.path.join(CONTRIB_ROOT, stored_name)
    if not os.path.isfile(stored_path):
        with open(stored_path, "wb") as fh:
            fh.write(data)
    m = _load_manifest()
    m["docs"][stored_name] = {
        "sha256": sha,
        "ingested_at": datetime.now(timezone.utc).isoformat(),
        "source": os.path.relpath(src_path, _DEV_ROOT)
        if src_path.startswith(_DEV_ROOT) else src_path,
    }
    binding = {"rule_id": rule_id, "doc": stored_name, "section": section,
               "sha256": sha, "bound_at": datetime.now(timezone.utc).isoformat()}
    exists = any(b.get("rule_id") == rule_id and b.get("doc") == stored_name
                 and b.get("section") == section for b in m["bindings"])
    if not exists:
        m["bindings"].append(binding)
    _save_manifest(m)
    return binding


def load_contributions(rule_id: str) -> list:
    """Return the contributions BOUND to rule_id (multi-session marker model).
    Each item: {doc, section, sha256, path, present}. The audit reads these on
    EVERY run so the user's contribution always frames the recette."""
    m = _load_manifest()
    out = []
    for b in m["bindings"]:
        if b.get("rule_id") != rule_id:
            continue
        doc = b.get("doc")
        path = os.path.join(CONTRIB_ROOT, doc) if doc else None
        out.append({
            "doc": doc,
            "section": b.get("section"),
            "sha256": b.get("sha256"),
            "path": os.path.relpath(path, _DEV_ROOT) if path else None,
            "present": bool(path and os.path.isfile(path)),
        })
    return out


def fetch(url: str, timeout: int = 15) -> dict:
    ctx = ssl.create_default_context()
    ctx.check_hostname = False
    ctx.verify_mode = ssl.CERT_NONE
    # Browser-like headers: many CMS sites (AEM/dispatcher, WAFs) serve a stub
    # page to a non-browser UA, which strips the structural fingerprint markers.
    req = urllib.request.Request(url, headers={
        "User-Agent": ("Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
                       "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"),
        "Accept": ("text/html,application/xhtml+xml,application/xml;q=0.9,"
                   "image/avif,image/webp,*/*;q=0.8"),
        "Accept-Language": "en-US,en;q=0.9",
    })
    try:
        with urllib.request.urlopen(req, timeout=timeout, context=ctx) as resp:
            raw = resp.read()
            status = resp.status
            # urllib preserves header case; keep it (faithful wire format).
            hdrs = "".join(f"{k}: {v}\n" for k, v in resp.headers.items())
            body = raw.decode("utf-8", errors="replace")
            reason = getattr(resp, "reason", "") or ""
            status_line = f"HTTP/1.1 {status} {reason}".rstrip() if status else ""
            return {"ok": True, "status": status, "headers": hdrs, "body": body,
                    "status_line": status_line, "engine": "urllib"}
    except urllib.error.HTTPError as he:  # noqa: PERF203
        # A 4xx/5xx is NOT a fetch failure -- the response still carries
        # fingerprint signals. ci.jenkins.io returns 403 WITH X-Jenkins;
        # gitlab.com returns 403 WITH GitLab markers; many WAF-fronted
        # instances answer 401/403 yet leak a product header/body. Read the
        # error response as a real banner (it is a valid HTTP response object).
        try:
            raw = he.read()
        except Exception:  # noqa: BLE001
            raw = b""
        status = getattr(he, "code", 0) or 0
        hdrs = "".join(f"{k}: {v}\n" for k, v in (he.headers or {}).items())
        body = raw.decode("utf-8", errors="replace")
        reason = getattr(he, "reason", "") or ""
        status_line = f"HTTP/1.1 {status} {reason}".rstrip() if status else ""
        return {"ok": True, "status": status, "headers": hdrs, "body": body,
                "status_line": status_line, "engine": "urllib", "http_error": True}
    except Exception as exc:  # noqa: BLE001
        return {"ok": False, "error": str(exc)}


# Anti-bot stealth fetch backend (Scrapling StealthyFetcher) lives in a separate
# pipx venv; we subprocess it. Path is resolved at call time (no hard dependency
# when --stealth is not used).
_SCRAPLING_VENV_PY = os.path.expanduser(
    "~/.local/share/pipx/venvs/scrapling/bin/python")
_STEALTH_FETCH = os.path.join(
    _DEV_ROOT, "_alire", "tracking", "liaprobe-multirecette",
    "tooling", "stealth_fetch.py")


def stealth_fetch(url: str, timeout: int = 120) -> dict:
    """Live fetch through the stealth browser engine (Cloudflare-solving), for
    WAF-protected hosts that 403 the default urllib fetch. Returns the same
    shape as fetch(): {ok, status, headers (k: v\\n string), body}. GET-only."""
    import subprocess
    if not os.path.exists(_SCRAPLING_VENV_PY):
        return {"ok": False, "error": "scrapling venv not found "
                f"({_SCRAPLING_VENV_PY}) -- pipx install scrapling && scrapling install"}
    try:
        proc = subprocess.run(
            [_SCRAPLING_VENV_PY, _STEALTH_FETCH, url,
             "--timeout-ms", str(timeout * 1000)],
            capture_output=True, text=True, timeout=timeout + 60)
    except Exception as exc:  # noqa: BLE001
        return {"ok": False, "error": f"stealth subprocess: {exc}"}
    if not proc.stdout.strip():
        return {"ok": False, "error": "stealth fetch: empty output "
                f"(stderr: {proc.stderr.strip()[:200]})"}
    try:
        d = json.loads(proc.stdout.strip().splitlines()[-1])
    except Exception as exc:  # noqa: BLE001
        return {"ok": False, "error": f"stealth fetch parse: {exc}"}
    if not d.get("ok"):
        return {"ok": False, "error": d.get("error", "stealth fetch failed")}
    hdrs = "".join(f"{k}: {v}\n" for k, v in (d.get("headers") or {}).items())
    return {"ok": True, "status": d.get("status", 0), "headers": hdrs,
            "body": d.get("body", ""), "engine": "scrapling-stealth",
            "status_line": d.get("status_line", "")}


def multi_hash(data) -> dict:
    """sha256 + md5 of a payload (str or bytes). Multi-algo evidence hashing so
    a capture is comparable across tools (sha256 canonical, md5 legacy/cross-ref).
    favicon adds mmh3 separately (Shodan-style)."""
    if isinstance(data, str):
        data = data.encode("utf-8", "replace")
    data = data or b""
    return {"sha256": hashlib.sha256(data).hexdigest(),
            "md5": hashlib.md5(data).hexdigest(),  # noqa: S324 (evidence, not security)
            "bytes": len(data)}


def fetch_favicon(base_url: str, stealth: bool = False) -> dict:
    """Fetch <origin>/favicon.ico (static, GET-only) and hash it sha256+md5+mmh3
    (the favicon hash is a strong, theme-stable fingerprint signal). urllib by
    default (static assets are rarely WAF-challenged); the page itself may have
    needed --stealth but the favicon usually does not."""
    from urllib.parse import urlsplit
    p = urlsplit(base_url)
    if not p.scheme or not p.netloc:
        return {"ok": False, "error": "bad base url"}
    fav = f"{p.scheme}://{p.netloc}/favicon.ico"
    raw = b""
    status = 0
    try:
        ctx = ssl.create_default_context()
        ctx.check_hostname = False
        ctx.verify_mode = ssl.CERT_NONE
        req = urllib.request.Request(fav, headers={
            "User-Agent": ("Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
                           "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36")})
        with urllib.request.urlopen(req, timeout=20, context=ctx) as resp:
            raw = resp.read()
            status = resp.status
    except Exception as exc:  # noqa: BLE001
        return {"ok": False, "url": fav, "error": str(exc)}
    h = multi_hash(raw)
    out = {"ok": True, "url": fav, "status": status, "bytes": h["bytes"],
           "sha256": h["sha256"], "md5": h["md5"]}
    try:
        import base64
        import mmh3
        out["mmh3"] = mmh3.hash(base64.encodebytes(raw))
    except Exception:  # noqa: BLE001
        out["mmh3"] = None
    return out


def build_todo(rule: dict, verdict: dict) -> list:
    """Per-rule audit gaps -> a TODO list so nothing is silently skipped.
    User directive 2026-05-30: hashes + favicon + VERSION + CVE + final engine
    test are mandatory per rule; whatever is missing becomes an explicit TODO."""
    todo = []
    live = verdict.get("live") or []
    detected = any(r.get("detected") for r in live)
    if live and not detected:
        todo.append("LIVE MISS: rule did not reach threshold on a live host -- "
                    "fix matcher coverage (gate via recette-onyphe) or capture a "
                    "host that exposes the signal.")
    ver = (verdict.get("version") or {}).get("version")
    if live and not ver:
        todo.append("VERSION not extracted on the live host -- the version is "
                    "hidden or the rule lacks a version matcher; capture a host "
                    "that exposes the build/version, or add a version probe.")
    cve = verdict.get("cve") or {}
    if not cve.get("ok") or not cve.get("count"):
        todo.append("CVE not correlated -- the rule has no usable cpe23_template "
                    "or the product is absent from PostgreSQL; set the real "
                    "product cpe and re-run --cve.")
    ev = verdict.get("evidence") or {}
    if not ev.get("favicon", {}).get("ok"):
        todo.append("FAVICON hash missing -- fetch <origin>/favicon.ico and "
                    "record sha256+md5+mmh3 as a theme-stable signal.")
    et = verdict.get("engine_test") or {}
    if not et.get("ok"):
        todo.append("FINAL ENGINE TEST not run -- run --engine-gate (recette-onyphe "
                    "-http-layer BEFORE/AFTER) to confirm zero regression before "
                    "any commit.")
    elif et.get("regression"):
        todo.append("ENGINE GATE RED: the edit regressed CORRECT/WRONG/MISS -- "
                    "REVERT the matcher change and REPLAN (R4).")
    return todo


def write_todo_md(workdir: str, rule: dict, todo: list) -> str:
    """Persist the per-rule TODO so audit gaps survive across sessions."""
    path = os.path.join(workdir, "TODO.md")
    ts = datetime.now(timezone.utc).isoformat()
    head = "" if os.path.exists(path) else (
        f"# TODO -- {rule.get('id')}\n\nPer-rule audit gaps (hashes + favicon + "
        f"version + CVE + final engine test). Newest at bottom.\n")
    with open(path, "a", encoding="utf-8") as fh:
        if head:
            fh.write(head)
        fh.write(f"\n## {ts}\n")
        if todo:
            for t in todo:
                fh.write(f"- [ ] {t}\n")
        else:
            fh.write("- all mandatory evidence present (hashes, favicon, "
                     "version, CVE, engine test).\n")
    return path


def db_url() -> str:
    """Read DATABASE_URL live from the systemd unit (never cache/log it)."""
    import subprocess
    try:
        out = subprocess.run(["systemctl", "cat", "lia-backend"],
                             capture_output=True, text=True, timeout=10).stdout
        for line in out.splitlines():
            if "Environment=DATABASE_URL=" in line:
                return line.split("DATABASE_URL=", 1)[1].strip()
    except Exception:  # noqa: BLE001
        pass
    return os.environ.get("DATABASE_URL", "")


# product-token version patterns applied to header VALUES (engine-style) + body.
# Generic: "<Product> N.N(.N)" or "<slug>/N.N(.N)" or a bare semver in a versionful header.
def extract_version(rule: dict, headers: str, body: str) -> dict:
    """Extract the running product VERSION from a live capture. Honors a per-rule
    override `_lia_independent_authoring.version_extract` (regex) + `version_group`
    (int, default 1) FIRST -- the precise, R18-authored path. Otherwise a generic
    cascade: full product name then optional trailing words then a version, with
    an optional build suffix (`-NN`, e.g. Nexus 'OSS 2.15.2-03'). The first-word
    pattern was too rigid -- it missed `Nexus Repository Manager OSS 2.15.2-03`
    because 'Nexus' is followed by 'Repository', not a digit."""
    product = str(rule.get("product") or "").strip()
    hvals = "\n".join(v for _n, _s, v in
                      ((h, ":", h.split(":", 1)[1]) for h in headers.splitlines()
                       if ":" in h))
    candidates = []

    # 1) per-rule authored override (precise, R18)
    lia = rule.get("_lia_independent_authoring") or {}
    vx = lia.get("version_extract")
    vg = lia.get("version_group", 1)
    if isinstance(vx, str) and vx:
        # raw `headers` (WITH header names) FIRST so a header-anchored override
        # like `X-GitLab-Version:\s*(...)` fires (hvals strips the names).
        for src in (headers, hvals, body[:8000]):
            try:
                m = re.search(vx, src, re.I)
            except re.error:
                break
            if m:
                try:
                    grp = m.group(vg)
                except (IndexError, Exception):
                    grp = m.group(0)
                candidates.append({"version": grp, "via": "rule version_extract"})
                break

    # 2) generic cascade
    if not candidates:
        first = re.escape(product.split()[0]) if product else r"[A-Za-z][A-Za-z0-9_-]+"
        full = re.escape(product) if product else first
        verre = r"(\d+(?:\.\d+){1,3}(?:[._-]\d+)?)"  # N.N[.N[.N]] + optional -NN build
        pats = [
            (rf"{full}(?:\s+[A-Za-z]+){{0,3}}\s+{verre}", "full-product-name version"),
            (rf"{first}[ /]{verre}", "product-version header/body"),
            (rf"{first}\s+(?:[A-Za-z]+\s+){{0,2}}{verre}", "product ... N.N.N"),
            (r"(?i)CHANGELOG[^\n]*\n[^\n]*?(\d+\.\d+(?:\.\d+)?),\s*\d{4}", "changelog line"),
        ]
        for src in (hvals, body[:8000]):
            for pat, why in pats:
                try:
                    m = re.search(pat, src)
                except re.error:
                    continue
                if m:
                    candidates.append({"version": m.group(1), "via": why})
                    break
            if candidates:
                break

    ver = candidates[0]["version"] if candidates else None
    return {"version": ver, "candidates": candidates}


def cve_correlate(rule: dict, version: str | None, limit: int = 15) -> dict:
    """version -> CPE pattern -> cve_nvd_data + KEV (PostgreSQL). Read-only."""
    cpe = str(rule.get("cpe23_template") or "")
    if not cpe.startswith("cpe:2.3:"):
        return {"ok": False, "error": "no cpe23_template"}
    parts = cpe.split(":")
    if len(parts) < 6:
        return {"ok": False, "error": "malformed cpe23_template"}
    part, vendor, product = parts[2], parts[3], parts[4]
    # exact-version pattern when a version is known, else the whole product line
    if version:
        pattern = f"cpe:2.3:{part}:{vendor}:{product}:{version}:%"
    else:
        pattern = f"cpe:2.3:{part}:{vendor}:{product}:%"
    url = db_url()
    if not url:
        return {"ok": False, "error": "no DATABASE_URL"}
    sql = (
        "SELECT c.cve_id, c.cvss_severity, c.cvss_score, (k.cve_id IS NOT NULL) "
        "FROM cve_nvd_data c JOIN cve_product cp ON cp.cve_id=c.cve_id "
        "JOIN product p ON p.product_id=cp.product_id "
        "LEFT JOIN kev_cisa_vulnerabilities k ON k.cve_id=c.cve_id "
        "WHERE p.cpe23_uri LIKE %(pat)s AND c.cve_state NOT ILIKE 'reject%%' "
        "ORDER BY (k.cve_id IS NOT NULL) DESC, c.cvss_score DESC NULLS LAST "
        "LIMIT %(lim)s"
    )
    import subprocess
    # parameterized via psql variables to avoid injection (R7)
    q = sql.replace("%(pat)s", "'" + pattern.replace("'", "''") + "'") \
           .replace("%(lim)s", str(int(limit)))
    try:
        out = subprocess.run(["psql", url, "-tA", "-F", "|", "-c", q],
                             capture_output=True, text=True, timeout=30)
    except Exception as exc:  # noqa: BLE001
        return {"ok": False, "error": str(exc)}
    if out.returncode != 0:
        return {"ok": False, "error": out.stderr.strip()[:200]}
    rows = []
    kev = 0
    for ln in out.stdout.splitlines():
        f = ln.split("|")
        if len(f) >= 4:
            is_kev = f[3] == "t"
            kev += 1 if is_kev else 0
            rows.append({"cve_id": f[0], "severity": f[1],
                         "cvss": f[2], "kev": is_kev})
    return {"ok": True, "cpe_pattern": pattern, "version_pinned": bool(version),
            "count": len(rows), "kev_count": kev, "cves": rows}


def _is_discriminating(target: str, field: str, value: str,
                       product: str, vendor: str) -> bool:
    """A fired matcher is DISCRIMINATING (proves a real INSTANCE, not a page that
    merely MENTIONS the product) when it anchors on a structural signal rather
    than the bare product name. A header / cookie / response / banner match is
    always structural. A body match is structural only if its literal carries a
    runtime artifact (a URL / path / asset host / specific attribute), NOT just
    the product/vendor word -- a bare `body:"virtuemart"` false-fires on any
    marketplace / blog / extension-shop page that names the product (FALSE LIVE).
    Incident 2026-05-31: codecanyon + jpro.studio scored LIVE for VirtueMart on a
    bare-name body matcher; data.doremus.org/sparql (Virtuoso) and status.kuma.pet
    (Uptime Kuma) and cdn.abicart.com (Abicart) are REAL because their matcher is
    a structural artifact."""
    t = (target or "").lower()
    if t in ("header", "cookie", "response", "banner", "tls", "cert"):
        return True
    if t != "body":
        return True  # path/probe-level signal is structural
    val = (value or "").lower()
    # structural artifact tokens a mention-page would not carry verbatim
    if re.search(r"[/=]|cdn[\.-]|static[\.-]|assets?[\.-]|\.(?:com|net|io|org)/|"
                 r"wp-|data-[a-z]|x-[a-z]|__|<meta|generator|powered\s+by", val):
        return True
    # strip regex to literal words; non-discriminating if they are only the
    # product/vendor name (or substrings of it)
    lits = re.sub(r"[\\^$.?*+()\[\]{}|]", " ", val)
    words = {w for w in re.split(r"\s+", lits) if len(w) >= 3}
    names = set()
    for n in (product, vendor):
        for w in re.split(r"[^a-z0-9]+", (n or "").lower()):
            if len(w) >= 3:
                names.add(w)
    # every literal word is just (part of) the product/vendor name -> weak
    if words and all(any(w in nm or nm in w for nm in names) for w in words):
        return False
    return bool(words)  # some other specific literal -> treat as discriminating


def score_live(rule: dict, matchers, headers: str, body: str,
               status_line: str = "") -> dict:
    base = rule.get("base_confidence") or 0.0
    threshold = rule.get("confidence_threshold") or 0.0
    product = rule.get("product") or rule.get("taxonomy_name") or ""
    vendor = rule.get("vendor") or ""
    # Reconstruct a faithful wire-format response banner (G1): raw status line +
    # CRLF-joined headers + blank line + body, so a target:response matcher
    # anchored on "^HTTP/1.1 200 OK\r\n" and "\r\n"-delimited header lines can
    # fire. NOTE: the stealth engine lowercases header KEYS, so a verbose
    # response matcher that needs exact header case must be validated via the
    # urllib fetch (case-preserved) or the liaprobe AGENT active probe.
    hdr_crlf = headers.replace("\r\n", "\n").replace("\n", "\r\n")
    prefix = (status_line + "\r\n") if status_line else ""
    banner = prefix + hdr_crlf + "\r\n" + body
    hv, bdy = split_banner(banner)
    hdrs = parse_headers(banner)
    fired = []
    score = base
    has_disc = False
    for t, rx, v, cd, field in matchers:
        if matcher_fires(t, rx, field, banner, hv, bdy, hdrs):
            disc = _is_discriminating(t, field, v, product, vendor)
            fired.append({"target": t, "field": field, "value": v, "delta": cd,
                          "discriminating": disc})
            score += (cd or 0.0)
            has_disc = has_disc or disc
    # detected = score threshold (the matcher-discrimination signal is recorded in
    # `has_discriminating` for observability, but is NOT a hard LIVE gate: a real
    # self-hosted app whose page title IS the product name -- Uptime Kuma -- would
    # be a false-negative. The false-LIVE class (marketplace / aggregator pages
    # that merely MENTION the product) is filtered upstream by HOST, in
    # online_verify._keep, not here. R18: gate where the signal is reliable.)
    return {
        "base": base, "threshold": threshold, "score": round(score, 3),
        "detected": score >= threshold,
        "has_discriminating": has_disc,
        "fired": fired, "fired_count": len(fired), "total_matchers": len(matchers),
    }


def suggest(rule: dict, headers: str, matchers) -> list:
    """Propose high-signal matchers from captured headers that the rule ignores."""
    tokens = set()
    for f in (rule.get("product"), rule.get("vendor"),
              rule.get("id"), rule.get("taxonomy_code")):
        if f:
            for w in re.split(r"[^A-Za-z0-9]+", str(f).lower()):
                if len(w) >= 4:
                    tokens.add(w)
    covered = " ".join(m[2].lower() for m in matchers)
    out = []
    for hl in headers.splitlines():
        if ":" not in hl:
            continue
        name, _, val = hl.partition(":")
        name = name.strip()
        nl = name.lower()
        # a header whose NAME carries the product token is a strong fingerprint
        if any(tok in nl for tok in tokens) and nl not in covered:
            out.append({
                "header_name": name,
                "header_value_sample": val.strip()[:60],
                "why": f"header name carries product token; rule does not key on '{name}'",
                "proposed": {"target": "header_name", "match_type": "literal",
                             "value": name, "note": "verify engine supports header_name target"},
            })
    return out


LIAPROBE_ROOT = "/opt/lia-sec/liaprobe"
# Durable HTTP-banner gate corpus (3502 real HTTP responses, ground-truth labels).
# The canonical *.appgt/*.proxygt zst corpora are RAW BINARY banners and produce
# 100% NO_PATTERN under -http-layer -- they are NOT valid for web-signature evolve.
_GT_HTTP = os.path.join(
    _DEV_ROOT, "_alire", "tracking", "liaprobe-multirecette", "_gt_corpus",
    "http_appgt_3502.jsonl")


def resolve_gt_corpus(arg: str) -> str:
    """recette-onyphe -f corpus for the evolve gate. Prefers an explicit path,
    else the DURABLE HTTP corpus under tracking, else the volatile A139 subset
    in _alire/temp (last resort). Returns '' if nothing resolves."""
    if arg and os.path.isfile(arg):
        return arg
    if os.path.isfile(_GT_HTTP):
        return _GT_HTTP
    a139 = os.path.join(_DEV_ROOT, "_alire", "temp", "A139_validate.jsonl")
    return a139 if os.path.isfile(a139) else ""


def run_recette(corpus: str, root: str) -> dict:
    """Run the LiaProbe engine recette-onyphe gate over the GT corpus and parse
    the verdict counts. -http-layer is mandatory for web-signature probes."""
    import subprocess
    bin_path = os.path.join(root, "bin", "recette-onyphe")
    if not os.path.isfile(bin_path):
        return {"ok": False, "error": f"missing {bin_path}"}
    try:
        # recette-onyphe loads patterns/ relative to CWD -> must run from root.
        out = subprocess.run(
            [bin_path, "-f", corpus, "-http-layer", "-src", "all", "-out", "table"],
            cwd=root, capture_output=True, text=True, timeout=900)
    except Exception as exc:  # noqa: BLE001
        return {"ok": False, "error": str(exc)}
    if out.returncode != 0:
        return {"ok": False, "error": out.stderr.strip()[:300], "raw": out.stdout}
    counts = {"raw": out.stdout, "ok": True}
    for key in ("CORRECT", "WRONG", "MISS", "GT_MISLABEL", "NO_PATTERN"):
        m = re.search(rf"^\s*{key}\s*:\s*(\d+)", out.stdout, re.M)
        counts[key] = int(m.group(1)) if m else None
    return counts


def engine_gate(rule_path: str, root: str, corpus: str, workdir: str) -> dict:
    """G3 -- generic engine regression gate for a manual matcher edit already on
    disk. Runs recette-onyphe AFTER (current state) and BEFORE (the rule reverted
    to git HEAD), then verdicts zero-regression on CORRECT/WRONG/MISS. Writes the
    raw BEFORE/AFTER tables to <workdir>/recette/. No mutation of the rule (the
    git stash/pop is transient and restores the on-disk edit)."""
    import subprocess
    recdir = os.path.join(workdir, "recette")
    os.makedirs(recdir, exist_ok=True)
    rel = os.path.relpath(rule_path, root)

    def _git(*args):
        return subprocess.run(["git", "-C", root, *args],
                              capture_output=True, text=True, timeout=60)

    # Is the rule modified vs HEAD? If not, BEFORE == AFTER (no-op gate).
    dirty = _git("diff", "--quiet", "--", rel).returncode != 0
    after = run_recette(corpus, root)
    if not after.get("ok"):
        return {"ok": False, "error": after.get("error", "recette AFTER failed")}
    with open(os.path.join(recdir, "engine_gate_AFTER.txt"), "w",
              encoding="utf-8") as fh:
        fh.write(after.get("raw", ""))
    if not dirty:
        return {"ok": True, "regression": False, "dirty": False,
                "before": after, "after": after,
                "delta": {"CORRECT": 0, "WRONG": 0, "MISS": 0},
                "note": "rule unchanged vs HEAD -- BEFORE==AFTER"}

    # Revert the rule to HEAD for the BEFORE baseline, then restore.
    stash = _git("stash", "push", "--", rel)
    reverted = stash.returncode == 0 and "No local changes" not in stash.stdout
    before = run_recette(corpus, root)
    if reverted:
        _git("stash", "pop")
    if not before.get("ok"):
        return {"ok": False, "error": before.get("error", "recette BEFORE failed")}
    with open(os.path.join(recdir, "engine_gate_BEFORE.txt"), "w",
              encoding="utf-8") as fh:
        fh.write(before.get("raw", ""))
    delta = {k: (after.get(k) or 0) - (before.get(k) or 0)
             for k in ("CORRECT", "WRONG", "MISS")}
    regression = (delta["CORRECT"] < 0 or delta["WRONG"] > 0 or delta["MISS"] > 0)
    return {"ok": True, "regression": regression, "dirty": True,
            "before": {k: before.get(k) for k in ("CORRECT", "WRONG", "MISS", "GT_MISLABEL")},
            "after": {k: after.get(k) for k in ("CORRECT", "WRONG", "MISS", "GT_MISLABEL")},
            "delta": delta}


def evolve_candidates(suggestions: list, delta: float) -> list:
    """Turn missing-high-signal-header suggestions into engine matchers
    (target:header value-present). Conservative: value '.+' = the header exists,
    which for a product-token header is a strong, low-FP fingerprint."""
    out = []
    seen = set()
    for s in suggestions:
        name = s.get("header_name")
        if not name or name.lower() in seen:
            continue
        seen.add(name.lower())
        out.append({
            "target": "header", "field": name, "match_type": "regex",
            "value": ".+", "confidence_delta": round(float(delta), 3),
            "_lia_evolve": "multirecette suggested high-signal header (name carries product token)",
        })
    return out


def inject_matchers(rule: dict, cands: list) -> str:
    """Insert candidate matchers into the rule's primary L7_HTTP probe (or first
    probe, or banner_matchers). Adds a matcher_evolve_multirecette audit block.
    Returns the container name for reporting."""
    probes = rule.get("probes")
    where = ""
    if isinstance(probes, list) and probes:
        tgt = next((p for p in probes
                    if str(p.get("layer", "")).upper() == "L7_HTTP"), probes[0])
        tgt.setdefault("matchers", []).extend(cands)
        where = "probes[].matchers"
    else:
        rule.setdefault("banner_matchers", []).extend(cands)
        where = "banner_matchers"
    lia = rule.get("_lia_independent_authoring")
    if not isinstance(lia, dict):
        lia = {}
        rule["_lia_independent_authoring"] = lia
    lia["matcher_evolve_multirecette"] = {
        "date": datetime.now(timezone.utc).isoformat(),
        "added": [{"target": c["target"], "field": c.get("field"),
                   "value": c["value"], "confidence_delta": c["confidence_delta"]}
                  for c in cands],
        "container": where,
        "reason": ("MISS on a real host: added a high-signal product-token header "
                   "matcher. Kept only after recette-onyphe zero-regression gate."),
        "model_source": "multirecette --evolve (engine gate-validated)",
        "marked_by": "multirecette_evolve",
    }
    return where


def gen_dork_sheet(rule: dict) -> str:
    """Lazy-load the standalone dork generator (single source of truth in
    tooling/) and render the passive discovery sheet for this rule. Keeping the
    generator as one tool avoids drift between the CLI and the --dorks path."""
    import importlib.util
    gen_path = os.path.join(
        _DEV_ROOT, "_alire", "tracking", "liaprobe-multirecette",
        "tooling", "gen_discovery_dorks.py")
    spec = importlib.util.spec_from_file_location("gen_discovery_dorks", gen_path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    now = datetime.now(timezone.utc).isoformat()
    header = (f"# Passive discovery dorks (derived from rule matchers)\n\n"
              f"Generated: {now}\nRule: {rule.get('id')}\n\n"
              f"PASSIVE ONLY -- no request is emitted to any candidate host. "
              f"Returned hosts go to `multirecette.py --live <url>` (GET-only) "
              f"for the detection gate.\n\n")
    return header + mod.sheet_for(rule)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--rule", required=True)
    ap.add_argument("--live", default="", help="comma-separated live URLs")
    ap.add_argument("--stealth", action="store_true",
                    help="fetch --live URLs through the anti-bot stealth engine "
                         "(Scrapling, solves Cloudflare) instead of urllib -- "
                         "use when the default fetch returns 403 on a WAF host. "
                         "GET-only.")
    ap.add_argument("--corpus", default="", help="comma-separated Onyphe jsonl corpora")
    ap.add_argument("--corpus-limit", type=int, default=0)
    ap.add_argument("--suggest", action="store_true")
    ap.add_argument("--apply", action="store_true",
                    help="inject verified=true + capture artifact IF a live host DETECTs")
    ap.add_argument("--version", action="store_true",
                    help="extract the product version from live/corpus capture")
    ap.add_argument("--cve", action="store_true",
                    help="correlate version -> CPE -> CVE (PostgreSQL cve_nvd_data + KEV)")
    ap.add_argument("--evolve", action="store_true",
                    help="apply suggested matchers, gate via recette-onyphe (BEFORE/AFTER), "
                         "keep ONLY on zero regression else revert (default: dry-run, always revert)")
    ap.add_argument("--evolve-apply", action="store_true",
                    help="with --evolve: KEEP the change on disk when the gate is green "
                         "(without it, --evolve reverts even a green change and just reports)")
    ap.add_argument("--evolve-delta", type=float, default=0.5,
                    help="confidence_delta for each evolved header matcher (default 0.5)")
    ap.add_argument("--gt-corpus", default="",
                    help="recette-onyphe -f corpus path (default: durable canonical appgt)")
    ap.add_argument("--liaprobe-root", default=LIAPROBE_ROOT,
                    help="liaprobe repo root (recette-onyphe + lia-rule-validate)")
    ap.add_argument("--out", default=None, help="verdict json path")
    ap.add_argument("--contribution", default="",
                    help="ingest a USER contribution doc (marker model) and BIND it "
                         "to this rule -- persisted durably + auto-loaded every session")
    ap.add_argument("--contribution-section", default="",
                    help="with --contribution: name the section of a multi-doc "
                         "contribution that applies to this rule (e.g. WORDPRESS)")
    ap.add_argument("--engine-gate", action="store_true",
                    help="G3 -- run the recette-onyphe regression gate around the "
                         "rule's current on-disk edit (BEFORE=git HEAD vs AFTER), "
                         "verdict zero-regression on CORRECT/WRONG/MISS. ~12 min "
                         "(two engine runs). Use after a manual matcher edit.")
    ap.add_argument("--no-favicon", action="store_true",
                    help="skip favicon hash capture (default: ON when --live, "
                         "records favicon sha256+md5+mmh3 as a theme-stable signal)")
    ap.add_argument("--dorks", action="store_true",
                    help="emit passive discovery dorks (Google/Shodan/ONYPHE) "
                         "derived from this rule's matchers into the per-rule "
                         "workdir (discovery_dorks.md). PASSIVE -- no request to "
                         "any candidate host.")
    ap.add_argument("--no-stamp", action="store_true",
                    help="do NOT write the recette status level into the rule JSON "
                         "(default: stamp _lia_independent_authoring.recette.level, "
                         "non-downgrading, leak-safe -- no host/IP in the stamp)")
    ap.add_argument("--contributions", action="store_true",
                    help="list the contributions bound to this rule and exit")
    args = ap.parse_args()

    if load_matchers is None:
        print("ERROR: cannot import onyphe_match helpers", file=sys.stderr)
        return 2

    rule = json.load(open(args.rule, encoding="utf-8"))
    matchers = load_matchers(rule)
    rid = rule.get("id") or os.path.basename(args.rule)
    verdict = {
        "rule": rid, "file": os.path.basename(args.rule),
        "product": rule.get("product"), "matchers": len(matchers),
        "offline": [], "live": [], "suggestions": [],
        "generated_at": datetime.now(timezone.utc).isoformat(),
    }

    # USER contributions (marker model) -- ingest if provided, then ALWAYS load
    # the contributions bound to this rule so the audit is framed by them every
    # session (multi-session persistence the user asked the skill to guarantee).
    if args.contribution:
        try:
            b = ingest_contribution(args.contribution, rid,
                                    args.contribution_section or None)
            print(f"  [contribution] ingested '{b['doc']}'"
                  + (f" section={b['section']}" if b['section'] else "")
                  + f" -> bound to {rid}")
        except FileNotFoundError:
            print(f"  [contribution] WARN: file not found: {args.contribution}",
                  file=sys.stderr)
    verdict["contributions"] = load_contributions(rid)
    if args.contributions:
        contribs = verdict["contributions"]
        if not contribs:
            print(f"  no contributions bound to {rid}")
        for c in contribs:
            flag = "" if c["present"] else " [MISSING FILE]"
            sec = f" section={c['section']}" if c.get("section") else ""
            print(f"  contribution: {c['doc']}{sec} sha={(c.get('sha256') or '')[:12]}{flag}")
            print(f"               -> {c['path']}")
        return 0

    print(f"=== multirecette: {rid} (product={rule.get('product')}, matchers={len(matchers)}) ===")
    if verdict["contributions"]:
        print(f"  [contribution] {len(verdict['contributions'])} bound "
              f"(marker model frames this audit)")

    # OFFLINE
    for corp in [c for c in args.corpus.split(",") if c]:
        if not os.path.isfile(corp):
            print(f"  [offline] SKIP missing {corp}", file=sys.stderr)
            continue
        total = hits = 0
        for b, gt in banners(corp):
            total += 1
            if args.corpus_limit and total > args.corpus_limit:
                total -= 1
                break
            hv, bdy = split_banner(b)
            hdrs = parse_headers(b)
            if any(matcher_fires(t, rx, field, b, hv, bdy, hdrs)
                   for t, rx, v, cd, field in matchers):
                hits += 1
        rate = (hits / total * 100) if total else 0.0
        row = {"corpus": os.path.basename(corp), "scanned": total,
               "matched": hits, "rate_pct": round(rate, 2)}
        verdict["offline"].append(row)
        flag = "  <-- 100% = too-broad matcher, FP risk" if rate >= 99.9 and total > 5 else ""
        print(f"  [offline] {row['corpus']}: {hits}/{total} ({rate:.1f}%){flag}")

    # LIVE
    detected_capture = None
    capture_hb = None
    first_live_url = None
    for url in [u.strip() for u in args.live.split(",") if u.strip()]:
        f = stealth_fetch(url) if args.stealth else fetch(url)
        if not f["ok"]:
            verdict["live"].append({"url": url, "ok": False, "error": f["error"]})
            print(f"  [live] {url} FETCH FAILED: {f['error']}")
            continue
        if capture_hb is None:
            capture_hb = (f["headers"], f["body"])
            first_live_url = url
        sc = score_live(rule, matchers, f["headers"], f["body"],
                        status_line=f.get("status_line", ""))
        bh = multi_hash(f["body"])
        hh = multi_hash(f["headers"])
        row = {"url": url, "ok": True, "status": f["status"], **sc,
               "html_sha256": bh["sha256"], "html_md5": bh["md5"],
               "headers_sha256": hh["sha256"], "headers_md5": hh["md5"],
               "engine": f.get("engine", "urllib")}
        verdict["live"].append(row)
        tag = "DETECT" if sc["detected"] else "MISS"
        fired = ", ".join(m["value"] for m in sc["fired"]) or "(none)"
        print(f"  [live] {url} HTTP {f['status']} -> {tag} "
              f"score={sc['score']}/{sc['threshold']} fired[{sc['fired_count']}/{sc['total_matchers']}]: {fired}")
        if sc["detected"] and detected_capture is None:
            detected_capture = row
        if args.suggest or not sc["detected"]:
            sg = suggest(rule, f["headers"], matchers)
            for s in sg:
                if s not in verdict["suggestions"]:
                    verdict["suggestions"].append(s)

    if verdict["suggestions"]:
        print("  [suggest] high-signal headers the rule ignores:")
        for s in verdict["suggestions"]:
            print(f"      {s['header_name']}: {s['header_value_sample']!r} -> {s['why']}")

    # VERSION (from the first live capture)
    detected_version = None
    if args.version or args.cve:
        if capture_hb is not None:
            ver = extract_version(rule, capture_hb[0], capture_hb[1])
            detected_version = ver["version"]
            verdict["version"] = ver
            print(f"  [version] {detected_version or '(not found)'}"
                  + (f"  via {ver['candidates'][0]['via']}" if ver["candidates"] else ""))
        else:
            print("  [version] no live capture (provide --live to extract version)")

    # CVE correlation (version -> CPE -> PostgreSQL)
    if args.cve:
        cv = cve_correlate(rule, detected_version)
        verdict["cve"] = cv
        if cv["ok"]:
            scope = "exact version" if cv["version_pinned"] else "all versions (no version pinned)"
            print(f"  [cve] {cv['count']} CVE ({cv['kev_count']} KEV) for {cv['cpe_pattern']} [{scope}]")
            for c in cv["cves"][:10]:
                print(f"      {c['cve_id']}  {c['severity']:8s} {c['cvss']:4s}"
                      + ("  KEV" if c["kev"] else ""))
        else:
            print(f"  [cve] unavailable: {cv['error']}")

    # EVOLVE (R4 gate: matchers change ONLY behind the recette-onyphe regression gate)
    if args.evolve:
        import shutil
        import subprocess
        evo = {"requested": True}
        verdict["evolve"] = evo
        cands = evolve_candidates(verdict["suggestions"], args.evolve_delta)
        if not cands:
            evo["status"] = "NO_CANDIDATE"
            print("\n  [evolve] no high-signal header suggestion -> nothing to add "
                  "(provide a --live host that MISSes to surface candidates).")
        else:
            corpus = resolve_gt_corpus(args.gt_corpus)
            root = args.liaprobe_root
            if not corpus:
                evo["status"] = "NO_CORPUS"
                print("\n  [evolve] ABORT: no GT corpus resolved (pass --gt-corpus).")
            else:
                wd_e = workdir_for(rule, args.rule)
                rdir = os.path.join(wd_e, "recette")
                bak = os.path.join(rdir, os.path.basename(args.rule) + ".evolve.bak")
                shutil.copy2(args.rule, bak)
                print(f"\n  [evolve] {len(cands)} candidate matcher(s): "
                      + ", ".join(f"header {c['field']} d{c['confidence_delta']}" for c in cands))
                print(f"  [evolve] gate corpus: {os.path.relpath(corpus, _DEV_ROOT) if corpus.startswith(_DEV_ROOT) else corpus}")
                # BEFORE (current on-disk rule)
                before = run_recette(corpus, root)
                if not before.get("ok"):
                    shutil.copy2(bak, args.rule)
                    evo["status"] = "GATE_ERROR_BEFORE"
                    evo["error"] = before.get("error")
                    print(f"  [evolve] ABORT: recette BEFORE failed: {before.get('error')}")
                else:
                    where = inject_matchers(rule, cands)
                    tmp = args.rule + ".tmp"
                    with open(tmp, "w", encoding="utf-8") as fh:
                        json.dump(rule, fh, indent=2, ensure_ascii=False)
                        fh.write("\n")
                    os.replace(tmp, args.rule)
                    # SCHEMA gate
                    val_bin = os.path.join(root, "bin", "lia-rule-validate")
                    schema_ok = True
                    if os.path.isfile(val_bin):
                        v = subprocess.run([val_bin, "-q", "-allow-disabled", args.rule],
                                           capture_output=True, text=True, timeout=60)
                        schema_ok = v.returncode == 0
                        if not schema_ok:
                            evo["schema_error"] = (v.stdout + v.stderr).strip()[:300]
                    if not schema_ok:
                        shutil.copy2(bak, args.rule)
                        evo["status"] = "SCHEMA_FAIL"
                        print(f"  [evolve] REVERT: schema invalid after injection: {evo.get('schema_error')}")
                    else:
                        after = run_recette(corpus, root)
                        if not after.get("ok"):
                            shutil.copy2(bak, args.rule)
                            evo["status"] = "GATE_ERROR_AFTER"
                            evo["error"] = after.get("error")
                            print(f"  [evolve] REVERT: recette AFTER failed: {after.get('error')}")
                        else:
                            bC, bW, bM = before["CORRECT"], before["WRONG"], before["MISS"]
                            aC, aW, aM = after["CORRECT"], after["WRONG"], after["MISS"]
                            regress = (aC < bC) or (aW > bW) or (aM > bM)
                            evo.update({
                                "before": {"CORRECT": bC, "WRONG": bW, "MISS": bM},
                                "after": {"CORRECT": aC, "WRONG": aW, "MISS": aM},
                                "delta": {"CORRECT": aC - bC, "WRONG": aW - bW, "MISS": aM - bM},
                                "regression": regress,
                            })
                            with open(os.path.join(rdir, "evolve_before.txt"), "w") as fh:
                                fh.write(before["raw"])
                            with open(os.path.join(rdir, "evolve_after.txt"), "w") as fh:
                                fh.write(after["raw"])
                            print(f"  [evolve] gate: CORRECT {bC}->{aC} ({aC-bC:+d}) | "
                                  f"WRONG {bW}->{aW} ({aW-bW:+d}) | MISS {bM}->{aM} ({aM-bM:+d})")
                            if regress:
                                shutil.copy2(bak, args.rule)
                                evo["status"] = "REGRESSION_REVERTED"
                                print("  [evolve] REVERT: regression (CORRECT down or WRONG/MISS up). Rule restored.")
                            elif args.evolve_apply:
                                evo["status"] = "KEPT"
                                print(f"  [evolve] KEEP: zero regression, change applied to {where}. "
                                      "Commit in liaprobe repo (safe_commit).")
                            else:
                                shutil.copy2(bak, args.rule)
                                evo["status"] = "GREEN_DRYRUN_REVERTED"
                                print("  [evolve] GREEN (dry-run): zero regression. Re-run with "
                                      "--evolve-apply to keep the change.")

    # APPLY (R4-safe)
    if args.apply:
        if detected_capture is None:
            print("\n  [apply] REFUSED: no live host scored >= threshold. "
                  "Never fabricate verified=true. Fix coverage first (see suggestions).")
        else:
            lia = rule.get("_lia_independent_authoring")
            if not isinstance(lia, dict):
                lia = {}
                rule["_lia_independent_authoring"] = lia
            # Anti-leak: NEVER write the live host into the PUBLIC rule JSON.
            # The host (vendor or third-party) stays ONLY in the private dev
            # capture (capture_*.jsonl under _alire/tracking, gitignored from the
            # public liaprobe repo). The public rule carries opaque sha256 hashes
            # + a private evidence ref. Verify-by-replay uses the private capture.
            _rid = rule.get("id") or os.path.splitext(os.path.basename(args.rule))[0]
            _priv_ref = (f"private-evidence: _alire/tracking/liaprobe-multirecette/"
                         f"rules/{_rid} (live host not disclosed in public rule)")
            lia.setdefault("http_gate", {})
            lia["http_gate"].update({
                "verified": True,
                "http_status": detected_capture["status"],
                "verified_url": _priv_ref,
                "verified_date": datetime.now(timezone.utc).date().isoformat(),
                "note": "live recette: rule fired >= threshold on a real host (host in private capture)",
            })
            art = rule.get("artifacts")
            if not isinstance(art, dict):
                art = rule.setdefault("artifacts", {})
            art.update({
                "capture_url": _priv_ref,
                "html_sha256": detected_capture["html_sha256"],
                "headers_sha256": detected_capture["headers_sha256"],
                "capture_date": datetime.now(timezone.utc).date().isoformat(),
                "observation_provenance": "live_verified_private_evidence",
            })
            tmp = args.rule + ".tmp"
            with open(tmp, "w", encoding="utf-8") as fh:
                json.dump(rule, fh, indent=2, ensure_ascii=False)
                fh.write("\n")
            os.replace(tmp, args.rule)
            print(f"\n  [apply] verified=true + capture artifact injected from {detected_capture['url']}")

    # Durable per-rule workdir (NEVER _alire/temp). Multi-session resumable.
    wd = workdir_for(rule, args.rule)
    # persist the live capture as durable evidence (not temp), with multi-algo
    # hashes (sha256 + md5) so the capture is comparable across tools.
    if capture_hb is not None:
        bh = multi_hash(capture_hb[1])
        hh = multi_hash(capture_hb[0])
        cap = os.path.join(wd, "captures",
                           "capture_" + datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ") + ".jsonl")
        with open(cap, "w", encoding="utf-8") as fh:
            fh.write(json.dumps({
                "headers": capture_hb[0], "body": capture_hb[1], "rule": rid,
                "url": first_live_url,
                "hashes": {
                    "body_sha256": bh["sha256"], "body_md5": bh["md5"],
                    "headers_sha256": hh["sha256"], "headers_md5": hh["md5"],
                }}) + "\n")
        verdict["capture_file"] = os.path.relpath(cap, _DEV_ROOT)

    # Per-rule evidence contract (user directive 2026-05-30): hashes + favicon +
    # version + CVE + final engine test. Whatever is missing -> explicit TODO.
    evidence = {}
    if capture_hb is not None:
        evidence["body_hashes"] = multi_hash(capture_hb[1])
        evidence["headers_hashes"] = multi_hash(capture_hb[0])
    if first_live_url and not args.no_favicon:
        fav = fetch_favicon(first_live_url, stealth=args.stealth)
        evidence["favicon"] = fav
        if fav.get("ok"):
            print(f"  [favicon] {fav['url']} sha256={fav['sha256'][:16]} "
                  f"md5={fav['md5'][:16]} mmh3={fav.get('mmh3')}")
    if evidence:
        verdict["evidence"] = evidence
    if args.dorks:
        dp = os.path.join(wd, "discovery_dorks.md")
        with open(dp, "w", encoding="utf-8") as fh:
            fh.write(gen_dork_sheet(rule))
        verdict["discovery_dorks"] = os.path.relpath(dp, _DEV_ROOT)
        print(f"\n  [dorks] passive discovery sheet -> {os.path.relpath(dp, _DEV_ROOT)}")
    # Engine gate BEFORE build_todo so the TODO sees the engine_test result.
    if args.engine_gate:
        corpus = resolve_gt_corpus(args.gt_corpus)
        if not corpus:
            print("\n  [engine-gate] no GT corpus resolved -- skipped")
        else:
            print("\n  [engine-gate] running recette-onyphe BEFORE/AFTER (~12 min)...")
            eg = engine_gate(args.rule, args.liaprobe_root, corpus, wd)
            verdict["engine_test"] = eg
            if eg.get("ok"):
                d = eg.get("delta", {})
                verdict_str = "REGRESSION" if eg.get("regression") else "OK (zero regression)"
                print(f"  [engine-gate] {verdict_str} "
                      f"CORRECT {d.get('CORRECT', 0):+d} WRONG {d.get('WRONG', 0):+d} "
                      f"MISS {d.get('MISS', 0):+d}")
                if eg.get("regression"):
                    print("  [engine-gate] REVERT the edit and REPLAN (R4 gate red).")
            else:
                print(f"  [engine-gate] FAILED: {eg.get('error')}")
    todo = build_todo(rule, verdict)
    verdict["todo"] = todo
    if args.live:
        tp = write_todo_md(wd, rule, todo)
        if todo:
            print(f"  [todo] {len(todo)} audit gap(s) -> {os.path.relpath(tp, _DEV_ROOT)}")
            for t in todo:
                print(f"      - {t.split(' -- ')[0]}")
    out = args.out or os.path.join(
        wd, "verdict_" + datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ") + ".json")
    with open(out, "w", encoding="utf-8") as fh:
        json.dump(verdict, fh, indent=2)
    append_session(wd, verdict)
    if not args.no_stamp:
        lvl = stamp_recette_level(rule, args.rule, verdict, wd)
        if lvl:
            print(f"  [stamp] recette.level={lvl} written into rule JSON "
                  "(non-downgrading, leak-safe)")
    print(f"\nworkdir: {os.path.relpath(wd, _DEV_ROOT)}")
    print(f"verdict: {os.path.relpath(out, _DEV_ROOT)}")
    print(f"session: {os.path.relpath(os.path.join(wd, 'SESSION.md'), _DEV_ROOT)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
