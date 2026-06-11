# Censys

## Auth
- Env var: `CENSYS_API_TOKEN` (Personal Access Token, Bearer auth) -- recommended
- Legacy: `CENSYS_API_ID` + `CENSYS_API_SECRET` (HTTP Basic) -- fallback
- Sign up: https://search.censys.io/register

## Quotas
- Community: 250 queries/month
- Enterprise: bulk

## Query syntax
- `services.software.product: "nginx"`
- `services.software.vendor: "Apache"`
- `services.banner: "OpenSSH_9.0"`
- `services.port: 443`
- `services.tls.certificates.leaf_data.subject.common_name: "*.example.com"`
- Combine with `and`/`or`

## API v2
- POST `https://search.censys.io/api/v2/hosts/search`
- Body: `{"q":"<query>","per_page":<n>}`
- Headers: `Authorization: Basic <token>`, `Content-Type: application/json`
- Returns `{result: {hits: [{ip, services: [{port, banner, http:{response:{headers,body,status_code}}}]}]}}`

## Recommended usage
- Tier 2. Most accurate banner cleanup.
- Limit per-host to 1 service to avoid blowing the budget.
