#!/usr/bin/env python3
"""Promote nightly harvest evidence into LiaProbe rule JSON.

Reads the proposed_patch.json files produced by the nightly harvest rollup
(rule_rollup._build_patch) for promotion_ready rules and applies the patch
into the actual rule JSON under /opt/lia-sec/liaprobe:
  - merge artifacts.{html_sha256, headers_sha256, capture_url, capture_date,
    observation_provenance}
  - set _lia_independent_authoring.http_gate = {date, verified, http_status, note}
  - drop _lia_independent_authoring.wild_traffic_unconfirmed

Dry-run by default. Pass --apply to write. Idempotent (re-applying yields no
change). Appends a promotion ledger. Does NOT commit and does NOT change any
detection logic (probes/matchers) -- only metadata/provenance fields, so the
engine verdict is unaffected. The caller runs the recette regression gate and
commits.

Usage:
  promote_evidence.py [--date YYYY-MM-DD] [--rule RULE_ID] [--apply]
"""

from __future__ import annotations

import argparse
import glob
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

THIS_DIR = Path(__file__).resolve().parent
if str(THIS_DIR) not in sys.path:
    sys.path.insert(0, str(THIS_DIR))

from lib.rule_loader import iter_rules  # noqa: E402

SESSION_ROOT = Path("/opt/lia-sec/dev/_alire/tracking/liaprobe-fingerprint-rebuild")
NIGHTLY = SESSION_ROOT / "nightly"
LEDGER = NIGHTLY / "PROMOTION_LEDGER.jsonl"


def _rule_paths() -> dict:
    return {r.rule_id: r.path for r in iter_rules()}


def _collect_patches(date_filter: str, rule_filter: str) -> dict:
    """Return {rule_id: (patch_dict, score, night)} keeping the best score."""
    best: dict = {}
    for p in sorted(glob.glob(str(NIGHTLY / "2026-*" / "*" / "proposed_patch.json"))):
        pp = Path(p)
        night, rid = pp.parts[-3], pp.parts[-2]
        if date_filter and night != date_filter:
            continue
        if rule_filter and rid != rule_filter:
            continue
        try:
            d = json.loads(pp.read_text())
        except Exception:
            continue
        score = float((d.get("_basis") or {}).get("match_score") or 0.0)
        if rid not in best or score > best[rid][1]:
            best[rid] = (d, score, night)
    return best


def _set_dotted(obj: dict, dotted: str, value) -> None:
    parts = dotted.split(".")
    cur = obj
    for k in parts[:-1]:
        cur = cur.setdefault(k, {})
    cur[parts[-1]] = value


def _drop_dotted(obj: dict, dotted: str) -> None:
    parts = dotted.split(".")
    cur = obj
    for k in parts[:-1]:
        if not isinstance(cur, dict) or k not in cur:
            return
        cur = cur[k]
    if isinstance(cur, dict):
        cur.pop(parts[-1], None)


def _apply_patch(rule: dict, patch_doc: dict) -> dict:
    p = patch_doc.get("patch") or {}
    arts = dict(rule.get("artifacts") or {})
    arts.update(p.get("artifacts") or {})
    rule["artifacts"] = arts
    for key, val in p.items():
        if key in ("artifacts", "_drop_keys"):
            continue
        _set_dotted(rule, key, val)
    for dk in p.get("_drop_keys") or []:
        _drop_dotted(rule, dk)
    return rule


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--date", default="", help="Only promote patches from this nightly date.")
    ap.add_argument("--rule", default="", help="Only promote this rule_id.")
    ap.add_argument("--apply", action="store_true", help="Write changes (default: dry-run).")
    args = ap.parse_args()

    paths = _rule_paths()
    best = _collect_patches(args.date, args.rule)
    if not best:
        print("no proposed_patch.json matched the filters")
        return 0

    ts = datetime.now(timezone.utc).isoformat()
    applied = 0
    for rid, (patch_doc, score, night) in sorted(best.items(), key=lambda x: -x[1][1]):
        path = paths.get(rid)
        basis = patch_doc.get("_basis") or {}
        if not path or not path.exists():
            print(f"  SKIP  {rid:30} rule file not found")
            continue
        rule = json.loads(path.read_text())
        before = json.dumps(rule, sort_keys=True)
        _apply_patch(rule, patch_doc)
        after = json.dumps(rule, sort_keys=True)
        changed = before != after
        gate = (rule.get("_lia_independent_authoring") or {}).get("http_gate") or {}
        tag = "APPLY" if args.apply else "DRY  "
        print(f"  {tag} {rid:30} score={score:.2f} night={night} "
              f"host={str(basis.get('host'))[:38]:38} verified={gate.get('verified')} changed={changed}")
        if args.apply and changed:
            path.write_text(json.dumps(rule, indent=1, ensure_ascii=False) + "\n")
            LEDGER.parent.mkdir(parents=True, exist_ok=True)
            with open(LEDGER, "a") as f:
                f.write(json.dumps({
                    "ts": ts, "rule_id": rid, "path": str(path), "night": night,
                    "score": score, "host": basis.get("host"),
                    "source": basis.get("source"), "http_status": basis.get("http_status"),
                }) + "\n")
            applied += 1

    verb = "applied" if args.apply else "would apply"
    print(f"\n{verb}: {applied if args.apply else len(best)} rule(s)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
