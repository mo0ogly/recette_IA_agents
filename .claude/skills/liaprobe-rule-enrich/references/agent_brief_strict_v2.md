# Strict Schema Brief Template for Cycle 9 Cert Pattern Agents (R-LiaProbeEnrich-v2)

**Status**: BLOCKING for all Phase 5+ agent invocations.

## Why this exists

Phase 1-4 agents produced 5+ schema variants (`cert_patterns` vs `patterns`,
`match_field`/`match_value` vs `field`/`value`, top-level product-keyed vs
nested under `products`, etc.). Each variant required custom normalization
in `merge_fragments.py` (50+ LOC overhead). Phase 5 onward uses ONE canonical
schema, validated via JSONSchema before merge.

Reference schema: `_alire/tracking/liaprobe-enrich-v2/schemas/cert_pattern_fragment.schema.json`

Validator: `python3 .claude/skills/liaprobe-rule-enrich/scripts/validate_fragment.py <fragment_path>`

## Required output structure (CANONICAL)

```json
{
  "_meta": {
    "agent": "<vendor_name>",
    "session": "phase_<N>_cycle_9",
    "generated_at": "2026-05-03T10:00:00Z",
    "verified_against_schema": "v1"
  },
  "pattern_definitions": {
    "<pattern_id>": {
      "name": "Human-readable name (max 80 chars)",
      "rationale": "Why this pattern is unique to the product. 1-3 sentences with verbatim doc quote.",
      "severity": "info | low | medium | high",
      "confidence": 0.85,
      "match": {
        "subject_cn_regex": "^idrac-[A-Z0-9]{7}$",
        "subject_dn_regex": "(?i)O=Dell Inc",
        "issuer_cn_regex": "^Self-Signed-CA$",
        "issuer_dn_regex": "(?i)O=Vendor Inc",
        "san_regex": "\\.cluster\\.local$"
      },
      "source_id": "vendor_docs_<vendor>",
      "source_url": "https://vendor.com/docs/page",
      "source_sha256": "abc123...64hex",
      "source_section": "Verbatim quote or section reference",
      "verified_at": "2026-05-03T10:00:00Z"
    }
  },
  "products": {
    "<vendor>/<product>": {
      "vendor": "Full Vendor Name",
      "product": "Product Name",
      "patterns": ["<pattern_id_1>", "<pattern_id_2>"]
    }
  },
  "todo_unverified": ["item not verifiable, with reason"]
}
```

## Hard rules (validator REFUSES if violated)

### `pattern_definitions` (required, even if empty `{}`)

- Each key: snake_case `^[a-z][a-z0-9_]+$` (no hyphens, no slashes, no uppercase).
- Each value: REQUIRED fields = `name`, `rationale`, `severity`, `confidence`, `match`,
  `source_id`, `source_url`, `source_sha256`, `verified_at`.
- `severity` enum: `info` | `low` | `medium` | `high`. Nothing else.
- `confidence`: number 0.0-1.0. NOT a string ("high"/"medium").
- `match`: object, MIN 1 populated key. Allowed keys ONLY:
  `subject_cn_regex`, `subject_dn_regex`, `issuer_cn_regex`, `issuer_dn_regex`, `san_regex`.
- `source_url`: full URL with scheme.
- `source_sha256`: 64 hex chars OR literal `TODO_VERIFY` OR `n/a (...)` description.
- `verified_at`: ISO 8601 datetime.

### FORBIDDEN inside `pattern_definitions[<id>]`

- `match_field` (use `match.subject_cn_regex` etc.)
- `match_type`, `match_value` (legacy phase 4 pattern -- DROP)
- `pattern_id` (key IS the id, redundant)
- `description` (use `rationale`)
- `confidence` as string
- ANY other field

### `products` (required, even if empty `{}`)

- Each key: `^[a-z0-9][a-z0-9_-]*\/[a-z0-9][a-z0-9_.-]*$`
  (e.g. `dell/idrac`, `hashicorp/vault`, `vmware/vcenter_server`).
- Each value: REQUIRED `vendor`, `product`, `patterns`.
- `patterns`: array of pattern_ids (strings only). Pattern_ids MUST exist in
  `pattern_definitions` (cross-checked by validator).
- Optional `_alias_of`: canonical key if this is a CPE alias.

### FORBIDDEN inside `products[<key>]`

- `cert_patterns` (it's `patterns`, not `cert_patterns`)
- `display_name`, `description`, `default_port`, `ports` (these go in the
  LiaProbe rule file, not the master fragment)
- `keystore_path_*`, `keystore_password`, `keystore_alias` (out of scope)
- `cert_is_self_signed`, `aliases` (legacy variants)
- ANY other field except `_alias_of`

## Pre-submission self-check

Before claiming completion, the agent MUST run:

```bash
python3 /opt/lia-sec/dev/.claude/skills/liaprobe-rule-enrich/scripts/validate_fragment.py <fragment_path>
```

Expected output: `OK     <fragment.json>`. Any FAIL = STOP, fix, re-validate.

## Examples

### Valid minimal fragment (negative finding)

```json
{
  "_meta": {"agent": "vendor_x", "verified_against_schema": "v1"},
  "pattern_definitions": {},
  "products": {},
  "todo_unverified": [
    "vendor_x_factory_cn: vendor doc 403 paywall -- requires lab capture via openssl s_client"
  ]
}
```

Empty `pattern_definitions` + empty `products` = valid (negative finding).
Document the reason in `todo_unverified`.

### Valid fragment with 2 patterns

```json
{
  "_meta": {
    "agent": "axis",
    "session": "phase_5_cycle_9",
    "generated_at": "2026-05-03T10:00:00Z",
    "verified_against_schema": "v1"
  },
  "pattern_definitions": {
    "axis_idevid_cn_format": {
      "name": "Axis Device ID IDevID CN format",
      "rationale": "Verbatim from AXIS OS Knowledge Base: Common Name 'axis-b8a44f281db4-eccp256-1' encodes MAC + crypto type + sequence. Pre-provisioned at manufacturing for Edge Vault devices.",
      "severity": "info",
      "confidence": 0.9,
      "match": {
        "subject_cn_regex": "^axis-[0-9a-f]{12}-(eccp256|rsa4096)-\\d+$"
      },
      "source_id": "vendor_docs_axis",
      "source_url": "https://help.axis.com/en-us/axis-os-knowledge-base",
      "source_sha256": "f65118eb8b7b2a32f81807f608cff2969a6a0d8425515049daa845946603784d",
      "source_section": "AXIS OS Knowledge Base IDevID section",
      "verified_at": "2026-05-03T10:00:00Z"
    },
    "axis_issuer_o": {
      "name": "Axis Issuer Organization",
      "rationale": "Verified via openssl x509 -noout -issuer on official Axis PKI Root CA PEM download.",
      "severity": "info",
      "confidence": 0.85,
      "match": {
        "issuer_dn_regex": "(?i)O=Axis Communications AB"
      },
      "source_id": "vendor_docs_axis",
      "source_url": "https://axis-pki.axis.com/ca-bundle.pem",
      "source_sha256": "70f703ab17d7ef241aae0bcfdd54af888c231b6dda91924aee69e10d05c5492f",
      "source_section": "openssl x509 dump of axis_device_id_root_ca_rsa.pem",
      "verified_at": "2026-05-03T10:00:00Z"
    }
  },
  "products": {
    "axis/network_camera": {
      "vendor": "Axis Communications AB",
      "product": "Network Camera / IP Camera",
      "patterns": ["axis_idevid_cn_format", "axis_issuer_o"]
    }
  },
  "todo_unverified": []
}
```

## Common rejections

| Error | Cause | Fix |
|-------|-------|-----|
| `'pattern_definitions' is a required property` | Top-level missing key | Add `"pattern_definitions": {}` |
| `'patterns' is a required property` (in products) | Used `cert_patterns` | Rename to `patterns` |
| `Additional properties are not allowed ('match_field')` | Phase 4 field naming | Use `match.subject_cn_regex` etc. |
| `'high' is not of type 'number'` (confidence) | String confidence | Use 0.85 (number) |
| `'CN/foo' does not match` (product key) | Slash position wrong | Use `vendor/product` exactly |
| `pattern_id 'foo' not defined in pattern_definitions` | Cross-check fail | Define the pattern in `pattern_definitions` first |

## When to write `todo_unverified` vs invent

If a vendor doc is paywalled, 403, login-required, or behind WAF:

1. Cache the failed-fetch response (HTTP status + URL) in `vendor_docs/<vendor>/_fetch_log.txt`
2. Add entry to `todo_unverified` with reason and lab-capture path
3. Do NOT invent the value -- R4/R18 enforced

If the vendor explicitly does NOT auto-generate (operator must provide):

1. Document the negative finding verbatim from vendor doc
2. Add to `todo_unverified` as `negative_finding`
3. Empty `pattern_definitions` is valid

## See also

- `cert_pattern_fragment.schema.json` -- the JSONSchema itself
- `validate_fragment.py` -- pre-submission validator
- `merge_fragments.py` -- post-validation merge into master
- RETEX Phase 1-4: documents the 5 schema variants this brief eliminates
