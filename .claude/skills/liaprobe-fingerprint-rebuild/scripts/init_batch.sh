#!/usr/bin/env bash
# init_batch.sh -- bootstrap a new batch session for liaprobe-fingerprint-rebuild
# Usage: ./init_batch.sh <batch_slug>
# Example: ./init_batch.sh top100_critical

set -euo pipefail

BATCH_SLUG="${1:-}"
if [ -z "$BATCH_SLUG" ]; then
  echo "Usage: $0 <batch_slug>"
  echo "Example: $0 top100_critical"
  exit 1
fi

DATE=$(date +%Y-%m-%d)
ROOT="_alire/tracking/liaprobe-fingerprint-rebuild"
SESSION_DIR="${ROOT}/sessions/${DATE}_${BATCH_SLUG}"

if [ -d "$SESSION_DIR" ]; then
  echo "ERROR: Session subdir already exists: $SESSION_DIR"
  echo "STRICT rule: 1 batch = 1 subdir. Choose another slug or use existing."
  exit 1
fi

mkdir -p "${SESSION_DIR}/captures"

# SESSION.md template
cat > "${SESSION_DIR}/SESSION.md" <<EOF
# Batch ${BATCH_SLUG} -- ${DATE}

## Goal

Re-author N rules from \`patterns/web-signatures/\`.
Selection criteria: <fill in>

## Input proposals

See \`proposals_${BATCH_SLUG}.json\`.

## Outcome

| Metric | Value |
|--------|-------|
| Proposed | TBD |
| AUTHORED | TBD |
| DEFERRED | TBD |
| SKIPPED | TBD |
| Verdict | PENDING |
| Wave score | TBD/50 |

## Files modified

(updated end-of-batch)

## Decisions

See \`decisions.md\`.

## Cross-repo commits

- LIA-SEC : (TBD)
- LiaProbe : (TBD)
EOF

# PLAN file
cat > "${SESSION_DIR}/PLAN_${BATCH_SLUG}.md" <<EOF
# PLAN -- ${BATCH_SLUG}

## Status: EN_COURS

## Sub-tasks

- [ ] Resolve canonical URLs for all proposals
- [ ] Capture artifacts (HTML/favicon/headers)
- [ ] Extract signals independently
- [ ] Author regex from observation
- [ ] Verify uniqueness against 5+ controls
- [ ] Write rule v2-independent
- [ ] Sample-verify 3 random rules end-to-end
- [ ] Update SESSION.md with verdict
- [ ] Append decision_log.jsonl entry
- [ ] Cross-repo commit (liaprobe + LIA-SEC)
EOF

# Empty journal + decisions
touch "${SESSION_DIR}/journal.jsonl"
cat > "${SESSION_DIR}/decisions.md" <<EOF
# Batch ${BATCH_SLUG} Decisions

(architectural decisions made during this batch)
EOF

# Empty proposals stub
cat > "${SESSION_DIR}/proposals_${BATCH_SLUG}.json" <<EOF
{
  "batch_slug": "${BATCH_SLUG}",
  "date": "${DATE}",
  "selection_criteria": "<fill in>",
  "rules": []
}
EOF

# Add captures to gitignore (if not already)
GITIGNORE_LINE="_alire/tracking/liaprobe-fingerprint-rebuild/sessions/*/captures/"
if ! grep -qF "$GITIGNORE_LINE" .gitignore 2>/dev/null; then
  echo "" >> .gitignore
  echo "# liaprobe-fingerprint-rebuild transient captures" >> .gitignore
  echo "$GITIGNORE_LINE" >> .gitignore
fi

echo "OK Batch session initialized:"
echo "  $SESSION_DIR/"
echo "    SESSION.md"
echo "    PLAN_${BATCH_SLUG}.md"
echo "    journal.jsonl"
echo "    decisions.md"
echo "    proposals_${BATCH_SLUG}.json"
echo "    captures/ (gitignored)"
echo ""
echo "Next steps:"
echo "  1. Edit proposals_${BATCH_SLUG}.json with rule list to rebuild"
echo "  2. Begin per-rule workflow (see references/workflow.md)"
echo "  3. Append journal.jsonl per rule"
