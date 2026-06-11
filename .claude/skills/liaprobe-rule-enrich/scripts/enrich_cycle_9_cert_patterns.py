"""
Cycle 9 -- TLS X.509 certificate pattern enrichment.

Source: master_data/cert_patterns_master.json -- per-pattern source_url + sha256
verified against vendor docs (OpenSSL config, Let's Encrypt CA chain page,
Kubernetes DNS doc, Synology DSM docs, VMware vSphere docs).

Output: rule.certificate_patterns = [
    {
        pattern_id, name, severity, confidence, match: {...},
        source_url, source_sha256, source_section, verified_at, ...
    },
    ...
]

Match strategy:
1. Build product_key from cpe23_template parts 3+4 (vendor/product)
2. Lookup master.products[product_key] for product-specific patterns
3. Lookup master.products["{vendor}/*"] for vendor wildcard
4. Lookup master.products["*/*"] for universal patterns (OpenSSL default DN, Let's Encrypt)
5. Resolve pattern_ids to full pattern objects from master.pattern_definitions
6. De-duplicate by pattern_id
7. Inject into rule.certificate_patterns

LiaProbe scanner uses these patterns at runtime via tls_subject / tls_issuer
matchers (Bug A activated targets) to flag passive product/deployment signals
in the TLS handshake.
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


CYCLE_ID = "cycle_9_cert_patterns"
MAX_PATTERNS = 25  # cap injection per-rule (protect rule size)


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
    return find_tracking_root() / "master_data" / "cert_patterns_master.json"


def _load_master(master_path: Path) -> dict:
    if not master_path.exists():
        raise DependencyMissingError(
            f"cert_patterns_master.json not found at {master_path}"
        )
    return json.loads(master_path.read_text(encoding="utf-8"))


def lookup_pattern_ids(product_key: str, master: dict) -> list[str]:
    """Return ordered, de-duplicated list of pattern_ids that apply to product_key.

    Lookup order:
    1. exact product_key (e.g. "vmware/vmware_esxi_server")
    2. vendor wildcard (e.g. "synology/*")
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
        entry = products.get(ck)
        if entry is None:
            continue
        # Schema variants: legacy = list of pattern_ids; v2 = dict with "patterns" list
        pids = entry if isinstance(entry, list) else entry.get("patterns", [])
        for pid in pids:
            if pid not in seen:
                seen.add(pid)
                out.append(pid)

    return out[:MAX_PATTERNS]


def resolve_patterns(pattern_ids: list[str], master: dict) -> list[dict]:
    """Resolve pattern_ids to full pattern dicts from master.pattern_definitions."""
    defs = master.get("pattern_definitions", {})
    out: list[dict] = []
    for pid in pattern_ids:
        if pid in defs:
            entry = dict(defs[pid])
            entry["pattern_id"] = pid
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
    """Execute cycle 9 certificate pattern enrichment.

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

    pattern_ids = lookup_pattern_ids(product_key, master)
    if not pattern_ids:
        sm.mark_cycle_skipped(
            rule_path, CYCLE_ID,
            f"no certificate patterns for product_key={product_key}",
        )
        return False, {}, {
            "skipped": True,
            "reason": "no_match",
            "product_key": product_key,
        }

    patterns = resolve_patterns(pattern_ids, master)
    if not patterns:
        sm.mark_cycle_skipped(
            rule_path, CYCLE_ID,
            f"pattern_ids resolved to empty (master.pattern_definitions inconsistent)",
        )
        return False, {}, {
            "skipped": True,
            "reason": "empty_resolution",
            "pattern_ids": pattern_ids,
        }

    rule_sha_before = sha256_file(rule_path)

    rule_after = dict(rule_data)
    rule_after["certificate_patterns"] = patterns
    meta = rule_after.get("_meta_enrichment", {})
    meta_cycle = {
        "applied_at": utc_now_iso(),
        "evidence_path": None,
        "evidence_sha256": None,
        "product_key": product_key,
        "patterns_count": len(patterns),
        "pattern_ids": pattern_ids,
        "master_generated_at": master.get("generated_at"),
    }
    meta[CYCLE_ID] = meta_cycle
    rule_after["_meta_enrichment"] = meta

    source_ids_used = sorted(set(p.get("source_id", "unknown") for p in patterns))
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
        "patterns_by_source": {
            sid: sum(1 for p in patterns if p.get("source_id") == sid)
            for sid in source_ids_used
        },
        "executed_at": utc_now_iso(),
    }
    applied_diff = {
        "added_keys": ["certificate_patterns"],
        "added_value": {"certificate_patterns": patterns},
    }
    summary = {
        "product_key": product_key,
        "patterns_count": len(patterns),
        "pattern_ids": pattern_ids,
        "source_ids_used": source_ids_used,
        "max_severity": _max_severity(patterns),
    }

    ev_path, ev_sha = ew.write(
        rule_path=rule_path,
        cycle_id=CYCLE_ID,
        rule_data=rule_data,
        rule_sha256_before=rule_sha_before,
        rule_sha256_after="pending",
        source_meta=source_meta,
        raw_data=patterns,
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


def _max_severity(patterns: list[dict]) -> str:
    """Return the highest severity present in the patterns list."""
    order = {"info": 0, "low": 1, "medium": 2, "high": 3, "critical": 4}
    best = "info"
    best_n = 0
    for p in patterns:
        sev = (p.get("severity") or "info").lower()
        n = order.get(sev, 0)
        if n > best_n:
            best_n = n
            best = sev
    return best


__all__ = [
    "CYCLE_ID",
    "handle",
    "lookup_pattern_ids",
    "resolve_patterns",
    "_build_product_key",
    "MAX_PATTERNS",
]
