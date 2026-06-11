"""
Cycle 10 -- HTTP behavior signals enrichment.

Source: master_data/behavior_master.json (6 definitions sourced from Apache HTTPD,
nginx, IIS, Tomcat docs + RFC 9110/9113/6265 with per-entry sha256).

Output: rule.http_behavior = [
    {
        definition_id, name, signals[]: list of {signal_id, type, ...},
        source_url, source_sha256, source_section, verified_at
    },
    ...
]

Match strategy:
1. Build product_key from cpe23_template (parts 3+4)
2. Lookup master.products[product_key] then "*/*" universal
3. Resolve definition_ids -> full blocks via master.definitions
4. De-duplicate
5. Inject into rule.http_behavior

Phase 1 = metadata + handler. Phase 2 (deferred) = HeaderOrder []string field
in HTTPProbeResponse Go-side (model.go) + behavior-aware matcher target.
Without Phase 2, the scanner has the metadata but cannot actively match against
header_order or 404_hash signals -- it serves as enrichment for downstream
auditor analytics.

R4 anti-abuse: data is INFORMATIVE. The scanner does not aggressively probe
malformed methods or fuzz endpoints; only metadata is attached.
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


CYCLE_ID = "cycle_10_behavior"
MAX_DEFINITIONS = 10  # cap injection per-rule (protect rule size)


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
    return find_tracking_root() / "master_data" / "behavior_master.json"


def _load_master(master_path: Path) -> dict:
    if not master_path.exists():
        raise DependencyMissingError(
            f"behavior_master.json not found at {master_path}"
        )
    return json.loads(master_path.read_text(encoding="utf-8"))


def lookup_definition_ids(product_key: str, master: dict) -> list[str]:
    """Return ordered, de-duplicated definition_ids for product_key.

    Lookup order: exact, vendor wildcard, universal "*/*".
    """
    products = master.get("products", {})
    seen: set[str] = set()
    out: list[str] = []

    candidates: list[str] = [product_key]
    if "/" in product_key:
        vendor, _ = product_key.split("/", 1)
        candidates.append(f"{vendor}/*")
    candidates.append("*/*")

    for ck in candidates:
        for did in products.get(ck, []):
            if did not in seen:
                seen.add(did)
                out.append(did)

    return out[:MAX_DEFINITIONS]


def resolve_definitions(definition_ids: list[str], master: dict) -> list[dict]:
    """Resolve definition_ids to full blocks from master.definitions."""
    defs = master.get("definitions", {})
    out: list[dict] = []
    for did in definition_ids:
        if did in defs:
            entry = dict(defs[did])
            entry["definition_id"] = did
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
    """Execute cycle 10 HTTP behavior enrichment.

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

    definition_ids = lookup_definition_ids(product_key, master)
    if not definition_ids:
        sm.mark_cycle_skipped(
            rule_path, CYCLE_ID,
            f"no http behavior definitions for product_key={product_key}",
        )
        return False, {}, {
            "skipped": True,
            "reason": "no_match",
            "product_key": product_key,
        }

    definitions = resolve_definitions(definition_ids, master)
    if not definitions:
        sm.mark_cycle_skipped(
            rule_path, CYCLE_ID,
            "definition_ids resolved to empty (master inconsistent)",
        )
        return False, {}, {
            "skipped": True,
            "reason": "empty_resolution",
            "definition_ids": definition_ids,
        }

    rule_sha_before = sha256_file(rule_path)

    rule_after = dict(rule_data)
    rule_after["http_behavior"] = definitions

    meta = rule_after.get("_meta_enrichment", {})
    meta_cycle = {
        "applied_at": utc_now_iso(),
        "evidence_path": None,
        "evidence_sha256": None,
        "product_key": product_key,
        "definitions_count": len(definitions),
        "definition_ids": definition_ids,
        "phase": "1_metadata_only",
        "go_schema_patch_required": True,
        "go_schema_patch_status": "deferred_phase_2",
        "master_generated_at": master.get("generated_at"),
    }
    meta[CYCLE_ID] = meta_cycle
    rule_after["_meta_enrichment"] = meta

    source_meta = {
        "type": "manual",
        "master_path": str(
            mp.relative_to(find_tracking_root().parent.parent)
            if str(mp).startswith(str(find_tracking_root().parent.parent))
            else mp
        ),
        "master_schema": master.get("$schema"),
        "master_generated_at": master.get("generated_at"),
        "executed_at": utc_now_iso(),
    }
    applied_diff = {
        "added_keys": ["http_behavior"],
        "added_value": {"http_behavior": definitions},
    }
    signals_count = sum(len(d.get("signals", [])) for d in definitions)
    summary = {
        "product_key": product_key,
        "definitions_count": len(definitions),
        "definition_ids": definition_ids,
        "signals_count": signals_count,
    }

    ev_path, ev_sha = ew.write(
        rule_path=rule_path,
        cycle_id=CYCLE_ID,
        rule_data=rule_data,
        rule_sha256_before=rule_sha_before,
        rule_sha256_after="pending",
        source_meta=source_meta,
        raw_data=definitions,
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
    "lookup_definition_ids",
    "resolve_definitions",
    "_build_product_key",
    "MAX_DEFINITIONS",
]
