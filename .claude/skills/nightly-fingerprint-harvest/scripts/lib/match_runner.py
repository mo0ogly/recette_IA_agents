"""Apply rule probes to captured evidence to compute a match score.

Output structure consumed by the downstream recette step:

    {
      "rule_id": "<id>",
      "any_probe_matched": bool,
      "banner_match": bool,
      "match_score": float,        # sum of confidence_delta of matched matchers
      "matched_matchers": [
        {"probe_id": "<id>", "target": "body", "match_type": "regex",
         "value": "<pattern>", "version_extract": "<v>", "confidence_delta": 0.7}
      ],
      "unmatched_matchers": [...],
    }
"""

from __future__ import annotations

import re
from typing import Optional


def _normalize_text(data: bytes) -> str:
    try:
        return data.decode("utf-8", errors="replace")
    except Exception:
        return ""


def _match_value(matcher: dict, haystack: str) -> tuple[bool, Optional[str]]:
    """Return (matched, version_extract_value)."""
    match_type = matcher.get("match_type", "regex")
    pattern = matcher.get("value", "")
    ci = matcher.get("case_insensitive", False)
    flags = re.IGNORECASE if ci else 0

    if match_type == "exact":
        return haystack.strip() == pattern, None
    if match_type == "contains":
        if ci:
            return pattern.lower() in haystack.lower(), None
        return pattern in haystack, None
    # default = regex
    try:
        m = re.search(pattern, haystack, flags)
    except re.error:
        return False, None
    if not m:
        return False, None
    ve_pattern = matcher.get("version_extract")
    if ve_pattern:
        try:
            vm = re.search(ve_pattern, haystack, flags)
            if vm and vm.groups():
                cand = vm.group(matcher.get("version_group", 1))
                if _is_plausible_version(cand):
                    return True, cand
                # Broken version_extract (e.g. greedy ^(.+)$ on target=body)
                # captured the whole text. Detection still holds; version is
                # discarded rather than recording the entire body as a version.
                return True, None
        except re.error:
            return True, None
    return True, None


# A real version token is short and single-line: digits, dots, and a few
# common separators/qualifiers (e.g. "9.0.71", "1.24.0", "v3.2-beta1").
# Anything longer / multiline / containing markup is a broken-regex capture.
_VERSION_RE = re.compile(r"^[vV]?[0-9][0-9A-Za-z._\-+]{0,38}$")


def _is_plausible_version(value: Optional[str]) -> bool:
    if not value or not isinstance(value, str):
        return False
    v = value.strip()
    if not v or len(v) > 40 or "\n" in v or "<" in v or ">" in v:
        return False
    return bool(_VERSION_RE.match(v))


def run_match(rule: dict, body: bytes, headers: dict[str, str], banner: Optional[str] = None) -> dict:
    body_text = _normalize_text(body) if body else ""
    headers_text = "\n".join(f"{k}: {v}" for k, v in (headers or {}).items())

    matched = []
    unmatched = []
    score = 0.0
    banner_hit = False
    any_hit = False

    for probe in rule.get("probes", []):
        probe_id = probe.get("id", "")
        for matcher in probe.get("matchers", []):
            target = matcher.get("target", "body")
            haystack = ""
            if target == "body":
                haystack = body_text
            elif target == "headers":
                haystack = headers_text
            elif target == "banner":
                haystack = banner or ""
            else:
                haystack = body_text  # fallback

            hit, version = _match_value(matcher, haystack)
            entry = {
                "probe_id": probe_id,
                "target": target,
                "match_type": matcher.get("match_type", "regex"),
                "value": matcher.get("value", ""),
                "version_extract": version,
                "confidence_delta": matcher.get("confidence_delta", 0.0),
            }
            if hit:
                matched.append(entry)
                score += float(matcher.get("confidence_delta") or 0.0)
                any_hit = True
                if target == "banner":
                    banner_hit = True
            else:
                unmatched.append(entry)

    return {
        "rule_id": rule.get("id"),
        "any_probe_matched": any_hit,
        "banner_match": banner_hit,
        "match_score": round(score, 3),
        "matched_matchers": matched,
        "unmatched_matchers": unmatched,
    }
