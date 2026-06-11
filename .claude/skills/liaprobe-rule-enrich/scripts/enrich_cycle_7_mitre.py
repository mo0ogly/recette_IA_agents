"""
Cycle 7 -- MITRE ATT&CK + D3FEND mapping enrichment.

Source: PostgreSQL `cve_attack_mapping` (technique_name embedded since
mitre_techniques table is empty per PRECONDITIONS V1).

Depends on: cycle 4 CVE (need known_cves[] populated).

Output: rule.attack_surface = {techniques: [...], tactics: [...]}.
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
    PGClient,
    StateManager,
    sha256_file,
    utc_now_iso,
)


CYCLE_ID = "cycle_7_mitre"
MAX_TECHNIQUES = 30


MITRE_QUERY = """
SELECT DISTINCT
  technique_id,
  technique_short_id,
  technique_name
FROM cve_attack_mapping
WHERE cve_id = ANY(%(cve_ids)s)
ORDER BY technique_short_id
LIMIT %(limit)s;
"""


def fetch_techniques(cve_ids: list[str], pg: PGClient | None = None) -> list[dict]:
    if not cve_ids:
        return []
    pg_owned = pg is None
    if pg_owned:
        pg = PGClient()
        pg.__enter__()
    try:
        return pg.query(MITRE_QUERY, {"cve_ids": cve_ids, "limit": MAX_TECHNIQUES})
    finally:
        if pg_owned:
            pg.__exit__(None, None, None)


def handle(
    rule_path: Path,
    rule_data: dict,
    ew: EvidenceWriter,
    sm: StateManager,
    lock: LockManager,
    *,
    pg: PGClient | None = None,
) -> tuple[bool, dict, dict]:
    cves = rule_data.get("known_cves") or []
    cve_ids = [c.get("cve_id") for c in cves if c.get("cve_id")]
    if not cve_ids:
        sm.mark_cycle_skipped(rule_path, CYCLE_ID, "no known_cves[] populated (run cycle 4 first)")
        return False, {}, {"skipped": True, "reason": "no_cves"}

    try:
        rows = fetch_techniques(cve_ids, pg=pg)
    except DependencyMissingError as e:
        sm.mark_cycle_skipped(rule_path, CYCLE_ID, f"PG unavailable: {e}")
        return False, {}, {"skipped": True, "reason": "pg_down"}

    if not rows:
        sm.mark_cycle_skipped(rule_path, CYCLE_ID, "0 ATT&CK technique mapped from CVE list")
        return False, {}, {"skipped": True, "reason": "no_match"}

    techniques = []
    for r in rows:
        techniques.append({
            "id": r.get("technique_short_id") or r.get("technique_id"),
            "stix_id": r.get("technique_id"),
            "name": r.get("technique_name"),
        })

    rule_sha_before = sha256_file(rule_path)
    attack_surface = {
        "data_source": "cve_attack_mapping",
        "techniques": techniques,
        "techniques_count": len(techniques),
        "cve_source_count": len(cve_ids),
    }

    rule_after = dict(rule_data)
    rule_after["attack_surface"] = attack_surface
    meta = rule_after.get("_meta_enrichment", {})
    meta[CYCLE_ID] = {
        "applied_at": utc_now_iso(),
        "evidence_path": None,
        "evidence_sha256": None,
        "techniques_count": len(techniques),
        "cve_source_count": len(cve_ids),
    }
    rule_after["_meta_enrichment"] = meta

    source_meta = {
        "type": "postgresql",
        "database": "lia_scan",
        "query_template": "SELECT DISTINCT technique_id, technique_short_id, technique_name FROM cve_attack_mapping WHERE cve_id = ANY(:cve_ids) LIMIT :limit",
        "query_params": {"cve_count": len(cve_ids), "limit": MAX_TECHNIQUES},
        "result_count": len(rows),
        "executed_at": utc_now_iso(),
    }
    applied_diff = {
        "added_keys": ["attack_surface"],
        "added_value": {"attack_surface": attack_surface},
    }
    summary = {
        "techniques_count": len(techniques),
        "cve_source_count": len(cve_ids),
    }

    ev_path, ev_sha = ew.write(
        rule_path=rule_path,
        cycle_id=CYCLE_ID,
        rule_data=rule_data,
        rule_sha256_before=rule_sha_before,
        rule_sha256_after="pending",
        source_meta=source_meta,
        raw_data=rows,
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


__all__ = ["CYCLE_ID", "handle", "fetch_techniques", "MITRE_QUERY"]
