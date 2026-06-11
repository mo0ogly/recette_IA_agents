# Phase 3 -- POSITIONING

**Goal:** Turn phase 1 (facts) and phase 2 (market) into a compelling story. Narrative, USP, moat, personas, roadmap, pricing strategy, the ask.

**Complexity:** MODERATE
**Dependencies:** Phase 1 (G2) AND Phase 2 (G3) validated
**Output:** positioning/narrative.md, usp.md, moat.md, personas.md, roadmap.md, pricing_strategy.md, ask.md

## Why this phase exists

Phases 1 and 2 give us facts. An investor pitch is not facts -- it is a story arc that places those facts in tension and resolves the tension with the product. Phase 3 builds that story BEFORE we touch slides.

## Sub-tasks

| # | Sub-task | Tool | Success criteria |
|---|----------|------|------------------|
| 3.1 | Narrative (problem -> insight -> solution -> proof -> ask) | Write | narrative.md follows the story arc, every claim cross-refs phase 1 or 2 |
| 3.2 | USPs (3 to 5 unique selling propositions) | Write | usp.md justifies each USP against the competitor table |
| 3.3 | Moat analysis (defensibility) | Write | moat.md identifies >= 2 moat types (data, regulation, integration, team) |
| 3.4 | Personas (buyers + users) | Write | personas.md has >= 3 personas with pain + buying trigger |
| 3.5 | Roadmap 18/24/36 month | Write | roadmap.md has milestones tied to investor outcomes |
| 3.6 | Pricing strategy (our model) | Write | pricing_strategy.md has tier structure + ACV target derived from phase 2 |
| 3.7 | The ask | Write | ask.md has amount + use of funds + concrete milestones |

OPTIONAL: invoke `doc-coauthoring` skill for narrative.md if the user wants a co-authored draft.

## Narrative arc (template)

The investor narrative is always the same structure:

```
1. PROBLEM (slide 2-3)
   - The pain that exists in the market today
   - The cost of inaction (regulatory, financial, operational)
   - Why current tools fail
   -> source: phase 2 regulatory_drivers + phase 2 competitors gap analysis

2. INSIGHT (slide 4)
   - The non-obvious thing we figured out
   - The reason competitors cannot just bolt this on
   -> source: founder thesis + phase 2 competitor weaknesses

3. SOLUTION (slide 5-7)
   - What we built, in 1 sentence
   - The architecture in 1 diagram
   - The unique mechanism (the "how")
   -> source: phase 1 features_inventory + architecture_summary

4. PROOF (slide 8-12)
   - Working product (screenshots from phase 1)
   - Real metrics (from phase 1 metrics.md)
   - Differentiation table vs competitors (from phase 2)
   - Customer validation if any
   -> source: phase 1 + phase 2

5. MARKET (slide 13-15)
   - TAM / SAM / SOM (phase 2 market_sizing)
   - Why now (phase 2 regulatory_drivers)
   - Buyer personas (phase 3 personas)

6. BUSINESS (slide 16-17)
   - Pricing model (phase 3 pricing_strategy)
   - Go-to-market (phase 3 positioning)
   - Unit economics if any data

7. ROADMAP & TEAM (slide 18-19)
   - 18-24 month roadmap
   - Team credentials

8. ASK (slide 20)
   - Amount, use of funds, milestones tied to dollars
```

## USP framework

For each USP, fill the template:

```
### USP {N}: {one sentence}

What we do : {factual statement, source: phase 1 file}
What competitors do : {table reference: phase 2 competitors.md row}
Why this matters to the buyer : {persona reference: phase 3 personas.md}
Defensibility : {moat reference: phase 3 moat.md}
```

A USP that does not cross-reference 4 source files is not a USP -- it is a marketing claim.

## Moat types

Pick at least 2 from:

| Moat type | Example signal |
|-----------|---------------|
| Data | Proprietary dataset (CVE pipeline, threat intel feed, customer telemetry) |
| Regulation | Certification we hold that competitors don't (HDS, ISO, ANSSI label) |
| Integration | Network effect with framework providers, integrators, partners |
| Switching cost | Sticky workflow, multi-year contracts, deep customization |
| Team | Founder/operator background, prior exits, technical depth |
| Technology | Patented method, novel architecture, AI advantage |

For each, justify with phase 1 or phase 2 evidence.

## Pricing strategy template

Derive from phase 2 pricing_benchmarks.md. Do NOT just copy a competitor.

```
### Tier 1 : {name}
- Price : {amount} {currency} {period}
- For : {persona / company size}
- Includes : {features}
- Justification vs market : {why this number}

### Tier 2 : ...
### Tier 3 : ...

## ACV target (year 1 / year 3)
{amount with derivation}

## Pricing model
{per-asset / per-user / per-scan / flat / hybrid}
{justification: why this model fits the buyer behaviour}
```

## Ask template

```
## The Ask

Amount : {EUR X}
Round : {pre-seed / seed / series A}
Equity : {if known, else "open to discussion"}
Lead : {if known, else "seeking lead investor"}

## Use of funds

| Bucket | % | EUR | Outcome |
|--------|---|-----|---------|
| Engineering | X% | EUR Y | {N} hires, {feature} shipped |
| Rule QA / sandbox infra | X% | EUR Y | sandbox lab covering {N} techs |
| Sales / GTM | X% | EUR Y | {N} reps, {N} pilots, EUR Z ARR |
| Compliance / certification | X% | EUR Y | ISO 27001, HDS, ANSSI label |
| Working capital | X% | EUR Y | {N} months runway |

## 18-month milestones (tied to dollars)

| Month | Milestone | Funded by |
|-------|-----------|----------|
| 6 | {milestone} | {bucket} |
| 12 | {milestone} | {bucket} |
| 18 | {milestone} | {bucket} |
```

## End of phase 3

NO user gate at the end of phase 3. The user validates phase 4 (outline) which IS the synthesis of phase 3.

## Anti-patterns in this phase

- Writing narrative claims that are not in phase 1 or phase 2 files
- Inventing customer logos or testimonials
- Building a USP table that disagrees with phase 2 competitors.md
- Producing roadmap milestones unrelated to the funding bucket
- Setting prices without a derivation from phase 2 benchmarks
- Writing in vague visionary tone without facts
