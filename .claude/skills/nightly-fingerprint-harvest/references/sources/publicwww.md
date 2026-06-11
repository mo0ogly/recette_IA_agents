# PublicWWW

## Auth
- None for free web UI.
- Paid REST API exists; not used here.

## Quotas
- Free web UI: ~50 results/query, ~50 queries/day per IP.

## Query syntax
- Raw HTML / JS / CSS fragment.
- Examples:
  - `var _3d_cart=`
  - `powered by 3dcart Shopping Cart Software`
  - `<meta name="generator" content="WordPress`

## Endpoint
- GET `https://publicwww.com/websites/<urlencoded_needle>/`
- Returns HTML page; parse anchors to extract host list.

## Use case in this skill
- Best when the rule has a LITERAL needle in matchers (regex `contains` or
  a `regex` that is actually a literal — see Rule.literal_needles).
- Otherwise falls back to product name (less precise).

## Caveats
- No bypass to fetch body via PublicWWW: it only returns the host list.
- Orchestrator MUST issue a live HTTP fetch to capture full evidence.
