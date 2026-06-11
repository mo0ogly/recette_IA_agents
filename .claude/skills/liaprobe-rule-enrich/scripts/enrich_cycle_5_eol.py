"""
Cycle 5 -- Lifecycle / EOL enrichment.

Source: endoflife.date public API.
Output: rule.lifecycle = {data_source, latest_cycle, released, eol, is_eol_now, ...}

Handler signature compatible with ooda_engine.CycleHandler.

Slug resolution order:
1. Lookup product_key in master_data/endoflife_slug_mapping.csv
2. Slugify(product) -> first-guess
3. Slugify(vendor) -> fallback
"""
from __future__ import annotations

import csv
import json
import re
from datetime import datetime
from pathlib import Path
from typing import Any

from enrich_lib import (
    AtomicJSONWriter,
    DependencyMissingError,
    EvidenceWriter,
    HTTPClient,
    HTTPResponse,
    LockManager,
    StateManager,
    find_tracking_root,
    sha256_canonical_json,
    sha256_file,
    utc_now_iso,
)


CYCLE_ID = "cycle_5_eol"
DEFAULT_API_BASE = "https://endoflife.date/api"


def _slugify(name: str) -> str:
    s = name.lower().strip()
    s = re.sub(r"[^a-z0-9]+", "-", s)
    return s.strip("-")


def _build_product_key(rule: dict) -> str | None:
    cpe = rule.get("cpe23_template", "")
    if cpe and cpe.startswith("cpe:2.3:"):
        parts = cpe.split(":")
        if len(parts) >= 5:
            return f"{parts[3].lower()}/{parts[4].lower()}"
    vendor = (rule.get("vendor") or "").lower().strip()
    product = (rule.get("product") or "").lower().strip()
    if vendor and product:
        return f"{vendor}/{product}"
    return None


def _resolve_slug(rule: dict, slug_csv_path: Path | None) -> str | None:
    """Slug resolution: master CSV -> product slugify -> vendor slugify."""
    product_key = _build_product_key(rule)
    if slug_csv_path and slug_csv_path.exists() and product_key:
        try:
            with slug_csv_path.open(newline="", encoding="utf-8") as fp:
                reader = csv.DictReader(fp)
                for row in reader:
                    if (row.get("liaprobe_product_key") or "").lower() == product_key:
                        slug = (row.get("endoflife_slug") or "").strip()
                        if slug:
                            return slug
        except OSError:
            pass
    product = rule.get("product") or ""
    if product:
        s = _slugify(product)
        if s:
            return s
    vendor = rule.get("vendor") or ""
    if vendor:
        s = _slugify(vendor)
        if s:
            return s
    return None


def _parse_eol_value(value: Any) -> tuple[str | None, bool]:
    """endoflife.date returns: ISO string, true/false, or null.

    Returns (date_or_none, is_past_now).
    """
    if value is None or value is False:
        return None, False
    if value is True:
        return None, True
    if isinstance(value, str):
        try:
            d = datetime.fromisoformat(value)
            return value, d < datetime.utcnow()
        except ValueError:
            return None, False
    return None, False


def _build_lifecycle(cycles: list[dict]) -> dict | None:
    """Aggregate cycles -> compact lifecycle{} block."""
    if not cycles:
        return None

    def _release_dt(c: dict) -> datetime:
        rel = c.get("releaseDate", "")
        try:
            return datetime.fromisoformat(rel) if rel else datetime.min
        except ValueError:
            return datetime.min

    sorted_cycles = sorted(cycles, key=_release_dt, reverse=True)
    latest = sorted_cycles[0]
    eol_date, is_eol = _parse_eol_value(latest.get("eol"))
    lts = next((c for c in sorted_cycles if c.get("lts")), None)

    out: dict[str, Any] = {
        "data_source": "endoflife.date",
        "latest_cycle": latest.get("cycle"),
        "released": latest.get("releaseDate"),
        "eol": eol_date,
        "is_eol_now": is_eol,
        "current_stable": latest.get("latest") or latest.get("cycle"),
    }
    if lts:
        out["lts_cycle"] = lts.get("cycle")
        lts_eol, _ = _parse_eol_value(lts.get("eol"))
        if lts_eol:
            out["lts_eol"] = lts_eol
    if "extendedSupport" in latest and isinstance(latest["extendedSupport"], str):
        out["extended_support_until"] = latest["extendedSupport"]
    if "support" in latest and isinstance(latest["support"], str):
        out["support_until"] = latest["support"]
    return {k: v for k, v in out.items() if v is not None}


def _http_client(cache_dir: Path | None = None) -> HTTPClient:
    base = cache_dir or (find_tracking_root() / "runtime" / "endoflife_cache")
    return HTTPClient(cache_dir=base)


def fetch_eol(slug: str, http: HTTPClient | None = None) -> tuple[HTTPResponse | None, list[dict] | None]:
    """Fetch endoflife.date data for slug. Returns (response, parsed_cycles)."""
    http = http or _http_client()
    url = f"{DEFAULT_API_BASE}/{slug}.json"
    try:
        resp = http.get(url)
    except DependencyMissingError:
        return None, None
    if resp.status != 200:
        return resp, None
    try:
        data = json.loads(resp.body.decode("utf-8"))
        if not isinstance(data, list):
            return resp, None
        return resp, data
    except (json.JSONDecodeError, UnicodeDecodeError):
        return resp, None


def handle(
    rule_path: Path,
    rule_data: dict,
    ew: EvidenceWriter,
    sm: StateManager,
    lock: LockManager,
    *,
    http: HTTPClient | None = None,
    slug_csv_path: Path | None = None,
) -> tuple[bool, dict, dict]:
    """Execute cycle 5 EOL enrichment.

    Returns (success, applied_diff, summary).
    """
    slug = _resolve_slug(rule_data, slug_csv_path)
    if not slug:
        sm.mark_cycle_skipped(rule_path, CYCLE_ID, "no slug derivable from product/vendor")
        return False, {}, {"skipped": True, "reason": "no slug"}

    resp, cycles = fetch_eol(slug, http=http)
    if resp is None:
        sm.mark_cycle_skipped(rule_path, CYCLE_ID, f"network failure for slug={slug}")
        return False, {}, {"skipped": True, "reason": "network", "slug": slug}
    if resp.status == 404 or cycles is None:
        sm.mark_cycle_skipped(
            rule_path, CYCLE_ID,
            f"endoflife.date returned {resp.status} for slug={slug}",
        )
        return False, {}, {
            "skipped": True,
            "reason": f"http_{resp.status}",
            "slug": slug,
        }

    lifecycle = _build_lifecycle(cycles)
    if not lifecycle:
        sm.mark_cycle_skipped(rule_path, CYCLE_ID, f"no usable lifecycle data for slug={slug}")
        return False, {}, {"skipped": True, "reason": "no_data", "slug": slug}

    # Compute rule sha256 BEFORE write
    rule_sha_before = sha256_file(rule_path)

    # Inject lifecycle into rule
    rule_after = dict(rule_data)
    rule_after["lifecycle"] = lifecycle
    meta = rule_after.get("_meta_enrichment", {})
    meta_cycle = {
        "applied_at": utc_now_iso(),
        "evidence_path": None,  # set below
        "evidence_sha256": None,
        "slug_used": slug,
        "cycles_count": len(cycles),
    }
    meta[CYCLE_ID] = meta_cycle
    rule_after["_meta_enrichment"] = meta

    # Write evidence FIRST
    source_meta = {
        "type": "http",
        "url": resp.url,
        "method": "GET",
        "http_status": resp.status,
        "response_size_bytes": resp.response_size_bytes,
        "fetched_at": resp.fetched_at,
        "from_cache": resp.from_cache,
        "user_agent": "LiaProbe-enrich/v2",
        "slug_used": slug,
    }
    applied_diff = {
        "added_keys": ["lifecycle"],
        "added_value": {"lifecycle": lifecycle},
    }
    summary = {
        "slug_used": slug,
        "cycles_count": len(cycles),
        "is_eol_now": lifecycle.get("is_eol_now", False),
        "latest_cycle": lifecycle.get("latest_cycle"),
        "lts_present": "lts_cycle" in lifecycle,
    }

    ev_path, ev_sha = ew.write(
        rule_path=rule_path,
        cycle_id=CYCLE_ID,
        rule_data=rule_data,
        rule_sha256_before=rule_sha_before,
        rule_sha256_after="pending",  # will fixed after write
        source_meta=source_meta,
        raw_data=cycles,
        applied_diff=applied_diff,
        summary=summary,
    )

    # Backfill evidence path in meta + write rule
    rule_after["_meta_enrichment"][CYCLE_ID]["evidence_path"] = str(ev_path)
    rule_after["_meta_enrichment"][CYCLE_ID]["evidence_sha256"] = ev_sha
    AtomicJSONWriter.write(rule_path, rule_after)

    # Update state
    sm.mark_cycle_done(
        rule_path=rule_path,
        cycle_id=CYCLE_ID,
        evidence_path=ev_path,
        evidence_sha256=ev_sha,
        summary=summary,
    )

    return True, applied_diff, summary


__all__ = [
    "CYCLE_ID",
    "handle",
    "fetch_eol",
    "_resolve_slug",
    "_build_lifecycle",
    "_parse_eol_value",
    "_slugify",
    "_build_product_key",
]
