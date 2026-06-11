#!/bin/bash
# Hook PostToolUse : marks a Playwright verification as recent.
# Drops a mtime-stamped marker read by no_fix_without_live_verify.sh.

REPO_ROOT="$(git rev-parse --show-toplevel 2>/dev/null || pwd)"
STATE_DIR="$REPO_ROOT/.claude/state"
mkdir -p "$STATE_DIR" 2>/dev/null

# Touch the marker; companion Stop hook checks mtime.
touch "$STATE_DIR/playwright_recent"
exit 0
