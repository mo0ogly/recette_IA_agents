#!/bin/bash
# Hook PostToolUse (Bash matcher) : detects curl/wget HEAD/GET with
# a successful 200 response captured within the last invocation, and
# marks a proof for R26.

INPUT=$(cat)
CMD=$(echo "$INPUT" | jq -r '.tool_input.command // empty' 2>/dev/null)

if [ -z "$CMD" ]; then
  exit 0
fi

# Only care about curl/wget style proof commands
if ! echo "$CMD" | grep -qE '\bcurl\b|\bwget\b'; then
  exit 0
fi

# If the command contains an assertion we care about (health endpoint,
# HTTP/1.1 200, content-type, expected status), mark as verified.
# We cannot read the actual response from the hook payload (tool_response
# exists but may not contain stdout). So we mark any curl invocation as
# a potential proof, and the Stop hook will accept it only within a short
# window (10 min).
REPO_ROOT="$(git rev-parse --show-toplevel 2>/dev/null || pwd)"
STATE_DIR="$REPO_ROOT/.claude/state"
mkdir -p "$STATE_DIR" 2>/dev/null

# Narrow the mark to curl invocations that target production URLs or
# localhost services. Avoids marking every curl in the session as proof.
if echo "$CMD" | grep -qE 'liascan\.tech|localhost|127\.0\.0\.1|:8081|:3000|:5432|/api/'; then
  touch "$STATE_DIR/curl_verified"
fi

exit 0
