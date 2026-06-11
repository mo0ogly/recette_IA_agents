# LiaProbe engine internals (c9 read-only review)

Source files inspected :
- `pkg/fingerprint/matcher.go` (1437 LOC) -- core matching logic
- `pkg/fingerprint/loader.go` -- pattern loading
- `cmd/recette-banners/main.go` -- recette tool (recette-onyphe binary
  comes from same/similar source, dedicated source dir absent in this tree)

## matchSingle dispatch (matcher.go:889-936)

`matchSingle(matcher, value)` returns `(bool, string)`. Switch on
`matcher.MatchType` :

| MatchType | Logic |
|-----------|-------|
| `regex` | `getCompiledRegex(value, case_insensitive).FindString(value) != ""` |
| `contains` | `strings.Contains(toLowerCached(value), matcherLower)` -- always case-insensitive |
| `exact` | `strings.EqualFold(value, matcher.Value)` -- case-insensitive equality |
| `exists` | `value != ""` -- presence check only |
| `not_contains` | inverse of contains |

For `regex` : full Go regexp library, NOT anchored automatically -- use `^...$`
for full-string match.

## Target dispatch (matcher.go:198-)

| Target | Source resolution |
|--------|-------------------|
| `banner` | `data.Banner` (raw TCP banner string) |
| `body` | `httpResp.Body` (HTTP body) |
| `header` | `httpResp.Headers[m.Field]` -- REQUIRES Field present; absent header -> no match |
| `cookie` | `httpResp.Cookies[m.Field]` -- REQUIRES Field present |
| `status_code` | string repr of HTTP status |
| `title`, `script_src`, `js_global`, `attr`, `url` | parsed from body |

## Verdict logic (recette-banners/main.go:297-330)

```
computeVerdict(gtProduct, detProduct, conf, threshold, nbCandidates) :
  if nbCandidates == 0 :        return "NO_PATTERN"
  if conf < threshold or detProduct == "" : return "MISS"
  if productMatches(gtProduct, detProduct) : return "CORRECT"
  return "WRONG"
```

`productMatches(gt, det)` :
1. Lowercase + trim both
2. Exact match OR bidirectional substring (`Contains(det, gt) || Contains(gt, det)`)
3. Equivalence groups (FTP / SMTP / POP3 / generic web servers all grouped)

The bidirectional substring is **the key insight** : `productMatches("Kerio Connect", "POP3 Service")` returns FALSE, but `productMatches("Server", "Web Server")` returns TRUE due to "Server" being substring of "Web Server".

## bestPatID selection

Engine evaluates ALL patterns against each banner, collects candidates with
conf >= threshold, then picks the one with highest confidence. The
`PatternID` in output is the `id` field (lowercased) of that winning rule.

When 2+ rules have the same `id`, the engine still picks one winner per
banner, but the output shows them as the same PatternID = the 670
duplicate clusters audit problem.

## DetProduct source

`bestProduct` in output comes from `rule.product` field. Engine does NOT
read `_meta_enrichment.canonical_vendor.product_name_db` (despite c7 hypothesis).

So c7 renames of `rule.product` DID change DetProduct for engine output --
which explains the -2 CORRECT / +2 WRONG delta observed post-rename.

## Open question (c10 candidate)

Why does `gfi_kerio_connect` rule match on banners with
`Server: ScreenConnect/...` ? The single matcher is a regex
`^Kerio Connect ([\d.]+)...$` on Server header. ScreenConnect doesn't
contain "Kerio Connect" in its Server value.

Hypotheses :
- Banner may contain "Kerio Connect" somewhere beyond the first 1500 chars
  we inspected (banners can be 16384 chars long)
- Engine may have a secondary scoring path we did not yet trace
- Confidence accumulation across implicit matchers

C10 task : add tracer flag to recette-onyphe that logs which matcher
fired for each verdict, then re-run on the 134 FP banners.

## Reference files

| File | Lines | Topic |
|------|-------|-------|
| matcher.go | 1437 | matchSingle, evaluateBanner/Service/Probe matchers, version extract |
| loader.go | ? | rule loading, validation, pre-compile |
| probe.go | ? | probe orchestration |
| jarm.go | ? | TLS JARM fingerprint |
| recette-banners/main.go | 600+ | recette tool, verdict, productMatches |
