"""
Cycle 4 -- CVE awareness enrichment.

Source: PostgreSQL LIA-SEC `lia_scan` DB.
Tables: cve_nvd_data, cve_product, product, kev_cisa_vulnerabilities.

Output: rule.known_cves[] = [{cve_id, severity, cvss_v3, published, in_kev,
                              kev_date_added, ...}, ...]

Schema verified in PRECONDITIONS.md V1 (2026-05-02).
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from enrich_lib import (
    AtomicJSONWriter,
    DependencyMissingError,
    EnrichError,
    EvidenceWriter,
    LockManager,
    PGClient,
    StateManager,
    sha256_file,
    utc_now_iso,
)


CYCLE_ID = "cycle_4_cve"
MAX_CVES = 50


# Cheap existence probe: does the product table know this CPE at all?
# Distinguishes "dead product, not in NVD corpus" (no_nvd_entry) from
# "product exists but currently zero CVE" (no_match).
PRODUCT_PROBE_QUERY = """
SELECT 1
FROM product p
WHERE p.cpe23_uri LIKE %(cpe_pattern)s
LIMIT 1;
"""


CVE_QUERY = """
SELECT
  c.cve_id,
  c.cvss_severity AS severity,
  c.cvss_score AS cvss_v3,
  c.published_date,
  c.cwe_ids,
  (k.cve_id IS NOT NULL) AS in_kev,
  k.date_added::text AS kev_date_added,
  k.known_ransomware_use AS kev_ransomware
FROM cve_nvd_data c
JOIN cve_product cp ON cp.cve_id = c.cve_id
JOIN product p ON p.product_id = cp.product_id
LEFT JOIN kev_cisa_vulnerabilities k ON k.cve_id = c.cve_id
WHERE p.cpe23_uri LIKE %(cpe_pattern)s
  AND c.cve_state NOT ILIKE 'reject%%'
ORDER BY (k.cve_id IS NOT NULL) DESC, c.cvss_score DESC NULLS LAST
LIMIT %(limit)s;
"""


def _cpe_part(cpe: str) -> str | None:
    """Extract the CPE part letter (a/o/h) from a 2.3 or 2.2 URI.

    cpe:2.3:a:vendor:product:...  -> 'a'
    cpe:/o:vendor:product...      -> 'o'  (legacy CPE 2.2)
    Returns None when the string is not a recognizable CPE.
    """
    if not cpe:
        return None
    if cpe.startswith("cpe:2.3:"):
        parts = cpe.split(":")
        if len(parts) >= 3 and parts[2] in ("a", "o", "h"):
            return parts[2]
        return None
    if cpe.startswith("cpe:/"):
        # CPE 2.2: cpe:/<part>:vendor:product:...
        tail = cpe[len("cpe:/"):]
        if tail[:2] in ("o:", "a:", "h:"):
            return tail[0]
    return None


def _build_cpe_pattern(rule: dict) -> str | None:
    """Build LIKE pattern from cpe23_template.

    cpe:2.3:a:vendor:product:{version}:* -> cpe:2.3:a:vendor:product:%
    Only CPE 2.3 application/hardware parts produce a usable pattern; OS-host
    (:o:) and legacy 2.2 URIs return None (classified upstream in handle()).
    """
    cpe = rule.get("cpe23_template", "")
    if not cpe or not cpe.startswith("cpe:2.3:"):
        return None
    parts = cpe.split(":")
    if len(parts) < 5:
        return None
    return f"cpe:2.3:{parts[2]}:{parts[3]}:{parts[4]}:%"


def probe_product_exists(cpe_pattern: str, pg: PGClient) -> bool:
    """True when the product table holds at least one row for this CPE pattern."""
    rows = pg.query(PRODUCT_PROBE_QUERY, {"cpe_pattern": cpe_pattern})
    return bool(rows)


def _row_to_cve_entry(row: dict) -> dict:
    entry: dict[str, Any] = {
        "cve_id": row.get("cve_id"),
        "severity": row.get("severity") or "UNKNOWN",
    }
    if row.get("cvss_v3") is not None:
        try:
            entry["cvss_v3"] = float(row["cvss_v3"])
        except (TypeError, ValueError):
            pass
    if row.get("published_date") is not None:
        pd = row["published_date"]
        if hasattr(pd, "isoformat"):
            entry["published"] = pd.isoformat()
        else:
            entry["published"] = str(pd)
    if row.get("cwe_ids"):
        entry["cwe_ids"] = list(row["cwe_ids"])
    if row.get("in_kev"):
        entry["cisa_kev"] = True
        if row.get("kev_date_added"):
            entry["kev_date_added"] = row["kev_date_added"]
        if row.get("kev_ransomware"):
            entry["kev_ransomware_use"] = bool(row["kev_ransomware"])
    return entry


def fetch_cves(cpe_pattern: str, pg: PGClient | None = None) -> list[dict]:
    """Query PG for CVEs matching CPE LIKE pattern."""
    pg_owned = pg is None
    if pg_owned:
        pg = PGClient()
        pg.__enter__()
    try:
        rows = pg.query(CVE_QUERY, {"cpe_pattern": cpe_pattern, "limit": MAX_CVES})
        return rows
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
    """Execute cycle 4 CVE enrichment.

    Skip reasons (richer than legacy no_cpe/no_match, see RETEX wave 6):
      no_cpe         : rule has no cpe23_template at all
      cpe_part_os    : CPE part is :o: (OS host) -- misattribution risk, NOT a
                       product CPE. Flagged needs_cpe_correction=True so a later
                       pass (or a human) can rewrite it to an :a:/:h: product CPE
                       (incident class: QTSS shipped cpe:/o:apple:mac_os_x).
      cpe_unparseable: CPE present but not a usable 2.3 :a:/:h: pattern
                       (e.g. legacy 2.2 URI) -- needs_cpe_correction=True.
      no_nvd_entry   : usable CPE but the product table has NO row for it ->
                       dead/niche product absent from the NVD corpus
                       (dead_product_candidate=True). Nothing to enrich without
                       fabrication (R4) -- distinct from no_match.
      no_match       : product exists in NVD corpus but currently zero CVE.
      pg_down        : PostgreSQL unreachable.
    """
    cpe = rule_data.get("cpe23_template", "")
    if not cpe:
        sm.mark_cycle_skipped(rule_path, CYCLE_ID, "no cpe23_template in rule")
        return False, {}, {"skipped": True, "reason": "no_cpe"}

    part = _cpe_part(cpe)
    if part == "o":
        sm.mark_cycle_skipped(
            rule_path, CYCLE_ID, f"CPE part :o: (OS host) -- needs correction: {cpe}"
        )
        return False, {}, {
            "skipped": True, "reason": "cpe_part_os",
            "cpe": cpe, "needs_cpe_correction": True,
        }

    cpe_pattern = _build_cpe_pattern(rule_data)
    if not cpe_pattern:
        sm.mark_cycle_skipped(
            rule_path, CYCLE_ID, f"CPE not a usable 2.3 a/h pattern: {cpe}"
        )
        return False, {}, {
            "skipped": True, "reason": "cpe_unparseable",
            "cpe": cpe, "needs_cpe_correction": True,
        }

    # Share a single PG connection across the existence probe + CVE fetch.
    pg_owned = pg is None
    if pg_owned:
        try:
            pg = PGClient()
            pg.__enter__()
        except DependencyMissingError as e:
            sm.mark_cycle_skipped(rule_path, CYCLE_ID, f"PG unavailable: {e}")
            return False, {}, {"skipped": True, "reason": "pg_down", "error": str(e)}
    try:
        try:
            product_known = probe_product_exists(cpe_pattern, pg)
            rows = fetch_cves(cpe_pattern, pg=pg)
        except DependencyMissingError as e:
            sm.mark_cycle_skipped(rule_path, CYCLE_ID, f"PG unavailable: {e}")
            return False, {}, {"skipped": True, "reason": "pg_down", "error": str(e)}
    finally:
        if pg_owned and pg is not None:
            pg.__exit__(None, None, None)
            pg = None

    if not rows:
        if not product_known:
            sm.mark_cycle_skipped(
                rule_path, CYCLE_ID,
                f"product absent from NVD corpus for {cpe_pattern}"
            )
            return False, {}, {
                "skipped": True, "reason": "no_nvd_entry",
                "cpe": cpe_pattern, "dead_product_candidate": True,
            }
        sm.mark_cycle_skipped(rule_path, CYCLE_ID, f"0 CVE matched for {cpe_pattern}")
        return False, {}, {"skipped": True, "reason": "no_match", "cpe": cpe_pattern}

    known_cves = [_row_to_cve_entry(r) for r in rows]
    rule_sha_before = sha256_file(rule_path)

    rule_after = dict(rule_data)
    rule_after["known_cves"] = known_cves
    meta = rule_after.get("_meta_enrichment", {})
    meta[CYCLE_ID] = {
        "applied_at": utc_now_iso(),
        "evidence_path": None,
        "evidence_sha256": None,
        "cpe_pattern": cpe_pattern,
        "cve_count": len(known_cves),
    }
    rule_after["_meta_enrichment"] = meta

    raw_data_serializable = []
    for r in rows:
        entry: dict[str, Any] = {}
        for k, v in r.items():
            if hasattr(v, "isoformat"):
                entry[k] = v.isoformat()
            else:
                entry[k] = v
        raw_data_serializable.append(entry)

    source_meta = {
        "type": "postgresql",
        "database": "lia_scan",
        "query_template": "cve_nvd_data JOIN cve_product JOIN product LEFT JOIN kev_cisa_vulnerabilities WHERE cpe23_uri LIKE :cpe AND cve_state NOT ILIKE 'reject%' ORDER BY in_kev DESC, cvss_score DESC LIMIT :limit",
        "query_params": {"cpe_pattern": cpe_pattern, "limit": MAX_CVES},
        "result_count": len(rows),
        "executed_at": utc_now_iso(),
    }
    applied_diff = {
        "added_keys": ["known_cves"],
        "added_value": {"known_cves": known_cves},
    }
    summary = {
        "cpe_pattern": cpe_pattern,
        "cve_count": len(known_cves),
        "kev_count": sum(1 for c in known_cves if c.get("cisa_kev")),
        "max_cvss": max((c.get("cvss_v3") or 0) for c in known_cves) if known_cves else 0,
        "critical_count": sum(1 for c in known_cves if (c.get("cvss_v3") or 0) >= 9.0),
    }

    ev_path, ev_sha = ew.write(
        rule_path=rule_path,
        cycle_id=CYCLE_ID,
        rule_data=rule_data,
        rule_sha256_before=rule_sha_before,
        rule_sha256_after="pending",
        source_meta=source_meta,
        raw_data=raw_data_serializable,
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
    "fetch_cves",
    "probe_product_exists",
    "_build_cpe_pattern",
    "_cpe_part",
    "_row_to_cve_entry",
    "CVE_QUERY",
    "PRODUCT_PROBE_QUERY",
]
