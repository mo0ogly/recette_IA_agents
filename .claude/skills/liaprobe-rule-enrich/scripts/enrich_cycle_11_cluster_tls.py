"""
Cycle 11 -- Cluster topology + JARM Phase 1 enrichment.

Source: master_data/cluster_topology_master.json (11 products with single-GET
discovery endpoints sourced from official vendor docs with per-entry sha256).

Output: rule.cluster_topology = {
    discovery_endpoints[]: list of {method, path, expected_keys, interpretation},
    anomaly_indicators[]: list of strings,
    request_discipline: "single_request_only",
    enumeration_forbidden: bool,
    source_url, source_sha256, verified_at
}

Plus rule.jarm_signatures section (Phase 1 placeholder, populated in Phase 2 once
active TLS probe lands and lab observations are recorded). The tls_jarm matcher
target is already activated by Bug B fix in pkg/fingerprint/{loader,matcher}.go.

Match strategy:
1. Build product_key from cpe23_template parts 3+4 (vendor/product)
2. Lookup master.products[product_key]
3. Resolve definition_ids to full topology blocks via master.definitions
4. Inject into rule.cluster_topology + jarm_signatures (placeholder)

R4 anti-abuse: data is INFORMATIVE. LiaProbe scanner does NOT enumerate cluster
members aggressively (request_discipline=single_request_only). The auditor's
ROE governs whether to follow up with deeper API calls.
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


CYCLE_ID = "cycle_11_cluster_tls"


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
    return find_tracking_root() / "master_data" / "cluster_topology_master.json"


def _load_master(master_path: Path) -> dict:
    if not master_path.exists():
        raise DependencyMissingError(
            f"cluster_topology_master.json not found at {master_path}"
        )
    return json.loads(master_path.read_text(encoding="utf-8"))


def lookup_definition_ids(product_key: str, master: dict) -> list[str]:
    """Return ordered definition_ids for a product_key (no wildcards for cluster)."""
    products = master.get("products", {})
    return list(products.get(product_key, []))


def resolve_definitions(definition_ids: list[str], master: dict) -> list[dict]:
    """Resolve definition_ids to full topology blocks from master.definitions."""
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
    """Execute cycle 11 cluster topology enrichment.

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
            f"no cluster topology for product_key={product_key}",
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
    rule_after["cluster_topology"] = definitions
    # Phase 1 JARM placeholder -- populated in Phase 2 once active probe + lab
    # observations land. Bug B already activated the tls_jarm matcher target.
    rule_after["jarm_signatures"] = {
        "phase": "1",
        "status": "placeholder",
        "lab_verify_required": True,
        "note": "Active JARM probe deferred to cycle 11 Phase 2",
    }

    meta = rule_after.get("_meta_enrichment", {})
    meta_cycle = {
        "applied_at": utc_now_iso(),
        "evidence_path": None,
        "evidence_sha256": None,
        "product_key": product_key,
        "definitions_count": len(definitions),
        "definition_ids": definition_ids,
        "jarm_phase": "1_placeholder",
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
        "added_keys": ["cluster_topology", "jarm_signatures"],
        "added_value": {
            "cluster_topology": definitions,
            "jarm_signatures": rule_after["jarm_signatures"],
        },
    }
    summary = {
        "product_key": product_key,
        "definitions_count": len(definitions),
        "definition_ids": definition_ids,
        "endpoints_count": sum(
            len(d.get("discovery_endpoints", [])) for d in definitions
        ),
        "has_anomaly_indicators": any(
            d.get("anomaly_indicators") for d in definitions
        ),
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
]
