# crt.sh (Certificate Transparency logs)

## Auth
- None. Public.

## Quotas
- No hard limit. Be polite (1 request/sec).
- Service can be slow during peak hours (timeouts common).

## Query syntax
- `?q=<vendor>` — search CN/SAN/issuer fields
- `&output=json` — JSON response
- Wildcards: `?q=%25example.com` (URL-encoded `%`)
- Identity search: `?q=mozilla.org&output=json`

## Endpoint
- GET `https://crt.sh/?q=<query>&output=json`
- Returns array of `{name_value: "host1\nhost2", issuer_ca_id, ...}`

## Use case in this skill
- Discover hostnames presenting certs that mention vendor/product.
- Yields HOSTNAMES ONLY. No body, no banner.
- Orchestrator must fetch the host separately to capture payload (HTTP GET).

## Caveats
- Many SANs are wildcards (`*.example.com`) — collector strips leading `*.`.
- Subdomain explosion possible: limit via `max_hosts`.
