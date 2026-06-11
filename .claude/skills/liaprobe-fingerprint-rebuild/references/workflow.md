# Per-Rule Workflow -- Independent Re-Observation

## 6-Step Procedure (per rule)

### Step 1 : RESOLVE_CANONICAL_URL

Input : `product_name` (e.g. "Adform", "Melibo", "CodeIgniter")

Action :
1. If `vendor_website` provided in proposals input : use it
2. Else : `WebSearch "<product_name> official website"` (filter to top 3 results)
3. Verify URL :
   ```bash
   curl -sLI "<url>" | head -5
   # expect HTTP 200 + Content-Type text/html
   ```
4. Confirm DOM contains the product brand reference :
   ```bash
   curl -sL "<url>" | grep -i "<product_name>"
   ```

### Step 1.5 : Pivot when root returns 4xx

Many vendor sites have 404 on `/` because they redirect to product subpath
(SaaS marketing pages) or use SPA routing. When root fails, try in order :

```bash
URL_BASE="https://example.com"
for path in "/" "/user_guide/" "/docs/" "/products/" "/about" "/index.html"; do
  http_code=$(curl -sLI -o /dev/null -w "%{http_code}" "${URL_BASE}${path}")
  if [ "$http_code" = "200" ]; then
    URL="${URL_BASE}${path}"
    break
  fi
done
```

Document the pivot in `decisions.md` ("root 404 -> pivoted to /user_guide/").

If unreachable after all paths tried + 1 retry : mark `vendor_unreachable` in journal, return `DEFERRED` verdict, move to next rule.

### Step 1.6 : Cross-reference public source code

When the canonical site returns minimal markup (Sphinx docs, SPA shell) and
the fingerprint relies on default config values (cookie names, header names,
session keys), cross-reference the project's PUBLIC SOURCE CODE on GitHub :

```bash
# Example : fetch CodeIgniter4 default Session cookieName
curl -sL "https://raw.githubusercontent.com/codeigniter4/CodeIgniter4/develop/system/Session/Session.php" \
  | grep "cookieName"
```

This cross-reference strengthens the "merger doctrine" defense: the cookie
name is a factual default config value, with only one way to express it.
Hash both artifacts (doc page + source file) for audit trail.

### Step 2 : CAPTURE_ARTIFACTS

Atomic capture of public artifacts :

```bash
PROD_SLUG="adform"  # snake_case product name
mkdir -p captures/${PROD_SLUG}
URL="https://site.adform.com"

# HTML body
curl -sL "$URL" > captures/${PROD_SLUG}/page.html
HTML_SHA=$(sha256sum captures/${PROD_SLUG}/page.html | awk '{print $1}')

# Favicon (try multiple paths)
curl -sL "${URL}/favicon.ico" > captures/${PROD_SLUG}/favicon.ico
FAV_SHA=$(sha256sum captures/${PROD_SLUG}/favicon.ico | awk '{print $1}')

# HTTP headers
curl -sLI "$URL" > captures/${PROD_SLUG}/headers.txt
HDR_SHA=$(sha256sum captures/${PROD_SLUG}/headers.txt | awk '{print $1}')

# Favicon MMH3 (Shodan-style int32 signed)
FAV_MMH3=$(python3 -c "
import codecs, mmh3
with open('captures/${PROD_SLUG}/favicon.ico','rb') as f:
    b64 = codecs.encode(f.read(), 'base64').decode()
print(mmh3.hash(b64))
" 2>/dev/null || echo "null")
```

Record all 4 artifacts in journal entry.

#### Anti-bot fallback (G2) -- WAF-protected hosts (Cloudflare / Akamai)

When `curl` returns HTTP 403 / a challenge interstitial (Cloudflare managed
challenge, Akamai), the marketing site or deployment is WAF-protected and the
artifacts cannot be captured with curl -- a NEW rule cannot be authored from
that host without the anti-bot fetch. Use the stealth backend (Scrapling
StealthyFetcher, solves the Cloudflare turnstile) as a fallback:

```bash
# Detect the block first
CODE=$(curl -sL -o /dev/null -w '%{http_code}' "$URL")
if [ "$CODE" = "403" ] || [ "$CODE" = "503" ]; then
  # Stealth capture: rendered HTML + headers + sha256/md5 into a JSON probe
  /home/liadev/.local/share/pipx/venvs/scrapling/bin/python \
    /opt/lia-sec/dev/_alire/tracking/liaprobe-multirecette/tooling/stealth_fetch.py \
    "$URL" > captures/${PROD_SLUG}/stealth.json
  # Extract body + status line + headers for EXTRACT_SIGNALS
  python3 -c "import json;d=json.load(open('captures/${PROD_SLUG}/stealth.json'));open('captures/${PROD_SLUG}/page.html','w').write(d.get('body',''));print('stealth status',d.get('status'),'sha',d.get('html_sha256','')[:16])"
fi
```

GET-only, read-only (same constraints as curl capture). The favicon is usually
NOT WAF-challenged (static) so the curl favicon path above still works. One-time
setup: `pipx install scrapling && scrapling install`. Tag the rule's
`artifacts.observation_provenance` and MANIFEST `signals` to note the stealth
capture. The favicon hash can also seed a `favicon_sha256` matcher (the engine
supports favicon_sha256 / favicon_md5 / favicon_hash mmh3 targets).

### Step 3 : EXTRACT_SIGNALS (independent inspection)

**CRITICAL** : Do NOT open the prior rule file. Inspect captures/ directly.

Look for unique product identifiers in :

| Source | Pattern type | Example |
|--------|--------------|---------|
| `<script src=...>` | domain pattern | `\.adform\.net/` (CDN-served scripts) |
| `<link rel="stylesheet" href=...>` | CSS resource | `\.example\.com/styles\.css` |
| `Set-Cookie:` | product cookie | `ci_session` (CodeIgniter) |
| HTTP `X-Powered-By:` | framework header | `WordPress`, `ASP.NET` |
| HTTP `Server:` | server software | `nginx/1.18`, `Microsoft-IIS/10.0` |
| `<meta name="generator">` | generator tag | `WordPress 6.4`, `Hugo 0.118` |
| `<noscript>` content | fallback markup | product-specific text |
| HTML comment markers | watermark | `<!-- Powered by X -->` |
| Favicon MMH3 hash | binary identifier | int32 signed (Shodan) |

Inspect with grep / awk :
```bash
grep -oE '<script[^>]+src="[^"]*"' captures/${PROD_SLUG}/page.html | sort -u
grep -i "set-cookie" captures/${PROD_SLUG}/headers.txt
grep -oE '<meta[^>]+>' captures/${PROD_SLUG}/page.html | head -10
```

### Step 4 : AUTHOR_REGEX (creative expression)

Author NEW regex from observation (do NOT copy):

Guidelines :
- Use anchors (`^`, `$`) where appropriate
- Use non-greedy quantifiers (`.*?` rather than `.*`)
- Escape literal dots (`\\.`)
- Prefer specific patterns over generic
- Use named groups for captures (`(?P<version>[\\d.]+)`)
- Document why this pattern uniquely identifies the product

Example (Adform observation : adform.net domain in script_src) :
```regex
\\.adform\\.net/(serving|tagsserver|matching)/
```

The choice of `(serving|tagsserver|matching)` is your creative decision based on observed paths.

#### Favicon-hash matcher (G4) -- when the favicon is stable and product-specific

If `captures/${PROD_SLUG}/favicon.ico` is a real, product-specific icon (not a
generic CDN/placeholder), seed a favicon-hash matcher. The engine supports three
favicon targets (`favicon_sha256`, `favicon_md5`, `favicon_hash` = mmh3 Shodan).
Prefer `favicon_sha256` (collision-resistant); add mmh3 too for Shodan
cross-reference. The hash is taken from `FAV_SHA` / `FAV_MMH3` captured in Step 2:

```json
{
  "id": "lia_favicon",
  "layer": "L7_HTTP",
  "matchers": [
    { "target": "favicon_sha256", "match_type": "exact", "value": "<FAV_SHA>", "confidence_delta": 0.6 },
    { "target": "favicon_hash",   "match_type": "favicon_hash", "value": "<FAV_MMH3>", "confidence_delta": 0.4 }
  ]
}
```

Confidence: a favicon hash is a strong but theme-overridable signal -> keep it a
SECONDARY corroborator (<= 0.6), never the sole high-confidence matcher (PRIMARY
SIGNAL order in the quality gates still prefers Server/X-Powered-By header,
default cookie, canonical path). Only emit it when the favicon is genuinely
distinctive; a shared framework favicon (e.g. a default Bootstrap/React icon) is
a false-positive source -> skip it.

### Step 5 : VERIFY_UNIQUENESS

Test the regex against 5+ unrelated pages :

```bash
# Control pages (well-known, NOT the target product)
CONTROLS=(
  "https://www.example.com"
  "https://en.wikipedia.org/wiki/Main_Page"
  "https://github.com"
  "https://www.cloudflare.com"
  "https://stackoverflow.com"
)

REGEX='\.adform\.net/(serving|tagsserver|matching)/'

for url in "${CONTROLS[@]}"; do
  body=$(curl -sL "$url")
  if echo "$body" | grep -qE "$REGEX"; then
    echo "FALSE_POSITIVE on $url"
    exit 1
  fi
done
echo "VERIFIED: 5/5 controls negative"

# Now test against actual vendor page (must be POSITIVE)
if grep -qE "$REGEX" captures/${PROD_SLUG}/page.html; then
  echo "POSITIVE on vendor page"
else
  echo "FAIL: regex doesnt match vendor page"
  exit 1
fi
```

If false positive : refine regex (more specific) and retry.
If 3 attempts fail : mark `SKIPPED` in journal with note `regex_too_generic`.

### Step 6 : WRITE_RULE_V2

Output `lia-fingerprint-v2-independent` JSON to `patterns/web-signatures/<X>.json` (overwrite prior).

Use schema in [output-schema.md](output-schema.md).

After write : append journal entry :

```bash
echo "$(jq -nc \
  --arg ts "$(date -u +%Y-%m-%dT%H:%M:%SZ)" \
  --arg prod "$PROD_SLUG" \
  --arg url "$URL" \
  --arg html_sha "$HTML_SHA" \
  --arg fav_sha "$FAV_SHA" \
  --argjson mmh3 "$FAV_MMH3" \
  '{timestamp:$ts,product:$prod,vendor_website:$url,html_sha256:$html_sha,favicon_sha256:$fav_sha,favicon_mmh3:$mmh3,verdict:"AUTHORED"}')" \
  >> sessions/<DATE>_<batch>/journal.jsonl
```

## Stop conditions

- HTTP 4xx/5xx after 3 retries : `DEFERRED`
- No unique signal identifiable after 30 min : `SKIPPED` (mark in journal, return existing rule untouched)
- 3 false-positive iterations : `SKIPPED` (regex_too_generic)
- 2 consecutive rules `DEFERRED` or `SKIPPED` : STOP batch -> /replan

## Time budget

| Activity | Per rule |
|----------|----------|
| Step 1 RESOLVE | 1-2 min |
| Step 2 CAPTURE | 30 sec |
| Step 3 EXTRACT | 3-5 min |
| Step 4 AUTHOR | 3-5 min |
| Step 5 VERIFY | 2-3 min |
| Step 6 WRITE | 1 min |
| **Total** | **10-16 min** |

## Examples

### Example 1 : CodeIgniter (PHP framework)

Step 1 : URL = `https://www.codeigniter.com`
Step 2 : capture HTML + headers
Step 3 : Set-Cookie includes `ci_session` (highly unique)
Step 4 : regex on `target=cookie field=ci_session match_type=exists`
Step 5 : 0 FP on 5 controls
Step 6 : write rule, journal AUTHORED

### Example 2 : Adform (adtech)

Step 1 : URL = `https://site.adform.com`
Step 2 : capture
Step 3 : `<script src="https://s2.adform.net/banners/scripts/...">` observed
Step 4 : regex `\\.adform\\.net/(banners|serving)/`
Step 5 : 0 FP
Step 6 : AUTHORED

### Example 3 : Melibo (chatbot SaaS, German)

Step 1 : URL = `https://www.melibo.de`
Step 2 : capture
Step 3 : `<script src="https://chat.melibo.de/widget.js">` observed
Step 4 : regex `melibo\\.(de|com)/(chat|widget)`
Step 5 : 0 FP
Step 6 : AUTHORED
