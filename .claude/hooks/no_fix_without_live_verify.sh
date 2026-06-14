#!/bin/bash
# Hook Stop : R26 No Fix Without Live Verification
# Blocks the Stop when Claude claims "fix done / deployed / resolved" without
# a recent Playwright verification marker or an explicit unverified escape.
# Exit 2 = blocks Claude and forces a continuation message.

INPUT=$(cat)
RESPONSE=$(echo "$INPUT" | jq -r '.stop_response // empty' 2>/dev/null)

if [ -z "$RESPONSE" ]; then
  exit 0
fi

# G4 (OMC integration anti-loop): if Claude Code signals stop_hook_active, a
# Stop hook already ran in the current Stop chain (e.g. OMC persistent-mode
# forcing a continuation). Re-blocking here would create an infinite loop.
# R26 still blocks on the FIRST Stop (stop_hook_active=false); this only
# prevents re-entrancy. Standard Claude Code anti-loop pattern.
STOP_ACTIVE=$(echo "$INPUT" | jq -r '.stop_hook_active // false' 2>/dev/null)
if [ "$STOP_ACTIVE" = "true" ]; then
  exit 0
fi

# R26 clause "no excuse preamble": block responses that start with mea culpa,
# apology, or "you are right" patterns. The rule requires: deliver root cause
# + fix + proof directly, without preamble. User feedback 2026-04-24:
# "les excuses ne me vont pas".
FIRST_LINE=$(echo "$RESPONSE" | sed -n '1{/^\s*$/d;p;q;};2{p;q;}' | head -c 400)
EXCUSE_PATTERNS=(
  "^[[:space:]]*mea culpa"
  "^[[:space:]]*tu as raison"
  "^[[:space:]]*t'as raison"
  "^[[:space:]]*vous avez raison"
  "^[[:space:]]*desole"
  "^[[:space:]]*je m'excuse"
  "^[[:space:]]*mes excuses"
  "^[[:space:]]*pardon\b"
  "^[[:space:]]*sorry\b"
  "^[[:space:]]*my bad"
  "^[[:space:]]*my apolog"
  "^[[:space:]]*you'?re right"
)
for pattern in "${EXCUSE_PATTERNS[@]}"; do
  if echo "$FIRST_LINE" | grep -qiE "$pattern"; then
    cat >&2 <<EOF
R26 BLOCK: response starts with an excuse preamble ("$pattern" matched).
The rule forbids "mea culpa / tu as raison / desole" openings. Deliver
directly: root cause + fix + proof. No apology sentence before the
content. User feedback 2026-04-24: "les excuses ne me vont pas".
Reference: .claude/rules/no-fix-without-live-verification.md (R26 escape hatches section)
EOF
    exit 2
  fi
done

# Phrases claiming success. If any match, we require proof of verification.
CLAIM_PATTERNS=(
  "fix deploye"
  "fix appliqu"
  "fix prod"
  "prod reparee"
  "prod repar"
  "repare[ez]*"
  "resolu\b"
  "corrige\b"
  "fonctionne maintenant"
  "marche maintenant"
  "testez maintenant"
  "pret a tester"
  "ready to test"
  "production repaired"
  "bundle deploye"
  "deploy OK"
  "deployed and working"
  "tu peux tester"
  "vas-y teste"
  "ca marche"
)

# Explicit escape phrases that downgrade a claim to "not verified".
# If the response contains any of these AND the claim, we let it pass.
ESCAPE_PATTERNS=(
  "non verifie"
  "non-verifie"
  "a verifier par toi"
  "a verifier manuellement"
  "test manuel requis"
  "livre, a verifier"
  "requires manual verification"
  "user must verify"
  "test manuel requis"
)

# Check for a claim
HAS_CLAIM=0
for pattern in "${CLAIM_PATTERNS[@]}"; do
  if echo "$RESPONSE" | grep -qiE "$pattern"; then
    HAS_CLAIM=1
    MATCHED_CLAIM="$pattern"
    break
  fi
done

if [ "$HAS_CLAIM" = "0" ]; then
  exit 0
fi

# Check for an explicit escape phrase alongside the claim
for pattern in "${ESCAPE_PATTERNS[@]}"; do
  if echo "$RESPONSE" | grep -qiE "$pattern"; then
    exit 0
  fi
done

# Ack file bypass: user explicitly said "verified, move on"
ACK="$(git rev-parse --show-toplevel 2>/dev/null || pwd)/.claude/state/verify_ack"
if [ -f "$ACK" ]; then
  ACK_MTIME=$(stat -c %Y "$ACK" 2>/dev/null || echo 0)
  NOW=$(date +%s)
  AGE=$((NOW - ACK_MTIME))
  if [ "$AGE" -lt 900 ]; then
    exit 0
  fi
fi

# Proof check: Playwright recent marker (written by PostToolUse companion hook)
MARKER="$(git rev-parse --show-toplevel 2>/dev/null || pwd)/.claude/state/playwright_recent"
if [ -f "$MARKER" ]; then
  MARKER_MTIME=$(stat -c %Y "$MARKER" 2>/dev/null || echo 0)
  NOW=$(date +%s)
  AGE=$((NOW - MARKER_MTIME))
  # 15 minutes window
  if [ "$AGE" -lt 900 ]; then
    exit 0
  fi
fi

# Also accept : a very recent curl/fetch confirming 200 OR 2xx through a proof file
CURL_MARKER="$(git rev-parse --show-toplevel 2>/dev/null || pwd)/.claude/state/curl_verified"
if [ -f "$CURL_MARKER" ]; then
  CURL_MTIME=$(stat -c %Y "$CURL_MARKER" 2>/dev/null || echo 0)
  NOW=$(date +%s)
  AGE=$((NOW - CURL_MTIME))
  if [ "$AGE" -lt 600 ]; then
    exit 0
  fi
fi

# Claim without proof -> block.
cat >&2 <<EOF
R26 BLOCK: fix-success claim detected ("$MATCHED_CLAIM") without proof.
You must EITHER:
  1) Run the actual user flow via mcp__playwright__browser_* and capture
     the expected log / DOM assertion (screenshot or ARIA snapshot).
  2) OR explicitly downgrade the claim to "non verifie" / "a verifier par toi"
     with the reason.
  3) OR touch .claude/state/verify_ack if the user explicitly accepted
     the claim without verification.
Reference: .claude/rules/no-fix-without-live-verification.md (R26)
Related skill: /verify-fix
EOF
exit 2
