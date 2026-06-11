#!/usr/bin/env bash
# Wrapper invoked by n8n SSH node "Nightly Fingerprint Harvest".
#
# Workflow:
#   1. Source the skill .env (API keys).
#   2. Run nightly_run.py (capture stdout/stderr).
#   3. Run report_status.py (refresh global status).
#   4. Emit a single-line JSON synthesis to stdout for n8n to parse.
#
# Exit code mirrors the harvest run. n8n captures stdout regardless.

set -uo pipefail

DEV_DIR=/opt/lia-sec/dev
SKILL_DIR="$DEV_DIR/.claude/skills/nightly-fingerprint-harvest"
SESSION_ROOT="$DEV_DIR/_alire/tracking/liaprobe-fingerprint-rebuild"
LOG_DIR="$DEV_DIR/_alire/02_LOGS/nightly_harvest"
RUN_DATE="$(date -u +%Y-%m-%d)"
RUN_TS="$(date -u +%Y-%m-%dT%H:%M:%SZ)"
mkdir -p "$LOG_DIR"
RUN_LOG="$LOG_DIR/${RUN_DATE}_harvest.log"

log() {
    echo "[$(date -u +%Y-%m-%dT%H:%M:%SZ)] $*" >> "$RUN_LOG"
}

emit_json() {
    # Single-line JSON to stdout for n8n. Other diagnostics go to RUN_LOG.
    printf '%s\n' "$1"
}

# Load API keys (gitignored)
if [[ -f "$SKILL_DIR/.env" ]]; then
    set -a
    # shellcheck disable=SC1091
    . "$SKILL_DIR/.env"
    set +a
    log "loaded .env"
else
    log "WARN no .env at $SKILL_DIR/.env"
fi

# Tunable via n8n env override.
MAX_RULES="${HARVEST_MAX_RULES:-30}"
MAX_HOSTS="${HARVEST_MAX_HOSTS:-3}"
COOLDOWN_DAYS="${HARVEST_COOLDOWN_DAYS:-7}"
# Working free-tier sources only (censys/zoomeye/rapid7_sonar dropped 2026-06-01:
# dead credentials / moved API / needs offline dump). Override via HARVEST_SOURCES
# once fresh keys are supplied.
SOURCES="${HARVEST_SOURCES:-netlas,crtsh,publicwww}"

# Online live-recette wave (dork -> SERP -> live GET -> DETECT -> LIVE_VERIFIED).
# BOUNDED so a nightly run cannot blow the free SERP/Netlas quota: ONLINE_WAVE_SIZE
# rules x ONLINE_WAVES waves, deployable web-signatures only. Set ONLINE_ENABLED=0
# to skip the online step (harvest + inline only). wave_recette.py commits each
# wave via safe_commit (no push -- deploy/propagate pushes).
ONLINE_ENABLED="${ONLINE_RECETTE_ENABLED:-1}"
ONLINE_WAVE_SIZE="${ONLINE_WAVE_SIZE:-8}"
ONLINE_WAVES="${ONLINE_WAVES:-1}"

log "starting nightly_run max_rules=$MAX_RULES max_hosts=$MAX_HOSTS cooldown=$COOLDOWN_DAYS sources=$SOURCES"
HARVEST_START="$(date +%s)"
python3 "$SKILL_DIR/scripts/nightly_run.py" \
    --max-rules "$MAX_RULES" \
    --max-hosts "$MAX_HOSTS" \
    --cooldown-days "$COOLDOWN_DAYS" \
    --sources "$SOURCES" \
    >> "$RUN_LOG" 2>&1
HARVEST_RC=$?
HARVEST_ELAPSED=$(( $(date +%s) - HARVEST_START ))
log "nightly_run exit=$HARVEST_RC elapsed=${HARVEST_ELAPSED}s"

log "refreshing global status report"
python3 "$SKILL_DIR/scripts/report_status.py" >> "$RUN_LOG" 2>&1
REPORT_RC=$?
log "report_status exit=$REPORT_RC"

# ONLINE live-recette wave: probe the IP/domains found by harvest against the
# real engine via a live GET, advancing DETECT rules to LIVE_VERIFIED. Bounded
# (ONLINE_WAVE_SIZE x ONLINE_WAVES, deployable web-signatures) so the free
# SERP/Netlas quota is never blown. This is the missing online half: harvest
# finds hosts, the inline engine_reproduce step (below) re-checks captures, and
# THIS step does the outward live GET. wave_recette commits each wave itself.
ONLINE_LIVE=0
# Prefer the deployable-only filter (CMS/portal/admin rules a dork finds a LIVE
# instance of). But that pool drains; when it does, the night would do 0 online
# work despite 2300+ web-signature NONE rules waiting. ONLINE_DEPLOYABLE_ONLY=1
# (default) starts deployable; on a drained wave the loop FALLS BACK to a broader
# web-signature wave (no --deployable-only) so the backlog keeps moving. Set
# ONLINE_DEPLOYABLE_ONLY=0 to go broad from the first wave.
ONLINE_DEPLOYABLE_ONLY="${ONLINE_DEPLOYABLE_ONLY:-1}"
if [[ "$ONLINE_ENABLED" == "1" ]]; then
    log "online recette wave size=$ONLINE_WAVE_SIZE waves=$ONLINE_WAVES deployable_only=$ONLINE_DEPLOYABLE_ONLY"
    ONLINE_START="$(date +%s)"
    ONLINE_RC=0
    _deploy_flag=""
    [[ "$ONLINE_DEPLOYABLE_ONLY" == "1" ]] && _deploy_flag="--deployable-only"
    # wave_recette processes ONE wave per invocation (no --max-waves flag). Run it
    # ONLINE_WAVES times; each call self-selects the next NONE rules (stamped rules
    # leave the NONE queue, so offset 0 each call gets fresh ones) and self-commits
    # via safe_commit (--commit). On a drained deployable wave, drop the filter for
    # the rest of the run so the broader web-sig backlog is worked. Stop on rc!=0.
    _wave_out="$LOG_DIR/${RUN_DATE}_online_wave.out"
    for _w in $(seq 1 "$ONLINE_WAVES"); do
        python3 "$DEV_DIR/_alire/tracking/liaprobe-multirecette/tooling/wave_recette.py" \
            --wave-size "$ONLINE_WAVE_SIZE" \
            $_deploy_flag \
            --commit \
            > "$_wave_out" 2>&1
        rc=$?
        cat "$_wave_out" >> "$RUN_LOG"
        log "online wave $_w/$ONLINE_WAVES exit=$rc flag='${_deploy_flag:-broad}'"
        [[ "$rc" != "0" ]] && { ONLINE_RC=$rc; break; }
        # Deployable pool drained -> drop the filter and retry this wave broad.
        if [[ -n "$_deploy_flag" ]] && grep -q "queue drained at offset 0" "$_wave_out"; then
            log "deployable queue drained -> falling back to broad web-sig wave"
            _deploy_flag=""
            python3 "$DEV_DIR/_alire/tracking/liaprobe-multirecette/tooling/wave_recette.py" \
                --wave-size "$ONLINE_WAVE_SIZE" \
                --commit \
                >> "$RUN_LOG" 2>&1
            rc=$?
            log "online wave $_w/$ONLINE_WAVES (broad fallback) exit=$rc"
            [[ "$rc" != "0" ]] && { ONLINE_RC=$rc; break; }
        fi
    done
    rm -f "$_wave_out" 2>/dev/null
    ONLINE_ELAPSED=$(( $(date +%s) - ONLINE_START ))
    # Count LIVE stamped tonight from the wave heartbeat (newest waves first).
    ONLINE_LIVE=$(python3 - "$ONLINE_WAVES" <<'PYEOF' 2>>"$RUN_LOG"
import json, os, sys
hb = ("/opt/lia-sec/dev/_alire/tracking/liaprobe-multirecette/reports/"
      "wave_heartbeat.jsonl")
n = int(sys.argv[1]) if len(sys.argv) > 1 else 1
rows = []
if os.path.exists(hb):
    with open(hb, encoding="utf-8") as fh:
        for line in fh:
            try:
                rows.append(json.loads(line))
            except ValueError:
                pass
print(sum(r.get("live_count", 0) for r in rows[-n:]))
PYEOF
)
    log "online wave exit=$ONLINE_RC elapsed=${ONLINE_ELAPSED}s live_tonight=${ONLINE_LIVE:-0}"
else
    log "online recette wave SKIPPED (ONLINE_RECETTE_ENABLED=0)"
fi

# Refresh the UNIFIED recette board (joins this skill + multirecette + patterns
# proof). Keeps the operator's done/pending/todo view current every night.
log "refreshing unified recette board"
python3 "$DEV_DIR/_alire/tracking/liaprobe-recette-unified/tooling/unify_status.py" >> "$RUN_LOG" 2>&1
log "unify_status exit=$?"

# Engine reproduction: re-run the offline matcher engine on every capture and
# record what ACTUALLY fires (engine-detect + version PROVEN, not declared).
log "running engine reproduction harness"
python3 "$DEV_DIR/_alire/tracking/liaprobe-recette-unified/tooling/engine_reproduce.py" >> "$RUN_LOG" 2>&1
log "engine_reproduce exit=$?"

# Synthesis -- parse artefacts produced by the run.
SYNTHESIS=$(python3 - <<PYEOF
import json
import os
from pathlib import Path

session_root = Path("${SESSION_ROOT}")
run_date = "${RUN_DATE}"
status_path = session_root / "nightly" / ".state" / "rules_status.json"
manifest_path = session_root / "nightly" / run_date / "nightly_manifest.jsonl"
overview_md = session_root / "nightly" / ".state" / "global_status.md"

status = {}
if status_path.exists():
    try:
        status = json.loads(status_path.read_text())
    except Exception:
        pass

# Tonight's manifest stats.
captures_tonight = 0
promotion_ready_tonight = []
drift_tonight = []
if manifest_path.exists():
    with manifest_path.open() as fh:
        for line in fh:
            try:
                row = json.loads(line)
            except Exception:
                continue
            captures_tonight += 1
            if row.get("any_probe_matched") and row.get("match_score", 0) >= 0.6:
                promotion_ready_tonight.append({
                    "rule_id": row.get("rule_id"),
                    "source": row.get("source"),
                    "host": row.get("host"),
                    "score": row.get("match_score"),
                    "folder": row.get("folder"),
                })

# Aggregate buckets.
buckets = {
    "promotion_ready": 0,
    "drift_detected": 0,
    "captured_no_match": 0,
    "queried_no_capture": 0,
}
total_rules_known = len(status)
for entry in status.values():
    if entry.get("drift_detected"):
        buckets["drift_detected"] += 1
    elif entry.get("promotion_ready"):
        buckets["promotion_ready"] += 1
    elif entry.get("total_captures", 0) > 0:
        buckets["captured_no_match"] += 1
    else:
        buckets["queried_no_capture"] += 1

out = {
    "run_date": run_date,
    "run_ts": "${RUN_TS}",
    "harvest_rc": ${HARVEST_RC},
    "report_rc": ${REPORT_RC},
    "elapsed_seconds": ${HARVEST_ELAPSED},
    "max_rules": ${MAX_RULES},
    "max_hosts": ${MAX_HOSTS},
    "online_enabled": ${ONLINE_ENABLED},
    "online_wave_size": ${ONLINE_WAVE_SIZE},
    "online_waves": ${ONLINE_WAVES},
    "online_live_tonight": ${ONLINE_LIVE:-0},
    "sources": "${SOURCES}".split(","),
    "captures_tonight": captures_tonight,
    "promotion_ready_tonight": promotion_ready_tonight,
    "promotion_ready_top": promotion_ready_tonight[:10],
    "buckets_cumulative": buckets,
    "rules_in_tracker": total_rules_known,
    "log_path": str(Path("${RUN_LOG}")),
    "global_status_md": str(overview_md),
}
print(json.dumps(out))
PYEOF
)

emit_json "$SYNTHESIS"
exit $HARVEST_RC
