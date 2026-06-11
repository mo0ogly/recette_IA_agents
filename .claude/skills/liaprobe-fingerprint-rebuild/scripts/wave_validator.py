#!/usr/bin/env python3
# wave_validator.py -- Rule validation and HTTP post-authoring verification gate.
import hashlib
import re
import urllib.request
import urllib.error

from wave_config import (
    REQUIRED_FIELDS,
    REQUIRED_ARTIFACTS,
    REQUIRED_AUTHORING,
    OBSOLETE_SIGNALS,
)


# ---------------------------------------------------------------------------
# Rule validators
# ---------------------------------------------------------------------------

def validate_rule(rule: dict) -> list:
    """Return list of validation errors (empty list = valid)."""
    errors = []
    for f in REQUIRED_FIELDS:
        if f not in rule:
            errors.append(f"missing field: {f}")

    if rule.get("$schema") != "lia-fingerprint-v2-independent":
        errors.append("$schema must be 'lia-fingerprint-v2-independent'")
    if rule.get("base_confidence", -1) != 0.0:
        errors.append("base_confidence must be 0.0")
    if not isinstance(rule.get("probes"), list):
        errors.append("probes must be non-empty array")
    elif len(rule.get("probes", [])) == 0 and rule.get("enabled", True) is not False:
        errors.append("probes must be non-empty array")

    arts = rule.get("artifacts", {})
    for f in REQUIRED_ARTIFACTS:
        if f not in arts:
            errors.append(f"artifacts missing: {f}")
    _VALID_PROVENANCES = {
        "vendor_self_host", "real_deployment_third_party",
        "documented_default_behavior", "NONE",
    }
    if arts.get("observation_provenance") not in _VALID_PROVENANCES:
        errors.append(
            f"observation_provenance must be one of {sorted(_VALID_PROVENANCES)}, "
            f"got: {arts.get('observation_provenance')!r}"
        )
    if arts.get("observation_provenance") == "vendor_self_host":
        if arts.get("html_sha256") is None and arts.get("favicon_sha256") is None:
            errors.append(
                "vendor_self_host requires html_sha256 or favicon_sha256 "
                "(both null -- no capture evidence)"
            )
    if arts.get("observation_provenance") == "real_deployment_third_party":
        if arts.get("html_sha256") is None and arts.get("favicon_sha256") is None:
            errors.append(
                "real_deployment_third_party requires html_sha256 or favicon_sha256 "
                "(both null -- no capture evidence)"
            )

    auth = rule.get("_lia_independent_authoring", {})
    for f in REQUIRED_AUTHORING:
        if f not in auth:
            errors.append(f"_lia_independent_authoring missing: {f}")
    if "NONE" not in str(auth.get("third_party_catalog_references_consulted", "")):
        errors.append("third_party_catalog_references_consulted must contain 'NONE'")

    return errors


def is_obsolete(rule: dict) -> bool:
    """Return True if rule signals an abandoned or defunct product."""
    if rule.get("enabled", True):
        return False
    rationale = rule.get("_lia_independent_authoring", {}).get("rationale", "").lower()
    return any(s in rationale for s in OBSOLETE_SIGNALS)


# ---------------------------------------------------------------------------
# HTTP post-authoring verification gate
# ---------------------------------------------------------------------------

def http_verify_rule(rule: dict) -> dict:
    """Attempt to verify matchers against the live vendor website.

    Returns dict with keys:
      "verified" bool  -- True if at least one matcher matched
      "tested"   bool  -- True if HTTP fetch was attempted
      "status"   int   -- HTTP status code (0 if fetch failed)
      "note"     str   -- human-readable result summary
    """
    vendor_url = rule.get("vendor_website") or rule.get(
        "_lia_independent_authoring", {}
    ).get("vendor_website", "")
    if not vendor_url:
        return {"verified": False, "tested": False, "status": 0, "note": "no vendor_website"}

    matchers = []
    for probe in rule.get("probes", []):
        for m in probe.get("matchers", []):
            if m.get("match_type") == "regex" and m.get("value"):
                matchers.append((m.get("target", "body"), m["value"]))

    if not matchers:
        return {
            "verified": False, "tested": False, "status": 0,
            "note": "no regex matchers", "verified_signal_class": None,
            "body_sha256": None, "capture_url": vendor_url,
        }

    try:
        req = urllib.request.Request(vendor_url)
        req.add_header("User-Agent", "Mozilla/5.0 (LiaProbe/2.0; +https://liascan.tech)")
        with urllib.request.urlopen(req, timeout=6) as resp:
            status = resp.status
            raw_body = resp.read(65536)
            body = raw_body.decode("utf-8", errors="replace")
            headers_raw = {k.lower(): v for k, v in resp.headers.items()}
        body_sha256 = hashlib.sha256(raw_body).hexdigest()
    except Exception as exc:
        return {
            "verified": False, "tested": True, "status": 0,
            "note": f"fetch error: {exc}", "verified_signal_class": None,
            "body_sha256": None, "capture_url": vendor_url,
        }

    matches = []  # list of (signal_class, summary) tuples
    for target, pattern in matchers:
        try:
            compiled = re.compile(pattern, re.IGNORECASE)
            if target in ("body", "html", "title"):
                if compiled.search(body):
                    signal_class = target if target in ("body", "title") else "body"
                    matches.append((signal_class, f"{target}:{pattern[:40]}"))
            elif target == "header":
                for hval in headers_raw.values():
                    if compiled.search(hval):
                        matches.append(("header", f"header:{pattern[:40]}"))
                        break
            elif target == "cookie":
                cookie_str = headers_raw.get("set-cookie", "")
                if compiled.search(cookie_str):
                    matches.append(("cookie", f"cookie:{pattern[:40]}"))
        except re.error:
            pass

    if matches:
        first_class, first_summary = matches[0]
        return {
            "verified": True,
            "tested": True,
            "status": status,
            "note": f"matched: {first_summary}",
            "verified_signal_class": first_class,
            "body_sha256": body_sha256,
            "capture_url": vendor_url,
        }
    return {
        "verified": False,
        "tested": True,
        "status": status,
        "note": f"no match (HTTP {status}, tested {len(matchers)} pattern(s))",
        "verified_signal_class": None,
        "body_sha256": body_sha256,
        "capture_url": vendor_url,
    }
