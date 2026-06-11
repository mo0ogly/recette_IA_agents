#!/usr/bin/env python3
# nightly_fingerprint_batch.sh -- LiaProbe nightly fingerprint re-authoring
# Called nightly by n8n SSH node at 02:00 AM.
# Outputs synthesis JSON to stdout for n8n email workflow.
#
# Uses `claude` CLI (Claude Code) for API calls -- no ANTHROPIC_API_KEY needed.
# The `claude` binary must be in PATH and already authenticated via Claude Code.
#
# Env vars optional:
#   N_WAVES            -- number of waves (default: 10)
#   RULES_PER_WAVE     -- rules per wave (default: 10)
#   DRY_RUN            -- if "true", skip writes and commits (default: false)
#   MODEL              -- Claude model for normal rules (default: claude-haiku-4-5-20251001)
#   ESCALATE_MODEL     -- Claude model for retry on failure (default: claude-sonnet-4-6)

import json
import os
import re
import shutil
import sys
import subprocess
import urllib.request
import urllib.error
from datetime import datetime, timezone
from pathlib import Path
from wave_processor import WaveConfig, process_wave

# --- Configuration ---
DEV_DIR = Path("/opt/lia-sec/dev")
LIAPROBE_DIR = Path("/opt/lia-sec/liaprobe")
MASTER_TODO = DEV_DIR / "_alire/tracking/liaprobe-fingerprint-rebuild/MASTER_TODO_LIST.md"
PATTERNS_DIR = LIAPROBE_DIR / "patterns/web-signatures"
ARCHIVE_DIR = PATTERNS_DIR / "archive"
LOG_DIR = DEV_DIR / "_alire/02_LOGS/nightly_batch"
N_WAVES = int(os.environ.get("N_WAVES", "10"))
RULES_PER_WAVE = int(os.environ.get("RULES_PER_WAVE", "10"))
DRY_RUN = os.environ.get("DRY_RUN", "false").lower() == "true"
MODEL = os.environ.get("MODEL", "claude-haiku-4-5-20251001")
ESCALATE_MODEL = os.environ.get("ESCALATE_MODEL", "claude-sonnet-4-6")
# RESOLVE_VENDOR_URL: "heuristic" (default) = domain guess only, no HTTP
#                     "http" = heuristic + HTTP HEAD verify (adds ~2-4s/product)
#                     "off" = skip url resolution entirely
RESOLVE_VENDOR_URL = os.environ.get("RESOLVE_VENDOR_URL", "heuristic").lower()
CLAUDE_BIN = shutil.which("claude") or os.path.expanduser("~/.npm-global/bin/claude")
RUN_DATE = datetime.now(timezone.utc).strftime("%Y-%m-%d")
RUN_ID = f"nightly_{RUN_DATE}_{os.getpid()}"

LOG_DIR.mkdir(parents=True, exist_ok=True)
LOG_FILE = LOG_DIR / f"{RUN_DATE}_run.log"


def log(msg: str):
    ts = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    line = f"[{ts}] {msg}"
    print(line, file=sys.stderr)
    with open(LOG_FILE, "a") as f:
        f.write(line + "\n")


def _domain_candidates(taxonomy_name: str, taxonomy_code: str) -> list[str]:
    """Generate likely domain candidates from product name/code."""
    candidates = []
    name_slug = re.sub(r"[^a-z0-9]", "", taxonomy_name.lower().strip())
    code_slug = taxonomy_code.lower().replace("_", "")
    seen = set()
    for slug in [name_slug, code_slug]:
        if slug and slug not in seen:
            seen.add(slug)
            candidates.append(f"https://www.{slug}.com")
            candidates.append(f"https://{slug}.com")
            candidates.append(f"https://www.{slug}.io")
    return candidates


def resolve_vendor_url(taxonomy_name: str, taxonomy_code: str) -> str:
    """Return likely vendor website for a product.

    RESOLVE_VENDOR_URL=heuristic: return first candidate without HTTP check.
    RESOLVE_VENDOR_URL=http: verify with HTTP HEAD (timeout 2s) before returning.
    RESOLVE_VENDOR_URL=off: always return "".
    """
    if RESOLVE_VENDOR_URL == "off":
        return ""
    candidates = _domain_candidates(taxonomy_name, taxonomy_code)
    if not candidates:
        return ""
    if RESOLVE_VENDOR_URL == "heuristic":
        return candidates[0]
    for url in candidates:
        try:
            req = urllib.request.Request(url, method="HEAD")
            req.add_header("User-Agent", "Mozilla/5.0 (LiaProbe/2.0)")
            with urllib.request.urlopen(req, timeout=2) as resp:
                if resp.status < 400:
                    return url
        except Exception:
            continue
    return candidates[0]


def get_next_products(n: int) -> list[dict]:
    """Read next n FILE_ONLY products from MASTER_TODO_LIST.md.

    Skips rules carrying a vendor_dead block in their on-disk JSON (vendor
    confirmed dead by prior audit). These rules require a separate audit
    pass to re-test, not nightly re-authoring.
    """
    products = []
    skipped_dead = 0
    pattern = re.compile(r"^\| \[\.\] FILE_ONLY \| (\S+) \|")
    with open(MASTER_TODO) as f:
        for line in f:
            m = pattern.match(line)
            if not m:
                continue
            taxonomy_code = m.group(1)
            rule_file = PATTERNS_DIR / f"{taxonomy_code}.json"
            product_name = taxonomy_code.replace("_", " ").title()
            taxonomy_name = product_name
            vendor = ""
            vendor_website = ""
            if rule_file.exists():
                try:
                    rule = json.loads(rule_file.read_text())
                except Exception:
                    rule = {}
                # Skip if the on-disk rule has a vendor_dead block: nightly
                # must not re-author known-dead vendors (loop prevention).
                if rule.get("_lia_independent_authoring", {}).get("vendor_dead"):
                    skipped_dead += 1
                    continue
                product_name = rule.get("product", product_name)
                taxonomy_name = rule.get("taxonomy_name", product_name)
                vendor = rule.get("vendor", "")
                vendor_website = rule.get("vendor_website", "")
            if not vendor_website and RESOLVE_VENDOR_URL != "off":
                vendor_website = resolve_vendor_url(taxonomy_name, taxonomy_code)
            products.append({
                "taxonomy_code": taxonomy_code,
                "product": product_name,
                "vendor": vendor,
                "vendor_website": vendor_website,
            })
            if len(products) >= n:
                break
    if skipped_dead:
        log(f"  get_next_products: skipped {skipped_dead} dead-vendor rule(s)")
    return products


def write_rule(rule: dict, taxonomy_code: str, archived: bool = False):
    """Write rule JSON to liaprobe patterns dir (or archive/ if obsolete)."""
    if archived:
        ARCHIVE_DIR.mkdir(parents=True, exist_ok=True)
        out = ARCHIVE_DIR / f"{taxonomy_code}.json"
        active = PATTERNS_DIR / f"{taxonomy_code}.json"
        if active.exists():
            active.unlink()
    else:
        out = PATTERNS_DIR / f"{taxonomy_code}.json"
    out.write_text(json.dumps(rule, indent=2, ensure_ascii=False) + "\n")


def mark_authored(taxonomy_code: str, today: str):
    """Update MASTER_TODO: FILE_ONLY -> AUTHORED."""
    content = MASTER_TODO.read_text()
    old = f"| [.] FILE_ONLY | {taxonomy_code} |"
    new = f"| [x] AUTHORED  | {taxonomy_code} | nightly-batch | {today} |"
    if old in content:
        MASTER_TODO.write_text(content.replace(old, new, 1))


def mark_deferred(taxonomy_code: str, today: str, reason: str):
    """Update MASTER_TODO: FILE_ONLY -> DEFERRED."""
    content = MASTER_TODO.read_text()
    old = f"| [.] FILE_ONLY | {taxonomy_code} |"
    new = f"| [D] DEFERRED  | {taxonomy_code} | {reason[:30]} | {today} |"
    if old in content:
        MASTER_TODO.write_text(content.replace(old, new, 1))


def mark_archived(taxonomy_code: str, today: str):
    """Update MASTER_TODO: FILE_ONLY -> ARCHIVED (obsolete/defunct product)."""
    content = MASTER_TODO.read_text()
    old = f"| [.] FILE_ONLY | {taxonomy_code} |"
    new = f"| [a] ARCHIVED  | {taxonomy_code} | nightly-obsolete | {today} |"
    if old in content:
        MASTER_TODO.write_text(content.replace(old, new, 1))


def requeue_deferred():
    """Convert all DEFERRED entries back to FILE_ONLY so next run retries them."""
    content = MASTER_TODO.read_text()
    pattern = re.compile(r"^\| \[D\] DEFERRED  \| (\S+) \|.*$", re.MULTILINE)
    count = len(pattern.findall(content))
    if count == 0:
        return 0

    def to_file_only(m):
        return f"| [.] FILE_ONLY | {m.group(1)} | - | - |"

    MASTER_TODO.write_text(pattern.sub(to_file_only, content))
    log(f"  requeue_deferred: {count} DEFERRED -> FILE_ONLY (will retry this run)")
    return count


def git_commit_wave(wave_num: int, authored_names: list[str],
                    archived_names: list[str] | None = None):
    """Commit authored rules in both repos."""
    if archived_names is None:
        archived_names = []
    if DRY_RUN:
        log(f"  DRY_RUN: skipping git commit wave {wave_num}")
        return

    batch_tag = f"nightly-{RUN_DATE}-w{wave_num:02d}"
    parts = [f"{len(authored_names)} AUTHORED"]
    if archived_names:
        parts.append(f"{len(archived_names)} ARCHIVED")
    msg = f"liaprobe-fingerprint-rebuild: {batch_tag} ({', '.join(parts)})"
    all_names = authored_names + archived_names
    names_str = ", ".join(all_names[:5])
    if len(all_names) > 5:
        names_str += f" +{len(all_names)-5}"
    full_msg = f"{msg}\n\nProducts: {names_str}"

    def run_git(cwd: str, *args):
        result = subprocess.run(
            ["git"] + list(args),
            cwd=cwd, capture_output=True, text=True
        )
        if result.returncode != 0:
            log(f"  git {' '.join(args)} FAILED in {cwd}: {result.stderr[:200]}")
        return result.returncode == 0

    run_git(str(LIAPROBE_DIR), "add", "patterns/web-signatures/")
    run_git(str(LIAPROBE_DIR), "commit", "-m", full_msg)
    run_git(str(LIAPROBE_DIR), "push")

    run_git(str(DEV_DIR), "add",
            "_alire/tracking/liaprobe-fingerprint-rebuild/MASTER_TODO_LIST.md")
    run_git(str(DEV_DIR), "commit", "-m", full_msg)
    run_git(str(DEV_DIR), "push")


def count_remaining() -> int:
    """Count remaining FILE_ONLY entries."""
    pattern = re.compile(r"^\| \[\.\] FILE_ONLY \|")
    with open(MASTER_TODO) as f:
        return sum(1 for line in f if pattern.match(line))


def count_authored() -> int:
    """Count AUTHORED entries."""
    pattern = re.compile(r"^\| \[x\] AUTHORED")
    with open(MASTER_TODO) as f:
        return sum(1 for line in f if pattern.match(line))


def main():
    log(f"=== Nightly fingerprint batch START run_id={RUN_ID} ===")
    log(f"N_WAVES={N_WAVES} RULES_PER_WAVE={RULES_PER_WAVE} MODEL={MODEL} "
        f"ESCALATE_MODEL={ESCALATE_MODEL} DRY_RUN={DRY_RUN}")

    if not CLAUDE_BIN or not os.path.isfile(CLAUDE_BIN):
        error = f"claude CLI not found (looked for: {CLAUDE_BIN})"
        log(f"FATAL: {error}")
        print(json.dumps({
            "run_id": RUN_ID,
            "date": RUN_DATE,
            "status": "failed",
            "error": error,
            "waves_completed": 0,
            "total_authored": 0,
            "total_deferred": 0,
        }))
        sys.exit(1)

    requeued = requeue_deferred()
    remaining_before = count_remaining()
    log(f"FILE_ONLY remaining before run: {remaining_before} "
        f"(including {requeued} requeued from DEFERRED)")

    cfg = WaveConfig(
        n_waves=N_WAVES,
        rules_per_wave=RULES_PER_WAVE,
        model=MODEL,
        escalate_model=ESCALATE_MODEL,
        dry_run=DRY_RUN,
        run_date=RUN_DATE,
        resolve_vendor_url=RESOLVE_VENDOR_URL,
        claude_bin=CLAUDE_BIN,
        get_products=get_next_products,
        mark_authored=mark_authored,
        mark_deferred=mark_deferred,
        mark_archived=mark_archived,
        write_rule=write_rule,
        git_commit=git_commit_wave,
        log=log,
    )

    wave_results = []
    total_authored = 0
    total_archived = 0
    total_deferred = 0
    total_errors = 0
    total_input_tokens = 0
    total_output_tokens = 0
    total_api_calls = 0
    total_escalations = 0

    for wave_num in range(1, N_WAVES + 1):
        result = process_wave(wave_num, cfg)
        wave_results.append(result)
        total_authored += result["authored"]
        total_archived += result.get("archived", 0)
        total_deferred += result["deferred"]
        total_errors += result["errors"]
        u = result.get("usage", {})
        total_input_tokens += u.get("input_tokens", 0)
        total_output_tokens += u.get("output_tokens", 0)
        total_api_calls += u.get("calls", 0)
        if u.get("escalated"):
            total_escalations += 1
        if result["status"] == "empty":
            log("All products processed. Stopping early.")
            break

    remaining_after = count_remaining()
    authored_total = count_authored()
    total_rules = remaining_before + authored_total
    progress_pct = round(authored_total / total_rules * 100, 1) if total_rules > 0 else 0

    synthesis = {
        "run_id": RUN_ID,
        "date": RUN_DATE,
        "model": MODEL,
        "escalate_model": ESCALATE_MODEL,
        "dry_run": DRY_RUN,
        "token_usage": {
            "input_tokens": total_input_tokens,
            "output_tokens": total_output_tokens,
            "total_tokens": total_input_tokens + total_output_tokens,
            "api_calls": total_api_calls,
            "escalations": total_escalations,
        },
        "status": "completed",
        "waves_completed": len(wave_results),
        "this_run": {
            "authored": total_authored,
            "archived": total_archived,
            "deferred": total_deferred,
            "errors": total_errors,
        },
        "overall_progress": {
            "authored_total": authored_total,
            "remaining": remaining_after,
            "progress_pct": progress_pct,
            "estimated_nights_left": (
                round(remaining_after / max(total_authored, 1))
                if total_authored > 0 else None
            ),
        },
        "waves": wave_results,
    }

    log(f"=== DONE: authored={total_authored} archived={total_archived} "
        f"deferred={total_deferred} errors={total_errors} ===")
    log(f"Overall progress: {authored_total} authored, {remaining_after} remaining "
        f"({progress_pct}%)")

    # c19: consume enrich queue at end of nightly. Emits batch JSON to
    # _alire/temp/apex/enrich_batches/ for next /liaprobe-rule-enrich pass.
    # No --invoke here -- the next interactive session picks up the batch
    # (avoids hijacking the nightly cron with long-running enrich workflow).
    try:
        consume_script = Path(__file__).resolve().parent / "consume_enrich_queue.py"
        if consume_script.exists():
            log("[enrich-queue] scanning + emitting batch...")
            res = subprocess.run(
                [sys.executable, str(consume_script), "--emit", "--mark", "--quiet"],
                capture_output=True, text=True, timeout=120,
            )
            log(f"[enrich-queue] exit={res.returncode}")
            if res.stdout:
                log(f"[enrich-queue stdout]\n{res.stdout.strip()}")
            if res.stderr:
                log(f"[enrich-queue stderr]\n{res.stderr.strip()}")
            synthesis["enrich_queue"] = {
                "consume_exit_code": res.returncode,
                "consumed": res.returncode == 0,
            }
        else:
            log(f"[enrich-queue] skipped (script not found: {consume_script})")
            synthesis["enrich_queue"] = {"skipped": "script_not_found"}
    except (subprocess.TimeoutExpired, OSError) as e:
        log(f"[enrich-queue] error: {e}")
        synthesis["enrich_queue"] = {"error": str(e)}

    synthesis_file = LOG_DIR / f"{RUN_DATE}_synthesis.json"
    synthesis_file.write_text(json.dumps(synthesis, indent=2))

    print(json.dumps(synthesis))


if __name__ == "__main__":
    main()
