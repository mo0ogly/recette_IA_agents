---
name: verify-fix
description: Run a strict live verification of a fix before claiming it is done. Invoke AFTER applying any fix (frontend, backend, infra) and BEFORE writing any "fix deploye / resolu / repare" claim. Scripts a Playwright/curl flow, captures console logs and screenshots, asserts the expected behavior, and outputs a PASS/FAIL verdict with proofs. If the result is FAIL, the fix is NOT done -- return to BUILD phase. Use when a user-flow exists. Triggers on "/verify-fix", "verify", "valide le fix", "preuve de fix", or autoinvoked at the end of debug-react/debug-go/deploy skills.
---

# /verify-fix - Live fix verification (R26)

## Why this skill exists

R26 (`.claude/rules/no-fix-without-live-verification.md`) forbids claiming
a fix done without running the actual user flow. This skill scripts the
verification in one pass and produces the exact proof format R26 requires:
user flow + assertion + snapshot.

Without this skill, I was declaring "fix deployed" after a surface-level
check (bundle 200, build OK, service active) and the user had to re-test
himself. The incident of 2026-04-24 (Launch Survey navigation bug) is the
reference case.

## When to invoke

- AFTER applying any fix that touches a user-facing path
- BEFORE writing the claim ("fix deploye", "reparee", "corrige", etc.)
- Whenever `/debug-react`, `/debug-go`, `/deploy` finish a fix
- When user asks "test it", "prove it works", "verify"

DO NOT invoke this skill:
- Before the fix is applied (nothing to verify yet)
- For pure doc changes (no user flow impacted)
- For test-only changes (already covered by their own test suite)
- For code cleanup without behavior change

## Input (the user or the preceding skill provides)

- **scenario** : short description of the user flow, IN THE USER'S WORDS
  (not my interpretation). Example: "on Compliance Frameworks, click
  Launch Survey for a framework, pick a client, submit, expect navigation
  to smsi-assessment-detail".
- **target_url** : URL entry point of the flow (e.g. https://liascan.tech/
  or http://localhost:3000/).
- **expected_assertion** : what must be true at the end. Either :
  - a log line signature (e.g. `[APP] Storage-driven navigation`)
  - a DOM element text (e.g. "Assessment Detail" in h1)
  - a network response shape (e.g. `POST /api/smsi/assessments -> 200 with id`)
- **auth_needed** : yes | no. If yes, request credentials or escape early.

## Workflow

### Phase 1 : OBSERVE

1. If `auth_needed=yes` and no credentials are available, STOP and output
   `VERDICT: UNVERIFIABLE - auth required`. Tell the user to provide
   credentials via `! lia_admin_pwreset` or give a test account.
2. Check the target URL is reachable : `curl -sI <target_url> | head -1`.
   If not 200/302/301, STOP and output `VERDICT: FAIL - target unreachable`.
3. Check the bundle/build is fresh : grep the deployed asset hash in
   `curl -s <target_url>/` and verify it matches a recent build.

### Phase 2 : RUN

1. `mcp__playwright__browser_navigate` to `<target_url>`.
2. Complete the auth flow if credentials are provided.
3. Navigate to the exact screen of the scenario
   (`mcp__playwright__browser_click` on each nav step).
4. Execute the user action (click, form fill, submit) that was reported
   as broken. Use `mcp__playwright__browser_snapshot` between steps to
   verify each intermediate state.
5. After the final action, wait 1-2 seconds then take :
   - `mcp__playwright__browser_snapshot` (ARIA tree of the result page)
   - `mcp__playwright__browser_console_messages(level="info")` (captures
     ALL `[COMPONENT]` logs from customLogger)

### Phase 3 : ASSERT

1. Search the console log output for the `expected_assertion` signature.
   If NOT found : VERDICT=FAIL, output the mismatch.
2. Search the ARIA snapshot for the expected UI element.
   If NOT found : VERDICT=FAIL.
3. If both present : VERDICT=PASS.

### Phase 4 : OUTPUT

Produce EXACTLY this structure :

```
VERDICT: PASS | FAIL | UNVERIFIABLE
User flow : <one-line recap of the scenario>
Target : <url>
Proof :
  - URL after action : <final url>
  - Console assertion : <matched line or "NOT FOUND">
  - DOM assertion : <matched element or "NOT FOUND">
  - Snapshot : .playwright-mcp/page-YYYY-MM-DD-...yml
  - Screenshot (if taken) : .playwright-mcp/page-...png
Next step :
  - PASS -> I can now say "fix verified" in the response
  - FAIL -> return to /debug-react or /debug-go with the evidence above
  - UNVERIFIABLE -> request creds or hand off to user with exact steps
```

### Phase 5 : CLAIM GATE

- If VERDICT=PASS : I MAY write a success claim with the proof block
  attached. R26 hook will see `.claude/state/playwright_recent` and allow
  the Stop.
- If VERDICT=FAIL : I MUST write "fix NOT verified, bug still reproducible"
  with the next debug step. No "should work" weasel words.
- If VERDICT=UNVERIFIABLE : I MUST write "livre, a verifier par toi"
  with the exact scenario steps for the user.

## Shortcuts when Playwright is not the right tool

**Backend API fix** : replace phases 2-3 by
```bash
RESP=$(curl -s -X <METHOD> "<URL>" -H "Authorization: Bearer $TOK" -d '<body>')
echo "$RESP" | jq .
# Assert shape / status / fields
```
Then drop `.claude/state/curl_verified` via `touch` (companion hook does
this automatically when the curl targets /api/).

**CLI / bash fix** : run the exact command, capture stdout+stderr+exit,
show the diff between before and after. Consider `diff` or `git diff`
as the assertion.

**Infra fix (systemd, nginx, etc)** : `systemctl is-active`, `nginx -t`,
`curl -sI` through the full nginx->backend path.

## Anti-patterns (forbidden)

- "The bundle is served 200 so the feature works" (deduction, not proof)
- "TypeScript compiles so the logic is correct" (type != runtime)
- "I checked the code, it looks right" (not a verification)
- "The test suite passes" (unit tests != user flow)
- Skipping Phase 3 ASSERT "because it obviously worked"

## Integration with other skills

| Skill | When it invokes /verify-fix |
|-------|-----------------------------|
| `/debug-react` | After Phase 4 VALIDER, before declaring resolved |
| `/debug-go` | After fix applied + build OK, before resolved |
| `/deploy` | After Phase 4 verification, before "deploy OK" claim |
| `/apex` | Phase 4c CONTRACT, supersedes surface-level smoke |
| `/audit-pdca` | Phase C.2 RUNTIME (Playwright smoke), enforced by R26 now |

## Tracing

Each invocation writes :
- `_alire/02_LOGS/Journals/verify_fix_log.jsonl` : `{timestamp, scenario,
  verdict, proofs_paths, duration_seconds}`
- `.claude/state/playwright_recent` : touched by companion PostToolUse hook
  (written automatically on any `mcp__playwright__*` call, not just by
  this skill)
- If FAIL : also updates the related PLAN_*.md TODO with the failure

## Example (from 2026-04-24 Launch Survey incident)

Input :
```
scenario = "On Compliance Frameworks, click Launch Survey on ADOBE_CCF,
pick a client+perimeter, click Create Assessment, expect navigation to
smsi-assessment-detail showing the new assessment"
target_url = https://liascan.tech/
expected_assertion = console log "[APP] Storage-driven navigation
{from: frameworks-manager, to: smsi-assessment-detail}"
auth_needed = yes
```

Had this skill existed at 11:38 UTC, I would have tried to run the flow,
hit the `auth_needed` gate with no creds, output `VERDICT: UNVERIFIABLE`
and said "livre, a verifier par toi" instead of "prod reparee, testez".
The user would have saved a round trip.
