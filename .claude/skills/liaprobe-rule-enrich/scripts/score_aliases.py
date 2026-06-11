#!/usr/bin/env python3
"""
score_aliases -- Score proposed vendor aliases before INSERT.

Reads a proposals JSON file describing candidate vendor_alias rows, queries
PostgreSQL for evidence (vendor existence, product count, CVE count, pg_trgm
similarity), computes the four-component score (source / match / evidence /
penalty), assigns a decision (apply / review / defer / reject), and persists
the trail in vendor_alias_score.

Optionally: if --apply is set, the script INSERTs only the rows whose
decision == 'apply' into vendor_alias and links them back via alias_id.

Rubric source: _alire/tracking/liaprobe-enrich-v2/recettes/pilot_50_kev_2026-05-03/
brainstorm_phase_f/agent6_adversarial_report.md (Phase F adversarial verdict).

Usage:
    python3 score_aliases.py --proposals proposals.json --wave-id phase_f1
    python3 score_aliases.py --proposals proposals.json --wave-id phase_f1 --apply

Proposals JSON shape:
    {
      "wave_id": "phase_f1",
      "phase": "phase_f1",
      "operator": "user",
      "proposals": [
        {
          "alias_name": "Various",
          "vendor_name": "lia-meta",
          "source_label": "manual_curation",
          "match_label": "exact_lower",
          "alias_type": "community",
          "rule_file": "EOL_DETECT.json",
          "rationale": "Multi-vendor EOL probe dispatcher",
          "source_url": null,
          "source_sha256": null,
          "penalty_label": "low_info_generic"
        },
        ...
      ]
    }

Exit codes (via EnrichError subclasses):
    0  success
    2  invalid input (missing file, malformed JSON)
    3  PG dependency missing or failure
    7  scoring rejected too many proposals (>50% reject) -- audit needed
"""
from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

# enrich_lib is co-located in this scripts directory
SCRIPT_DIR = Path(__file__).resolve().parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

from enrich_lib import (  # noqa: E402
    DependencyMissingError,
    EnrichError,
    InvalidInputError,
    PGClient,
    utc_now_iso,
)


# ======================================================================
# Scoring rubric (sourced from agent6_adversarial_report.md)
# ======================================================================

SOURCE_WEIGHTS: dict[str, float] = {
    "vendor_docs":       1.00,
    "nvd_cpe_direct":    0.95,
    "mitre_stix":        0.90,
    "cisa_kev":          0.85,
    "github_org":        0.85,
    "manual_curation":   0.70,
    "fuzzy_pgtrgm":      0.55,
    "community":         0.40,
    "lia_internal":      0.30,
}

MATCH_WEIGHTS: dict[str, float] = {
    "exact_lower":       1.00,
    "alias_known":       0.90,
    "fuzzy_high":        0.75,   # similarity >= 0.85
    "fuzzy_medium":      0.50,   # similarity >= 0.70
    "fuzzy_low":         0.20,   # similarity <  0.70
}

PENALTY_WEIGHTS: dict[str, float] = {
    "clean":             1.00,
    "brand_confusion":   0.60,
    "white_label_oem":   0.40,
    "low_info_generic":  0.20,
    "personal_author":   0.50,
}

WEIGHT_SOURCE   = 0.35
WEIGHT_MATCH    = 0.25
WEIGHT_EVIDENCE = 0.25
WEIGHT_PENALTY  = 0.15

DECISION_APPLY   = 0.85
DECISION_REVIEW  = 0.65
DECISION_DEFER   = 0.40

# Wave verdict scoring weights (calibrated from F1+F2 retex 2026-05-04).
# Earlier weights 0.40 / 0.40 / 0.20 capped warmup waves at PARTIAL even with
# perfect FP/regression. Rebalanced to value quality (FP) over volume so a
# small wave that ships 0 false-positives can earn GO.
WAVE_WEIGHT_CLOSURE     = 0.20
WAVE_WEIGHT_FP_INVERSE  = 0.50
WAVE_WEIGHT_REGRESSION  = 0.30

WAVE_VERDICT_GO_MIN      = 0.70
WAVE_VERDICT_PARTIAL_MIN = 0.50

# Synthetic vendor namespace prefix (R13 + lia-meta migration 150). Aliases
# whose target vendor has this prefix are allowed to bypass the standard
# apply threshold IFF --allow-synthetic is set on the CLI. They still leave
# a full audit trail row in vendor_alias_score.
SYNTHETIC_VENDOR_PREFIX = "lia-"

# pg_trgm similarity bands (mapped to match_label when caller did not set it)
SIMILARITY_HIGH   = 0.85
SIMILARITY_MEDIUM = 0.70


def evidence_score_from_counts(product_count: int, cve_count: int) -> tuple[float, str]:
    """Map NVD product/CVE counts into evidence score + label."""
    if product_count is None:
        return 0.20, "no_evidence"
    if product_count >= 10:
        return 1.00, "products_ge_10"
    if product_count >= 3:
        return 0.80, "products_3_to_9"
    if product_count >= 1:
        return 0.60, "products_1_to_2"
    return 0.20, "products_zero"


def map_match_label_from_similarity(similarity: float | None) -> str:
    if similarity is None:
        return "fuzzy_low"
    if similarity >= SIMILARITY_HIGH:
        return "fuzzy_high"
    if similarity >= SIMILARITY_MEDIUM:
        return "fuzzy_medium"
    return "fuzzy_low"


def decision_from_total(total: float) -> str:
    if total >= DECISION_APPLY:
        return "apply"
    if total >= DECISION_REVIEW:
        return "review"
    if total >= DECISION_DEFER:
        return "defer"
    return "reject"


# ======================================================================
# Evidence lookup
# ======================================================================

def lookup_vendor(pg: PGClient, vendor_name: str) -> dict[str, Any] | None:
    """Return {vendor_id, vendor_name, product_count, cve_count} or None.

    Case-insensitive lookup on `vendor.vendor_name`.
    """
    rows = pg.query(
        """
        SELECT v.vendor_id,
               v.vendor_name,
               (SELECT COUNT(*) FROM product p WHERE p.vendor_id = v.vendor_id)        AS product_count,
               (SELECT COUNT(DISTINCT cp.cve_id) FROM cve_product cp
                  JOIN product pp ON pp.product_id = cp.product_id
                  WHERE pp.vendor_id = v.vendor_id)                                     AS cve_count
        FROM vendor v
        WHERE LOWER(v.vendor_name) = LOWER(%s)
        LIMIT 1
        """,
        (vendor_name,),
    )
    if not rows:
        return None
    row = rows[0]
    # cve_count subquery may fail if cpe_match table absent in this snapshot;
    # treat NULL as "unknown" (0).
    if row.get("cve_count") is None:
        row["cve_count"] = 0
    return row


def fuzzy_similarity(pg: PGClient, alias_name: str, vendor_name: str) -> float | None:
    """Return pg_trgm similarity(alias_name, vendor_name) or None on failure."""
    try:
        rows = pg.query(
            "SELECT similarity(%s, %s) AS sim",
            (alias_name, vendor_name),
        )
    except DependencyMissingError:
        return None
    if not rows:
        return None
    val = rows[0].get("sim")
    return float(val) if val is not None else None


def existing_alias(pg: PGClient, alias_name: str) -> dict[str, Any] | None:
    """Detect duplicate alias to avoid INSERT conflict on lower(alias_name)."""
    rows = pg.query(
        "SELECT id, vendor_id FROM vendor_alias WHERE LOWER(alias_name) = LOWER(%s) LIMIT 1",
        (alias_name,),
    )
    return rows[0] if rows else None


# ======================================================================
# Scoring engine
# ======================================================================

def score_proposal(pg: PGClient, p: dict[str, Any]) -> dict[str, Any]:
    """Compute a full score record from a single proposal dict.

    Returns the row to be inserted into vendor_alias_score.
    """
    alias_name   = p["alias_name"]
    vendor_name  = p["vendor_name"]

    # 1. Source
    source_label = p.get("source_label") or "manual_curation"
    source_score = SOURCE_WEIGHTS.get(source_label, 0.50)

    # 2. Match (resolve via lookup + similarity if caller did not pre-set)
    vendor_row    = lookup_vendor(pg, vendor_name)
    similarity    = fuzzy_similarity(pg, alias_name, vendor_name)
    explicit_match = p.get("match_label")

    if explicit_match:
        match_label = explicit_match
    elif vendor_row and alias_name.lower() == vendor_row["vendor_name"].lower():
        match_label = "exact_lower"
    elif vendor_row:
        # Vendor exists but alias differs: rate by similarity
        match_label = map_match_label_from_similarity(similarity)
    else:
        # Vendor not found at all -> fuzzy_low at best
        match_label = "fuzzy_low"
    match_score = MATCH_WEIGHTS.get(match_label, 0.20)

    # 3. Evidence (product/CVE count)
    if vendor_row:
        product_count = int(vendor_row["product_count"])
        cve_count     = int(vendor_row["cve_count"])
    else:
        product_count = None
        cve_count     = None
    evidence_score, evidence_label = evidence_score_from_counts(
        product_count if product_count is not None else 0,
        cve_count if cve_count is not None else 0,
    )
    if vendor_row is None:
        evidence_label = "vendor_absent"
        evidence_score = 0.10

    # 4. Penalty
    penalty_label = p.get("penalty_label") or "clean"
    penalty_score = PENALTY_WEIGHTS.get(penalty_label, 0.50)

    # 5. Total
    total = (
        source_score   * WEIGHT_SOURCE
        + match_score    * WEIGHT_MATCH
        + evidence_score * WEIGHT_EVIDENCE
        + penalty_score  * WEIGHT_PENALTY
    )
    decision = decision_from_total(total)

    return {
        "proposed_alias_name":   alias_name,
        "proposed_vendor_id":    vendor_row["vendor_id"] if vendor_row else None,
        "proposed_vendor_name":  vendor_row["vendor_name"] if vendor_row else vendor_name,
        "source_score":          round(source_score, 4),
        "match_score":           round(match_score, 4),
        "evidence_score":        round(evidence_score, 4),
        "penalty_score":         round(penalty_score, 4),
        "total_score":           round(total, 4),
        "decision":              decision,
        "source_label":          source_label,
        "match_label":           match_label,
        "evidence_label":        evidence_label,
        "penalty_label":         penalty_label,
        "nvd_product_count":     product_count,
        "nvd_cve_count":         cve_count,
        "pgtrgm_similarity":     round(similarity, 4) if similarity is not None else None,
        "rule_file":             p.get("rule_file"),
        "rationale":             p.get("rationale"),
        "source_url":            p.get("source_url"),
        "source_sha256":         p.get("source_sha256"),
    }


def insert_score_row(pg: PGClient, row: dict[str, Any], wave_id: str) -> int:
    """Insert into vendor_alias_score, return generated id.

    UNIQUE (proposed_alias_name, proposed_vendor_id, wave_id) prevents dupes.
    """
    cur = pg._conn.cursor()
    cur.execute(
        """
        INSERT INTO vendor_alias_score (
            alias_id, proposed_alias_name, proposed_vendor_id, proposed_vendor_name,
            source_score, match_score, evidence_score, penalty_score, total_score,
            decision,
            source_label, match_label, evidence_label, penalty_label,
            nvd_product_count, nvd_cve_count, pgtrgm_similarity,
            rule_file, rationale, source_url, source_sha256,
            wave_id
        ) VALUES (
            NULL, %(proposed_alias_name)s, %(proposed_vendor_id)s, %(proposed_vendor_name)s,
            %(source_score)s, %(match_score)s, %(evidence_score)s, %(penalty_score)s, %(total_score)s,
            %(decision)s,
            %(source_label)s, %(match_label)s, %(evidence_label)s, %(penalty_label)s,
            %(nvd_product_count)s, %(nvd_cve_count)s, %(pgtrgm_similarity)s,
            %(rule_file)s, %(rationale)s, %(source_url)s, %(source_sha256)s,
            %(wave_id)s
        )
        ON CONFLICT (proposed_alias_name, proposed_vendor_id, wave_id) DO UPDATE SET
            source_score   = EXCLUDED.source_score,
            match_score    = EXCLUDED.match_score,
            evidence_score = EXCLUDED.evidence_score,
            penalty_score  = EXCLUDED.penalty_score,
            total_score    = EXCLUDED.total_score,
            decision       = EXCLUDED.decision,
            computed_at    = now()
        RETURNING id
        """,
        {**row, "wave_id": wave_id},
    )
    new_id = cur.fetchone()[0]
    pg._conn.commit()
    return int(new_id)


def insert_alias(pg: PGClient, p: dict[str, Any], score_row: dict[str, Any]) -> tuple[int | None, str]:
    """Insert into vendor_alias when decision == 'apply'.

    Returns (alias_id, status) where status is one of:
      "inserted"          -> new alias materialised, alias_id is the new row
      "duplicate_same"    -> existing alias points to the SAME proposed vendor_id
      "duplicate_other"   -> existing alias points to a DIFFERENT vendor_id (mismatch)
      "no_vendor"         -> proposed vendor not in vendor table

    Source whitelist enforced at the DB level: nvd_cpe / mitre_stix / cisa_kev
    / circl / manual / fuzzy_match. Caller proposals must use one of these.
    """
    if score_row["proposed_vendor_id"] is None:
        return None, "no_vendor"

    existing = existing_alias(pg, p["alias_name"])
    if existing is not None:
        if int(existing["vendor_id"]) == int(score_row["proposed_vendor_id"]):
            return int(existing["id"]), "duplicate_same"
        return int(existing["id"]), "duplicate_other"

    cur = pg._conn.cursor()
    cur.execute(
        """
        INSERT INTO vendor_alias (
            vendor_id, alias_name, alias_type, source, source_url,
            confidence_score, added_by
        ) VALUES (
            %s, %s, %s, %s, %s, %s, %s
        )
        ON CONFLICT (lower(alias_name)) DO NOTHING
        RETURNING id
        """,
        (
            score_row["proposed_vendor_id"],
            p["alias_name"],
            p.get("alias_type") or "community",
            p.get("vendor_alias_source") or "manual",
            p.get("source_url"),
            score_row["total_score"],
            p.get("operator") or "score_aliases.py",
        ),
    )
    new = cur.fetchone()
    pg._conn.commit()
    if new:
        return int(new[0]), "inserted"
    # Race condition: another process inserted between existing_alias() check
    # and our INSERT. Re-resolve.
    existing = existing_alias(pg, p["alias_name"])
    if existing is None:
        return None, "no_vendor"
    if int(existing["vendor_id"]) == int(score_row["proposed_vendor_id"]):
        return int(existing["id"]), "duplicate_same"
    return int(existing["id"]), "duplicate_other"


def link_score_to_alias(pg: PGClient, score_id: int, alias_id: int) -> None:
    cur = pg._conn.cursor()
    cur.execute(
        "UPDATE vendor_alias_score SET alias_id = %s WHERE id = %s",
        (alias_id, score_id),
    )
    pg._conn.commit()


# ======================================================================
# Wave bookkeeping
# ======================================================================

def upsert_wave_run(pg: PGClient, wave_id: str, phase: str, operator: str | None,
                    counts: dict[str, int], no_match_total: int | None) -> None:
    cur = pg._conn.cursor()
    cur.execute(
        """
        INSERT INTO enrich_wave_runs (
            wave_id, phase, operator,
            proposed_count, applied_count, review_count, deferred_count, rejected_count,
            no_match_total, closure_rate, verdict
        ) VALUES (
            %(wave_id)s, %(phase)s, %(operator)s,
            %(proposed)s, %(applied)s, %(review)s, %(deferred)s, %(rejected)s,
            %(no_match_total)s,
            CASE WHEN %(no_match_total)s IS NOT NULL AND %(no_match_total)s > 0
                 THEN %(applied)s::float / %(no_match_total)s
                 ELSE NULL END,
            'PENDING'
        )
        ON CONFLICT (wave_id) DO UPDATE SET
            proposed_count   = EXCLUDED.proposed_count,
            applied_count    = EXCLUDED.applied_count,
            review_count     = EXCLUDED.review_count,
            deferred_count   = EXCLUDED.deferred_count,
            rejected_count   = EXCLUDED.rejected_count,
            no_match_total   = COALESCE(EXCLUDED.no_match_total, enrich_wave_runs.no_match_total),
            closure_rate     = EXCLUDED.closure_rate,
            completed_at     = now()
        """,
        {
            "wave_id": wave_id, "phase": phase, "operator": operator,
            "proposed": counts.get("proposed", 0),
            "applied":  counts.get("apply", 0),
            "review":   counts.get("review", 0),
            "deferred": counts.get("defer", 0),
            "rejected": counts.get("reject", 0),
            "no_match_total": no_match_total,
        },
    )
    pg._conn.commit()


# ======================================================================
# CLI
# ======================================================================

def render_table(scored: list[dict[str, Any]]) -> str:
    """One-line-per-row table for stdout reporting."""
    headers = ("DECISION", "TOTAL", "SRC", "MATCH", "EVID", "PEN", "ALIAS", "-> VENDOR", "PRODUCTS")
    lines = ["  ".join(f"{h:<10}" for h in headers)]
    for r in scored:
        lines.append("  ".join([
            f"{r['decision']:<10}",
            f"{r['total_score']:.2f}".ljust(10),
            f"{r['source_score']:.2f}".ljust(10),
            f"{r['match_score']:.2f}".ljust(10),
            f"{r['evidence_score']:.2f}".ljust(10),
            f"{r['penalty_score']:.2f}".ljust(10),
            f"{r['proposed_alias_name'][:18]:<18}",
            f"{(r['proposed_vendor_name'] or '?')[:18]:<18}",
            f"{r['nvd_product_count'] if r['nvd_product_count'] is not None else '-'}",
        ]))
    return "\n".join(lines)


def main() -> int:
    ap = argparse.ArgumentParser(description="Score vendor_alias proposals before INSERT.")
    ap.add_argument("--proposals", required=True, help="Path to proposals JSON")
    ap.add_argument("--wave-id", required=True, help="Wave identifier (e.g. phase_f1)")
    ap.add_argument("--phase", default=None, help="Wave phase label (default: same as wave-id)")
    ap.add_argument("--operator", default=None, help="Operator name for audit trail")
    ap.add_argument("--no-match-total", type=int, default=None,
                    help="Total no_match corpus size (for closure_rate)")
    ap.add_argument("--apply", action="store_true",
                    help="INSERT decision='apply' rows into vendor_alias")
    ap.add_argument("--allow-synthetic", action="store_true",
                    help=("Force-INSERT proposals targeting synthetic vendors prefixed "
                          f"'{SYNTHETIC_VENDOR_PREFIX}' regardless of decision threshold. "
                          "Bypasses the 0.85 apply gate but still records the score trail. "
                          "Required for lia-meta dispatcher aliases (Generic/Various/...)."))
    ap.add_argument("--out-json", default=None, help="Write scored proposals as JSON to this path")
    ap.add_argument("--max-reject-rate", type=float, default=0.50,
                    help="Abort if reject ratio exceeds this (default 0.50)")
    args = ap.parse_args()

    proposals_path = Path(args.proposals)
    if not proposals_path.exists():
        raise InvalidInputError(f"proposals file not found: {proposals_path}")
    try:
        payload = json.loads(proposals_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as e:
        raise InvalidInputError(f"proposals JSON invalid: {e}") from e

    proposals = payload.get("proposals")
    if not isinstance(proposals, list) or not proposals:
        raise InvalidInputError("proposals JSON must contain a non-empty 'proposals' list")

    wave_id  = args.wave_id
    phase    = args.phase or payload.get("phase") or wave_id
    operator = args.operator or payload.get("operator") or "unknown"

    scored: list[dict[str, Any]] = []
    counts = {"proposed": 0, "apply": 0, "review": 0, "defer": 0, "reject": 0}

    with PGClient() as pg:
        for p in proposals:
            counts["proposed"] += 1
            row = score_proposal(pg, p)
            score_id = insert_score_row(pg, row, wave_id)
            row["score_id"] = score_id
            counts[row["decision"]] += 1

            # Determine whether this proposal is materialised in vendor_alias.
            # Standard path : decision == 'apply' AND --apply flag.
            # Synthetic path : --allow-synthetic AND target vendor name starts
            # with 'lia-' (lia-meta, lia-iot-mesh ...) -- bypasses 0.85 gate.
            is_synthetic = (
                row.get("proposed_vendor_name") is not None
                and row["proposed_vendor_name"].startswith(SYNTHETIC_VENDOR_PREFIX)
            )
            should_insert = (
                (args.apply and row["decision"] == "apply")
                or (args.allow_synthetic and args.apply and is_synthetic)
            )

            if should_insert:
                alias_id, status = insert_alias(pg, p, row)
                row["inserted_alias_id"] = alias_id
                row["apply_status"] = status
                if alias_id is not None and status == "inserted":
                    link_score_to_alias(pg, score_id, alias_id)
                elif status == "duplicate_same":
                    # Existing alias already maps to the same canonical vendor.
                    # Link the score row to that alias to dedupe trail.
                    link_score_to_alias(pg, score_id, alias_id)
                    row["dedup_note"] = "existing alias points to same canonical vendor"
                elif status == "duplicate_other":
                    # Existing alias maps to a DIFFERENT vendor -- do NOT link
                    # alias_id (would corrupt the trail). Surface in rationale.
                    row["dedup_note"] = "WARN: existing alias points to a different vendor (not linked)"
                elif status == "no_vendor":
                    row["dedup_note"] = "vendor not found in vendor table"

                # Synthetic apply that bypassed the gate gets an audit suffix.
                if is_synthetic and row["decision"] != "apply":
                    suffix = (f" [SYNTHETIC_OVERRIDE wave={wave_id}: bypassed "
                              f"decision={row['decision']} gate via --allow-synthetic]")
                    cur = pg._conn.cursor()
                    cur.execute(
                        "UPDATE vendor_alias_score SET rationale = COALESCE(rationale,'') || %s WHERE id = %s",
                        (suffix, score_id),
                    )
                    pg._conn.commit()
            scored.append(row)

        upsert_wave_run(pg, wave_id, phase, operator, counts, args.no_match_total)

    print(render_table(scored))
    print()
    print(f"Wave {wave_id} ({phase}) -- {operator} -- {utc_now_iso()}")
    print(f"  Proposed: {counts['proposed']}")
    print(f"  Apply:    {counts['apply']}")
    print(f"  Review:   {counts['review']}")
    print(f"  Defer:    {counts['defer']}")
    print(f"  Reject:   {counts['reject']}")
    if args.no_match_total:
        closure = counts["apply"] / args.no_match_total
        print(f"  Closure:  {counts['apply']}/{args.no_match_total} = {closure:.2%}")

    if args.out_json:
        Path(args.out_json).write_text(
            json.dumps({
                "wave_id": wave_id,
                "phase": phase,
                "operator": operator,
                "computed_at": utc_now_iso(),
                "counts": counts,
                "no_match_total": args.no_match_total,
                "scored": scored,
            }, indent=2),
            encoding="utf-8",
        )
        print(f"  Output:   {args.out_json}")

    reject_ratio = counts["reject"] / counts["proposed"] if counts["proposed"] else 0
    if reject_ratio > args.max_reject_rate:
        print(f"\nERROR: reject ratio {reject_ratio:.2%} > threshold {args.max_reject_rate:.2%}", file=sys.stderr)
        return 7

    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except EnrichError as e:
        print(f"ERROR: {e}", file=sys.stderr)
        sys.exit(e.exit_code)
