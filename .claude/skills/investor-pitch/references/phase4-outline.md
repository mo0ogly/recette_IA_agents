# Phase 4 -- OUTLINE

**Goal:** Produce the N-slide deck outline as the contract for phase 5. The outline is the BLOCKING checkpoint -- nothing gets generated until the user validates this file.

**Complexity:** MODERATE
**Dependencies:** Phase 3 complete
**Output:** deliverables/deck_outline.md, USER VALIDATED

## Critical rule

**NEVER call the pptx skill before the outline is user-validated.** The outline IS the contract. If the user changes their mind on slide 7 after the .pptx is built, you waste a build. If the user changes their mind after the outline is shown, you fix one Markdown file.

## Sub-tasks

| # | Sub-task | Tool | Success criteria |
|---|----------|------|------------------|
| 4.1 | Draft slide-by-slide structure | Write | deck_outline.md has N slides, each with title + key message |
| 4.2 | Cross-reference each slide to source files | Write | Every claim ends with [src: phase1/file or phase2/file or phase3/file] |
| 4.3 | Specify visuals per slide | Write | Each slide names its visual (chart, screenshot, diagram, table) |
| 4.4 | Specify speaker note headline | Write | Each slide has 1-2 lines of speaker hint |
| 4.5 | Self-review : zero unsourced claim | Read + Grep | grep "[src:" returns N+ matches, grep "TODO" returns 0 |
| 4.6 | Present G4 Outline gate to user (BLOCKING) | conversation | User answers OK / valide / go |

## Slide outline format

```markdown
# Deck Outline -- {PRODUCT}

Slides : {N}
Date : {YYYY-MM-DD}
Status : DRAFT / VALIDATED

## Slide 1 : Cover

Title : {Product} -- {Tagline}
Visual : Logo + tagline + round info
Key message : {one sentence}
Speaker note : {2 lines}
Sources : phase 0 scope_intake.md

## Slide 2 : The problem

Title : {short headline}
Visual : {chart / image / icon set}
Key message : {one sentence}
Bullet content :
- {claim} [src: research/regulatory_drivers.md#nis2]
- {claim} [src: research/competitors.md#gap-analysis]
- {claim} [src: research/market_sizing.md]
Speaker note : {2 lines}

## Slide 3 : ...
```

EVERY bullet on every slide must end with `[src: ...]`. No exceptions.

## Canonical 20-slide structure (LIA-SEC default, adapt to product)

| # | Slide | Source phase |
|---|-------|-------------|
| 1 | Cover (logo, tagline, round) | phase 0 |
| 2 | The problem (fragmented cyber stack) | phase 2 + 3 |
| 3 | The cost of inaction (regulatory pressure, breaches, GRC overhead) | phase 2 regulatory_drivers |
| 4 | The insight (real risk = CVE x exposure x misconfig x threat actor) | phase 3 narrative |
| 5 | The solution (one platform, N integrated modules) | phase 1 features_inventory |
| 6 | Architecture diagram (collectors -> engine -> dashboards -> remediation -> compliance) | phase 1 architecture_summary |
| 7 | The differentiator / moat (extensible Sigma-style rules + cross-correlation) | phase 3 moat |
| 8 | Agentic AI layer (LLM agents at every workflow step) | phase 1 features_inventory + phase 3 usp |
| 9 | Multi-persona views (CIO macro / admin micro / auditor offline) | phase 3 personas |
| 10 | Live screenshots (the 4 best captures from phase 1) | phase 1 screenshots/ |
| 11 | Real metrics (routes, tables, CVE, frameworks, AI providers) | phase 1 metrics.md |
| 12 | Use cases (CISO dashboard, audit on demand, continuous compliance, regulatory evidence) | phase 3 personas |
| 13 | Competitive landscape (table vs N competitors) | phase 2 competitors.md |
| 14 | Market sizing (TAM / SAM / SOM) | phase 2 market_sizing.md |
| 15 | Why now (NIS2, DORA, AI maturity, founder timing) | phase 2 regulatory_drivers + phase 3 narrative |
| 16 | Deployment models (SaaS Admin / Auditor airgap / On-premise / Hardened cloud) | phase 1 features + phase 3 personas |
| 17 | Pricing & business model | phase 3 pricing_strategy |
| 18 | 18-month roadmap | phase 3 roadmap |
| 19 | Team & traction | phase 0 scope_intake + public profiles |
| 20 | The ask (amount, use of funds, milestones) | phase 3 ask |

The 20 slides above are a STARTING point. The final outline must be tailored to the user's product, audience and round.

## Visual specification

For each slide, name the visual explicitly. Vague specs like "a nice chart" are forbidden. Examples:

- "Bar chart : market sizing TAM=EUR Xb / SAM=EUR Yb / SOM=EUR Zm, source labelled in caption"
- "Screenshot : platform/screenshots/05_compliance_dashboard.png"
- "Diagram : 4-layer architecture (collectors / engine / correlation / dashboards), Mermaid flowchart embedded as image"
- "Table : 5 competitors x 7 feature axes, green/yellow/red coverage cells"

If a visual requires generation (Mermaid -> PNG, custom illustration), note the tool to use:
- Mermaid -> mermaid CLI -> embed PNG
- Custom design -> canvas-design or frontend-design skill
- Theme styling -> theme-factory or brand-guidelines

## Self-review checklist (before G4)

```bash
# Zero TODO
grep -c "TODO" deliverables/deck_outline.md   # must be 0

# Every bullet has a source
grep -c "\[src:" deliverables/deck_outline.md  # must be >= number of bullets

# All referenced source files exist
grep -oP "\[src: \K[^\]]+" deliverables/deck_outline.md | sort -u | while read f; do
  test -f "${PITCH_DIR}/${f%%#*}" || echo "MISSING: $f"
done
```

If any check fails: STOP, fix, re-check. NEVER present a draft outline with red checks.

## G4 Outline gate -- exact wording to send to user

```
G4 OUTLINE VALIDATION (BLOCKING)

I have produced the deck outline at:
{PITCH_DIR}/deliverables/deck_outline.md

- {N} slides
- {M} bullet claims, all sourced
- {K} visuals specified (screenshots, diagrams, charts, tables)

Self-review : 0 TODO, {M} sourced bullets, all source files exist.

Top 3 slides I think are strongest :
1. Slide {X} : {title} -- {why}
2. Slide {Y} : {title} -- {why}
3. Slide {Z} : {title} -- {why}

Top 3 slides I think are weakest (and why) :
1. Slide {X} : {weakness}
2. ...

Please READ the full outline file. This is the contract -- once validated, the .pptx will be built from it without changes.

Reply "valide" or "OK" to proceed to phase 5 BUILD.
Reply with line-level changes if you want to adjust before build.
```

NEVER auto-progress past G4. NEVER assume validation. NEVER call the pptx skill on a draft outline.

## Anti-patterns in this phase

- Generating slides before validation
- Hiding weak slides ("the user won't notice")
- Vague visuals ("nice chart")
- Bullets without [src: ...]
- Adding new claims that are not in phase 1/2/3 files
- Padding slide count to reach N when fewer slides would tell a stronger story (if N is too high, ask the user to reduce)
