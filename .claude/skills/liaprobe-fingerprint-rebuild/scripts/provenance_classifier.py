"""Capture provenance classification — pure logic, no I/O.

Classifies how a capture URL relates to the vendor website to assess
whether the fingerprint was observed on a real deployment or on a
vendor-controlled marketing page.
"""


def classify_provenance(
    rule_id: str,
    vendor_website: str | None,
    capture_url: str | None,
    source: str | None,
) -> str:
    """Classify observation provenance for a rule.

    Discrimination by URL source:
    - "MANIFEST.<key>" and capture_url == vendor_website
        -> SUSPECT_MARKETING (capture done on vendor home page)
    - "MANIFEST.<key>" and capture_url != vendor_website
        -> real_deployment_third_party
    - "fallback_vendor_website"
        -> UNVERIFIED_FALLBACK (no MANIFEST; needs active HTTP verification)
    - vendor domain substring of capture_url but not equal
        -> vendor_self_host
    - No URL found
        -> SUSPECT_NO_CAPTURE

    Args:
        rule_id: taxonomy code (unused here, reserved for future heuristics)
        vendor_website: rule.vendor_website (may be None)
        capture_url: resolved capture URL (may be None)
        source: url_source string from find_capture_url()

    Returns:
        Provenance label string.
    """
    if not capture_url:
        return "SUSPECT_NO_CAPTURE"

    if source == "fallback_vendor_website":
        return "UNVERIFIED_FALLBACK"

    cu = capture_url.rstrip("/")
    vw = (vendor_website or "").rstrip("/")

    if cu == vw or cu == vw + "/" or capture_url == vendor_website:
        return "SUSPECT_MARKETING"

    if vw and vw in capture_url:
        return "vendor_self_host"

    return "real_deployment_third_party"
