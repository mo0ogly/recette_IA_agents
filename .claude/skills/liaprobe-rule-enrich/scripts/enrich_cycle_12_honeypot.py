"""
Cycle 12 -- Honeypot detection enrichment.

Source: master_data/honeypot_master.json -- per-indicator source_url + sha256
verified against open-source honeypot project repos (Cowrie BSD-3, Conpot
GPL-2 behavior-only, T-Pot Apache-2.0).

Output: rule.honeypot_indicators = [
    {
        indicator_id, name, type, match: {...}, confidence, severity,
        source_url, source_sha256, source_section, verified_at, ...
    },
    ...
]

Match strategy:
1. Build product_key from cpe23_template parts 3+4 (vendor/product)
2. Lookup master.products[product_key], vendor wildcard, then "*/*"
3. Resolve indicator_ids to full indicator objects via master.indicator_definitions
4. De-duplicate
5. Inject into rule.honeypot_indicators

Scoring rule (applied at scanner runtime, not at enrichment time):
  If 2+ indicators match for the same target -> is_likely_honeypot = true
  honeypot_confidence = max(matched_confidence)
  Single match = informative only

R4 anti-abuse: data is INFORMATIVE for the LIA-SEC platform analytics layer.
LiaProbe scanner does NOT actively probe the target with malformed packets to
verify honeypot behavior -- it only observes passive signals already collected.
"""
from __future__ import annotations

import json
from pathlib import Path

from enrich_lib import (
    AtomicJSONWriter,
    DependencyMissingError,
    EvidenceWriter,
    LockManager,
    StateManager,
    find_tracking_root,
    sha256_file,
    utc_now_iso,
)


CYCLE_ID = "cycle_12_honeypot"
MAX_INDICATORS = 20  # cap injection per-rule (protect rule size)


def _build_product_key(rule: dict) -> str | None:
    """Derive product_key from cpe23_template (parts 3+4) or vendor+product."""
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


def _master_path(master_path: Path | None = None) -> Path:
    if master_path is not None:
        return master_path
    return find_tracking_root() / "master_data" / "honeypot_master.json"


def _load_master(master_path: Path) -> dict:
    if not master_path.exists():
        raise DependencyMissingError(
            f"honeypot_master.json not found at {master_path}"
        )
    return json.loads(master_path.read_text(encoding="utf-8"))


def lookup_indicator_ids(product_key: str, master: dict) -> list[str]:
    """Return ordered, de-duplicated indicator_ids that apply to product_key.

    Lookup order:
    1. exact product_key
    2. vendor wildcard
    3. universal "*/*"
    """
    products = master.get("products", {})
    seen: set[str] = set()
    out: list[str] = []

    candidate_keys: list[str] = [product_key]
    if "/" in product_key:
        vendor, _ = product_key.split("/", 1)
        candidate_keys.append(f"{vendor}/*")
    candidate_keys.append("*/*")

    for ck in candidate_keys:
        for iid in products.get(ck, []):
            if iid not in seen:
                seen.add(iid)
                out.append(iid)

    return out[:MAX_INDICATORS]


def resolve_indicators(indicator_ids: list[str], master: dict) -> list[dict]:
    """Resolve indicator_ids to full dicts from master.indicator_definitions."""
    defs = master.get("indicator_definitions", {})
    out: list[dict] = []
    for iid in indicator_ids:
        if iid in defs:
            entry = dict(defs[iid])
            entry["indicator_id"] = iid
            out.append(entry)
    return out


def handle(
    rule_path: Path,
    rule_data: dict,
    ew: EvidenceWriter,
    sm: StateManager,
    lock: LockManager,
    *,
    master_path: Path | None = None,
) -> tuple[bool, dict, dict]:
    """Execute cycle 12 honeypot indicator enrichment.

    Returns (success, applied_diff, summary).
    """
    product_key = _build_product_key(rule_data)
    if not product_key:
        sm.mark_cycle_skipped(rule_path, CYCLE_ID, "no product_key derivable")
        return False, {}, {"skipped": True, "reason": "no_product_key"}

    mp = _master_path(master_path)
    try:
        master = _load_master(mp)
    except DependencyMissingError as e:
        sm.mark_cycle_skipped(rule_path, CYCLE_ID, f"master not available: {e}")
        return False, {}, {"skipped": True, "reason": "master_missing", "error": str(e)}

    indicator_ids = lookup_indicator_ids(product_key, master)
    if not indicator_ids:
        sm.mark_cycle_skipped(
            rule_path, CYCLE_ID,
            f"no honeypot indicators for product_key={product_key}",
        )
        return False, {}, {
            "skipped": True,
            "reason": "no_match",
            "product_key": product_key,
        }

    indicators = resolve_indicators(indicator_ids, master)
    if not indicators:
        sm.mark_cycle_skipped(
            rule_path, CYCLE_ID,
            f"indicator_ids resolved to empty (master.indicator_definitions inconsistent)",
        )
        return False, {}, {
            "skipped": True,
            "reason": "empty_resolution",
            "indicator_ids": indicator_ids,
        }

    rule_sha_before = sha256_file(rule_path)

    rule_after = dict(rule_data)
    rule_after["honeypot_indicators"] = indicators
    meta = rule_after.get("_meta_enrichment", {})
    meta_cycle = {
        "applied_at": utc_now_iso(),
        "evidence_path": None,
        "evidence_sha256": None,
        "product_key": product_key,
        "indicators_count": len(indicators),
        "indicator_ids": indicator_ids,
        "scoring_rule": master.get("scoring_rule"),
        "master_generated_at": master.get("generated_at"),
    }
    meta[CYCLE_ID] = meta_cycle
    rule_after["_meta_enrichment"] = meta

    source_ids_used = sorted(set(p.get("source_id", "unknown") for p in indicators))
    source_meta = {
        "type": "manual",
        "master_path": str(
            mp.relative_to(find_tracking_root().parent.parent)
            if str(mp).startswith(str(find_tracking_root().parent.parent))
            else mp
        ),
        "master_schema": master.get("$schema"),
        "master_generated_at": master.get("generated_at"),
        "source_ids_used": source_ids_used,
        "indicators_by_source": {
            sid: sum(1 for p in indicators if p.get("source_id") == sid)
            for sid in source_ids_used
        },
        "executed_at": utc_now_iso(),
    }
    applied_diff = {
        "added_keys": ["honeypot_indicators"],
        "added_value": {"honeypot_indicators": indicators},
    }
    summary = {
        "product_key": product_key,
        "indicators_count": len(indicators),
        "indicator_ids": indicator_ids,
        "source_ids_used": source_ids_used,
        "max_severity": _max_severity(indicators),
        "max_confidence": max((p.get("confidence", 0.0) for p in indicators), default=0.0),
    }

    ev_path, ev_sha = ew.write(
        rule_path=rule_path,
        cycle_id=CYCLE_ID,
        rule_data=rule_data,
        rule_sha256_before=rule_sha_before,
        rule_sha256_after="pending",
        source_meta=source_meta,
        raw_data=indicators,
        applied_diff=applied_diff,
        summary=summary,
    )

    rule_after["_meta_enrichment"][CYCLE_ID]["evidence_path"] = str(ev_path)
    rule_after["_meta_enrichment"][CYCLE_ID]["evidence_sha256"] = ev_sha
    AtomicJSONWriter.write(rule_path, rule_after)

    sm.mark_cycle_done(
        rule_path=rule_path,
        cycle_id=CYCLE_ID,
        evidence_path=ev_path,
        evidence_sha256=ev_sha,
        summary=summary,
    )

    return True, applied_diff, summary


def _max_severity(indicators: list[dict]) -> str:
    """Return the highest severity present in the indicators list."""
    order = {"info": 0, "low": 1, "medium": 2, "high": 3, "critical": 4}
    best = "info"
    best_n = 0
    for p in indicators:
        sev = (p.get("severity") or "info").lower()
        n = order.get(sev, 0)
        if n > best_n:
            best_n = n
            best = sev
    return best


__all__ = [
    "CYCLE_ID",
    "handle",
    "lookup_indicator_ids",
    "resolve_indicators",
    "_build_product_key",
    "MAX_INDICATORS",
]
