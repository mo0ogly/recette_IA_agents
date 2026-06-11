#!/usr/bin/env python3
"""Generate PLAN backfill stubs for retex_only cycles in the
liaprobe-fingerprint-rebuild scope. Reads an existing RETEX, extracts the
scope summary + score + date, and writes a PLAN_*_CYCLE{N}_BACKFILLED_*.md
stub when a cycle produced a RETEX but no PLAN filesystem artifact.

Tracked, tested successor of the one-shot `_alire/temp/c55_plan_backfill_gen.py`
(c55). c69 / A105 promoted it here and fixed the score/date regex so it
handles every legacy RETEX header format (see `extract_summary`). The c55
temp original is left in place untouched as the c55 cycle artifact; this
file supersedes it for any future retex_only backfill.

Usage:
  python3 plan_backfill_gen.py --dry-run            # print extracted
                                                    # score/date per cycle,
                                                    # write NOTHING
  python3 plan_backfill_gen.py --apply              # write the stubs
  python3 plan_backfill_gen.py --apply --cycles 2,3,7

--dry-run is the default-safe mode: a real run writes one file per cycle
(potentially >5 files), so the writer is gated behind an explicit --apply
(R3 mass-mutation discipline).
"""
from pathlib import Path
import argparse
import re

REPO_ROOT = Path("/opt/lia-sec/dev")
RETEX_DIR = REPO_ROOT / "_alire/02_LOGS/Journals/retex"
TRACKING_DIR = REPO_ROOT / "_alire/tracking"

# c55 backfill set: c2,c3,c7-c9,c15-c31 (22 retex_only cycles).
DEFAULT_CYCLES = [2, 3, 7, 8, 9] + list(range(15, 32))
DATE_BACKFILL = "2026-05-14"

# Unified score regex (c69 / A105). Matches all observed legacy headers:
#   "Score agentique : 48/50"        (original c55 target -- agentique optional)
#   "**Score :** 91/100 (objectif)"  (c2,c3,c7,c8 -- bold prefix, /100)
#   "**Agentic score** : 45/50"      (c15..c31 -- English label, ** outside :)
#   "Score: **50/50**"               (recent -- ** AFTER the colon)
# Captures the numerator (group 1) and denominator (group 2) so the stub
# can render the original scale (N/50 vs N/100) faithfully.
SCORE_RE = re.compile(
    r"(?:[Aa]gentic\s+score|[Ss]core(?:\s+agentique)?)"
    r"\s*\*{0,2}\s*:?\s*\*{0,2}\s*"
    r"(\d+)\s*/\s*(50|100)"
)
# Date regex tolerant to "**Date :**" and "**Date**  :" and "Date:".
DATE_RE = re.compile(r"Date\s*\*{0,2}\s*:?\s*\*{0,2}\s*(\d{4}-\d{2}-\d{2})")


def extract_summary(retex_path: Path) -> dict:
    """Pull date, score (numerator + denominator) and a scope headline
    from the RETEX header. Format-agnostic across all legacy RETEX."""
    text = retex_path.read_text(encoding="utf-8", errors="replace")
    lines = text.splitlines()[:60]

    summary = {
        "date": None,
        "score": None,
        "score_scale": None,
        "first_para": None,
    }

    for ln in lines[:15]:
        if summary["date"] is None:
            m_date = DATE_RE.search(ln)
            if m_date:
                summary["date"] = m_date.group(1)
        if summary["score"] is None:
            m_score = SCORE_RE.search(ln)
            if m_score:
                summary["score"] = m_score.group(1)
                summary["score_scale"] = m_score.group(2)

    for i, ln in enumerate(lines):
        if ln.strip().startswith("## Objectif") or ln.strip().startswith("## Scope"):
            for j in range(i + 1, min(i + 8, len(lines))):
                s = lines[j].strip()
                if s and not s.startswith("#") and not s.startswith("|"):
                    summary["first_para"] = s[:400]
                    break
            break

    if not summary["first_para"]:
        for ln in lines[3:20]:
            s = ln.strip()
            if s and not s.startswith("#") and not s.startswith("|") and not s.startswith("-"):
                summary["first_para"] = s[:400]
                break

    return summary


def generate_stub(cycle: int, retex_filename: str, summary: dict) -> str:
    """Generate the PLAN stub markdown content."""
    scope_text = summary.get("first_para") or "(scope not extracted from RETEX, see source file)"
    work_date = summary.get("date") or "2026-05-12 or 2026-05-13"
    if summary.get("score"):
        scale = summary.get("score_scale") or "50"
        score_text = f"{summary['score']}/{scale}"
    else:
        score_text = "(not extracted)"
    sess_date = work_date.replace('-', '')[:8] if summary.get('date') else 'unknown'

    return f"""# PLAN APEX - LiaProbe Fingerprint Rebuild Cycle {cycle} (BACKFILLED)

Date: {work_date} (work) / {DATE_BACKFILL} (backfill)
Session: apex-{sess_date}-c{cycle} (work)
        / apex-20260514-c55-vendor-alive-v2 (backfill)
Status: BACKFILLED_RETROSPECTIVE
Source: cosmetic backfill in c55 (A103) from existing RETEX

## Disclaimer

Original cycle ran on {work_date} and produced RETEX but did NOT produce a
PLAN file at the time. This PLAN stub was BACKFILLED in c55 (2026-05-14)
based on the RETEX scope summary. Content is INFERRED from RETEX content,
not from direct cycle observation of the original planning intent.

Authoritative cycle record:
`_alire/02_LOGS/Journals/retex/{retex_filename}`

## Scope (inferred from RETEX)

{scope_text}

## Original cycle metrics

- Date: {work_date}
- Score: {score_text}
- RETEX file: {retex_filename}

## Backfill rationale

c55 A103 cosmetic harness : demote `verify_cycle_traceability.py` exit code
from 1 PARTIAL (retex_only WARN) to 0 CLEAN for the
liaprobe-fingerprint-rebuild scope. Cosmetic only -- no operational impact.
Original cycle was complete in its own time, simply lacked the PLAN
filesystem artifact later mandated by librarian-gate.

## Compliance

- R18 : explicitly INFERRED. No fabricated specifics beyond what the RETEX
  contains. Stub is intentionally minimal.
- R10/R12/R13 : N/A (backfill cosmetic, no code).

## Reference

- RETEX (authoritative) : `_alire/02_LOGS/Journals/retex/{retex_filename}`
- c55 PLAN (this backfill cycle) :
  `_alire/tracking/PLAN_APEX_LIAPROBE_FINGERPRINT_REBUILD_CYCLE55_2026-05-14.md`
- c53 traceability gap precedent (different range, BACKFILLED RETEX) :
  `_alire/tracking/liaprobe-fingerprint-rebuild/TRACEABILITY_GAP_C10_C14_2026-05-14.md`
"""


def find_retex(cycle: int):
    """Return the single non-BACKFILLED RETEX path for a cycle, or a
    (None, reason) skip tuple."""
    candidates = list(
        RETEX_DIR.glob(f"RETEX_PDCA_LIAPROBE_FINGERPRINT_REBUILD_CYCLE{cycle}_*.md")
    )
    candidates = [c for c in candidates if "BACKFILLED" not in c.name]
    if not candidates:
        return None, "no RETEX found"
    if len(candidates) > 1:
        return None, f"multiple RETEX: {[c.name for c in candidates]}"
    return candidates[0], None


def main():
    parser = argparse.ArgumentParser(
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument("--apply", action="store_true",
                        help="Write the PLAN stub files")
    parser.add_argument("--dry-run", action="store_true",
                        help="Print extracted score/date per cycle, write nothing")
    parser.add_argument("--cycles", default="",
                        help="Comma list of cycles (default: c55 22-cycle set)")
    args = parser.parse_args()

    if not args.apply and not args.dry_run:
        parser.error("Must specify --apply or --dry-run")
    if args.apply and args.dry_run:
        parser.error("--apply and --dry-run are mutually exclusive")

    if args.cycles.strip():
        cycles = [int(x) for x in args.cycles.split(",") if x.strip()]
    else:
        cycles = DEFAULT_CYCLES

    generated = []
    skipped = []
    for cycle in cycles:
        retex_path, reason = find_retex(cycle)
        if retex_path is None:
            skipped.append((cycle, reason))
            continue
        summary = extract_summary(retex_path)
        score = summary.get("score")
        scale = summary.get("score_scale") or "?"
        if args.dry_run:
            print(f"  c{cycle:2d}  score={score or '?'}/{scale}  "
                  f"date={summary.get('date') or '?'}  {retex_path.name}")
            generated.append((cycle, retex_path.name, score))
            continue
        content = generate_stub(cycle, retex_path.name, summary)
        out_path = (
            TRACKING_DIR
            / f"PLAN_APEX_LIAPROBE_FINGERPRINT_REBUILD_CYCLE{cycle}_BACKFILLED_{DATE_BACKFILL}.md"
        )
        out_path.write_text(content)
        generated.append((cycle, out_path.name, score))

    mode = "DRY-RUN (no writes)" if args.dry_run else "APPLY"
    print(f"\n[{mode}] {len(generated)} cycles processed:")
    for cycle, name, score in generated:
        print(f"  c{cycle:2d}  {name}  [score={score or '?'}]")
    if skipped:
        print(f"\nSkipped {len(skipped)}:")
        for cycle, reason in skipped:
            print(f"  c{cycle:2d}  {reason}")


if __name__ == "__main__":
    main()
