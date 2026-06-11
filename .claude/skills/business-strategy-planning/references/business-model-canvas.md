# Business Model Canvas + USP / Value Proposition

Reference for the business-model sub-task. Load when the deliverable requires a
BMC, a value proposition, or a USP statement.

## Table of contents

1. The 9 blocks
2. Fill order (right-to-left value-first)
3. USP framework
4. Value Proposition Canvas (pain/gain fit)
5. Revenue model patterns
6. LIA-SEC grounding

## 1. The 9 blocks

```
+------------------+------------------+---------+------------------+------------------+
| Key Partners     | Key Activities   |  Value  | Customer Rel.    | Customer         |
|                  +------------------+  Prop.  +------------------+ Segments         |
|                  | Key Resources    |         | Channels         |                  |
+------------------+------------------+---------+------------------+------------------+
| Cost Structure                      | Revenue Streams                              |
+-------------------------------------+----------------------------------------------+
```

1. Customer Segments -- who you create value for (distinct, prioritized)
2. Value Propositions -- the bundle that solves a real pain / creates a gain
3. Channels -- how you reach + deliver (awareness, evaluation, purchase, delivery, after-sales)
4. Customer Relationships -- self-serve, dedicated, community, automated
5. Revenue Streams -- how value converts to money (see block 5 below)
6. Key Resources -- the assets the model requires (IP, data, team, infra)
7. Key Activities -- what you must do well (engine R&D, rule authoring, RAG ops)
8. Key Partnerships -- who you rely on (cloud sovereign, channel, data feeds)
9. Cost Structure -- fixed + variable, value-driven vs cost-driven

## 2. Fill order (value-first)

Fill the right side first (customer + value), then the left (how you deliver),
then the bottom (economics). A BMC built infra-first usually invents a product
nobody asked for.

```
Segments -> Value Prop -> Channels -> Relationships -> Revenue
                       -> Key Resources -> Key Activities -> Partners -> Costs
```

## 3. USP framework

A USP is ONE sentence, defensible, and not copyable by an incumbent in a quarter.

```
For [segment] who [need/pain],
[product] is a [category] that [single biggest benefit],
unlike [main alternative], because [the structural reason it cannot be copied].
```

The "because" clause must be a STRUCTURAL moat (architecture, data, regulatory
posture), not a feature. A feature is copied; a structure is not.

## 4. Value Proposition Canvas (pain/gain fit)

```
Customer profile                Value map
-----------------               ---------------
Jobs-to-be-done       <----->   Products & services
Pains                 <----->   Pain relievers
Gains                 <----->   Gain creators
```

Fit exists when each top pain has a named reliever and each top gain a named
creator. Unmatched relievers = features nobody needs. Unmatched pains = gaps.

## 5. Revenue model patterns

| Pattern | When it fits | Note |
|---------|-------------|------|
| Per-seat SaaS | predictable usage per user | simple, caps expansion |
| Per-asset / per-scan | value scales with estate size | aligns price to value delivered |
| Tiered (Free/Pro/Enterprise) | broad funnel + upsell | needs a real free-tier hook |
| Usage / consumption | variable workloads | revenue less predictable |
| Platform + modules | suite with optional add-ons | land-and-expand; LIASCAN-shaped |

State the chosen pattern, the price metric, and why the metric tracks customer
value (the single most-challenged assumption in due diligence).

## 6. LIA-SEC grounding

When the BMC is for LIASCAN itself, anchor every block in the verified corpus
under `_alire/01_DOCUMENTATION/business-plan/`:

- Value Prop + USP: the 11 NO-DIRECT-COMPETITOR differentiators in
  `STRATEGIC_ASSESSMENT.md` (agnostic tree-parser engine, code/rules separation,
  nightly CVE rule-gen, 100% remediation coverage, agentic-by-design AI).
- Key Resources: the engine (`pkg/engine`), the rule corpus (~14,700 LiaProbe
  patterns + LIA-Scan rules), the 754-skill RAG, PostgreSQL data.
- Key Partnerships: sovereign FR cloud (OVH / Outscale / Scaleway), airgap posture.
- Cost Structure: single-VPS today (real constraint, state it honestly).

Never claim a block the code does not support. A BMC block with no file:line
backing is `UNVERIFIED` and must be flagged before it reaches an investor.
