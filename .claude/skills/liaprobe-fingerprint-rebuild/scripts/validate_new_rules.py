#!/usr/bin/env python3
# validate_new_rules.py
#
# Onyphe ground-truth validator for newly authored rules. Run after
# nightly batch authoring to validate each new rule against wild-traffic
# banners via the real Go engine (bin/recette-onyphe).
#
# Per rule:
#   - Compute TP / FP / not_triggered counts on Onyphe merged set
#   - If TP > 0 -> add _lia_independent_authoring.proven_by_onyphe block
#   - If FP > TP -> auto-disable + audit trail (FP-dominant rule)
#   - If TP = 0 AND FP = 0 -> add wild_traffic_unconfirmed marker
#
# Implements RELIABILITY GATE 3 from SKILL.md (Onyphe ground-truth check).
#
# Usage:
#   python3 validate_new_rules.py --rules CODE1 CODE2 CODE3
#   python3 validate_new_rules.py --since-commit HEAD~5   # auto-detect new
#   python3 validate_new_rules.py --dry-run --rules CODE1
#   python3 validate_new_rules.py --apply --rules CODE1 CODE2

import argparse
import json
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

LIAPROBE_DIR = Path("/opt/lia-sec/liaprobe")
PATTERNS_ROOT = LIAPROBE_DIR / "patterns"
RECETTE_BIN = LIAPROBE_DIR / "bin/recette-onyphe"
DEV_DIR = Path("/opt/lia-sec/dev")
DEFAULT_ONYPHE = DEV_DIR / "_alire/temp/onyphe_merged_unique_2026-05-12.jsonl"
TRACKING_DIR = DEV_DIR / "_alire/tracking/liaprobe-fingerprint-rebuild"

RUN_DATE = datetime.now(timezone.utc).strftime("%Y-%m-%d")
NOW_ISO = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
PASS_ID = f"{RUN_DATE}_validate_new_rules"


def run_engine(onyphe_file: Path) -> list:
    cmd = [str(RECETTE_BIN), "-f", str(onyphe_file), "-out", "json", "-src", "all"]
    proc = subprocess.run(cmd, cwd=str(LIAPROBE_DIR),
                          capture_output=True, text=True, timeout=600)
    if proc.returncode != 0:
        print(f"[ERROR] engine returncode {proc.returncode}: {proc.stderr}",
              file=sys.stderr)
        sys.exit(2)
    return json.loads(proc.stdout)


def find_rule_path(code_or_id: str) -> Path | None:
    """Locate rule .json by taxonomy_code or pattern id (lowercase)."""
    needle = code_or_id.lower()
    for sub in ("web-signatures", "banner-signatures",
                "service-detectors", "tcp-probes", "lia"):
        d = PATTERNS_ROOT / sub
        if not d.exists():
            continue
        for path in d.glob("*.json"):
            stem = path.stem.lower()
            if stem == needle:
                return path
            try:
                rule = json.loads(path.read_text())
            except (json.JSONDecodeError, OSError):
                continue
            if (rule.get("id", "").lower() == needle
                    or rule.get("taxonomy_code", "").lower() == needle):
                return path
    return None


def detect_recent_rules(since_commit: str) -> list:
    """List taxonomy codes from rules added/modified since a git commit (liaprobe repo)."""
    proc = subprocess.run(
        ["git", "diff", "--name-only", "--diff-filter=AM",
         since_commit, "HEAD", "--", "patterns/"],
        cwd=str(LIAPROBE_DIR), capture_output=True, text=True,
    )
    codes = []
    for line in proc.stdout.splitlines():
        if not line.endswith(".json") or "/archive/" in line or "_trace.txt" in line:
            continue
        codes.append(Path(line).stem)
    return codes


def classify_rule(verdicts: list, pattern_id: str) -> dict:
    """Aggregate engine output for a single PatternID."""
    pid = pattern_id.lower()
    tp = 0
    fp = 0
    gt_when_tp = {}
    gt_when_fp = {}
    samples_tp = []
    samples_fp = []
    for v in verdicts:
        if (v.get("PatternID") or "").lower() != pid:
            continue
        verdict = v.get("Verdict")
        gt = v.get("GTProduct", "")
        if verdict == "CORRECT":
            tp += 1
            gt_when_tp[gt] = gt_when_tp.get(gt, 0) + 1
            if len(samples_tp) < 5:
                samples_tp.append({"gt": gt, "port": v.get("Port"),
                                   "protocol": v.get("Protocol")})
        elif verdict == "WRONG":
            fp += 1
            gt_when_fp[gt] = gt_when_fp.get(gt, 0) + 1
            if len(samples_fp) < 5:
                samples_fp.append({"gt": gt, "port": v.get("Port"),
                                   "protocol": v.get("Protocol")})
    return {
        "pattern_id": pid,
        "tp": tp,
        "fp": fp,
        "precision": round(tp / (tp + fp), 3) if (tp + fp) else None,
        "gt_when_tp": gt_when_tp,
        "gt_when_fp": gt_when_fp,
        "samples_tp": samples_tp,
        "samples_fp": samples_fp,
    }


def apply_result_to_rule(path: Path, classification: dict, dry: bool) -> str:
    try:
        rule = json.loads(path.read_text())
    except (json.JSONDecodeError, OSError) as e:
        return f"ERROR_READ {path.name}: {e}"

    auth = rule.setdefault("_lia_independent_authoring", {})
    tp = classification["tp"]
    fp = classification["fp"]
    precision = classification["precision"]
    action = "no_change"

    if tp > 0:
        auth["proven_by_onyphe"] = {
            "date": NOW_ISO,
            "tp": tp,
            "fp": fp,
            "precision": precision,
            "gt_when_tp": classification["gt_when_tp"],
            "gt_when_fp": classification["gt_when_fp"],
            "marked_by": f"validate_new_rules.py {PASS_ID}",
        }
        action = "marked_proven"
        if fp > tp:
            rule["enabled"] = False
            auth["disabled_fp_dominant"] = {
                "date": NOW_ISO,
                "tp": tp,
                "fp": fp,
                "precision": precision,
                "marked_by": f"validate_new_rules.py {PASS_ID}",
            }
            action = "disabled_fp_dominant"
    elif fp > 0:
        rule["enabled"] = False
        auth["disabled_fp_dominant"] = {
            "date": NOW_ISO,
            "tp": 0,
            "fp": fp,
            "precision": 0.0,
            "marked_by": f"validate_new_rules.py {PASS_ID}",
        }
        action = "disabled_only_fp"
    else:
        auth["wild_traffic_unconfirmed"] = {
            "date": NOW_ISO,
            "marked_by": f"validate_new_rules.py {PASS_ID}",
        }
        action = "marked_unconfirmed"

    if dry:
        return f"DRY-RUN {path.name}: action={action} tp={tp} fp={fp} prec={precision}"
    path.write_text(json.dumps(rule, indent=2, ensure_ascii=False) + "\n")
    return f"APPLIED {path.name}: action={action} tp={tp} fp={fp} prec={precision}"


def main():
    p = argparse.ArgumentParser(description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--rules", nargs="+",
                   help="Taxonomy codes or pattern IDs to validate")
    p.add_argument("--since-commit", type=str,
                   help="Auto-detect new rules since this git commit in liaprobe")
    p.add_argument("--onyphe-file", type=str, default=str(DEFAULT_ONYPHE))
    p.add_argument("--apply", action="store_true")
    p.add_argument("--dry-run", action="store_true")
    args = p.parse_args()
    if not args.apply and not args.dry_run:
        p.error("Specify --apply or --dry-run")
    if not args.rules and not args.since_commit:
        p.error("Specify --rules CODE [CODE...] or --since-commit REF")

    target_codes = list(args.rules or [])
    if args.since_commit:
        detected = detect_recent_rules(args.since_commit)
        target_codes.extend(detected)
        print(f"[INFO] Auto-detected {len(detected)} new/modified rule files "
              f"since {args.since_commit}")

    if not target_codes:
        print("[INFO] No target codes")
        return 0

    print(f"[INFO] Validating {len(target_codes)} rule(s) against "
          f"{Path(args.onyphe_file).name}")
    verdicts = run_engine(Path(args.onyphe_file))
    print(f"[INFO] Engine produced {len(verdicts)} verdicts")

    results = []
    for code in target_codes:
        path = find_rule_path(code)
        if not path:
            print(f"  NOT_FOUND {code}")
            continue
        rule = json.loads(path.read_text())
        pid = (rule.get("id") or path.stem).lower()
        cls = classify_rule(verdicts, pid)
        action = apply_result_to_rule(path, cls, args.dry_run)
        print(f"  {action}")
        results.append({"code": code, "path": str(path.relative_to(LIAPROBE_DIR)),
                        **cls, "action": action})

    out = TRACKING_DIR / f"VALIDATE_NEW_RULES_{RUN_DATE}.json"
    out.write_text(json.dumps({
        "schema": "lia-validate-new-rules-v1",
        "run_date": RUN_DATE,
        "onyphe_file": str(args.onyphe_file),
        "results": results,
    }, indent=2, ensure_ascii=False))
    print(f"\nReport: {out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
