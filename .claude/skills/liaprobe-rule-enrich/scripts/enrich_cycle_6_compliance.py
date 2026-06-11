"""
Cycle 6 -- Compliance framework mapping enrichment.

Source: master_data/compliance_master.json -- per-control source_url + source_sha256
verified against authoritative compliance publications:
  - ANSSI Guide Hygiene Informatique v2 (R1-R42)
  - NIS2 Directive (EU) 2022/2555 Article 21(2) items (a)-(j),
    verified from Commission Implementing Regulation (EU) 2024/2690
  - ISO/IEC 27001:2022 Annex A (93 controls, A.5-A.8)
  - EBIOS RM v1.5 (workshops WS1-WS5, feared event categories)

Output: rule.compliance_mappings = {
    "anssi": ["R5", "R14", "R17", ...],
    "nis2": ["art21.2.a", "art21.2.b", ...],
    "iso27001": ["A.8.8", "A.8.9", ...],
    "ebios_rm": ["WS1", "WS4", "FE.CONF", ...]
}

Match strategy:
1. Build product_key from cpe23_template parts 3+4 (vendor/product)
2. Lookup master.product_mappings[product_key] (exact match only -- no wildcard)
3. Inject into rule.compliance_mappings

Controls marked TODO_VERIFY in the master require manual confirmation
against authenticated copies of the source documents.
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


CYCLE_ID = "cycle_6_compliance"
SUPPORTED_FRAMEWORKS = ("anssi", "nis2", "iso27001", "ebios_rm")


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
    return find_tracking_root() / "master_data" / "compliance_master.json"


def _load_master(master_path: Path) -> dict:
    if not master_path.exists():
        raise DependencyMissingError(
            f"compliance_master.json not found at {master_path}"
        )
    return json.loads(master_path.read_text(encoding="utf-8"))


def lookup_compliance_mappings(product_key: str, master: dict) -> dict | None:
    """Return the compliance mappings dict for product_key, or None if no match.

    Only exact product_key lookups are performed -- no wildcards.
    The returned dict contains keys for each supported framework with
    lists of control IDs.
    """
    mappings = master.get("product_mappings", {})
    entry = mappings.get(product_key)
    if not entry:
        return None
    # Ensure all supported frameworks present (even if empty)
    return {fw: list(entry.get(fw, [])) for fw in SUPPORTED_FRAMEWORKS}


def handle(
    rule_path: Path,
    rule_data: dict,
    ew: EvidenceWriter,
    sm: StateManager,
    lock: LockManager,
    *,
    master_path: Path | None = None,
) -> tuple[bool, dict, dict]:
    """Execute cycle 6 compliance framework mapping enrichment.

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

    mappings = lookup_compliance_mappings(product_key, master)
    if mappings is None:
        sm.mark_cycle_skipped(
            rule_path, CYCLE_ID,
            f"no compliance mappings for product_key={product_key}",
        )
        return False, {}, {
            "skipped": True,
            "reason": "no_match",
            "product_key": product_key,
        }

    # Tally controls across frameworks for summary
    total_controls = sum(len(v) for v in mappings.values())

    rule_sha_before = sha256_file(rule_path)

    rule_after = dict(rule_data)
    rule_after["compliance_mappings"] = mappings
    meta = rule_after.get("_meta_enrichment", {})
    meta_cycle = {
        "applied_at": utc_now_iso(),
        "evidence_path": None,
        "evidence_sha256": None,
        "product_key": product_key,
        "frameworks": list(SUPPORTED_FRAMEWORKS),
        "controls_count": total_controls,
        "per_framework_count": {fw: len(mappings[fw]) for fw in SUPPORTED_FRAMEWORKS},
        "master_generated_at": master.get("generated_at"),
        "master_schema": master.get("$schema"),
    }
    meta[CYCLE_ID] = meta_cycle
    rule_after["_meta_enrichment"] = meta

    master_sha = _compute_master_sha256(mp)
    source_meta = {
        "type": "manual",
        "master_path": str(mp),
        "master_schema": master.get("$schema"),
        "master_generated_at": master.get("generated_at"),
        "master_sha256": master_sha,
        "frameworks": list(SUPPORTED_FRAMEWORKS),
        "executed_at": utc_now_iso(),
    }
    applied_diff = {
        "added_keys": ["compliance_mappings"],
        "added_value": {"compliance_mappings": mappings},
    }
    summary = {
        "product_key": product_key,
        "total_controls": total_controls,
        "per_framework": {fw: len(mappings[fw]) for fw in SUPPORTED_FRAMEWORKS},
        "frameworks_enriched": [fw for fw in SUPPORTED_FRAMEWORKS if mappings[fw]],
    }

    ev_path, ev_sha = ew.write(
        rule_path=rule_path,
        cycle_id=CYCLE_ID,
        rule_data=rule_data,
        rule_sha256_before=rule_sha_before,
        rule_sha256_after="pending",
        source_meta=source_meta,
        raw_data=mappings,
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


def _compute_master_sha256(master_path: Path) -> str:
    """Return hex SHA-256 of the master JSON file."""
    import hashlib
    data = master_path.read_bytes()
    return hashlib.sha256(data).hexdigest()


__all__ = [
    "CYCLE_ID",
    "SUPPORTED_FRAMEWORKS",
    "handle",
    "lookup_compliance_mappings",
    "_build_product_key",
]
