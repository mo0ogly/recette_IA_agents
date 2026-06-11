# Output Schema -- lia-fingerprint-v2-independent

## Full template

```json
{
  "$schema": "lia-fingerprint-v2-independent",
  "id": "<product_slug>",
  "version": "2.0.0",
  "enabled": true,
  "taxonomy_code": "<UPPER_SLUG>",
  "taxonomy_name": "<ProductName>",
  "product": "<ProductName>",
  "vendor": "<VendorName_or_empty>",
  "default_ports": [80, 443],
  "probes": [
    {
      "id": "lia_<slug>_http",
      "layer": "L7_HTTP",
      "method": "GET",
      "path": "/",
      "follow_redirects": true,
      "matchers": [
        {
          "target": "script_src|cookie|header|body|favicon_mmh3|favicon_hash",
          "match_type": "regex|exact|exists|equals",
          "value": "<your_independent_regex_or_value>",
          "field": "<optional_for_cookie_or_header>",
          "confidence_delta": 0.5
        }
      ]
    }
  ],
  "base_confidence": 0.0,
  "confidence_threshold": 0.6,
  "tags": [],
  "_lia_independent_authoring": {
    "review_date": "<YYYY-MM-DD>",
    "operator": "<operator_id>",
    "method": "direct_public_observation",
    "vendor_website": "<https://canonical/>",
    "artifacts": {
      "html_sha256": "<64hex>",
      "favicon_sha256": "<64hex_or_null>",
      "headers_sha256": "<64hex>",
      "favicon_mmh3": "<int32_signed_or_null>",
      "capture_url": "<exact URL captured -- MANDATORY post-2026-05-07 audit>",
      "observation_provenance": "vendor_self_host|real_deployment_third_party|documented_default_behavior"
    },
    "rationale": "<why_this_regex_uniquely_matches>",
    "false_positive_check": "<patterns_tested_against_unrelated_sites>",
    "third_party_catalog_references_consulted": "NONE -- pattern authored from public observation",
    "supersedes_prior_rule": "<existing_rule_path>"
  }
}
```

## Required fields (BLOCKING)

| Field | Type | Required |
|-------|------|----------|
| `$schema` | string | YES, must equal `lia-fingerprint-v2-independent` |
| `id` | string | YES, snake_case slug |
| `taxonomy_code` | string | YES, UPPER_SNAKE |
| `taxonomy_name` | string | YES, human-readable |
| `product` | string | YES |
| `vendor` | string | optional but recommended |
| `default_ports` | int[] | YES, at minimum [80,443] for web |
| `probes` | object[] | YES, >=1 probe |
| `confidence_threshold` | number | YES, recommend 0.6 |
| `_lia_independent_authoring` | object | **YES, all sub-fields required** |

## _lia_independent_authoring sub-fields (BLOCKING)

| Sub-field | Type | Required |
|-----------|------|----------|
| `review_date` | string ISO date | YES |
| `operator` | string | YES |
| `method` | string | YES, must equal `direct_public_observation` |
| `vendor_website` | string URL | YES |
| `artifacts.html_sha256` | string 64hex | YES |
| `artifacts.favicon_sha256` | string 64hex or null | YES (null if no favicon) |
| `artifacts.headers_sha256` | string 64hex | YES |
| `artifacts.favicon_mmh3` | int or null | YES (null if no favicon) |
| `artifacts.capture_url` | string URL | **YES** (added 2026-05-07 post-audit retroactif). Exact URL captured -- must match `captures/{PRODUCT}/MANIFEST.json` `capture_url`. NEVER empty when `html_sha256` is present. |
| `artifacts.observation_provenance` | string enum | **YES** (added 2026-05-07). One of `vendor_self_host` / `real_deployment_third_party` / `documented_default_behavior`. NEVER `vendor_marketing_site`. |
| `rationale` | string | YES, >=20 chars |
| `false_positive_check` | string | YES, list control URLs tested |
| `third_party_catalog_references_consulted` | string | YES, must equal `"NONE -- pattern authored from public observation"` |
| `supersedes_prior_rule` | string | YES, path to prior rule |

## Forbidden fields (DO NOT INCLUDE)

| Field | Why forbidden |
|-------|---------------|
| `categories` | Third-party catalog category IDs = compilation copyright |
| `notes` | Third-party catalog descriptions verbatim = literal copy |
| `website` | If copied from prior rule = literal copy. If re-derived from independent obs OK to keep but redundant with vendor_website. |
| `source.original_name` | Hint of catalog origin |
| `source.file` | Hint of catalog filename |

## Allowed matcher targets

| target | Use case | Notes |
|--------|----------|-------|
| `script_src` | <script src=...> URL pattern | Most common for SaaS detection |
| `cookie` | Set-Cookie name/value | Use `field` sub-key for cookie name |
| `header` | HTTP response header | Use `field` for header name |
| `body` | HTML body content | Be specific to avoid FP |
| `favicon_mmh3` | Shodan-style int32 hash | Numeric exact match |
| `favicon_hash` | Legacy MD5 favicon hash | Backwards compat (deprecated for new rules) |
| `meta` | <meta> tag content | content attribute regex |
| `link_href` | <link rel> href URL | CSS/manifest patterns |

## jq validation

```bash
# Validate single rule schema (post-2026-05-07 audit, includes capture_url + observation_provenance gates)
RULE="patterns/web-signatures/ADFORM.json"
jq -e '
  .["$schema"] == "lia-fingerprint-v2-independent"
  and .id != null
  and .product != null
  and (.probes | length) >= 1
  and ._lia_independent_authoring.method == "direct_public_observation"
  and (._lia_independent_authoring.third_party_catalog_references_consulted | startswith("NONE"))
  and ._lia_independent_authoring.artifacts.html_sha256 != null
  and ._lia_independent_authoring.artifacts.capture_url != null
  and (._lia_independent_authoring.artifacts.capture_url | length) > 0
  and (._lia_independent_authoring.artifacts.observation_provenance |
       . == "vendor_self_host" or
       . == "real_deployment_third_party" or
       . == "documented_default_behavior")
' "$RULE" || echo "INVALID: $RULE"
```

## Migration -- prior schema mapping

Prior schema `lia-fingerprint-v1` -> new `lia-fingerprint-v2-independent` :

| Prior field | Action |
|-------------|--------|
| `$schema: lia-fingerprint-v1` | Replace with `lia-fingerprint-v2-independent` |
| `categories: [...]` | DROP |
| `notes: "..."` | DROP |
| `source.original_name` | DROP |
| `source.file` | DROP, replaced by `_lia_independent_authoring.supersedes_prior_rule` |
| `probes[].matchers[].value` (regex) | RE-WRITE from observation, do NOT copy |
| `id`, `taxonomy_code`, `product` | KEEP (factual) |
| `default_ports`, `confidence_threshold` | KEEP |

## Sanity checks per output

```bash
RULE_PATH="patterns/web-signatures/ADFORM.json"

# 1. Schema valid
jq -e '.["$schema"] == "lia-fingerprint-v2-independent"' "$RULE_PATH"

# 2. Authoring block complete
jq -e '
  ._lia_independent_authoring.html_sha256 != null
  and ._lia_independent_authoring.method == "direct_public_observation"
  and ._lia_independent_authoring.third_party_catalog_references_consulted | startswith("NONE")
' "$RULE_PATH"

# 3. No forbidden field
for f in categories notes; do
  if jq -e "has(\"$f\")" "$RULE_PATH" >/dev/null; then
    echo "FORBIDDEN field $f present in $RULE_PATH"
    exit 1
  fi
done

# 4. Probes have at least 1 matcher
jq -e '.probes | length >= 1 and (.[0].matchers | length >= 1)' "$RULE_PATH"
```

## Backwards compatibility

The runtime loader (`pkg/fingerprint/loader.go`) accepts both `lia-fingerprint-v1` and `lia-fingerprint-v2-independent` schemas during transition. v2 rules are loaded with `_lia_independent_authoring` metadata available for audit but not used at scan time.

## Audit retroactif 2026-05-07 -- post-mortem

Discovered systemic issues across batches 001-066 that drove the schema changes above :

| Finding | Count / % | Schema response |
|---------|-----------|-----------------|
| Total rules in `patterns/web-signatures/` | 5418 | n/a |
| Rules with `_lia_independent_authoring` block | 506 (9.3%) | already enforced |
| Rules with `artifacts.html_sha256` | 402 (7.4%) | already enforced |
| Rules with `artifacts.capture_url` documented | **37 (0.7%)** | **NEW : MANDATORY** |
| Captures where `capture_url == vendor_website` | 24/37 (65%) | **NEW : `observation_provenance` enum** |
| Rules matching only on `script_src` (legacy CDN-pattern style) | 3371/5418 (62%) | **NEW : matcher target preference order in SKILL.md gates** |

Tracking : `_alire/tracking/PLAN_LIAPROBE_AUDIT_RETROACTIF_2026-05-07.md`
RETEX : `_alire/02_LOGS/Journals/retex/RETEX_LIAPROBE_AUDIT_DECLENCHE_2026-05-07.md`
