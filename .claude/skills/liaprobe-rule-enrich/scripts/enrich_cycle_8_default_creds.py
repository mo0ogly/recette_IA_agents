"""
Cycle 8 -- Default credentials enrichment.

Source: master_data/default_creds_master.json (multi-source aggregated from
DefaultCreds-cheat-sheet + SecLists + BetterDefaultPasslist with per-entry
source_url + sha256 + line for replay verification).

Output: rule.default_credentials = [
    {username, password, source_id, source_url, source_sha256, source_line, ...},
    ...
]

Match strategy:
1. Build product_key from cpe23_template parts 3+4 (vendor/product)
2. Lookup master.products[product_key]
3. Inject credentials list (each carrying its own source-tracking)

Anti-abuse: data is INFORMATIVE only -- LiaProbe does NOT auto-test these
credentials live (R4 + ROE compliance).
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

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


CYCLE_ID = "cycle_8_default_creds"
MAX_CREDENTIALS = 50  # cap injection per-rule (protect rule size)


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
    return find_tracking_root() / "master_data" / "default_creds_master.json"


def _load_master(master_path: Path) -> dict:
    if not master_path.exists():
        raise DependencyMissingError(
            f"default_creds_master.json not found at {master_path} -- run "
            f"build_default_creds_master_v2.py first"
        )
    return json.loads(master_path.read_text(encoding="utf-8"))


def lookup_credentials(product_key: str, master: dict) -> list[dict]:
    """Return credentials list for product_key (empty if no match)."""
    products = master.get("products", {})
    creds = products.get(product_key, [])
    return creds[:MAX_CREDENTIALS]


def handle(
    rule_path: Path,
    rule_data: dict,
    ew: EvidenceWriter,
    sm: StateManager,
    lock: LockManager,
    *,
    master_path: Path | None = None,
) -> tuple[bool, dict, dict]:
    """Execute cycle 8 default credentials enrichment.

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

    creds = lookup_credentials(product_key, master)
    if not creds:
        sm.mark_cycle_skipped(
            rule_path, CYCLE_ID,
            f"no default credentials for product_key={product_key}",
        )
        return False, {}, {
            "skipped": True,
            "reason": "no_match",
            "product_key": product_key,
        }

    # Compute rule sha256 BEFORE write
    rule_sha_before = sha256_file(rule_path)

    # Inject default_credentials into rule
    rule_after = dict(rule_data)
    rule_after["default_credentials"] = creds
    meta = rule_after.get("_meta_enrichment", {})
    meta_cycle = {
        "applied_at": utc_now_iso(),
        "evidence_path": None,
        "evidence_sha256": None,
        "product_key": product_key,
        "credentials_count": len(creds),
        "master_generated_at": master.get("generated_at"),
    }
    meta[CYCLE_ID] = meta_cycle
    rule_after["_meta_enrichment"] = meta

    # source_meta references master file (the master file itself tracks
    # per-credential source_url + sha256, so evidence stores summary only)
    source_ids_used = sorted(set(c.get("source_id", "unknown") for c in creds))
    source_meta = {
        "type": "manual",
        "master_path": str(mp.relative_to(find_tracking_root().parent.parent)
                            if str(mp).startswith(str(find_tracking_root().parent.parent))
                            else mp),
        "master_schema": master.get("$schema"),
        "master_generated_at": master.get("generated_at"),
        "source_ids_used": source_ids_used,
        "credentials_by_source": {
            sid: sum(1 for c in creds if c.get("source_id") == sid)
            for sid in source_ids_used
        },
        "executed_at": utc_now_iso(),
    }
    applied_diff = {
        "added_keys": ["default_credentials"],
        "added_value": {"default_credentials": creds},
    }
    summary = {
        "product_key": product_key,
        "credentials_count": len(creds),
        "source_ids_used": source_ids_used,
        "first_username": creds[0].get("username") if creds else None,
        "has_blank_password": any(c.get("password") is None for c in creds),
    }

    ev_path, ev_sha = ew.write(
        rule_path=rule_path,
        cycle_id=CYCLE_ID,
        rule_data=rule_data,
        rule_sha256_before=rule_sha_before,
        rule_sha256_after="pending",
        source_meta=source_meta,
        raw_data=creds,
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


__all__ = [
    "CYCLE_ID",
    "handle",
    "lookup_credentials",
    "_build_product_key",
    "MAX_CREDENTIALS",
]
