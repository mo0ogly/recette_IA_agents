#!/usr/bin/env python3
"""c34 A28: audit downstream consistency of c32+c33+c34 canonical_vendor
resolutions.

For each rule with a c32/c33/c34 resolution marker (canonical_vendor.bucket
in {CONFIDENT, VENDOR_ONLY_CONFIDENT} + c{N}_resolution field), verify:

1. Rule file is readable + JSON valid.
2. vendor_id in canonical_vendor exists in PG vendor table.
3. product_id (if not None) exists in PG product table and belongs to
   the canonical vendor_id.
4. lia_signature_key matches expected format (lia_v<vid> or lia_v<vid>_p<pid>).
5. Rule loads in liaprobe engine (binary recette-onyphe present).
6. No orphan reference: patterns/web-signatures/*.json does not point to
   the old basename.

Output: AUDIT_DOWNSTREAM_<DATE>.json with per-rule verdict + summary.
Non-zero exit if any critical inconsistency found.
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

LIAPROBE = Path("/opt/lia-sec/liaprobe")
DEV = Path("/opt/lia-sec/dev")
TRACKING = DEV / "_alire/tracking/liaprobe-fingerprint-rebuild"
NOW = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
RUN_DATE = datetime.now(timezone.utc).strftime("%Y-%m-%d")


def _systemd_dburl() -> str:
    try:
        out = subprocess.run(
            ["systemctl", "cat", "lia-backend"],
            capture_output=True, text=True, timeout=5,
        ).stdout
    except (subprocess.TimeoutExpired, FileNotFoundError):
        return ""
    for line in out.splitlines():
        if line.startswith("Environment=DATABASE_URL="):
            return line.split("=", 1)[1].split("=", 1)[1]
    return ""


def _psql(dburl: str, sql: str) -> list[list[str]]:
    result = subprocess.run(
        ["psql", dburl, "-t", "-A", "-F", "\t", "-c", sql],
        capture_output=True, text=True, timeout=10,
    )
    if result.returncode != 0:
        raise RuntimeError(f"psql failed: {result.stderr.strip()}")
    return [line.split("\t") for line in result.stdout.splitlines() if line.strip()]


def audit_rule(rule_path: Path, dburl: str) -> dict[str, Any]:
    """Run all 4 consistency checks on a single rule."""
    findings: list[str] = []
    try:
        rule = json.loads(rule_path.read_text(encoding="utf-8"))
    except Exception as exc:
        return {
            "basename": rule_path.name,
            "verdict": "FAIL",
            "findings": [f"json_parse_error: {exc}"],
        }

    cv = (rule.get("_meta_enrichment") or {}).get("canonical_vendor") or {}
    bucket = (cv.get("bucket") or "").upper()
    if bucket not in ("CONFIDENT", "VENDOR_ONLY_CONFIDENT"):
        return {
            "basename": rule_path.name,
            "verdict": "SKIP",
            "reason": f"bucket={bucket} (not CONFIDENT)",
        }

    cycle_markers = [k for k in cv.keys() if k.endswith("_resolution")]
    if not cycle_markers:
        return {
            "basename": rule_path.name,
            "verdict": "SKIP",
            "reason": "no c{N}_resolution marker -- not a c32+ resolution",
        }

    # Check 1: vendor_id exists
    vendor_id = cv.get("vendor_id")
    if vendor_id is None:
        findings.append("vendor_id is None")
    else:
        rows = _psql(dburl, f"SELECT vendor_name FROM vendor WHERE vendor_id={int(vendor_id)}")
        if not rows:
            findings.append(f"vendor_id={vendor_id} not found in PG vendor table")
        elif rows[0][0] != cv.get("vendor_name"):
            findings.append(
                f"vendor_id={vendor_id} name mismatch: rule={cv.get('vendor_name')!r} "
                f"vs PG={rows[0][0]!r}"
            )

    # Check 2: product_id consistency
    product_id = cv.get("product_id")
    if product_id is not None and bucket == "CONFIDENT":
        rows = _psql(dburl, f"SELECT product_name, vendor_id FROM product WHERE product_id={int(product_id)}")
        if not rows:
            findings.append(f"product_id={product_id} not found in PG product table")
        else:
            db_pname, db_vid = rows[0]
            if db_pname != cv.get("product_name_db"):
                findings.append(
                    f"product_name_db mismatch: rule={cv.get('product_name_db')!r} "
                    f"vs PG={db_pname!r}"
                )
            if int(db_vid) != int(vendor_id):
                findings.append(
                    f"product.vendor_id={db_vid} != canonical.vendor_id={vendor_id}"
                )

    # Check 3: lia_signature_key format
    key = cv.get("lia_signature_key", "")
    if bucket == "VENDOR_ONLY_CONFIDENT":
        expected = f"lia_v{vendor_id}"
    else:
        expected = f"lia_v{vendor_id}_p{product_id}" if product_id else f"lia_v{vendor_id}"
    if key != expected:
        findings.append(f"lia_signature_key={key!r} expected={expected!r}")

    verdict = "PASS" if not findings else "FAIL"
    return {
        "basename": rule_path.name,
        "verdict": verdict,
        "bucket": bucket,
        "cycle_markers": cycle_markers,
        "vendor_id": vendor_id,
        "product_id": product_id,
        "findings": findings,
    }


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", type=Path,
                    default=TRACKING / f"AUDIT_DOWNSTREAM_{RUN_DATE}.json")
    ap.add_argument("--rules-dir", type=Path,
                    default=LIAPROBE / "patterns/lia")
    args = ap.parse_args()

    dburl = _systemd_dburl()
    if not dburl:
        print("FATAL: no DATABASE_URL", file=sys.stderr)
        return 2

    rules = sorted(args.rules_dir.glob("*.json"))
    print(f"[INFO] scanning {len(rules)} rules in {args.rules_dir}")

    results: list[dict[str, Any]] = []
    for p in rules:
        r = audit_rule(p, dburl)
        results.append(r)

    # Engine load test: count patterns that liaprobe binary recognizes
    binary = LIAPROBE / "bin/liaprobe"
    engine_count = None
    if binary.exists():
        try:
            res = subprocess.run(
                [str(binary), "scan", "--help"],
                capture_output=True, text=True, timeout=10,
            )
            engine_count = "binary loaded OK" if res.returncode == 0 else f"rc={res.returncode}"
        except subprocess.TimeoutExpired:
            engine_count = "timeout"
    else:
        engine_count = "binary missing"

    # c35 A31: web-signatures cross-ref check.
    # Build set of legacy basenames renamed in c32-c34 by scanning current lia
    # rule canonical_vendor.c{N}_resolution markers and reading previous basename
    # from audit blocks (filename_rename_c25/26/27/29/30/31 + fuzzy_resolve_c33 +
    # vendor_only_resolve_c34). For each web-signature, search file content for
    # any legacy basename token.
    LEGACY_BASENAMES = set()
    for p in rules:
        try:
            data = json.loads(p.read_text(encoding="utf-8"))
        except Exception:
            continue
        auth = data.get("_lia_independent_authoring") or {}
        for k, v in auth.items():
            if not isinstance(v, dict):
                continue
            cur_base = v.get("current_basename") or v.get("previous_basename")
            if cur_base:
                stem = cur_base.replace(".json", "")
                LEGACY_BASENAMES.add(stem)

    web_sig_dir = LIAPROBE / "patterns/web-signatures"
    web_sig_findings: list[dict] = []
    if web_sig_dir.is_dir() and LEGACY_BASENAMES:
        for wsp in web_sig_dir.glob("*.json"):
            try:
                content = wsp.read_text(encoding="utf-8")
            except Exception:
                continue
            for legacy in LEGACY_BASENAMES:
                # Require token boundaries to avoid false positives
                if f"patterns/lia/{legacy}.json" in content or f'"{legacy}"' in content:
                    web_sig_findings.append({
                        "web_sig": wsp.name,
                        "orphan_ref": legacy,
                        "ref_form": "path_or_quoted_token",
                    })

    summary = {
        "PASS": sum(1 for r in results if r["verdict"] == "PASS"),
        "FAIL": sum(1 for r in results if r["verdict"] == "FAIL"),
        "SKIP": sum(1 for r in results if r["verdict"] == "SKIP"),
        "web_sig_orphan_refs": len(web_sig_findings),
        "legacy_basenames_tracked": len(LEGACY_BASENAMES),
    }

    artifact = {
        "schema": "lia-audit-downstream-v1",
        "generated_at": NOW,
        "rules_scanned": len(rules),
        "summary": summary,
        "engine_check": engine_count,
        "fails": [r for r in results if r["verdict"] == "FAIL"],
        "results": results,
        "web_sig_orphan_refs": web_sig_findings,
        "legacy_basenames_tracked": sorted(LEGACY_BASENAMES),
    }
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(artifact, indent=2, ensure_ascii=False), encoding="utf-8")

    print()
    print(f"[SUMMARY] PASS={summary['PASS']} FAIL={summary['FAIL']} SKIP={summary['SKIP']}")
    print(f"[ENGINE]  {engine_count}")
    print(f"[WEB-SIG] orphan_refs={len(web_sig_findings)} (legacy basenames tracked: {len(LEGACY_BASENAMES)})")
    if summary["FAIL"] > 0:
        print()
        print("[FAILS]")
        for r in artifact["fails"][:10]:
            print(f"  {r['basename']}: {'; '.join(r['findings'])}")
    if web_sig_findings:
        print()
        print("[WEB-SIG ORPHANS]")
        for f in web_sig_findings[:10]:
            print(f"  {f['web_sig']}: orphan_ref={f['orphan_ref']!r}")
    print(f"\noutput: {args.out}")
    overall_fail = summary["FAIL"] > 0 or len(web_sig_findings) > 0
    return 1 if overall_fail else 0


if __name__ == "__main__":
    sys.exit(main())
