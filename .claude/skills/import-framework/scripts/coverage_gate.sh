#!/usr/bin/env bash
# Coverage gate wrapper for clean-room framework imports.
# Reads PLAN.md baseline values from `_alire/tracking/import-frameworks/{CODE}/`
# and runs the Python coverage gate against `data/{code}_questions.json`.
#
# Usage:
# bash .claude/skills/import-framework/scripts/coverage_gate.sh {CODE} [--justified "reason"]
#
# Required tracking layout:
# _alire/tracking/import-frameworks/{CODE}/data/{code-lower}_questions.json
# _alire/tracking/import-frameworks/{CODE}/PLAN.md (must contain "assessables_legacy" or "assessables_reference")
#
# Exit codes:
# 0 = PASS
# 1 = FAIL (block commit)
# 2 = WARN without justification

set -euo pipefail

CODE="${1:?Usage: coverage_gate.sh CODE [--justified \"reason\"]}"
shift || true

JUSTIFIED=""
while [ $# -gt 0 ]; do
 case "$1" in
 --justified) JUSTIFIED="${2:-}"; shift 2 ;;
 *) echo "Unknown flag: $1" >&2; exit 2 ;;
 esac
done

ROOT="$(git rev-parse --show-toplevel 2>/dev/null || pwd)"
TR="${ROOT}/_alire/tracking/import-frameworks/${CODE}"

if [ ! -d "${TR}" ]; then
 echo "FAIL coverage_gate: tracking dir not found: ${TR}" >&2
 exit 1
fi

# Locate the hand-authored questions JSON.
# Convention: data/{code-lower}_questions.json OR data/ai_act_questions.json etc.
QFILE=""
for cand in \
 "${TR}/data/${CODE,,}_questions.json" \
 "${TR}/data/$(echo "$CODE" | tr A-Z a-z)_questions.json" \
 "${TR}/data/ai_act_questions.json" \
 "${TR}/data/csf2_questions.json" \
 "${TR}/data/iso27001_questions.json" \
 "${TR}/data/cis_questions.json" \
 "${TR}/data/dora_questions.json" \
 "${TR}/data/pci_questions.json" \
 "${TR}/data/soc2_questions.json" \
 "${TR}/data/hipaa_questions.json" \
 "${TR}/data/annex_nis2_questions.json"
do
 if [ -f "${cand}" ]; then
 QFILE="${cand}"
 break
 fi
done

if [ -z "${QFILE}" ]; then
 # Last-resort: any *_questions.json in data/
 QFILE="$(find "${TR}/data" -maxdepth 1 -name '*_questions.json' 2>/dev/null | head -n1)"
fi

if [ -z "${QFILE}" ] || [ ! -f "${QFILE}" ]; then
 echo "FAIL coverage_gate: no hand-authored questions JSON found under ${TR}/data/" >&2
 exit 1
fi

# Read baselines from PLAN.md.
# Convention: lines like "assessables_legacy: 462" or "assessables_reference: 462"
LEGACY=0
REFERENCE=0
if [ -f "${TR}/PLAN.md" ]; then
 LEGACY=$(grep -oE 'assessables_legacy[[:space:]]*[:=][[:space:]]*[0-9]+' "${TR}/PLAN.md" | grep -oE '[0-9]+' | head -n1 || echo 0)
 REFERENCE=$(grep -oE 'assessables_reference[[:space:]]*[:=][[:space:]]*[0-9]+' "${TR}/PLAN.md" | grep -oE '[0-9]+' | head -n1 || echo 0)
fi

if [ "${LEGACY}" = "0" ] && [ "${REFERENCE}" = "0" ]; then
 echo "WARN coverage_gate: no baseline declared in PLAN.md (assessables_legacy / assessables_reference). Coverage gate disabled for this framework." >&2
 echo "Add a line such as:" >&2
 echo " assessables_legacy: <N> # legacy DB assessable count (prior import)" >&2
 echo " assessables_reference: <N> # external reference count (public YAML / NIST OLIR)" >&2
 echo "to PLAN.md, then re-run." >&2
 exit 2
fi

OUT="${TR}/data/coverage_report.json"

ARGS=(
 --framework "${CODE}"
 --new-questions "${QFILE}"
 --legacy-count "${LEGACY}"
 --reference-count "${REFERENCE}"
 --out "${OUT}"
)

if [ -n "${JUSTIFIED}" ]; then
 ARGS+=(--justified "${JUSTIFIED}")
fi

python3 "${ROOT}/.claude/skills/import-framework/references/coverage-gate.py" "${ARGS[@]}"
