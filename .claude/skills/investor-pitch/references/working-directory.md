# Working Directory Layout

Each pitch lives in its own directory under `_alire/tracking/` so multiple pitches (different products, different rounds, different versions) coexist without collision.

## Directory pattern

```
_alire/tracking/investor_pitch_{PRODUCT_SLUG}_{YYYY-MM-DD}/
```

`PRODUCT_SLUG` is asked from the user in phase 0. Default = lower-case product name with hyphens (e.g. `lia-sec`).

## Layout (mandatory)

```
investor_pitch_{slug}_{date}/
├── README.md                            -- how to resume the work
├── PLAN.md                              -- phase tracking, current status, next action
├── decision_log.jsonl                   -- append-only decision log
│
├── research/
│   ├── web_research_log.md              -- every web fetch with URL + date + 1-line takeaway
│   ├── competitors.md                   -- competitive landscape, sourced
│   ├── market_sizing.md                 -- TAM/SAM/SOM with sources
│   ├── pricing_benchmarks.md            -- competitor pricing models, sourced
│   └── regulatory_drivers.md            -- NIS2/DORA/ANSSI/etc. as market drivers
│
├── platform/
│   ├── features_inventory.md            -- exhaustive feature list, code-verified
│   ├── architecture_summary.md          -- modules + integration story
│   ├── metrics.md                       -- every metric with the exact verification command
│   └── screenshots/                     -- Playwright captures (PNG)
│
├── positioning/
│   ├── narrative.md                     -- the story arc (problem -> insight -> solution -> ask)
│   ├── usp.md                           -- 3-5 unique selling propositions
│   ├── moat.md                          -- defensibility analysis
│   ├── personas.md                      -- buyers (CISO, RSSI, auditor, regulator, IT manager)
│   ├── roadmap.md                       -- 18 / 24 / 36 month milestones
│   ├── pricing_strategy.md              -- our own pricing model proposal
│   └── ask.md                           -- funding amount, use of funds, milestones tied to dollars
│
├── deliverables/
│   ├── deck_outline.md                  -- N-slide outline (the contract for .pptx)
│   ├── pitch_v1.pptx                    -- generated deck (phase 5)
│   ├── speaker_notes.md                 -- talking points per slide
│   └── claims_audit.md                  -- every claim cross-referenced to a source
│
└── sources_raw/
    └── {date}_{source-slug}.{html|pdf|md} -- raw cached pages for offline review
```

## README.md template

```markdown
# Investor Pitch -- {PRODUCT}

**Started:** {DATE}
**Owner:** {OWNER}
**Status:** EN_COURS / TERMINE / REPLANIFIE

## Resume from another session

If you (Claude or human) resume this work in a new session, do this in order:

1. Read `PLAN.md` -- master plan with phase tracking and current status
2. Read `decision_log.jsonl` (filter session=investor-pitch) -- decisions taken with reasoning
3. Read `research/web_research_log.md` -- every source consulted
4. Check `platform/features_inventory.md` for confirmed product facts
5. Check `deliverables/deck_outline.md` for the current slide structure (validated or draft)

The current state of the work is always reflected in PLAN.md checkboxes.

## Working principles

- NO INVENTION: every number, claim, or fact must have a source URL or a verified code reference
- SOURCE EVERYTHING: each line in competitors.md, market_sizing.md, pricing_benchmarks.md ends with [source: URL, accessed YYYY-MM-DD]
- CODE-VERIFIED METRICS: every internal metric has the exact verification command in metrics.md
- PHASES GATED: never skip a phase; user validates at G1 G2 G3 G4 G5
```

## PLAN.md template

```markdown
# PLAN -- Investor Pitch {PRODUCT}

Date : {YYYY-MM-DD}
Status : EN_COURS
Product slug : {slug}
Working dir : _alire/tracking/investor_pitch_{slug}_{date}/

## Objective

Build a {N}-slide investor deck for {PRODUCT} targeting {AUDIENCE} for a {ROUND_SIZE} round in {GEOGRAPHY}.

## Phases

- [ ] Phase 0 : INIT (scope intake + working dir + plan bootstrap)
  - [ ] G1 Scope validated by user
- [ ] Phase 1 : DISCOVERY (factual product inventory + screenshots)
  - [ ] G2 Discovery validated by user
- [ ] Phase 2 : RESEARCH (competitors + market + pricing + regulatory)
  - [ ] G3 Research validated by user
- [ ] Phase 3 : POSITIONING (narrative + USP + moat + roadmap + ask)
- [ ] Phase 4 : OUTLINE ({N}-slide structure with sources)
  - [ ] G4 Outline validated by user (BLOCKING -- no .pptx before this)
- [ ] Phase 5 : BUILD (.pptx via pptx skill)
- [ ] Phase 6 : REVIEW (claims audit + librarian gate)
  - [ ] G5 Final approval by user

## Working memory

Completed: []
Current: Phase 0
Pending: [1, 2, 3, 4, 5, 6]
Key findings: (empty)
Blockers: (none)

## Decisions taken

(append references to decision_log.jsonl entries here)

## Replans triggered

(none yet)

## Resultat

(filled at closure)
```

## decision_log.jsonl format

```json
{"timestamp":"2026-04-11T17:00:00Z","session":"investor-pitch","action":"PHASE_0_SCOPE_DEFINED","reasoning":"User confirmed: deep tech investors, EU geography, 20 slides, 5 competitors","alternatives_rejected":["10 slides (too short for the story)","global geo (out of scope for first round)"],"outcome":"Scope locked, working dir created","confidence":"high","plan_ref":"_alire/tracking/investor_pitch_lia-sec_2026-04-11/PLAN.md"}
```

One JSON per line. Append-only. Never edit past entries.
