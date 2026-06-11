# Financial Model -- 3-year forecast + unit economics

Reference for the financial-projection sub-task. Load when the deliverable
requires a forecast, unit economics, or a raise-size justification.

## Table of contents

1. Three-year P&L structure
2. Revenue build (bottom-up)
3. Unit economics (the numbers investors interrogate)
4. SaaS metrics
5. Scenario discipline
6. LIA-SEC grounding + anti-confabulation

## 1. Three-year P&L structure

```
                         Y1      Y2      Y3
Revenue (from build)     ...     ...     ...
  - COGS (hosting, support)
= Gross profit  (= GP%)
  - S&M
  - R&D
  - G&A
= EBITDA
Headcount (FTE)          ...     ...     ...
Cash burn / runway
```

Keep it driver-based: every line is a formula on an assumption, not a typed
number. An investor changes one assumption and the whole sheet must recompute.

## 2. Revenue build (bottom-up)

Never type a revenue number. Build it:

```
New customers_month = leads x conversion%
ARR_end = ARR_start x (1 - churn%) + new_ARR + expansion_ARR
new_ARR = new_customers x ACV
```

State the four drivers explicitly: leads, conversion%, ACV, churn%. These are the
assumptions due diligence attacks first.

## 3. Unit economics

| Metric | Formula | Healthy signal |
|--------|---------|----------------|
| CAC | total S&M / new customers | lower is better |
| LTV | (ACV x GP%) / churn% | -- |
| LTV/CAC | LTV / CAC | > 3x |
| CAC payback | CAC / (ACV x GP% per month) | < 12-18 months |
| Gross margin | GP / revenue | > 70% for SaaS |
| NRR | (start ARR + expansion - churn) / start ARR | > 100% (ideally >110%) |

If LTV/CAC < 3 or payback > 18 months, the GTM is not yet investable -- say so
honestly rather than tuning assumptions to hit the target.

## 4. SaaS metrics narrative

Pair each metric with the lever that moves it:
- Low NRR -> packaging/expansion problem (modules, per-asset pricing).
- High CAC -> wrong motion for the ACV (field-sales on a low-ACV product).
- Low GM -> COGS leak (over-provisioned infra, manual support).

## 5. Scenario discipline

Present three scenarios, not one:
- Conservative (base): defensible, what you commit to.
- Expected: realistic, the number you plan around.
- Upside: what happens if the wedge over-performs.

Single-scenario forecasts read as wishful. The spread shows you understand risk.

## 6. LIA-SEC grounding + anti-confabulation

- LIASCAN runs on a single VPS today (8 vCPU / 32 GB) -- a REAL infra constraint.
  COGS and the scaling story must reflect it; do not model hyperscaler economics
  the deployment does not have. State the scaling step (multi-node) as a planned
  cost, not a current one.
- Sovereign-cloud / airgap deployments change COGS and the sales motion (longer
  cycle, higher ACV, on-prem support). Model the FR-regulated segment separately
  from the international SaaS segment, consistent with the competitive corpus.
- EVERY assumption number is sourced or tagged `ASSUMPTION` with its rationale.
  No number reaches an investor sheet unlabelled. A forecast cell with no driver
  behind it is `UNVERIFIED` and must be fixed before delivery (R18 / R4).
