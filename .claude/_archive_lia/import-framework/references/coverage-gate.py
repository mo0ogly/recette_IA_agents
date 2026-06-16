#!/usr/bin/env python3
"""
Coverage gate for clean-room AGPL framework imports.

Incident 2026-05-26 (W2A-W2E.1): the anti-clone Jaccard gate enforces "new
text is different from legacy" but does NOT enforce "new questionnaire covers
at least as many assessable items as the legacy". 8 frameworks shipped with
40-76% coverage of the legacy assessable count (SOC2 40%, EU_AI_ACT 47%,
ANNEX_NIS2 48%, ISO 50%, DORA 54%, PCI 58%, CIS 76%, HIPAA 67% pre-expansion).
Anti-clone said PASS; coverage was silently halved.

The skill's Phase 1.4 already states the rule (`assessables_lia >=
assessables_reference`) but had NO executable enforcement. This is that
enforcement.

Threshold semantics (RETEX-tuned 2026-05-26):
  ratio = new_count / max(legacy_count, reference_count)
  ratio >= 0.90        -> PASS
  0.70 <= ratio < 0.90 -> WARN (must record justification, still PASS)
  ratio < 0.70         -> FAIL (BLOCKED unless --justified with non-empty reason)

The rule is INTENTIONALLY conservative. The skill text Phase 2.4 already
encodes how to recover: STRONG_SPLIT each sub-paragraph (a)(b)(c)(i)(ii)(iii)
into evaluable sub-questions, NOT collapse them into a single umbrella
question. A FAIL here means re-author with split granularity.

Usage:
  python3 coverage_gate.py \
    --framework {CODE} \
    --new-questions data/{code}_questions.json \
    --legacy-count 462 \
    --reference-count 462 \
    --out data/coverage_report.json \
    [--justified "scope volontairement restreint aux obligations entite"]

Exit codes:
  0 = PASS or WARN_JUSTIFIED
  1 = FAIL (coverage below threshold, no justification)
  2 = WARN (coverage below 90%, no justification recorded)
"""

import argparse
import json
import sys
from pathlib import Path


def count_questions(p: Path) -> int:
    """Count questions in a hand-authored JSON file (flat list or dict)."""
    data = json.loads(p.read_text())
    if isinstance(data, list):
        return len(data)
    if isinstance(data, dict):
        items = data.get("questions") or data.get("items")
        if items is not None:
            return len(items)
        # Per-part: sum sections[].questions
        total = 0
        for s in data.get("sections", []):
            total += len(s.get("questions", []))
        return total
    return 0


def verdict(ratio: float, justified: str) -> str:
    if ratio >= 0.90:
        return "PASS"
    if ratio >= 0.70:
        return "WARN_JUSTIFIED" if justified else "WARN"
    return "PASS_JUSTIFIED" if justified else "FAIL"


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--framework", required=True, help="framework code (CSF_2_0, DORA, ...)")
    ap.add_argument("--new-questions", required=True, type=Path,
                    help="path to hand-authored questions JSON")
    ap.add_argument("--legacy-count", type=int, default=0,
                    help="legacy DB assessable count (prior import)")
    ap.add_argument("--reference-count", type=int, default=0,
                    help="external reference count (public YAML / NIST OLIR / etc.)")
    ap.add_argument("--justified", default="",
                    help="explicit justification for sub-90%% coverage")
    ap.add_argument("--threshold-pass", type=float, default=0.90)
    ap.add_argument("--threshold-warn", type=float, default=0.70)
    ap.add_argument("--out", required=True, type=Path)
    args = ap.parse_args()

    new_count = count_questions(args.new_questions)
    baseline = max(args.legacy_count, args.reference_count)
    if baseline == 0:
        ratio = 1.0
        note = "no baseline provided -- gate disabled (record assessables_reference in PLAN.md)"
    else:
        ratio = new_count / baseline
        note = ""

    v = verdict(ratio, args.justified.strip())

    report = {
        "schema": "coverage-report-v1",
        "framework": args.framework,
        "new_count": new_count,
        "legacy_count": args.legacy_count,
        "reference_count": args.reference_count,
        "baseline": baseline,
        "ratio": round(ratio, 3),
        "threshold_pass": args.threshold_pass,
        "threshold_warn": args.threshold_warn,
        "justified": args.justified,
        "verdict": v,
        "note": note,
        "remediation": (
            "FAIL: re-author with Phase 2.4 STRONG_SPLIT -- each sub-paragraph "
            "(a)(b)(c)(i)(ii)(iii) becomes one evaluable sub-question with the "
            "verbatim sub-point text. NEVER collapse a multi-sub-point article "
            "into a single umbrella question. Target new_count >= baseline * 0.9."
            if v in ("FAIL", "WARN") else ""
        ),
    }
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(report, indent=2))

    print(f"Framework: {args.framework}")
    print(f"  new={new_count}, legacy={args.legacy_count}, ref={args.reference_count}, baseline={baseline}")
    print(f"  ratio={ratio:.3f} (pass>={args.threshold_pass}, warn>={args.threshold_warn})")
    print(f"  verdict={v}")
    if args.justified:
        print(f"  justification: {args.justified}")
    if note:
        print(f"  note: {note}")

    if v == "FAIL":
        print("\nFAIL: coverage below 70%. BLOCKED unless re-authored with sub-paragraph split.")
        print("Fix: invoke Phase 2.4 STRONG_SPLIT on each multi-sub-point article.")
        return 1
    if v == "WARN":
        print("\nWARN: coverage 70-90% without recorded justification.")
        print("Either enrich (preferred) OR pass --justified \"<reason>\" to record the scope restriction.")
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main())
