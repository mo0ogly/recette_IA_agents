#!/usr/bin/env python3
# wave_ai.py -- LLM calling layer: prompt building, Claude CLI invocation, JSON extraction.
import json
import re
import subprocess

from wave_config import SCHEMA_EXAMPLE


# ---------------------------------------------------------------------------
# Prompt builder
# ---------------------------------------------------------------------------

def _load_existing_ids() -> set:
    """Build set of all currently-used rule.id values in liaprobe patterns/
    (excluding archive/). Used to enforce id uniqueness on new rules."""
    import json as _json
    import glob as _glob
    ids = set()
    for path in _glob.glob("/opt/lia-sec/liaprobe/patterns/**/*.json", recursive=True):
        if "/archive/" in path:
            continue
        try:
            with open(path) as f:
                rule = _json.load(f)
        except Exception:
            continue
        pid = (rule.get("id") or "").lower().strip()
        if pid:
            ids.add(pid)
    return ids


def _discover_database_url() -> str:
    """Read DATABASE_URL from systemd unit (single source of truth).
    Returns empty string if unavailable -- caller MUST handle gracefully."""
    import subprocess as _sp
    try:
        out = _sp.run(["systemctl", "cat", "lia-backend"],
                      capture_output=True, text=True, timeout=5).stdout
    except Exception:
        return ""
    for line in out.splitlines():
        if line.startswith("Environment=DATABASE_URL="):
            return line.split("=", 2)[2].strip()
        if line.startswith("Environment=") and "DATABASE_URL" in line:
            return line.split("DATABASE_URL=", 1)[1].strip()
    return ""


def _resolve_canonical_vendors(products: list) -> dict:
    """Query postgres vendor_alias for canonical vendor + MITRE link per product.

    Returns dict {taxonomy_code: {vendor_id, canonical_name, mitre_groups}}
    where any missing entry means "not resolved" (no postgres or no match).

    Graceful no-op if postgres unreachable -- nightly batch must keep working
    even on dev machines without DB access.
    """
    url = _discover_database_url()
    if not url:
        return {}
    try:
        import psycopg2  # type: ignore
    except ImportError:
        return {}
    try:
        conn = psycopg2.connect(url, connect_timeout=5)
    except Exception:
        return {}

    out = {}
    try:
        with conn.cursor() as cur:
            for p in products:
                vendor_hint = (p.get("vendor") or "").lower().strip()
                product_hint = (p.get("product") or "").lower().strip()

                vendor_id = None
                vendor_name = None
                product_id = None
                product_name = None
                cpe23 = None

                # 1. Resolve product first (most specific path) -- product joins to vendor
                if product_hint:
                    cur.execute(
                        """
                        SELECT pr.product_id, pr.product_name, pr.cpe23_uri,
                               v.vendor_id, v.vendor_name
                        FROM product pr
                        JOIN vendor v ON v.vendor_id = pr.vendor_id
                        WHERE lower(pr.product_name) = %s
                        ORDER BY pr.product_id
                        LIMIT 1
                        """,
                        (product_hint,),
                    )
                    row = cur.fetchone()
                    if row:
                        product_id, product_name, cpe23, vendor_id, vendor_name = row

                # 2. Fall back to vendor alias resolution if no product match
                if vendor_id is None and vendor_hint:
                    cur.execute(
                        """
                        SELECT v.vendor_id, v.vendor_name
                        FROM vendor_alias va
                        JOIN vendor v ON v.vendor_id = va.vendor_id
                        WHERE lower(va.alias_name) = %s OR lower(v.vendor_name) = %s
                        ORDER BY va.confidence_score DESC NULLS LAST
                        LIMIT 1
                        """,
                        (vendor_hint, vendor_hint),
                    )
                    row = cur.fetchone()
                    if row:
                        vendor_id, vendor_name = row

                if vendor_id is None:
                    continue

                entry = {
                    "vendor_id": int(vendor_id),
                    "vendor_name": vendor_name,
                }
                if product_id is not None:
                    entry["product_id"] = int(product_id)
                    entry["product_name"] = product_name
                    if cpe23:
                        entry["cpe23"] = cpe23

                # MITRE link (best-effort)
                cur.execute(
                    """
                    SELECT mitre_object_id, mitre_object_type, relation_type
                    FROM vendor_mitre_link
                    WHERE vendor_id = %s
                    LIMIT 3
                    """,
                    (vendor_id,),
                )
                mitres = [{"mitre_id": r[0], "type": r[1], "relation": r[2]}
                           for r in cur.fetchall()]
                if mitres:
                    entry["mitre"] = mitres
                out[p["taxonomy_code"]] = entry
    except Exception:
        pass
    finally:
        try:
            conn.close()
        except Exception:
            pass
    return out


def build_prompt(products: list, run_date: str) -> tuple:
    """Build (system_msg, user_msg) for a batch of products."""
    system_msg = (
        "You are an autonomous fingerprint rule author for the lia-fingerprint-v2-independent schema. "
        "Your task: create HTTP fingerprint detection rules based ONLY on documented public vendor observations. "
        "NEVER reference Wappalyzer, Nuclei, Recog, WhatWeb, or any third-party detection catalog. "
        "Use only official vendor documentation, GitHub source code, or RFC specifications. "
        "MATCHER PRIORITY (in DESCENDING order of detection evidence strength on wild traffic): "
        "1) header (Server, X-Powered-By, X-Generator, set-cookie) -- proof of vendor self-host. "
        "2) cookie (session cookie names like PHPSESSID, JSESSIONID variants) -- product session proof. "
        "3) body / title -- weaker, often matches marketing content. Use only as fallback or 2nd factor. "
        "When designing matchers: prefer 1 strong header matcher + 1 cookie matcher over 2 body matchers. "
        "Body-only patterns produced 4% false positives in cycle 6 audit (Onyphe ground-truth, 16834 banners). "
        "Header/cookie matches were 97%+ precision in same audit. "
        "Return ONLY a valid JSON array (no markdown fences, no explanation, raw JSON array only)."
    )

    product_list = "\n".join(
        f"{i+1}. taxonomy_code={p['taxonomy_code']}, product={p['product']}"
        + (f", vendor={p['vendor']}" if p["vendor"] else "")
        + (f", vendor_website={p['vendor_website']}" if p["vendor_website"] else "")
        for i, p in enumerate(products)
    )

    # Build collision-avoidance hint for LLM: ids derived from current products
    # plus a sample of the most-common existing ids in corpus.
    try:
        existing_ids = _load_existing_ids()
    except Exception:
        existing_ids = set()
    proposed_ids = [p["taxonomy_code"].lower() for p in products]
    colliding = [pid for pid in proposed_ids if pid in existing_ids]
    forbidden_ids_excerpt = (
        ", ".join(colliding[:20]) if colliding
        else "(your proposed ids are all unique vs current corpus)"
    )

    # Resolve canonical vendors via postgres vendor_alias (LIA-SEC source-of-truth)
    # Gracefully no-ops if DB unreachable.
    try:
        canonical_vendors = _resolve_canonical_vendors(products)
    except Exception:
        canonical_vendors = {}
    if canonical_vendors:
        def fmt(code, info):
            parts = [f"vendor_id={info['vendor_id']}",
                     f"vendor={info['vendor_name']!r}"]
            if "product_id" in info:
                parts.append(f"product_id={info['product_id']}")
                parts.append(f"product={info['product_name']!r}")
            if "cpe23" in info:
                parts.append(f"cpe23={info['cpe23']!r}")
            if "mitre" in info and info["mitre"]:
                parts.append(f"mitre={info['mitre'][:1]}")
            return f"  - {code}: " + " ".join(parts)
        vendor_hints = "\n".join(fmt(code, info)
                                  for code, info in canonical_vendors.items())
        vendor_section = (
            "\nLIA-SEC CANONICAL RESOLUTION (postgres vendor + product tables, "
            "44856 aliases / 44566 vendors / 1M+ products with CPE URIs):\n"
            f"{vendor_hints}\n"
            "USE vendor + product values verbatim in rule.vendor + rule.product. "
            "If cpe23 provided, copy to rule.cpe23_template (replace specific "
            "version with '{version}' placeholder).\n"
        )
    else:
        vendor_section = "\n(canonical postgres base unavailable -- using product list values)\n"

    schema_filled = SCHEMA_EXAMPLE.replace("DATE", run_date)

    user_msg = f"""Create lia-fingerprint-v2-independent rules for these {len(products)} products.
ID COLLISION CHECK : the following proposed ids already exist in the corpus
and MUST be suffixed with "_lia" : {forbidden_ids_excerpt}
{vendor_section}


PRODUCTS:
{product_list}

TODAY: {run_date}

SCHEMA (every rule must follow this structure exactly):
{schema_filled}

MATCHER SHAPES REFERENCE -- pick ONLY the targets the product actually exposes;
do NOT emit every shape for every product. Copy the KEY STRUCTURE, never the
example values:
  header (presence) : {{"target":"header","field":"x-powered-by","match_type":"exists","value":"","confidence_delta":0.7}}
  header (content)  : {{"target":"header","field":"server","match_type":"regex","value":"(?i)nginx","confidence_delta":0.7}}
  cookie (presence) : {{"target":"cookie","field":"_spree_session","match_type":"exists","value":"","confidence_delta":0.75}}
  js_global         : {{"target":"js_global","field":"InstantClick","match_type":"exists","value":"","confidence_delta":0.8}}
  script_src (lib)  : {{"target":"script_src","match_type":"regex","value":"(?i)mobx[\\\\w.-]*\\\\.js","confidence_delta":0.8}}
  body (content)    : {{"target":"body","match_type":"regex","value":"(?i)powered by acme","confidence_delta":0.45}}
  status_code       : {{"target":"status_code","match_type":"exact","value":"401","confidence_delta":0.4}}

RULES:
- taxonomy_code: exact UPPER_CASE from the list above
- id: taxonomy_code lowercased (e.g. BAG -> bag, BUY_ME_A_COFFEE -> buy_me_a_coffee).
  CRITICAL: id MUST be unique across the entire patterns/ corpus.
  If an id collides with an existing rule (see ID COLLISION CHECK in user
  prompt below), append "_lia" suffix : "iis" -> "iis_lia".
  Generic vendor-only ids are PERMANENTLY FORBIDDEN regardless of collision:
  unknown, cisco, microsoft, hp, python, dlink, ibm, sun, apple, google,
  amazon, oracle, samsung, dell, lenovo, asus, lg, hpe (collide with
  hundreds of existing files and create silent winner conflicts in engine).
- matchers: use SPECIFIC patterns unique to each product (not generic regexes that match other products)
- matchers "target" MUST be one of: "header", "body", "cookie", "url", "status_code", "title", "script_src", "js_global", "attr", "json_field" -- no other values allowed (NOT "html", NOT "status", NOT "meta")
- matchers "field" -- the engine extracts the target value using "field" for these targets, so "field" is MANDATORY (a matcher with one of these targets and no "field" NEVER fires, it is silently dead):
    - target="header": field = exact lowercase header name (server, x-powered-by, set-cookie, content-type, x-generator, via, cf-ray, x-pingback, x-drupal-cache, x-joomla-version)
    - target="cookie": field = the exact cookie NAME (e.g. "PHPSESSID", "_spree_session", "JSESSIONID"); the engine looks up that cookie by name -- it does NOT pattern-match cookie names, so use the literal expected name, not a regex of names
    - target="js_global": field = the JS global/object identifier the library defines (e.g. "InstantClick", "Shopify", "Mobx"); the engine searches the body for `var FIELD=`, `window.FIELD=`, `"FIELD":`, then a name-presence fallback
    - target="json_field": field = the JSON key to extract from a JSON body
    - target="attr": field = a CSS-attribute selector (e.g. "meta[name='generator']", "a[href*='/wp-content/']")
  For target in "body", "title", "status_code", "url", "script_src" -- do NOT include a "field" key; "value" alone is matched against the extracted target string.
  NEVER invent field names like meta_name, comment_text, link_href, meta_generator.
- matchers "value" + "match_type" depend on intent, NOT on guessing:
    - presence detection (the library/cookie/global simply EXISTS): set match_type="exists" and value="" -- do NOT put the identifier in "value" (the identifier goes in "field")
    - content detection (a SPECIFIC value/version string): set match_type="regex" (or "contains") and value = the product-specific pattern matched against the EXTRACTED content
  Putting the identifier in "value" with no "field" is the single most common authoring error and produces a silently-dead rule.
- CLIENT-SIDE JS LIBRARIES (React, MobX, Mithril, jQuery plugins, players, widgets): PREFER target="script_src" with match_type="regex" and value = a regex of the library's OWN asset filename (e.g. "(?i)mobx[\\w.-]*\\.js", "(?i)instantclick(\\.min)?\\.js"). This is the strongest low-false-positive signal for a client-side lib (a page loading mobx.min.js IS using MobX). Use js_global only when no distinctive script asset exists.
- confidence_delta: each matcher >= 0.35; if single matcher, set >= 0.65 for threshold to be reached
- For FP risk: use TWO matchers (combined sum >= 0.65) when signal is ambiguous
- capture_url: set to the most specific official documentation URL you know for this product's HTTP behavior
- observation_provenance: ALWAYS set to exactly "documented_default_behavior" -- no other value is valid
- If product is abandoned/unknown/no web presence: set enabled=false, explain in rationale
- third_party_catalog_references_consulted: ALWAYS "NONE -- pattern authored from public observation"
- supersedes_prior_rule: "patterns/web-signatures/<TAXONOMY_CODE>.json"
- tags: 1-4 lowercase tags describing category (e.g. "cms", "analytics", "cdn", "ecommerce")

Return a JSON array of exactly {len(products)} rules. No markdown. No explanation. Raw JSON array only."""

    return system_msg, user_msg


# ---------------------------------------------------------------------------
# Claude CLI caller
# ---------------------------------------------------------------------------

def call_claude(system_msg: str, user_msg: str, claude_bin: str,
                model: str) -> tuple:
    """Invoke the claude CLI and return (text, usage_dict).

    Raises RuntimeError on non-zero exit or API-level error.
    """
    cmd = [
        claude_bin,
        "--model", model,
        "--system-prompt", system_msg,
        "--output-format", "json",
        "--no-session-persistence",
        "-p", user_msg,
    ]
    result = subprocess.run(cmd, capture_output=True, text=True, timeout=300)
    if result.returncode != 0:
        raise RuntimeError(
            f"claude CLI error (exit {result.returncode}): {result.stderr[:500]}"
        )
    body = json.loads(result.stdout)
    if body.get("is_error"):
        raise RuntimeError(f"Claude CLI error: {body.get('result', '')[:500]}")
    text = body.get("result", "")
    raw_usage = body.get("usage", {})
    usage = {
        "input_tokens": raw_usage.get("input_tokens", 0),
        "output_tokens": raw_usage.get("output_tokens", 0),
    }
    return text, usage


# ---------------------------------------------------------------------------
# JSON array extractor (handles markdown fences)
# ---------------------------------------------------------------------------

def extract_json_array(text: str) -> list:
    """Extract a JSON array from a Claude response string."""
    text = re.sub(r"^```(?:json)?\s*", "", text.strip(), flags=re.MULTILINE)
    text = re.sub(r"\s*```$", "", text.strip(), flags=re.MULTILINE)
    text = text.strip()
    start = text.find("[")
    end = text.rfind("]")
    if start == -1 or end == -1:
        raise ValueError("No JSON array found in response")
    return json.loads(text[start:end + 1])
