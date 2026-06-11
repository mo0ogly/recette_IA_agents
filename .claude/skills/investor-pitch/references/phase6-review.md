# Phase 6 -- REVIEW (Claims Audit + Librarian Gate)

**Goal:** Audit every claim in the final deck against its source. Produce claims_audit.md. Run the librarian gate. Get final user approval (G5).

**Complexity:** MODERATE
**Dependencies:** Phase 5 .pptx generated
**Output:** deliverables/claims_audit.md, RETEX, INDEX.md updated, final commit

## Sub-tasks

| # | Sub-task | Tool | Success criteria |
|---|----------|------|------------------|
| 6.1 | Extract all claims from the deck | Bash : `python -c` to read pptx with python-pptx | claims.txt has every bullet |
| 6.2 | Cross-reference each claim to its source file | Grep + Read | claims_audit.md table populated |
| 6.3 | Flag any unsourced claim | Grep | Zero red flags before user review |
| 6.4 | Verify every metric is still current | Re-run commands from metrics.md | All metrics match the deck |
| 6.5 | Verify every URL is still alive | curl -I | All URLs return 200 (or note dead ones) |
| 6.6 | Write RETEX | Write | RETEX_INVESTOR_PITCH_{date}.md with score, learnings, next steps |
| 6.7 | Update tracking INDEX.md | Edit | Investor pitch entry added under appropriate section |
| 6.8 | Group commit (all artifacts together) | Bash : git | Single commit with all files of this pitch |
| 6.9 | Present G5 Final gate to user | conversation | User signs off, deck ready for delivery |

## Claims audit format

```markdown
# Claims Audit -- {PRODUCT} Investor Pitch

Date : {YYYY-MM-DD}
Deck file : deliverables/pitch_v1.pptx
Total slides : {N}
Total claims : {M}
Unsourced claims : 0 (target)

## Per-slide audit

### Slide 1 : Cover
| Claim | Source file | Verifiable | Status |
|-------|-------------|------------|--------|
| (no claims) | -- | -- | OK |

### Slide 2 : The problem
| Claim | Source file | Verifiable | Status |
|-------|-------------|------------|--------|
| "Cyber teams use 8+ disconnected tools" | research/competitors.md | https://gartner.com/... | OK |
| "GRC overhead consumes 30% of CISO time" | research/regulatory_drivers.md | https://isaca.org/... | OK |
...
```

If any row has Status != OK, STOP. Either:
- Fix the deck (remove or correct the claim)
- Find a source for the claim
- Ask the user to confirm before shipping

## Metric re-verification

For every metric quoted in the deck (slides 11, 14, 17, 20 typically), re-run the command from `platform/metrics.md` and confirm the value still matches.

If a metric has drifted (e.g., route count changed because new code was added), update the deck.

## URL liveness check

```bash
grep -oP "https?://[^\s\)]+" "${PITCH_DIR}/research/web_research_log.md" | sort -u | while read url; do
  status=$(curl -s -o /dev/null -w "%{http_code}" -I "$url" 2>/dev/null)
  echo "$status $url"
done > "${PITCH_DIR}/deliverables/url_check.txt"
```

Dead URLs (4xx, 5xx) must be replaced or removed.

## RETEX template

```markdown
# RETEX -- Investor Pitch {PRODUCT}

Date : {YYYY-MM-DD}
Working dir : _alire/tracking/investor_pitch_{slug}_{date}/
Status : COMPLETE

## Score agentique

| Critere | Score | Justification |
|---------|-------|---------------|
| C1 Decomposition | /10 | {phases + sub-tasks identified} |
| C2 Planification | /10 | {PLAN.md created in phase 0, updated, closed} |
| C3 Replanification | /10 | {N replans triggered : list} |
| C4 Outillage | /10 | {websearch-agent for web, pptx for build} |
| C5 Tracabilite | /10 | {decision_log entries : N, web_research_log entries : M, metrics_log entries : K} |
| **Total** | **/50** | |

## What worked

- {observation 1}
- {observation 2}

## What did not work

- {observation 1}
- {observation 2}

## Decisions worth remembering for next pitch

- {decision 1, with rationale}

## Improvements for the skill itself

- {if any}
```

## Librarian Gate

Before final commit:

```bash
# 1. Copy PLAN.md to canonical tracking location (already there if PITCH_DIR is correct)
ls "${PITCH_DIR}/PLAN.md"

# 2. Update INDEX.md with this pitch
# Find the Pitches section, append a new line
echo "- $(date +%Y-%m-%d) : Investor pitch {PRODUCT} {ROUND} -- ${PITCH_DIR}/deliverables/pitch_v1.pptx" \
  >> _alire/tracking/INDEX.md  # adapt to actual INDEX.md format

# 3. Stage and commit (group everything related to this pitch in one commit)
git add "${PITCH_DIR}" \
        _alire/02_LOGS/Journals/decision_log.jsonl \
        _alire/02_LOGS/Journals/retex/RETEX_INVESTOR_PITCH_*.md \
        _alire/tracking/INDEX.md

# Commit message
git commit -m "feat(pitch): investor deck for {PRODUCT} {ROUND}

- {N}-slide deck delivered : ${PITCH_DIR}/deliverables/pitch_v1.pptx
- {M} sourced claims, claims_audit.md clean
- Phases 0-6 complete, agentic score : {X}/50
- Working dir resumable across sessions"
```

NEVER `git add -A` -- always stage explicit files.
NEVER skip the RETEX -- it is part of the librarian gate.

## G5 Final gate -- exact wording to send to user

```
G5 FINAL DELIVERY

Investor pitch deck is ready :

- File : {PITCH_DIR}/deliverables/pitch_v1.pptx
- Slides : {N}
- Claims audit : {M} claims, 0 unsourced, {K} metrics re-verified
- URL liveness : {N} URLs checked, {N_dead} dead (replaced/removed)
- Speaker notes : {PITCH_DIR}/deliverables/speaker_notes.md
- Score agentique : {X}/50
- RETEX : {RETEX file}

Working directory is fully tracked and resumable :
{PITCH_DIR}/

Reply "valide" / "OK" to mark the skill complete and produce the librarian commit.
Reply with revisions if anything in the deck or claims_audit needs adjustment.
```

After user OK : run librarian gate, commit, present commit hash to user.

## Anti-patterns in this phase

- Skipping the claims audit
- Trusting that "the deck is fine" without re-running metric commands
- Forgetting to update INDEX.md
- Using `git add -A`
- Skipping the RETEX
- Declaring done before user G5 OK
