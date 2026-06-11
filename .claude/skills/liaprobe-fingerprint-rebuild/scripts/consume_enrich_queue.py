#!/usr/bin/env python3
# consume_enrich_queue.py
#
# Scan patterns/ for rules with _lia_independent_authoring.enrich_queue blocks
# marked wave_target=next_enrich_pass. Bundle into a batch JSON ready for
# /liaprobe-rule-enrich skill invocation. Optionally invoke `claude` CLI.
#
# Workflow:
#   1. Scan LIAPROBE patterns/**/*.json
#   2. Collect rules with enrich_queue.wave_target == "next_enrich_pass"
#   3. Group by action_type (version_compare, cve_lookup, eol_check, ...)
#   4. Emit batch JSON to _alire/temp/apex/enrich_batch_<date>.json
#   5. Optional --invoke: call `claude --print` with the batch payload
#   6. On success, flip wave_target to "completed_<wave_id>" + add audit
#      "consume_history" entry in the rule
#
# Usage:
#   python3 consume_enrich_queue.py             # dry-run, list queued
#   python3 consume_enrich_queue.py --emit      # write batch JSON
#   python3 consume_enrich_queue.py --invoke    # write + claude --print
#
# Designed to be called from nightly_fingerprint_batch.sh AFTER authoring
# wave completes. Idempotent: a rule already marked completed_<id> is
# skipped on next run unless its wave_target is reset manually.

import argparse
import glob
import hashlib
import json
import shutil
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

DEV_DIR = Path("/opt/lia-sec/dev")
LIAPROBE_DIR = Path("/opt/lia-sec/liaprobe")
PATTERNS_ROOT = LIAPROBE_DIR / "patterns"
TRACKING_DIR = DEV_DIR / "_alire/tracking/liaprobe-enrich-v2"
QUEUE_MD = TRACKING_DIR / "NEXT_ENRICH_QUEUE.md"
BATCH_OUT_DIR = DEV_DIR / "_alire/temp/apex/enrich_batches"
BACKUP_DIR = DEV_DIR / "_alire/temp/apex/apex-20260513-c19/consume_backup"

RUN_DATE = datetime.now(timezone.utc).strftime("%Y-%m-%d")
NOW_ISO = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
WAVE_ID = f"{RUN_DATE}_apex_c19_consume"


def scan_queued_rules() -> list:
    """Find all rules with enrich_queue marked next_enrich_pass."""
    queued = []
    for f in glob.glob(str(PATTERNS_ROOT / "**/*.json"), recursive=True):
        try:
            r = json.loads(open(f).read())
        except (json.JSONDecodeError, OSError):
            continue
        auth = r.get("_lia_independent_authoring") or {}
        eq = auth.get("enrich_queue") or {}
        if eq.get("wave_target") != "next_enrich_pass":
            continue
        queued.append({
            "path": str(Path(f).relative_to(LIAPROBE_DIR)),
            "abs_path": f,
            "pattern_id": r.get("id"),
            "vendor": r.get("vendor"),
            "product": r.get("product"),
            "cpe23_template": r.get("cpe23_template"),
            "current_threshold": r.get("confidence_threshold"),
            "default_ports": r.get("default_ports", [])[:5],
            "enrich_queue": eq,
        })
    return queued


def build_batch_payload(queued: list, batch_id: str) -> dict:
    """Aggregate by action type for the /liaprobe-rule-enrich skill."""
    by_action = {}
    for q in queued:
        for action in q["enrich_queue"].get("actions_requested", []):
            atype = action.get("action", "unknown")
            by_action.setdefault(atype, []).append({
                "rule_file": q["path"],
                "pattern_id": q["pattern_id"],
                "vendor": q["vendor"],
                "product": q["product"],
                "cpe23_template": q["cpe23_template"],
                "current_threshold": q["current_threshold"],
                "default_ports": q["default_ports"],
                "action_params": {k: v for k, v in action.items() if k != "action"},
                "trigger": q["enrich_queue"].get("trigger"),
                "queued_at": q["enrich_queue"].get("queued_at"),
                "queued_by": q["enrich_queue"].get("queued_by"),
            })
    return {
        "schema": "lia-enrich-batch-v1",
        "batch_id": batch_id,
        "generated_at": NOW_ISO,
        "wave_id": WAVE_ID,
        "total_rules": len(queued),
        "total_actions": sum(len(v) for v in by_action.values()),
        "actions_by_type": {k: len(v) for k, v in by_action.items()},
        "batches": by_action,
    }


def mark_consumed(queued: list, batch_id: str, dry: bool) -> int:
    """Flip enrich_queue.wave_target to completed_<wave_id> + audit trail.
    Returns count of modified files. Idempotent.
    """
    count = 0
    for q in queued:
        if dry:
            count += 1
            continue
        p = Path(q["abs_path"])
        BACKUP_DIR.mkdir(parents=True, exist_ok=True)
        bp = BACKUP_DIR / p.name
        if not bp.exists():
            shutil.copy2(p, bp)
        try:
            r = json.loads(p.read_text())
        except (json.JSONDecodeError, OSError):
            continue
        auth = r.setdefault("_lia_independent_authoring", {})
        eq = auth.setdefault("enrich_queue", {})
        eq["wave_target"] = f"completed_{batch_id}"
        consume_hist = auth.setdefault("consume_history", [])
        consume_hist.append({
            "date": NOW_ISO,
            "batch_id": batch_id,
            "wave_id": WAVE_ID,
            "actions_dispatched": [a.get("action") for a in eq.get("actions_requested", [])],
            "marked_by": "consume_enrich_queue.py",
        })
        p.write_text(json.dumps(r, indent=2, ensure_ascii=False) + "\n")
        count += 1
    return count


def append_queue_history(queued: list, batch_id: str, dry: bool):
    """Move processed rows from queued table to History section in NEXT_ENRICH_QUEUE.md."""
    if dry or not QUEUE_MD.exists():
        return
    content = QUEUE_MD.read_text()
    if "## Audit trail (history)" not in content:
        return
    # Append history entries
    lines = []
    for q in queued:
        lines.append(
            f"| {NOW_ISO[:10]} | `{q['path']}` | `{q['pattern_id']}` | "
            f"batch={batch_id} wave={WAVE_ID} | "
            f"actions={','.join(a.get('action','?') for a in q['enrich_queue'].get('actions_requested', []))} |"
        )
    new_history = "\n".join(lines)
    # Insert after the existing history table (or create one). Idempotent
    # cosmetic guarantee: history rows accumulate AFTER the table header,
    # never inside the descriptive paragraph above it.
    insert_marker = "## Audit trail (history)"
    parts = content.split(insert_marker, 1)
    if len(parts) != 2:
        return
    history_section = parts[1]
    table_header = (
        "| Date processed | Rule file | Pattern ID | Batch | Actions dispatched |\n"
        "|----------------|-----------|------------|-------|--------------------|\n"
    )
    if "| Date processed |" not in history_section:
        history_section = (
            history_section.rstrip()
            + "\n\n" + table_header
            + new_history + "\n"
        )
    else:
        # Append rows after existing table (end of file)
        history_section = history_section.rstrip() + "\n" + new_history + "\n"
    new_content = parts[0] + insert_marker + history_section
    QUEUE_MD.write_text(new_content)


def main():
    p = argparse.ArgumentParser(description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--emit", action="store_true",
                   help="Write batch JSON to _alire/temp/apex/enrich_batches/")
    p.add_argument("--invoke", action="store_true",
                   help="After --emit, call `claude --print` with batch payload "
                        "and route to /liaprobe-rule-enrich skill. Implies --emit + --mark.")
    p.add_argument("--mark", action="store_true",
                   help="Flip enrich_queue.wave_target to completed_<batch> + append NEXT_ENRICH_QUEUE history. "
                        "Implied by --invoke.")
    p.add_argument("--batch-id", default=None,
                   help="Override batch id (default: SHA1(rules) prefix).")
    p.add_argument("--quiet", action="store_true",
                   help="No stdout summary, just exit code.")
    args = p.parse_args()

    queued = scan_queued_rules()
    if not args.quiet:
        print(f"[INFO] Found {len(queued)} rules with wave_target=next_enrich_pass")
        for q in queued:
            actions = [a.get("action", "?") for a in q["enrich_queue"].get("actions_requested", [])]
            print(f"  {q['pattern_id']:35s} {q['product']:30s} actions={actions}")

    if not queued:
        return 0

    sig_input = "|".join(sorted(q["pattern_id"] or "" for q in queued)).encode()
    batch_id = args.batch_id or hashlib.sha1(sig_input).hexdigest()[:12]
    payload = build_batch_payload(queued, batch_id)

    if args.invoke:
        args.emit = True
        args.mark = True

    if args.emit:
        BATCH_OUT_DIR.mkdir(parents=True, exist_ok=True)
        out = BATCH_OUT_DIR / f"enrich_batch_{RUN_DATE}_{batch_id}.json"
        out.write_text(json.dumps(payload, indent=2, ensure_ascii=False))
        if not args.quiet:
            print(f"\n[EMIT] Batch JSON: {out}")
            print(f"  rules: {payload['total_rules']}, actions: {payload['total_actions']}")
            print(f"  actions_by_type: {payload['actions_by_type']}")

    if args.mark:
        n = mark_consumed(queued, batch_id, dry=False)
        append_queue_history(queued, batch_id, dry=False)
        if not args.quiet:
            print(f"[MARK] {n} rules flipped to completed_{batch_id}")

    if args.invoke:
        # c22: direct call to run_enrich.py --from-batch-actions instead of
        # spawning a full `claude --print /liaprobe-rule-enrich` interactive
        # workflow. Faster, no API cost, deterministic, no agentic loop.
        # The skill's dispatcher (c21) handles action_type -> cycle_id +
        # inline mutations automatically.
        run_enrich_script = (
            DEV_DIR
            / ".claude/skills/liaprobe-rule-enrich/scripts/run_enrich.py"
        )
        if not run_enrich_script.exists():
            print(f"[ERROR] run_enrich.py not found at {run_enrich_script}",
                  file=sys.stderr)
            return 2
        cmd = [
            sys.executable,
            str(run_enrich_script),
            "--batch", str(out),
            "--from-batch-actions",
            "--liaprobe-root", str(LIAPROBE_DIR),
            "--summary",
            str(BATCH_OUT_DIR / f"enrich_batch_{RUN_DATE}_{batch_id}_summary.json"),
        ]
        if not args.quiet:
            print(f"\n[INVOKE] {' '.join(cmd)}")
        try:
            res = subprocess.run(cmd, capture_output=True, text=True,
                                 timeout=1800)
            if not args.quiet:
                print(f"[INVOKE] exit={res.returncode}")
                if res.stdout:
                    print(f"[INVOKE stdout]\n{res.stdout[:2000]}")
                if res.stderr:
                    print(f"[INVOKE stderr]\n{res.stderr[:1000]}",
                          file=sys.stderr)
            if res.returncode != 0:
                return res.returncode
        except subprocess.TimeoutExpired:
            print("[ERROR] run_enrich.py timed out after 30 min",
                  file=sys.stderr)
            return 3

    return 0


if __name__ == "__main__":
    sys.exit(main())
