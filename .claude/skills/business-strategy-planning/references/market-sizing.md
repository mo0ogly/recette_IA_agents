# Market Sizing -- TAM / SAM / SOM

Reference for the market-sizing sub-task. Load when the deliverable requires a
quantified addressable market.

## Table of contents

1. Definitions
2. Top-down method
3. Bottom-up method (preferred, harder to dispute)
4. Five-step research process
5. Anti-confabulation discipline
6. Output table

## 1. Definitions

| Layer | Meaning | Question it answers |
|-------|---------|---------------------|
| TAM (Total Addressable Market) | Total revenue if 100% of every possible buyer bought | "How big is the whole space?" |
| SAM (Serviceable Available Market) | Slice of TAM reachable by this product, geography, segment, channel | "Who can we actually sell to today?" |
| SOM (Serviceable Obtainable Market) | Slice of SAM realistically captured in N years given competition + go-to-market capacity | "What do we actually plan to win?" |

SOM is the number that drives the financial model. TAM is the number that
opens the investor conversation. Never present TAM as if it were revenue.

## 2. Top-down method

Start from a published market figure, narrow by filters.

```
TAM   = published industry revenue (cite source + year)
SAM   = TAM x %addressable (geography, segment, regulation filter)
SOM   = SAM x realistic market share target (year 1..3)
```

Weakness: every % is a judgment call. An investor will challenge each filter.
Use top-down only to bound the bottom-up estimate.

## 3. Bottom-up method (preferred)

Build market from unit economics. Much harder to dispute.

```
SOM_year_N = (number of reachable accounts in segment)
           x (% you can close given GTM capacity)
           x (average annual contract value)
```

Then SAM = reachable accounts x ACV, TAM = total accounts x ACV.

Bottom-up forces you to state your ACV and close-rate assumptions explicitly,
which is exactly what a serious investor wants to interrogate.

## 4. Five-step research process

1. Clarify the decision the number must support (pricing? raise size? GTM focus?).
2. Desk research: pull published reports, statistics, regulator filings, vendor
   10-Ks. Record every figure with source + year.
3. Field/primary signal: customer interviews, pipeline data, design-partner ACVs.
4. Quantitative + qualitative reconciliation: top-down vs bottom-up must be the
   same order of magnitude. If they diverge >3x, one assumption is wrong -- find it.
5. Insight + recommendation: state the SOM, the 2-3 assumptions it rests on, and
   the sensitivity (what breaks it).

## 5. Anti-confabulation discipline (LIA-SEC mandatory)

- Every TAM/SAM number cites a real source (analyst report, regulator, public
  filing) with year. No invented figures.
- A figure with no source is tagged `UNVERIFIED -- placeholder` until sourced.
  Never let an unsourced number reach an investor deck.
- Distinguish a market estimate (ranged, sourced) from a target (your plan).
- For the cyber-GRC / vuln-management / threat-intel space relevant to LIASCAN,
  prefer EU/FR-segmented figures when the pitch separates FR vs international
  (consistent with the competitive-analysis corpus already built under
  `_alire/01_DOCUMENTATION/business-plan/competitive/`).

## 6. Output table

```markdown
| Layer | Value | Basis | Source (year) |
|-------|-------|-------|----------------|
| TAM | EUR X.Xbn | total cyber-GRC spend, region | <analyst>, 2026 |
| SAM | EUR XXXm | mid-market + regulated, FR+EU | derived: TAM x XX% |
| SOM y1 | EUR Xm | <N> accounts x EUR <ACV> x close% | bottom-up |
| SOM y3 | EUR XXm | scaled accounts + ACV uplift | bottom-up |
```
