# Phase 2 -- RESEARCH

**Goal:** Map the external world: competitors, market sizing, pricing benchmarks, regulatory drivers. Every claim has a URL + access date. Sources are cached in sources_raw/ for offline review.

**Complexity:** COMPLEX
**Dependencies:** Phase 0 G1 validated (independent of phase 1, can run in parallel)
**Output:** research/competitors.md, market_sizing.md, pricing_benchmarks.md, regulatory_drivers.md, web_research_log.md (continuously appended)

## Critical rule

**ALWAYS use the `websearch-agent` via the Agent tool.** NEVER call WebSearch or WebFetch directly for research. The agent isolates web noise, deduplicates sources, and produces structured reports. Direct WebSearch pollutes the main context with raw search results.

```
Agent({
  description: "Competitive landscape research",
  subagent_type: "websearch-agent",
  prompt: "{detailed brief, see templates below}"
})
```

## Sub-tasks (parallelizable)

| # | Sub-task | Tool | Success criteria |
|---|----------|------|------------------|
| 2.1 | Competitor landscape | websearch-agent | competitors.md has >= 5 vendors with feature coverage table |
| 2.2 | Market sizing TAM/SAM/SOM | websearch-agent | market_sizing.md has >= 3 sources for TAM, SAM derivation logic, SOM justification |
| 2.3 | Pricing benchmarks | websearch-agent | pricing_benchmarks.md has competitor pricing or "no public pricing" with link |
| 2.4 | Regulatory drivers | websearch-agent | regulatory_drivers.md covers NIS2/DORA/ANSSI/etc. with source URLs |
| 2.5 | Cache raw sources | Bash + WebFetch | sources_raw/ contains the most important pages |
| 2.6 | Append every search to web_research_log.md | Write | log is append-only, every row has URL |
| 2.7 | Present G3 Research gate to user | conversation | User confirms competitor set + sizing assumptions |

Sub-tasks 2.1-2.4 can be run as parallel agents (4 Agent tool calls in one message).

## Source taxonomy

Tag every source by kind in web_research_log.md:

| Tag | Examples | Trust level |
|-----|----------|------------|
| primary | Vendor website, official pricing page, government framework, regulator | HIGH |
| analyst | Gartner, Forrester, IDC, Frost & Sullivan reports | HIGH (if recent) |
| stats | Statista, Grand View Research, MarketsAndMarkets | MEDIUM (cite ranges) |
| news | TechCrunch, The Register, Reuters | MEDIUM |
| github | OSS repo README, CHANGELOG | HIGH for technical claims |
| blog | Vendor blog post, engineering blog | MEDIUM (vendor bias) |
| user | Reddit, HackerNews, G2/Capterra reviews | LOW (use only for sentiment) |

**Reject sources of unknown origin.** No "I read somewhere that..." -- if the agent cannot produce a URL, the claim does not exist.

## websearch-agent prompt templates

### 2.1 Competitor landscape

```
Research the competitive landscape for {PRODUCT_CATEGORY}, specifically:
- {COMPETITOR_1}, {COMPETITOR_2}, ... {COMPETITOR_N} (mandatory, named by user)
- 2-3 additional notable players you discover

For each vendor, produce:
- Company name + HQ + founding year
- Funding to date (sources: Crunchbase, PitchBook public profiles)
- Core product positioning (one sentence)
- Feature coverage on these axes: {LIST THE PRODUCT'S MODULES}
- Public pricing OR "no public pricing -- contact sales"
- Notable customer logos if public
- Source URL for every claim

Format as a Markdown table. NO speculation about features. If a feature is not documented on the vendor site, mark "unknown".

Save raw vendor pages to sources_raw/ when possible.

Output: research/competitors.md
```

### 2.2 Market sizing

```
Produce a TAM / SAM / SOM analysis for {PRODUCT_CATEGORY} in {GEOGRAPHY}.

TAM (Total Addressable Market):
- 2026 global market size for {CATEGORY}
- Sources: at least 2 of (Gartner, IDC, Forrester, Statista, Grand View Research)
- Growth rate (CAGR) with source

SAM (Serviceable Addressable Market):
- Subset for {GEOGRAPHY} + relevant verticals
- Derivation logic explained (how we narrow TAM down)
- Sources for the narrowing assumptions

SOM (Serviceable Obtainable Market):
- Realistic 3-year capture, with assumptions explicit (sales motion, ACV range, win rate)
- Comparable: how much did similar players capture in their first 3 years (named with sources)

Format: research/market_sizing.md with a section per layer.

CRITICAL: every number ends with [source: URL, accessed YYYY-MM-DD]. NO unsourced number.
```

### 2.3 Pricing benchmarks

```
Find public pricing information for: {COMPETITOR_LIST}.

For each:
- Tier name + price (USD or EUR, note currency)
- What is included
- Source URL (vendor pricing page or trusted secondary source)
- Date accessed

If no public pricing exists, write "no public pricing, contact sales" with the link to the contact-sales page. DO NOT estimate prices.

Also gather any public information about:
- Average contract value (ACV) in {CATEGORY}
- Pricing models in use (per-asset, per-user, per-scan, flat enterprise)

Output: research/pricing_benchmarks.md
```

### 2.4 Regulatory drivers

```
Document the regulatory drivers for {PRODUCT_CATEGORY} in {GEOGRAPHY}, specifically:

- NIS2 (EU) -- enforcement timeline, scope, penalties
- DORA (EU finance) -- enforcement timeline, scope
- ANSSI guidelines and certifications (FR)
- ISO 27001 / 27005 / 27002 update cycles
- GDPR (where relevant)
- Sectoral mandates (healthcare HDS, finance ACPR, defense, etc.)

For each: short summary, enforcement date, scope, source URL (official regulator or law text).

Why it matters for the deck: these are the market PULL forces. Show that the demand exists by law, not just by buyer goodwill.

Output: research/regulatory_drivers.md
```

## G3 Research gate -- exact wording to send to user

```
G3 RESEARCH VALIDATION

I have produced 4 research deliverables:

1. competitors.md -- {N} vendors compared on {N} feature axes
2. market_sizing.md -- TAM EUR {X}B, SAM EUR {Y}B, SOM EUR {Z}M (3yr)
3. pricing_benchmarks.md -- {N} competitors with pricing data
4. regulatory_drivers.md -- {N} regulations covered

Total sources cited : {N}, all with URLs in research/web_research_log.md
Raw sources cached : {N} files in sources_raw/

Key findings I plan to bring into the deck:
- {finding 1}
- {finding 2}
- {finding 3}

Please skim research/competitors.md and research/market_sizing.md.

Reply "valide" to proceed to phase 3 POSITIONING.
Reply with additions/removals if the competitor set or sizing assumptions need adjustment.
```

NEVER auto-progress past G3.

## Anti-patterns in this phase

- Calling WebSearch directly instead of websearch-agent
- Quoting "the cybersecurity market is worth $200B" without a source
- Inventing competitor pricing
- Listing competitors that the user did not approve
- Producing market sizing in TAM only (SAM and SOM are mandatory)
- Skipping the source cache (sources_raw/ must contain at least the top 10 pages)
