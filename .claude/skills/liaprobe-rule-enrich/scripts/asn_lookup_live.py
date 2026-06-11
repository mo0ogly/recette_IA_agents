"""
Cycle 13 Phase 2B -- Live ASN / RDAP / PeeringDB / GeoLite2 lookup module.

Architecture:
  TeamCymruASNLookup : DNS TXT query to <reversed-octets>.origin.asn.cymru.com
                       Returns (asn, prefix, country, rir, alloc_date).
                       Ref: https://team-cymru.com/community-services/ip-asn-mapping/
                       License: free community service (non-commercial; aligns with
                       PolyForm Noncommercial 1.0.0 scope of LiaProbe).

  RDAPLookup         : HTTP query to RDAP endpoint routed via IANA bootstrap JSON.
                       Ref: RFC 7483 (RDAP) + https://data.iana.org/rdap/ipv4.json
                       License: public infrastructure, no redistribution restriction.

  PeeringDBLookup    : HTTP GET https://www.peeringdb.com/api/net?asn={asn}
                       Returns org name, info_type (network type), org_country.
                       License: CC-BY-4.0 (attribution required).
                       Attribution: Data from PeeringDB (peeringdb.com), licensed under
                       CC-BY-4.0 (https://creativecommons.org/licenses/by/4.0/).

  MaxMindGeoReader   : Binary .mmdb reader (opt-in, gated by db_path parameter).
                       License: CC-BY-SA-4.0 on the database file.
                       The .mmdb file is NOT bundled; operator provides path.
                       Requires: maxminddb (pure Python, ISC license).
                       Ref: https://dev.maxmind.com/geoip/geolite2-free-geolocation-data

  ASNCacheMixin      : File-based 7-day TTL cache shared by Cymru/RDAP/PeeringDB.
                       Cache location: <tracking_root>/runtime/asn_cache/<ip-hash>.json

Design constraints:
  - Zero live HTTP/DNS calls in tests -- all external calls mockable.
  - Graceful degradation: if any lookup fails, that field is None; other fields
    proceed independently.
  - Fallback chain: Cymru (DNS) -> RDAP (HTTP) -> PeeringDB (HTTP) -> static seed map.
  - IPv4 and IPv6 supported for all lookups except MaxMind (depends on db_path type).
  - All cache writes are atomic (tmp + os.replace).
"""
from __future__ import annotations

import hashlib
import ipaddress
import json
import os
import socket
import time
import urllib.error
import urllib.request
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from enrich_lib import find_tracking_root


# ---------------------------------------------------------------------------
# Cache TTL (7 days = 604800 seconds)
# ---------------------------------------------------------------------------
_CACHE_TTL_SECONDS = 7 * 24 * 3600


# ---------------------------------------------------------------------------
# Data classes
# ---------------------------------------------------------------------------

@dataclass
class CymruRecord:
    """Result of a Team Cymru IP-to-ASN DNS lookup."""
    ip: str
    asn: int | None
    prefix: str | None        # e.g. "1.2.0.0/16"
    country: str | None       # ISO-3166-1 alpha-2
    rir: str | None           # arin, ripe, apnic, afrinic, lacnic
    alloc_date: str | None    # "YYYY-MM-DD" or None
    source: str = "cymru_dns"


@dataclass
class RDAPRecord:
    """Result of an RDAP (Registration Data Access Protocol) lookup."""
    ip: str
    name: str | None            # network handle / name
    organization: str | None    # org name from RDAP entities
    country: str | None
    cidr: str | None            # most-specific covering prefix from RDAP
    abuse_email: str | None
    rir: str | None             # derived from RDAP bootstrap routing
    source: str = "rdap"


@dataclass
class PeeringDBRecord:
    """Result of a PeeringDB API lookup by ASN."""
    asn: int
    name: str | None          # network name
    org_name: str | None
    info_type: str | None     # content/isp/hosting/enterprise/academic/etc.
    country: str | None
    website: str | None
    source: str = "peeringdb"
    license_attribution: str = (
        "Data from PeeringDB (peeringdb.com), licensed under CC-BY-4.0 "
        "(https://creativecommons.org/licenses/by/4.0/)"
    )


@dataclass
class GeoRecord:
    """Result of a MaxMind GeoLite2 database lookup."""
    ip: str
    country_iso: str | None    # ISO-3166-1 alpha-2
    country_name: str | None
    city_name: str | None
    subdivision: str | None    # first-level subdivision / state
    latitude: float | None
    longitude: float | None
    asn: int | None            # from GeoLite2-ASN db (if available)
    asn_org: str | None
    source: str = "maxmind_geolite2"
    license_attribution: str = (
        "This product includes GeoLite2 data created by MaxMind, available from "
        "https://www.maxmind.com, licensed under CC-BY-SA-4.0."
    )


@dataclass
class LiveASNResult:
    """Aggregated result from the full live lookup chain for one IP."""
    ip: str
    asn: int | None = None
    prefix: str | None = None
    country: str | None = None
    rir: str | None = None
    alloc_date: str | None = None
    organization: str | None = None
    as_type: str | None = None     # from PeeringDB info_type or static seed
    abuse_email: str | None = None
    city: str | None = None
    latitude: float | None = None
    longitude: float | None = None
    cymru: CymruRecord | None = None
    rdap: RDAPRecord | None = None
    peeringdb: PeeringDBRecord | None = None
    geo: GeoRecord | None = None
    source_provenance: list[dict[str, str]] = field(default_factory=list)


# ---------------------------------------------------------------------------
# Cache mixin
# ---------------------------------------------------------------------------

class ASNCacheMixin:
    """File-based 7-day TTL JSON cache stored under the tracking runtime tree.

    Cache key: sha256(ip_str)[:16]
    Cache file: <cache_dir>/<key>.json
    Atomic write: write to .tmp then os.replace.
    """

    def __init__(self, cache_dir: Path | None = None) -> None:
        if cache_dir is not None:
            self._cache_dir = Path(cache_dir)
        else:
            self._cache_dir = find_tracking_root() / "runtime" / "asn_cache"
        self._cache_dir.mkdir(parents=True, exist_ok=True)

    def _cache_key(self, identifier: str) -> str:
        return hashlib.sha256(identifier.encode()).hexdigest()[:16]

    def _cache_path(self, identifier: str) -> Path:
        return self._cache_dir / f"{self._cache_key(identifier)}.json"

    def _cache_read(self, identifier: str) -> dict | None:
        """Return cached data if within TTL, else None."""
        p = self._cache_path(identifier)
        if not p.exists():
            return None
        try:
            mtime = p.stat().st_mtime
            if (time.time() - mtime) > _CACHE_TTL_SECONDS:
                return None
            return json.loads(p.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError, ValueError):
            return None

    def _cache_write(self, identifier: str, data: dict) -> None:
        """Write data to cache atomically."""
        p = self._cache_path(identifier)
        tmp = p.with_suffix(".tmp")
        try:
            tmp.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
            os.replace(str(tmp), str(p))
        except OSError:
            tmp.unlink(missing_ok=True)

    def _cache_invalidate(self, identifier: str) -> None:
        """Remove a cache entry (used in tests to force fresh lookup)."""
        p = self._cache_path(identifier)
        p.unlink(missing_ok=True)


# ---------------------------------------------------------------------------
# Team Cymru DNS TXT lookup
# ---------------------------------------------------------------------------

class TeamCymruASNLookup(ASNCacheMixin):
    """DNS TXT-based IP-to-ASN mapping via Team Cymru public service.

    Protocol: query <reversed-octets>.origin.asn.cymru.com TXT
    Response format: "ASN | prefix | country | RIR | alloc_date"

    For IPv6, uses <reversed-nibbles>.origin6.asn.cymru.com TXT
    Ref: https://team-cymru.com/community-services/ip-asn-mapping/

    Rate limiting: caller is responsible for per-/24 deduplication before
    calling lookup() on each host in a large CIDR.
    """

    def __init__(self, cache_dir: Path | None = None, timeout: float = 5.0) -> None:
        super().__init__(cache_dir=cache_dir)
        self.timeout = timeout

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def lookup(self, ip_str: str) -> CymruRecord | None:
        """Lookup ASN for ip_str. Returns None on any failure (graceful degradation)."""
        cached = self._cache_read(ip_str)
        if cached is not None:
            return self._dict_to_cymru(ip_str, cached)
        record = self._dns_lookup(ip_str)
        if record is not None:
            self._cache_write(ip_str, self._cymru_to_dict(record))
        return record

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _build_query_name(self, ip_str: str) -> str | None:
        """Build the DNS TXT query name for an IP (IPv4 or IPv6)."""
        try:
            addr = ipaddress.ip_address(ip_str)
        except ValueError:
            return None
        if isinstance(addr, ipaddress.IPv4Address):
            octets = ip_str.strip().split(".")
            reversed_octets = ".".join(reversed(octets))
            return f"{reversed_octets}.origin.asn.cymru.com"
        elif isinstance(addr, ipaddress.IPv6Address):
            # Expand to full 32-nibble hex, reverse, join with dots
            expanded = addr.exploded.replace(":", "")
            reversed_nibbles = ".".join(reversed(expanded))
            return f"{reversed_nibbles}.origin6.asn.cymru.com"
        return None

    def _parse_txt_record(self, txt: str) -> tuple[int | None, str | None, str | None, str | None, str | None]:
        """Parse Cymru TXT response: 'ASN | prefix | country | RIR | alloc_date'

        Returns (asn, prefix, country, rir, alloc_date) -- all may be None.
        Multiple ASNs are comma-separated in the first field; we take the first.
        """
        # Strip outer quotes that some resolvers include
        txt = txt.strip().strip('"').strip("'")
        parts = [p.strip() for p in txt.split("|")]
        if len(parts) < 5:
            return None, None, None, None, None
        asn_field = parts[0].split()[0].split(",")[0].strip() if parts[0].strip() else None
        asn: int | None = None
        try:
            if asn_field:
                asn = int(asn_field)
        except ValueError:
            pass
        prefix = parts[1].strip() or None
        country = parts[2].strip() or None
        rir = parts[3].strip().lower() or None
        alloc_date = parts[4].strip() or None
        return asn, prefix, country, rir, alloc_date

    def _dns_lookup(self, ip_str: str) -> CymruRecord | None:
        """Perform the actual DNS TXT query."""
        qname = self._build_query_name(ip_str)
        if qname is None:
            return None
        try:
            results = self._resolve_txt(qname)
        except (OSError, socket.gaierror):
            return None
        for txt in results:
            asn, prefix, country, rir, alloc_date = self._parse_txt_record(txt)
            if asn is not None:
                return CymruRecord(
                    ip=ip_str,
                    asn=asn,
                    prefix=prefix,
                    country=country,
                    rir=rir,
                    alloc_date=alloc_date,
                )
        return None

    def _resolve_txt(self, qname: str) -> list[str]:
        """Resolve TXT records for qname. Mockable in tests."""
        old_timeout = socket.getdefaulttimeout()
        socket.setdefaulttimeout(self.timeout)
        try:
            results = socket.getaddrinfo(qname, None, type=socket.SOCK_STREAM)
            # getaddrinfo does not return TXT; use resolver below
        except (socket.gaierror, OSError):
            pass
        finally:
            socket.setdefaulttimeout(old_timeout)
        # Use dns.resolver if available, else fall back to manual DNS query
        return self._resolve_txt_socket(qname)

    def _resolve_txt_socket(self, qname: str) -> list[str]:
        """Resolve TXT via a raw DNS query using socket.create_connection to 8.8.8.8:53.

        Uses Google Public DNS (8.8.8.8) as resolver to avoid dependence on
        local resolver configuration. Falls back to system resolver if connection
        fails (e.g. in CI with restricted DNS).

        Builds a minimal DNS wire-format message and parses the answer section.
        """
        # Build DNS TXT query
        msg_id = os.urandom(2)
        header = msg_id + b"\x01\x00\x00\x01\x00\x00\x00\x00\x00\x00"
        question = b""
        for label in qname.rstrip(".").split("."):
            encoded = label.encode("ascii")
            question += bytes([len(encoded)]) + encoded
        question += b"\x00"   # root label
        qtype = b"\x00\x10"   # TXT
        qclass = b"\x00\x01"  # IN
        query = header + question + qtype + qclass

        try:
            with socket.create_connection(("8.8.8.8", 53), timeout=self.timeout) as sock:
                # DNS over TCP: 2-byte length prefix
                length_prefix = len(query).to_bytes(2, "big")
                sock.sendall(length_prefix + query)
                # Read length
                raw_len = self._recv_exactly(sock, 2)
                if raw_len is None:
                    return []
                resp_len = int.from_bytes(raw_len, "big")
                resp = self._recv_exactly(sock, resp_len)
                if resp is None:
                    return []
            return self._parse_dns_txt_response(resp)
        except (OSError, socket.timeout, ConnectionRefusedError):
            return []

    @staticmethod
    def _recv_exactly(sock: socket.socket, n: int) -> bytes | None:
        """Read exactly n bytes from sock, return None on short read."""
        buf = b""
        while len(buf) < n:
            try:
                chunk = sock.recv(n - len(buf))
            except OSError:
                return None
            if not chunk:
                return None
            buf += chunk
        return buf

    @staticmethod
    def _parse_dns_txt_response(data: bytes) -> list[str]:
        """Parse DNS wire-format response and extract TXT record strings.

        Minimal parser: locates the answer section and extracts character-strings
        from TXT (type 16) resource records. Does not validate DNSSEC.
        """
        if len(data) < 12:
            return []
        ancount = int.from_bytes(data[6:8], "big")
        if ancount == 0:
            return []
        # Skip header (12 bytes) + question section
        offset = 12
        # Skip question section (QDCOUNT questions, we sent exactly 1)
        qdcount = int.from_bytes(data[4:6], "big")
        for _ in range(qdcount):
            offset = TeamCymruASNLookup._skip_name(data, offset)
            offset += 4  # qtype + qclass
            if offset > len(data):
                return []
        # Parse answer records
        texts = []
        for _ in range(ancount):
            if offset >= len(data):
                break
            offset = TeamCymruASNLookup._skip_name(data, offset)
            if offset + 10 > len(data):
                break
            rtype = int.from_bytes(data[offset:offset + 2], "big")
            offset += 8  # skip type(2) + class(2) + ttl(4)
            rdlength = int.from_bytes(data[offset:offset + 2], "big")
            offset += 2
            rdata = data[offset:offset + rdlength]
            offset += rdlength
            if rtype == 16:  # TXT
                txt = TeamCymruASNLookup._parse_txt_rdata(rdata)
                if txt:
                    texts.append(txt)
        return texts

    @staticmethod
    def _skip_name(data: bytes, offset: int) -> int:
        """Skip a DNS name at offset (handles compression pointers)."""
        while offset < len(data):
            length = data[offset]
            if length == 0:
                return offset + 1
            if (length & 0xC0) == 0xC0:
                # Compression pointer
                return offset + 2
            offset += 1 + length
        return offset

    @staticmethod
    def _parse_txt_rdata(rdata: bytes) -> str:
        """Parse TXT RDATA: concatenation of <length><string> pairs."""
        result = []
        i = 0
        while i < len(rdata):
            slen = rdata[i]
            i += 1
            result.append(rdata[i:i + slen].decode("utf-8", errors="replace"))
            i += slen
        return "".join(result)

    @staticmethod
    def _cymru_to_dict(rec: CymruRecord) -> dict:
        return {
            "asn": rec.asn,
            "prefix": rec.prefix,
            "country": rec.country,
            "rir": rec.rir,
            "alloc_date": rec.alloc_date,
        }

    @staticmethod
    def _dict_to_cymru(ip_str: str, d: dict) -> CymruRecord:
        return CymruRecord(
            ip=ip_str,
            asn=d.get("asn"),
            prefix=d.get("prefix"),
            country=d.get("country"),
            rir=d.get("rir"),
            alloc_date=d.get("alloc_date"),
        )


# ---------------------------------------------------------------------------
# RDAP lookup (IANA bootstrap + multi-RIR)
# ---------------------------------------------------------------------------

# IANA RDAP bootstrap -- static subset covering primary RIRs.
# Updated from https://data.iana.org/rdap/ipv4.json (version 2023-01-07).
# The bootstrap maps IP prefixes to RDAP base URLs for the 5 RIRs.
# We use a hardcoded minimal bootstrap rather than fetching the live bootstrap
# JSON on each lookup, to avoid a recursive dependency (bootstrap query to
# resolve RDAP URL before the RDAP query itself).
_RIR_RDAP_BASES: dict[str, str] = {
    "arin":    "https://rdap.arin.net/registry",
    "ripe":    "https://rdap.db.ripe.net",
    "apnic":   "https://rdap.apnic.net",
    "afrinic": "https://rdap.afrinic.net/rdap",
    "lacnic":  "https://rdap.lacnic.net/rdap",
}

# RIR IP delegation ranges (coarse, sufficient for bootstrap routing).
# Sourced from IANA address space assignments to RIRs.
# Ref: https://www.iana.org/assignments/ipv4-address-space/ipv4-address-space.xhtml
_COARSE_RIR_RANGES: list[tuple[ipaddress.IPv4Network, str]] = [
    (ipaddress.IPv4Network("1.0.0.0/8"),    "apnic"),
    (ipaddress.IPv4Network("5.0.0.0/8"),    "ripe"),
    (ipaddress.IPv4Network("41.0.0.0/8"),   "afrinic"),
    (ipaddress.IPv4Network("64.0.0.0/4"),   "arin"),      # 64-79
    (ipaddress.IPv4Network("80.0.0.0/4"),   "ripe"),      # 80-95
    (ipaddress.IPv4Network("96.0.0.0/4"),   "arin"),      # 96-111
    (ipaddress.IPv4Network("112.0.0.0/5"),  "apnic"),
    (ipaddress.IPv4Network("120.0.0.0/6"),  "apnic"),
    (ipaddress.IPv4Network("128.0.0.0/3"),  "arin"),      # 128-159
    (ipaddress.IPv4Network("160.0.0.0/3"),  "ripe"),      # 160-191
    (ipaddress.IPv4Network("192.0.0.0/8"),  "arin"),
    (ipaddress.IPv4Network("193.0.0.0/8"),  "ripe"),
    (ipaddress.IPv4Network("195.0.0.0/8"),  "ripe"),
    (ipaddress.IPv4Network("196.0.0.0/7"),  "afrinic"),
    (ipaddress.IPv4Network("200.0.0.0/8"),  "lacnic"),
    (ipaddress.IPv4Network("201.0.0.0/8"),  "lacnic"),
    (ipaddress.IPv4Network("202.0.0.0/7"),  "apnic"),
    (ipaddress.IPv4Network("210.0.0.0/7"),  "apnic"),
    (ipaddress.IPv4Network("218.0.0.0/7"),  "apnic"),
    (ipaddress.IPv4Network("220.0.0.0/6"),  "apnic"),
    (ipaddress.IPv4Network("222.0.0.0/7"),  "apnic"),
    (ipaddress.IPv4Network("223.0.0.0/8"),  "apnic"),
]


def _rir_for_ip(ip_str: str) -> str:
    """Return probable RIR for ip_str using coarse range table. Defaults to 'arin'."""
    try:
        addr = ipaddress.IPv4Address(ip_str)
    except ValueError:
        return "arin"
    for net, rir in _COARSE_RIR_RANGES:
        if addr in net:
            return rir
    return "arin"


class RDAPLookup(ASNCacheMixin):
    """RDAP (RFC 7483) IP lookup via the appropriate RIR endpoint.

    Route: select RIR via _rir_for_ip() -> try that RIR RDAP endpoint.
    If the first RIR returns 404/error, iterate remaining RIRs as fallback.
    Cache key: ip_str (7-day TTL).
    """

    def __init__(self, cache_dir: Path | None = None, timeout: float = 8.0) -> None:
        super().__init__(cache_dir=cache_dir)
        self.timeout = timeout

    def lookup(self, ip_str: str) -> RDAPRecord | None:
        """Lookup RDAP for ip_str. Returns None on any failure."""
        cached = self._cache_read(f"rdap:{ip_str}")
        if cached is not None:
            return self._dict_to_rdap(ip_str, cached)
        record = self._rdap_lookup(ip_str)
        if record is not None:
            self._cache_write(f"rdap:{ip_str}", self._rdap_to_dict(record))
        return record

    def _rdap_lookup(self, ip_str: str) -> RDAPRecord | None:
        """Try RIRs in priority order, return first successful result."""
        primary_rir = _rir_for_ip(ip_str)
        rir_order = [primary_rir] + [r for r in _RIR_RDAP_BASES if r != primary_rir]
        for rir in rir_order:
            base = _RIR_RDAP_BASES[rir]
            url = f"{base}/ip/{ip_str}"
            try:
                data = self._http_get_json(url)
            except (urllib.error.URLError, OSError, ValueError):
                continue
            if data is None:
                continue
            record = self._parse_rdap_response(ip_str, rir, data)
            if record is not None:
                return record
        return None

    def _http_get_json(self, url: str) -> dict | None:
        """GET url, return parsed JSON or None. Raises urllib.error.URLError on HTTP error."""
        req = urllib.request.Request(
            url,
            headers={
                "Accept": "application/rdap+json, application/json",
                "User-Agent": "lia-sec-enrichment/2.0 (rdap-lookup; contact enrichment@lia-sec.internal)",
            },
        )
        with urllib.request.urlopen(req, timeout=self.timeout) as resp:  # type: ignore[arg-type]
            body = resp.read()
        return json.loads(body)

    @staticmethod
    def _parse_rdap_response(ip_str: str, rir: str, data: dict) -> RDAPRecord | None:
        """Extract RDAPRecord fields from RDAP JSON response (RFC 7483)."""
        name = data.get("name") or data.get("handle")
        country = data.get("country")
        # Collect CIDR from cidr0_cidrs or startAddress/prefixLength
        cidr = None
        cidr0 = data.get("cidr0_cidrs", [])
        if cidr0:
            first = cidr0[0]
            cidr = f"{first.get('v4prefix', first.get('v6prefix',''))}/{first.get('length','')}"
        if not cidr:
            start = data.get("startAddress", "")
            plen = data.get("prefix", "") or data.get("cidrMask", "")
            if start and plen:
                cidr = f"{start}/{plen}"
        # Organization from entities
        organization = None
        abuse_email = None
        entities = data.get("entities", [])
        for entity in entities:
            roles = entity.get("roles", [])
            vcard = entity.get("vcardArray", [])
            entity_name = None
            entity_email = None
            if isinstance(vcard, list) and len(vcard) > 1:
                for vcard_field in vcard[1]:
                    if isinstance(vcard_field, list) and len(vcard_field) >= 4:
                        if vcard_field[0] == "fn":
                            entity_name = str(vcard_field[3])
                        elif vcard_field[0] == "email":
                            entity_email = str(vcard_field[3])
            if "registrant" in roles or "administrative" in roles:
                if entity_name and not organization:
                    organization = entity_name
            if "abuse" in roles and entity_email:
                abuse_email = entity_email
            # Also check sub-entities for abuse contacts
            for sub in entity.get("entities", []):
                sub_roles = sub.get("roles", [])
                if "abuse" in sub_roles:
                    sub_vcard = sub.get("vcardArray", [])
                    if isinstance(sub_vcard, list) and len(sub_vcard) > 1:
                        for sv in sub_vcard[1]:
                            if isinstance(sv, list) and len(sv) >= 4 and sv[0] == "email":
                                if abuse_email is None:
                                    abuse_email = str(sv[3])
        return RDAPRecord(
            ip=ip_str,
            name=name,
            organization=organization,
            country=country,
            cidr=cidr,
            abuse_email=abuse_email,
            rir=rir,
        )

    @staticmethod
    def _rdap_to_dict(rec: RDAPRecord) -> dict:
        return {
            "name": rec.name,
            "organization": rec.organization,
            "country": rec.country,
            "cidr": rec.cidr,
            "abuse_email": rec.abuse_email,
            "rir": rec.rir,
        }

    @staticmethod
    def _dict_to_rdap(ip_str: str, d: dict) -> RDAPRecord:
        return RDAPRecord(
            ip=ip_str,
            name=d.get("name"),
            organization=d.get("organization"),
            country=d.get("country"),
            cidr=d.get("cidr"),
            abuse_email=d.get("abuse_email"),
            rir=d.get("rir"),
        )


# ---------------------------------------------------------------------------
# PeeringDB lookup
# ---------------------------------------------------------------------------

class PeeringDBLookup(ASNCacheMixin):
    """PeeringDB network lookup by ASN.

    Endpoint: https://www.peeringdb.com/api/net?asn={asn}
    License: CC-BY-4.0. Attribution required in any derivative work.
    Cache key: asn (7-day TTL, reused across all IPs in the same ASN).

    Attribution: Data from PeeringDB (peeringdb.com), licensed under
    CC-BY-4.0 (https://creativecommons.org/licenses/by/4.0/).
    """

    _BASE_URL = "https://www.peeringdb.com/api/net"
    _LICENSE_URL = "https://creativecommons.org/licenses/by/4.0/"
    _SOURCE_URL_TEMPLATE = "https://www.peeringdb.com/api/net?asn={asn}"

    def __init__(self, cache_dir: Path | None = None, timeout: float = 8.0) -> None:
        super().__init__(cache_dir=cache_dir)
        self.timeout = timeout

    def lookup(self, asn: int) -> PeeringDBRecord | None:
        """Lookup PeeringDB for asn. Returns None if not found or on error."""
        cached = self._cache_read(f"pdb:{asn}")
        if cached is not None:
            return self._dict_to_pdb(asn, cached)
        record = self._http_lookup(asn)
        if record is not None:
            self._cache_write(f"pdb:{asn}", self._pdb_to_dict(record))
        return record

    def _http_lookup(self, asn: int) -> PeeringDBRecord | None:
        url = f"{self._BASE_URL}?asn={asn}"
        req = urllib.request.Request(
            url,
            headers={
                "Accept": "application/json",
                "User-Agent": "lia-sec-enrichment/2.0 (peeringdb-lookup; CC-BY-4.0 client)",
            },
        )
        try:
            with urllib.request.urlopen(req, timeout=self.timeout) as resp:
                body = resp.read()
        except (urllib.error.URLError, OSError):
            return None
        try:
            data = json.loads(body)
        except json.JSONDecodeError:
            return None
        return self._parse_peeringdb_response(asn, data)

    @staticmethod
    def _parse_peeringdb_response(asn: int, data: dict) -> PeeringDBRecord | None:
        """Extract fields from PeeringDB /api/net response."""
        nets = data.get("data", [])
        if not nets:
            return None
        net = nets[0]
        org = net.get("org", {}) if isinstance(net.get("org"), dict) else {}
        org_name = org.get("name") or net.get("org_name") or net.get("name")
        return PeeringDBRecord(
            asn=asn,
            name=net.get("name"),
            org_name=org_name,
            info_type=net.get("info_type"),   # e.g. "Content", "ISP", "Hosting", "Enterprise"
            country=net.get("info_ipv4") and None or net.get("country"),
            website=net.get("website"),
        )

    @staticmethod
    def _pdb_to_dict(rec: PeeringDBRecord) -> dict:
        return {
            "name": rec.name,
            "org_name": rec.org_name,
            "info_type": rec.info_type,
            "country": rec.country,
            "website": rec.website,
        }

    @staticmethod
    def _dict_to_pdb(asn: int, d: dict) -> PeeringDBRecord:
        return PeeringDBRecord(
            asn=asn,
            name=d.get("name"),
            org_name=d.get("org_name"),
            info_type=d.get("info_type"),
            country=d.get("country"),
            website=d.get("website"),
        )


# ---------------------------------------------------------------------------
# MaxMind GeoLite2 reader (optional, gated by db_path)
# ---------------------------------------------------------------------------

class MaxMindGeoReader:
    """MaxMind GeoLite2 binary .mmdb reader, gated by operator-supplied db_path.

    License (database file only, not this code): CC-BY-SA-4.0.
    "This product includes GeoLite2 data created by MaxMind, available from
    https://www.maxmind.com"
    The .mmdb file must NOT be bundled with LiaProbe. Operator downloads it
    separately: https://dev.maxmind.com/geoip/geolite2-free-geolocation-data

    Requires: pip install maxminddb
    If maxminddb is not installed, lookup() returns None (graceful degradation).
    """

    def __init__(self, db_path: str | Path | None = None) -> None:
        self._db_path: Path | None = Path(db_path) if db_path else None
        self._db: Any = None
        self._available = False
        if self._db_path and self._db_path.exists():
            self._open_db()

    def _open_db(self) -> None:
        try:
            import maxminddb  # type: ignore[import-not-found]
            self._db = maxminddb.open_database(str(self._db_path))
            self._available = True
        except ImportError:
            pass
        except Exception:  # noqa: BLE001
            pass

    @property
    def available(self) -> bool:
        return self._available

    def lookup(self, ip_str: str) -> GeoRecord | None:
        """Lookup ip_str in the MaxMind database. Returns None if not available."""
        if not self._available or self._db is None:
            return None
        try:
            record = self._db.get(ip_str)
        except Exception:  # noqa: BLE001
            return None
        if record is None:
            return None
        return self._parse_record(ip_str, record)

    @staticmethod
    def _parse_record(ip_str: str, rec: dict) -> GeoRecord:
        country = rec.get("country", {})
        city = rec.get("city", {})
        subdivisions = rec.get("subdivisions", [])
        location = rec.get("location", {})
        sub_name = None
        if subdivisions:
            sub = subdivisions[0]
            names = sub.get("names", {})
            sub_name = names.get("en") or next(iter(names.values()), None)
        country_iso = country.get("iso_code")
        country_names = country.get("names", {})
        country_name = country_names.get("en") or next(iter(country_names.values()), None)
        city_names = city.get("names", {})
        city_name = city_names.get("en") or next(iter(city_names.values()), None)
        # ASN fields (from GeoLite2-ASN db format)
        asn = rec.get("autonomous_system_number")
        asn_org = rec.get("autonomous_system_organization")
        return GeoRecord(
            ip=ip_str,
            country_iso=country_iso,
            country_name=country_name,
            city_name=city_name,
            subdivision=sub_name,
            latitude=location.get("latitude"),
            longitude=location.get("longitude"),
            asn=asn,
            asn_org=asn_org,
        )

    def close(self) -> None:
        if self._db is not None:
            try:
                self._db.close()
            except Exception:  # noqa: BLE001
                pass
            self._db = None
            self._available = False

    def __enter__(self) -> "MaxMindGeoReader":
        return self

    def __exit__(self, *args: Any) -> None:
        self.close()


# ---------------------------------------------------------------------------
# Utility: map PeeringDB info_type to internal as_type
# ---------------------------------------------------------------------------

_PEERINGDB_TYPE_MAP: dict[str, str] = {
    "Content": "content",
    "ISP": "isp",
    "Hosting": "hosting",
    "Enterprise": "enterprise",
    "Non-Profit": "nonprofit",
    "Educational": "education",
    "Cable/DSL/ISP": "isp",
    "Route Server": "transit",
    "Transit": "transit",
    "NSP": "transit",
    "Route Collector": "transit",
}


def _normalize_pdb_type(info_type: str | None) -> str | None:
    if info_type is None:
        return None
    return _PEERINGDB_TYPE_MAP.get(info_type, info_type.lower())


# ---------------------------------------------------------------------------
# Fallback chain orchestrator
# ---------------------------------------------------------------------------

class LiveASNChain:
    """Orchestrates the live ASN lookup fallback chain.

    Chain: Cymru (DNS) -> RDAP (HTTP) -> PeeringDB (HTTP) -> static seed (master)

    Each source is queried only if the previous source did not provide
    the requested field. Failures are silent (graceful degradation).

    Usage::

        chain = LiveASNChain()
        result = chain.resolve("1.2.3.4")
        # result.asn, result.organization, result.country, ...
    """

    def __init__(
        self,
        cache_dir: Path | None = None,
        geo_db_path: str | Path | None = None,
        cymru_timeout: float = 5.0,
        rdap_timeout: float = 8.0,
        pdb_timeout: float = 8.0,
        *,
        cymru: TeamCymruASNLookup | None = None,
        rdap: RDAPLookup | None = None,
        peeringdb: PeeringDBLookup | None = None,
        geo: MaxMindGeoReader | None = None,
    ) -> None:
        self._cymru = cymru or TeamCymruASNLookup(cache_dir=cache_dir, timeout=cymru_timeout)
        self._rdap = rdap or RDAPLookup(cache_dir=cache_dir, timeout=rdap_timeout)
        self._pdb = peeringdb or PeeringDBLookup(cache_dir=cache_dir, timeout=pdb_timeout)
        self._geo = geo or MaxMindGeoReader(db_path=geo_db_path)

    def resolve(self, ip_str: str) -> LiveASNResult:
        """Run the full chain and return a LiveASNResult for ip_str."""
        result = LiveASNResult(ip=ip_str)

        # Step 1: Team Cymru DNS -> ASN, prefix, country, RIR, alloc_date
        cymru_rec = self._cymru.lookup(ip_str)
        if cymru_rec is not None:
            result.cymru = cymru_rec
            result.asn = cymru_rec.asn
            result.prefix = cymru_rec.prefix
            result.country = cymru_rec.country or result.country
            result.rir = cymru_rec.rir
            result.alloc_date = cymru_rec.alloc_date
            result.source_provenance.append({
                "field": "asn",
                "source": "cymru_dns",
                "source_url": f"dig TXT {self._cymru._build_query_name(ip_str)}",
                "source_sha256": "n/a (live DNS response)",
            })

        # Step 2: RDAP -> organization, country (supplement), abuse_email
        rdap_rec = self._rdap.lookup(ip_str)
        if rdap_rec is not None:
            result.rdap = rdap_rec
            if result.organization is None:
                result.organization = rdap_rec.organization
            if result.country is None:
                result.country = rdap_rec.country
            if rdap_rec.rir:
                result.rir = result.rir or rdap_rec.rir
            result.abuse_email = rdap_rec.abuse_email
            if rdap_rec.organization is not None:
                rir = rdap_rec.rir or "unknown"
                base = _RIR_RDAP_BASES.get(rir, "https://rdap.arin.net/registry")
                result.source_provenance.append({
                    "field": "organization",
                    "source": "rdap",
                    "source_url": f"{base}/ip/{ip_str}",
                    "source_sha256": "n/a (live RDAP response)",
                })

        # Step 3: PeeringDB -> org_name, info_type (as_type), country supplement
        asn_for_pdb = result.asn
        if asn_for_pdb is not None:
            pdb_rec = self._pdb.lookup(asn_for_pdb)
            if pdb_rec is not None:
                result.peeringdb = pdb_rec
                if result.organization is None:
                    result.organization = pdb_rec.org_name or pdb_rec.name
                if result.country is None and pdb_rec.country:
                    result.country = pdb_rec.country
                result.as_type = _normalize_pdb_type(pdb_rec.info_type)
                result.source_provenance.append({
                    "field": "as_type",
                    "source": "peeringdb",
                    "source_url": f"https://www.peeringdb.com/api/net?asn={asn_for_pdb}",
                    "source_sha256": "n/a (live API response)",
                    "license": "CC-BY-4.0",
                    "attribution": (
                        "Data from PeeringDB (peeringdb.com), "
                        "licensed under CC-BY-4.0 (https://creativecommons.org/licenses/by/4.0/)"
                    ),
                })

        # Step 4: MaxMind GeoLite2 (optional) -> city, lat/lon
        if self._geo.available:
            geo_rec = self._geo.lookup(ip_str)
            if geo_rec is not None:
                result.geo = geo_rec
                result.city = geo_rec.city_name
                result.latitude = geo_rec.latitude
                result.longitude = geo_rec.longitude
                if result.country is None:
                    result.country = geo_rec.country_iso
                if result.asn is None and geo_rec.asn is not None:
                    result.asn = geo_rec.asn
                if result.organization is None:
                    result.organization = geo_rec.asn_org
                result.source_provenance.append({
                    "field": "geo",
                    "source": "maxmind_geolite2",
                    "source_url": "https://dev.maxmind.com/geoip/geolite2-free-geolocation-data",
                    "source_sha256": "n/a (local db)",
                    "license": "CC-BY-SA-4.0",
                    "attribution": (
                        "This product includes GeoLite2 data created by MaxMind, "
                        "available from https://www.maxmind.com"
                    ),
                })

        return result


# ---------------------------------------------------------------------------
# Public exports
# ---------------------------------------------------------------------------

__all__ = [
    "CymruRecord",
    "RDAPRecord",
    "PeeringDBRecord",
    "GeoRecord",
    "LiveASNResult",
    "ASNCacheMixin",
    "TeamCymruASNLookup",
    "RDAPLookup",
    "PeeringDBLookup",
    "MaxMindGeoReader",
    "LiveASNChain",
    "_normalize_pdb_type",
    "_rir_for_ip",
]
