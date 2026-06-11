# Netlas.io

## Auth
- Env var: `NETLAS_API_KEY`
- Sign up: https://app.netlas.io/register/ (free)

## Quotas
- Free tier: 50 queries/day, 1500/month
- Pro: paid tiers add credits + history depth

## Query syntax
- `product:"nginx"` — exact product match
- `vendor:"Apache"` — vendor field
- `port:443`
- `http.headers.server:"nginx/1.24"` — header regex
- `http.title:"phpMyAdmin"` — title contains
- `http.favicon.hash_md5:<md5>` — favicon MD5

## API
- GET `https://app.netlas.io/api/responses/?q=<query>&size=<n>`
- Header: `X-API-Key: <key>`
- Returns JSON `{items: [{data: {host, port, http:{headers,body,status_code,banner}}}]}`

## Recommended usage in this skill
- Tier 1 priority. First fallback after auth check.
- Query template auto-built in `collectors/netlas.py::_build_query`.
- Polite spacing: 200 ms between calls.
