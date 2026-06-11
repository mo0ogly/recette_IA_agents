"""URL extraction helpers for capture artifact provenance.

Finds the best capture URL for a rule, first by searching the per-product
MANIFEST.json under captures/, then falling back to rule.vendor_website.
"""

from pathlib import Path

URL_KEYS = [
    "capture_url",
    "url",
    "source_url",
    "vendor_url",
    "observation_url",
    "observed_url",
    "demo_url",
    "panel_source",
    "vendor_website",
]


def find_url_in_manifest(manifest: dict) -> tuple:
    """Return first non-empty URL field from manifest dict.

    Returns (url, key) or (None, None) if none found.
    """
    for key in URL_KEYS:
        v = manifest.get(key)
        if isinstance(v, str) and v.strip():
            return v.strip(), key
    return None, None


def find_capture_url(
    rule_id: str,
    captures_root: Path,
    existing_url: str | None = None,
    vendor_website: str | None = None,
) -> tuple:
    """Locate best capture URL for rule_id.

    Search order:
    1. existing_url already present in rule artifacts (no-op, returned as-is)
    2. captures_root/{RULE_ID_UPPER}/MANIFEST.json
    3. captures_root/{RULE_ID_UPPER_UNDERSCORE}/MANIFEST.json
    4. captures_root/{rule_id}/MANIFEST.json
    5. vendor_website as fallback

    Returns (capture_url, url_source, manifest_path) where:
    - capture_url: str or None
    - url_source: "already_present" | "MANIFEST.<key>" | "fallback_vendor_website" | None
    - manifest_path: Path or None (only set when MANIFEST.json found)
    """
    import json

    if existing_url:
        return existing_url, "already_present", None

    product_dir_candidates = [
        captures_root / rule_id.upper(),
        captures_root / rule_id.upper().replace("-", "_"),
        captures_root / rule_id,
    ]

    for candidate in product_dir_candidates:
        manifest_file = candidate / "MANIFEST.json"
        if manifest_file.exists():
            try:
                manifest = json.loads(manifest_file.read_text(encoding="utf-8"))
                url, key = find_url_in_manifest(manifest)
                if url:
                    return url, f"MANIFEST.{key}", manifest_file
            except Exception:
                continue

    if vendor_website:
        return vendor_website, "fallback_vendor_website", None

    return None, None, None
