"""
Cycle 13 -- Target context classifier (output enrichment, not pattern).

Classifies a scan target IP into actionable context using:
- Phase 1 (static): bogon detection (RFC 1918/6598/5737/3927/1112/IANA special-purpose)
  + ASN type lookup from cidr_context_master.json static seed map
  + CDN double-confirmation via Server: header value cross-check
- Phase 2B (live): Team Cymru DNS TXT, RDAP, PeeringDB CC-BY-4.0, MaxMind GeoLite2

Phase 2B is activated by passing live=True to classify_target().
All live lookups are cached 7 days under <tracking_root>/runtime/asn_cache/.

Output: dict with keys
  - is_bogon (bool), bogon_type (str|None)
  - asn (int|None), as_organization (str|None), as_type (str|None), country (str|None)
  - is_cdn (bool), cdn_provider (str|None)
  - is_cloud (bool), is_hosting (bool)
  - live_enriched (bool): True when Phase 2B lookups were performed
  - source_provenance: list of {field, source_url, source_sha256}

License attribution (Phase 2B live lookups):
  - Team Cymru DNS: free community service (https://team-cymru.com/community-services/ip-asn-mapping/)
  - RDAP: public infrastructure (RFC 7483)
  - PeeringDB: CC-BY-4.0 (https://creativecommons.org/licenses/by/4.0/)
  - MaxMind GeoLite2: CC-BY-SA-4.0, operator-provided .mmdb file
"""
from __future__ import annotations

import ipaddress
import json
from pathlib import Path
from typing import Any

from enrich_lib import find_tracking_root


def _master_path(master_path: Path | None = None) -> Path:
    if master_path is not None:
        return master_path
    return find_tracking_root() / "master_data" / "cidr_context_master.json"


def _load_master(master_path: Path) -> dict:
    if not master_path.exists():
        raise FileNotFoundError(f"cidr_context_master.json not found at {master_path}")
    return json.loads(master_path.read_text(encoding="utf-8"))


def detect_bogon(ip_str: str, master: dict) -> tuple[bool, str | None, dict | None]:
    """Return (is_bogon, type, source_entry) for an IP string.

    type is one of: private, cgnat, documentation, link_local, multicast,
    loopback, this_network, reserved, broadcast, or None.
    """
    try:
        ip = ipaddress.ip_address(ip_str)
    except ValueError:
        return False, None, None

    for entry in master.get("bogon_ranges", []):
        try:
            net = ipaddress.ip_network(entry["cidr"], strict=False)
        except ValueError:
            continue
        if ip in net:
            return True, entry.get("type"), entry
    return False, None, None


def lookup_asn_type(asn: int | None, master: dict) -> tuple[str | None, str | None, str | None]:
    """Return (organization, type, country) for an ASN, or (None, None, None) if unknown.

    Phase 1 lookup uses static asn_type_map seed. Phase 2 will replace with
    Team Cymru DNS TXT live lookup.
    """
    if asn is None:
        return None, None, None
    asns = master.get("asn_type_map", {}).get("asns", {})
    entry = asns.get(str(asn))
    if entry is None:
        return None, None, None
    return entry.get("organization"), entry.get("type"), entry.get("country")


def detect_cdn(server_header: str | None, asn: int | None, master: dict) -> tuple[bool, str | None]:
    """Detect CDN using double-confirmation: Server header AND ASN.

    Returns (is_cdn, cdn_provider_name) where confirmation requires:
    - server_header value matches known CDN markers
    - ASN matches the same CDN provider's ASN

    If only one matches: is_cdn=False, cdn_provider=hint (low confidence).
    If both match: is_cdn=True, cdn_provider=name (confirmed).
    """
    if server_header is None:
        return False, None

    cdn_map = master.get("cdn_server_header_map", {}).get("values", {})
    server_lower = server_header.lower().strip()

    # Find header match
    header_match: tuple[str, int | None] | None = None
    for marker, marker_asn in cdn_map.items():
        if marker.lower() in server_lower:
            asn_int = int(marker_asn) if marker_asn else None
            header_match = (marker, asn_int)
            break

    if header_match is None:
        return False, None

    marker_name, expected_asn = header_match

    # Confirm with ASN if available
    if asn is None or expected_asn is None:
        # Single-source: header marker present but cannot cross-check ASN
        return False, marker_name  # hint only
    if asn == expected_asn:
        return True, marker_name  # double-confirmed
    return False, marker_name  # ASN mismatch -- header may be spoofed or wrong


def classify_target(
    ip: str,
    asn: int | None = None,
    server_header: str | None = None,
    *,
    master_path: Path | None = None,
    live: bool = False,
    geo_db_path: str | Path | None = None,
    cache_dir: Path | None = None,
) -> dict[str, Any]:
    """Build the full target_context dict for a scan result.

    Args:
        ip: IPv4 or IPv6 address as string.
        asn: ASN of the IP (optional; if None and live=True, resolved via Cymru DNS).
        server_header: HTTP Server: header value (optional, for CDN confirmation).
        master_path: override master JSON path (for tests).
        live: if True, attempt Phase 2B live lookups (Cymru/RDAP/PeeringDB/GeoLite2)
              when ASN cannot be resolved from the static seed map. Results are cached
              7 days in <tracking_root>/runtime/asn_cache/.
        geo_db_path: path to a MaxMind GeoLite2 .mmdb file (opt-in, live=True only).
        cache_dir: override cache directory (for tests).

    Returns:
        dict with classification keys + source_provenance list.
        Includes 'live_enriched': True if Phase 2B lookups were performed.
    """
    mp = _master_path(master_path)
    master = _load_master(mp)

    is_bogon, bogon_type, bogon_entry = detect_bogon(ip, master)
    organization, as_type, country = lookup_asn_type(asn, master)
    is_cdn, cdn_provider = detect_cdn(server_header, asn, master)

    provenance: list[dict[str, str]] = []
    live_enriched = False

    if bogon_entry is not None:
        provenance.append({
            "field": "is_bogon",
            "source_url": bogon_entry.get("source_url", ""),
            "source_sha256": bogon_entry.get("source_sha256", ""),
        })

    # Phase 2B: live lookups when static seed has no ASN entry and live=True
    # Bogon addresses are not enriched (no public routing information).
    if live and not is_bogon and (asn is None or organization is None):
        live_result = _live_enrich(
            ip=ip,
            asn=asn,
            geo_db_path=geo_db_path,
            cache_dir=cache_dir,
        )
        if live_result is not None:
            live_enriched = True
            if asn is None and live_result.asn is not None:
                asn = live_result.asn
                # Re-run static lookup with resolved ASN (static seed may cover it)
                org_static, type_static, country_static = lookup_asn_type(asn, master)
                if org_static is not None:
                    organization = org_static
                if type_static is not None:
                    as_type = type_static
                if country_static is not None:
                    country = country_static
            # Fill gaps from live chain
            if organization is None:
                organization = live_result.organization
            if as_type is None:
                as_type = live_result.as_type
            if country is None:
                country = live_result.country
            provenance.extend(live_result.source_provenance)

    if as_type is not None and not any(p["field"] == "as_type" for p in provenance):
        asn_meta = master.get("asn_type_map", {})
        provenance.append({
            "field": "as_type",
            "source_url": asn_meta.get("source_url", ""),
            "source_sha256": "n/a (static seed map)",
        })

    # Re-run CDN detection if ASN was resolved by live chain
    if live_enriched and asn is not None:
        is_cdn, cdn_provider = detect_cdn(server_header, asn, master)

    is_cloud = as_type == "cloud"
    is_hosting = as_type == "hosting"

    return {
        "ip": ip,
        "is_bogon": is_bogon,
        "bogon_type": bogon_type,
        "asn": asn,
        "as_organization": organization,
        "as_type": as_type,
        "country": country,
        "is_cdn": is_cdn,
        "cdn_provider": cdn_provider,
        "is_cloud": is_cloud,
        "is_hosting": is_hosting,
        "live_enriched": live_enriched,
        "source_provenance": provenance,
    }


def _live_enrich(
    ip: str,
    asn: int | None,
    geo_db_path: str | Path | None,
    cache_dir: Path | None,
) -> "Any | None":
    """Run Phase 2B live enrichment chain and return a LiveASNResult or None.

    Import is deferred so Phase 1 callers have zero dependency on asn_lookup_live.
    """
    try:
        from asn_lookup_live import LiveASNChain
    except ImportError:
        return None
    chain = LiveASNChain(cache_dir=cache_dir, geo_db_path=geo_db_path)
    result = chain.resolve(ip)
    # If the chain found nothing useful, return None to avoid spurious provenance
    if result.asn is None and result.organization is None and result.country is None:
        return None
    return result


__all__ = [
    "classify_target",
    "detect_bogon",
    "lookup_asn_type",
    "detect_cdn",
]
