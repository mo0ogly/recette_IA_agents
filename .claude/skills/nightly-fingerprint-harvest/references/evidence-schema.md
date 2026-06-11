# Evidence schema

## Directory layout per run

```
_alire/tracking/liaprobe-fingerprint-rebuild/nightly/
  <YYYY-MM-DD>/
    nightly_manifest.jsonl     # append-only index of every capture
    <rule_id>/
      <source>_<host_sha8>/
        meta.json              # full metadata
        raw.bin                # HTTP body or TCP payload (bytes)
        headers.txt            # HTTP headers, one per line
        derived.json           # rule probes applied to this capture
  .state/
    quotas.json                # per-source daily/monthly call counters
```

## meta.json fields

| Field | Type | Description |
|-------|------|-------------|
| rule_id | string | LiaProbe rule id |
| source | string | netlas / censys / zoomeye / crtsh / publicwww / rapid7_sonar |
| host | string | IP or hostname observed |
| capture_url | string | URL fetched OR collector-scheme like `netlas:1.2.3.4:443` |
| http_status | int | HTTP response status code (0 if not HTTP) |
| html_sha256 | string\|null | SHA-256 of raw body bytes |
| headers_sha256 | string\|null | SHA-256 of joined headers |
| banner | string\|null | First-line banner (TCP/HTTP) |
| latency_ms | int | Round-trip latency |
| captured_at | string | ISO 8601 UTC |
| extra | object | Source-specific extras |

## derived.json fields

| Field | Type | Description |
|-------|------|-------------|
| rule_id | string | Same as meta.rule_id |
| any_probe_matched | bool | True if at least one matcher hit |
| banner_match | bool | True if a banner-target matcher hit |
| match_score | float | Sum of confidence_delta of hit matchers |
| matched_matchers | array | Details per hit matcher (incl. version_extract) |
| unmatched_matchers | array | Details per miss matcher |

## nightly_manifest.jsonl row shape

```json
{
  "rule_id": "trivy",
  "source": "netlas",
  "host_sha8": "a1b2c3d4",
  "host": "1.2.3.4",
  "capture_url": "netlas:1.2.3.4:4954",
  "http_status": 200,
  "html_sha256": "...",
  "headers_sha256": "...",
  "banner_match": false,
  "any_probe_matched": true,
  "match_score": 0.9,
  "folder": "nightly/2026-05-13/trivy/netlas_a1b2c3d4",
  "captured_at": "2026-05-13T22:30:11Z"
}
```

## Consumer contract

Downstream skill (APEX cycle, `liaprobe-rule-enrich`, recette) reads the
manifest and, for every row with `any_probe_matched=true`:

1. Promote `meta.html_sha256` -> rule's `artifacts.html_sha256`.
2. Promote `meta.capture_url` -> rule's `artifacts.capture_url`.
3. Append `meta.banner` to `examples[]` (banner-signatures).
4. Set `_lia_independent_authoring.http_gate.verified = true` and update
   `http_gate.date`.

Rows with `any_probe_matched=false` and `http_status=200` are kept for
adversarial review (false-positive auditing) but never promoted
automatically.
