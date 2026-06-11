# Anti-patterns -- Investor Pitch Skill

These patterns indicate the skill is being used wrong. Each is an instant FAIL : STOP, log to decision_log.jsonl with `action="ANTIPATTERN_DETECTED"`, fix, then continue.

## Phase boundary violations

| Anti-pattern | Why it's wrong |
|-------------|----------------|
| Generating slides before phase 4 outline is user-validated | The outline IS the contract. A draft outline produces a draft deck, which wastes the build and confuses the user. |
| Skipping phase 1 ("we already know the product") | Without re-verified metrics, the deck will contradict reality. Investors will catch the gap. |
| Skipping phase 2 ("we know the competitors") | The competitor list and market sizing must be sourced. Memory is not a source. |
| Running phase 5 without phase 4 G4 OK | The user is the loop closer. No exception. |
| Auto-progressing past a G gate | Every G gate (G1-G5) requires explicit user "valide" / "OK". Silence is not consent. |

## Sourcing violations

| Anti-pattern | Why it's wrong |
|-------------|----------------|
| Quoting a market number without a source URL on the same line | Investors will ask "where does this come from" -- if the answer is "memory" or "I think", the deck is dead. |
| Reusing a metric from CLAUDE.md without re-running its command | Metrics drift. The number in CLAUDE.md was true on a date. Re-verify always. |
| Inventing competitor pricing | "They probably charge X" is invention. Write "no public pricing, contact sales" with a URL to their contact page. |
| Listing a competitor the user did not approve | The user owns the competitor set. Adding without asking inflates the field and may include irrelevant players. |
| Claiming a customer or partnership that does not exist | Career-ending lie. Never. |

## Tool violations

| Anti-pattern | Why it's wrong |
|-------------|----------------|
| Calling WebSearch directly instead of websearch-agent | Pollutes context with raw search noise. Agents return structured reports. |
| Reimplementing slide generation instead of calling pptx skill | The pptx skill exists, is tested, and handles edge cases. Reimplementing is wasted effort and brittle. |
| Reading 30 source files via Read instead of using Grep | Token waste. Grep is the right tool for cross-file pattern search. |
| Running commands directly to navigate Playwright instead of webapp-testing skill | The skill encapsulates the right invocation pattern. Direct mcp__playwright__ calls bypass the methodology. |

## Tracking violations

| Anti-pattern | Why it's wrong |
|-------------|----------------|
| Forgetting to create PLAN.md in phase 0 | Breaks resume across sessions. The next session has no idea where you stopped. |
| Not appending to web_research_log.md after every search | The log is the audit trail. Without it, the source set is unverifiable. |
| Editing past entries in decision_log.jsonl | The log is append-only. Editing breaks audit trail integrity. |
| Skipping the claims_audit.md in phase 6 | The audit is the final defense against shipping unsourced claims. |
| Using `git add -A` in the librarian gate | Risk of committing unrelated files. Always stage explicit paths. |
| Skipping the RETEX | The RETEX is what makes the next pitch better. No RETEX = no learning. |

## Narrative violations

| Anti-pattern | Why it's wrong |
|-------------|----------------|
| Marketing words in phase 1 ("powerful", "next-gen", "revolutionary") | Phase 1 is purely factual. Marketing tone destroys the source-of-truth quality. |
| Padding the deck with vision slides when data is thin | Investors prefer "we have 3 modules that work" over "we will build 10 modules". Show what is real. |
| Hiding weak slides | Strong investors will spot the weakness anyway. Acknowledge in the pitch and turn it into the ask. |
| Producing a deck that contradicts phase 1 metrics | Internal contradiction = death. Run claims_audit BEFORE shipping. |

## Scope violations

| Anti-pattern | Why it's wrong |
|-------------|----------------|
| Treating the product as LIA-SEC by default | The skill is product-agnostic. Always ask in phase 0 "what product?". |
| Locking the slide count to 20 when the user said 12 | The user owns the slide count. Adjust the canonical 20-structure to fit. |
| Ignoring the audience parameter | A deck for a generalist VC is not the same as a deck for a deep-tech VC. Tone and depth differ. |
| Producing in French when audience is global | English is the default for international investors unless the user says otherwise. |

## Recovery protocol when an anti-pattern is detected

1. STOP the current action
2. Log to decision_log.jsonl :
   ```bash
   echo '{"timestamp":"'$(date -u +%Y-%m-%dT%H:%M:%SZ)'","session":"investor-pitch","action":"ANTIPATTERN_DETECTED","reasoning":"{which one}","alternatives_rejected":[],"outcome":"reverting","confidence":"high","plan_ref":"'${PITCH_DIR}'/PLAN.md"}' >> _alire/02_LOGS/Journals/decision_log.jsonl
   ```
3. Revert or fix the offending action (delete the bad slide, remove the unsourced claim, re-run the command)
4. Document the fix in PLAN.md "Decisions taken" section
5. Resume from the corrected state

NEVER hide an anti-pattern. NEVER ship despite a detected anti-pattern. The audit trail must reflect the recovery.
