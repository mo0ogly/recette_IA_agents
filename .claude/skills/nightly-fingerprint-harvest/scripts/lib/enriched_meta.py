"""Extract maximum useful metadata from collector raw_record.

Each external source returns a different shape. This module flattens them
into a uniform `EnrichedMeta` dict that recette can consume without
knowing the source layout.

Fields populated when present:
  - ip, port, hostname
  - asn, asn_org, isp
  - country, country_code, city, region
  - http_status, http_method, content_type, content_length, server_header
  - tls_issuer, tls_subject_cn, tls_subject_alt_names, tls_fingerprint_sha256
  - jarm, ja3, ja3s
  - software_product, software_vendor, software_version
  - cpe, last_seen_iso
  - favicon_hash_mmh3, favicon_sha256

Anything not derivable is left as null. The producer never invents
values (R4 / R18).
"""

from __future__ import annotations

from typing import Any, Optional


def _safe_get(d: Any, *path: str, default: Any = None) -> Any:
    cur = d
    for key in path:
        if isinstance(cur, dict) and key in cur:
            cur = cur[key]
        else:
            return default
    return cur


def _norm_str(value: Any) -> Optional[str]:
    if value is None:
        return None
    s = str(value).strip()
    return s or None


def enrich_from_netlas(raw: dict) -> dict:
    """Netlas /api/responses/ record shape (observed live)."""
    cert = raw.get("certificate") or {}
    geo = raw.get("geo") or {}
    http_block = raw.get("http") or {}
    out = {
        "ip": _norm_str(raw.get("ip")),
        "port": raw.get("port"),
        "hostname": _norm_str(raw.get("host")),
        "asn": _safe_get(raw, "asn", "number"),
        "asn_org": _norm_str(_safe_get(raw, "asn", "name")),
        "isp": _norm_str(raw.get("isp")),
        "country": _norm_str(geo.get("country")),
        "country_code": _norm_str(geo.get("country_iso")),
        "city": _norm_str(geo.get("city")),
        "region": _norm_str(geo.get("region")),
        "http_status": http_block.get("status_code"),
        "http_method": _norm_str(http_block.get("method")) or "GET",
        "content_type": _norm_str(_safe_get(http_block, "headers", "content_type")),
        "content_length": _safe_get(http_block, "headers", "content_length"),
        "server_header": _norm_str(_safe_get(http_block, "headers", "server")),
        "tls_issuer": _norm_str(cert.get("issuer_dn")),
        "tls_subject_cn": _norm_str(_safe_get(cert, "subject", "common_name")),
        "tls_subject_alt_names": cert.get("names") or [],
        "tls_fingerprint_sha256": _norm_str(cert.get("fingerprint_sha256")),
        "jarm": _norm_str(raw.get("jarm")),
        "ja3": _norm_str(_safe_get(raw, "tls", "ja3")),
        "ja3s": _norm_str(_safe_get(raw, "tls", "ja3s")),
        "software_product": _norm_str(_safe_get(raw, "product", "name")),
        "software_vendor": _norm_str(_safe_get(raw, "product", "vendor")),
        "software_version": _norm_str(_safe_get(raw, "product", "version")),
        "cpe": _safe_get(raw, "product", "cpe"),
        "last_seen_iso": _norm_str(raw.get("@timestamp") or raw.get("timestamp")),
        "favicon_hash_mmh3": _safe_get(http_block, "favicon", "mmh3"),
        "favicon_sha256": _norm_str(_safe_get(http_block, "favicon", "sha256")),
    }
    return out


def enrich_from_censys(raw: dict) -> dict:
    """Censys hosts/search record."""
    services = raw.get("services") or [{}]
    svc = services[0] if services else {}
    cert = _safe_get(svc, "tls", "certificates", "leaf_data") or {}
    location = raw.get("location") or {}
    autonomous_system = raw.get("autonomous_system") or {}
    http_response = _safe_get(svc, "http", "response") or {}
    out = {
        "ip": _norm_str(raw.get("ip")),
        "port": svc.get("port"),
        "hostname": _norm_str(svc.get("server_name")),
        "asn": autonomous_system.get("asn"),
        "asn_org": _norm_str(autonomous_system.get("name")),
        "isp": _norm_str(autonomous_system.get("description")),
        "country": _norm_str(location.get("country")),
        "country_code": _norm_str(location.get("country_code")),
        "city": _norm_str(location.get("city")),
        "region": _norm_str(location.get("province")),
        "http_status": http_response.get("status_code"),
        "http_method": _norm_str(http_response.get("protocol")) or "GET",
        "content_type": _norm_str(_safe_get(http_response, "headers", "Content_Type")),
        "content_length": _safe_get(http_response, "headers", "Content_Length"),
        "server_header": _norm_str(_safe_get(http_response, "headers", "Server")),
        "tls_issuer": _norm_str(_safe_get(cert, "issuer_dn")),
        "tls_subject_cn": _norm_str(_safe_get(cert, "subject", "common_name")),
        "tls_subject_alt_names": _safe_get(cert, "names") or [],
        "tls_fingerprint_sha256": _norm_str(_safe_get(cert, "fingerprint_sha256")),
        "jarm": _norm_str(_safe_get(svc, "jarm", "fingerprint")),
        "ja3": None,
        "ja3s": None,
        "software_product": _norm_str(_safe_get(svc, "software", 0, "product")),
        "software_vendor": _norm_str(_safe_get(svc, "software", 0, "vendor")),
        "software_version": _norm_str(_safe_get(svc, "software", 0, "version")),
        "cpe": _safe_get(svc, "software", 0, "cpe"),
        "last_seen_iso": _norm_str(svc.get("observed_at") or raw.get("last_updated_at")),
        "favicon_hash_mmh3": _safe_get(svc, "http", "favicons", 0, "shodan_hash"),
        "favicon_sha256": _norm_str(_safe_get(svc, "http", "favicons", 0, "sha256")),
    }
    return out


def enrich_from_zoomeye(raw: dict) -> dict:
    """ZoomEye host/search record."""
    portinfo = raw.get("portinfo") or {}
    geoinfo = raw.get("geoinfo") or {}
    out = {
        "ip": _norm_str(raw.get("ip")),
        "port": portinfo.get("port"),
        "hostname": _norm_str(portinfo.get("hostname")),
        "asn": _safe_get(geoinfo, "asn"),
        "asn_org": _norm_str(_safe_get(geoinfo, "organization")),
        "isp": _norm_str(_safe_get(geoinfo, "isp")),
        "country": _norm_str(_safe_get(geoinfo, "country", "names", "en")),
        "country_code": _norm_str(_safe_get(geoinfo, "country", "code")),
        "city": _norm_str(_safe_get(geoinfo, "city", "names", "en")),
        "region": _norm_str(_safe_get(geoinfo, "subdivisions", "names", "en")),
        "http_status": None,
        "http_method": "GET",
        "content_type": None,
        "content_length": None,
        "server_header": _norm_str(portinfo.get("product")),
        "tls_issuer": None,
        "tls_subject_cn": None,
        "tls_subject_alt_names": [],
        "tls_fingerprint_sha256": None,
        "jarm": None,
        "ja3": None,
        "ja3s": None,
        "software_product": _norm_str(portinfo.get("product")),
        "software_vendor": None,
        "software_version": _norm_str(portinfo.get("version")),
        "cpe": portinfo.get("cpe"),
        "last_seen_iso": _norm_str(raw.get("timestamp")),
        "favicon_hash_mmh3": None,
        "favicon_sha256": None,
    }
    return out


def enrich_from_crtsh(raw: dict) -> dict:
    """crt.sh row -- only cert metadata available."""
    return {
        "ip": None,
        "port": 443,
        "hostname": None,
        "asn": None,
        "asn_org": None,
        "isp": None,
        "country": None,
        "country_code": None,
        "city": None,
        "region": None,
        "http_status": None,
        "http_method": None,
        "content_type": None,
        "content_length": None,
        "server_header": None,
        "tls_issuer": _norm_str(raw.get("issuer_name")),
        "tls_subject_cn": _norm_str(raw.get("common_name")),
        "tls_subject_alt_names": (raw.get("name_value") or "").split("\n"),
        "tls_fingerprint_sha256": None,
        "jarm": None,
        "ja3": None,
        "ja3s": None,
        "software_product": None,
        "software_vendor": None,
        "software_version": None,
        "cpe": None,
        "last_seen_iso": _norm_str(raw.get("not_before") or raw.get("entry_timestamp")),
        "favicon_hash_mmh3": None,
        "favicon_sha256": None,
    }


_DISPATCH = {
    "netlas": enrich_from_netlas,
    "censys": enrich_from_censys,
    "zoomeye": enrich_from_zoomeye,
    "crtsh": enrich_from_crtsh,
}


def enrich(source: str, raw_record: dict) -> dict:
    fn = _DISPATCH.get(source)
    if fn is None or not isinstance(raw_record, dict):
        return {}
    try:
        return fn(raw_record)
    except Exception as exc:
        return {"_enrich_error": str(exc)}
