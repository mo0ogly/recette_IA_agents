"""Tests for asn_lookup_live (cycle 13 Phase 2B).

All external I/O (DNS, HTTP, maxminddb) is mocked via unittest.mock.
No live network calls are made in this test suite.

Coverage:
  - TeamCymruASNLookup: parse, IPv4 query build, IPv6 query build, cache hit/miss,
    fallback on DNS error, multi-ASN TXT, malformed TXT, DNS response parser.
  - RDAPLookup: parse full RDAP response, RIR routing, cache hit, HTTP error fallback.
  - PeeringDBLookup: parse PDB response, empty data set, cache hit, HTTP error.
  - MaxMindGeoReader: graceful degradation when maxminddb missing, available path.
  - LiveASNChain: fallback chain ordering, field merging, provenance list.
  - classify_target live=True: integration of Phase 1 + Phase 2B.
  - Cache: TTL expiry, atomic write, cache invalidation.
  - License attribution: PeeringDB CC-BY-4.0 string present in records.
"""
from __future__ import annotations

import json
import sys
import time
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import MagicMock, patch

SCRIPT_DIR = Path(__file__).resolve().parent.parent / "scripts"
sys.path.insert(0, str(SCRIPT_DIR))

import asn_lookup_live as asl  # noqa: E402
import target_context_classifier as tcc  # noqa: E402


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_cache_dir() -> tuple[TemporaryDirectory, Path]:
    tmp = TemporaryDirectory()
    return tmp, Path(tmp.name)


CYMRU_TXT_RESPONSE = "16509 | 1.2.0.0/16 | US | arin | 1992-12-01"
CYMRU_TXT_MULTIASN = "16509, 14618 | 1.2.0.0/16 | US | arin | 1992-12-01"
CYMRU_TXT_MALFORMED = "not-a-number | bad | xx | x | x"
CYMRU_TXT_PARTIAL_FIELDS = "15169 | 1.2.0.0/16 | US"  # only 3 fields


RDAP_RESPONSE = {
    "handle": "NET-1-2-0-0-1",
    "name": "AMAZON-EC2-US",
    "country": "US",
    "cidr0_cidrs": [{"v4prefix": "1.2.0.0", "length": "16"}],
    "entities": [
        {
            "roles": ["registrant"],
            "vcardArray": [
                "vcard",
                [
                    ["version", {}, "text", "4.0"],
                    ["fn", {}, "text", "Amazon Technologies Inc."],
                ],
            ],
        },
        {
            "roles": ["abuse"],
            "entities": [],
            "vcardArray": [
                "vcard",
                [
                    ["version", {}, "text", "4.0"],
                    ["fn", {}, "text", "Amazon Abuse"],
                    ["email", {}, "text", "abuse@amazonaws.com"],
                ],
            ],
        },
    ],
}

PEERINGDB_RESPONSE = {
    "data": [
        {
            "name": "AMAZON-02",
            "org_name": "Amazon Web Services",
            "info_type": "Content",
            "country": "US",
            "website": "https://aws.amazon.com",
        }
    ]
}

PEERINGDB_EMPTY = {"data": []}


MASTER_FIXTURE = {
    "$schema": "lia-cidr-context-master-v2",
    "bogon_ranges": [
        {
            "cidr": "10.0.0.0/8",
            "type": "private",
            "source_url": "https://www.rfc-editor.org/rfc/rfc1918.txt",
            "source_sha256": "abc",
        },
    ],
    "asn_type_map": {
        "source_url": "https://www.peeringdb.com/api/net",
        "asns": {
            "16509": {"organization": "AWS", "type": "cloud", "country": "US"},
            "13335": {"organization": "Cloudflare", "type": "cdn", "country": "US"},
        },
    },
    "cdn_server_header_map": {
        "values": {
            "cloudflare": "13335",
        }
    },
}


def _write_master(tmpdir: Path) -> Path:
    p = tmpdir / "cidr_context_master.json"
    p.write_text(json.dumps(MASTER_FIXTURE))
    return p


# ---------------------------------------------------------------------------
# TeamCymruASNLookup tests
# ---------------------------------------------------------------------------

class TestCymruQueryBuild(unittest.TestCase):
    def _lookup(self, tmp: Path) -> asl.TeamCymruASNLookup:
        return asl.TeamCymruASNLookup(cache_dir=tmp)

    def test_ipv4_query_name(self):
        tmp = TemporaryDirectory()
        lu = self._lookup(Path(tmp.name))
        qname = lu._build_query_name("1.2.3.4")
        self.assertEqual(qname, "4.3.2.1.origin.asn.cymru.com")
        tmp.cleanup()

    def test_ipv6_query_name(self):
        tmp = TemporaryDirectory()
        lu = self._lookup(Path(tmp.name))
        qname = lu._build_query_name("2001:db8::1")
        self.assertIn("origin6.asn.cymru.com", qname)
        tmp.cleanup()

    def test_invalid_ip_returns_none_query(self):
        tmp = TemporaryDirectory()
        lu = self._lookup(Path(tmp.name))
        qname = lu._build_query_name("not-an-ip")
        self.assertIsNone(qname)
        tmp.cleanup()


class TestCymruTXTParsing(unittest.TestCase):
    def setUp(self):
        self.tmp = TemporaryDirectory()
        self.lu = asl.TeamCymruASNLookup(cache_dir=Path(self.tmp.name))

    def tearDown(self):
        self.tmp.cleanup()

    def test_parse_standard_response(self):
        asn, prefix, country, rir, alloc = self.lu._parse_txt_record(CYMRU_TXT_RESPONSE)
        self.assertEqual(asn, 16509)
        self.assertEqual(prefix, "1.2.0.0/16")
        self.assertEqual(country, "US")
        self.assertEqual(rir, "arin")
        self.assertEqual(alloc, "1992-12-01")

    def test_parse_multi_asn_takes_first(self):
        asn, prefix, country, rir, alloc = self.lu._parse_txt_record(CYMRU_TXT_MULTIASN)
        self.assertEqual(asn, 16509)

    def test_parse_malformed_asn_returns_none(self):
        asn, prefix, country, rir, alloc = self.lu._parse_txt_record(CYMRU_TXT_MALFORMED)
        self.assertIsNone(asn)

    def test_parse_partial_fields_returns_none_asn(self):
        asn, prefix, country, rir, alloc = self.lu._parse_txt_record(CYMRU_TXT_PARTIAL_FIELDS)
        self.assertIsNone(asn)

    def test_parse_strips_outer_quotes(self):
        quoted = f'"{CYMRU_TXT_RESPONSE}"'
        asn, _, _, _, _ = self.lu._parse_txt_record(quoted)
        self.assertEqual(asn, 16509)


class TestCymruLookupWithMock(unittest.TestCase):
    """Lookup tests with _resolve_txt_socket mocked."""

    def setUp(self):
        self.tmp = TemporaryDirectory()
        self.lu = asl.TeamCymruASNLookup(cache_dir=Path(self.tmp.name))

    def tearDown(self):
        self.tmp.cleanup()

    def _mock_txt(self, responses: list[str]):
        return patch.object(self.lu, "_resolve_txt_socket", return_value=responses)

    def test_lookup_success(self):
        with self._mock_txt([CYMRU_TXT_RESPONSE]):
            rec = self.lu.lookup("1.2.3.4")
        self.assertIsNotNone(rec)
        self.assertEqual(rec.asn, 16509)
        self.assertEqual(rec.country, "US")
        self.assertEqual(rec.rir, "arin")

    def test_lookup_dns_error_returns_none(self):
        with self._mock_txt([]):
            rec = self.lu.lookup("1.2.3.4")
        self.assertIsNone(rec)

    def test_cache_hit_avoids_dns(self):
        # Populate cache
        with self._mock_txt([CYMRU_TXT_RESPONSE]):
            rec1 = self.lu.lookup("1.2.3.4")
        # Second call with DNS returning error -- should use cache
        with self._mock_txt([]):
            rec2 = self.lu.lookup("1.2.3.4")
        self.assertIsNotNone(rec2)
        self.assertEqual(rec2.asn, rec1.asn)

    def test_cache_miss_after_expiry(self):
        # Populate cache
        with self._mock_txt([CYMRU_TXT_RESPONSE]):
            self.lu.lookup("10.0.0.1")
        # Manually expire the cache entry
        cache_path = self.lu._cache_path("10.0.0.1")
        stale_mtime = time.time() - (asl._CACHE_TTL_SECONDS + 100)
        import os
        os.utime(str(cache_path), (stale_mtime, stale_mtime))
        # Should re-query
        called = []
        original = self.lu._resolve_txt_socket

        def spy(*a, **kw):
            called.append(1)
            return []

        with patch.object(self.lu, "_resolve_txt_socket", spy):
            self.lu.lookup("10.0.0.1")
        self.assertTrue(len(called) > 0, "Expected a fresh DNS call after cache expiry")

    def test_bogon_ip_lookup_proceeds(self):
        # Cymru lookup does not block bogons; classification layer blocks
        with self._mock_txt([]):
            rec = self.lu.lookup("10.0.0.1")
        self.assertIsNone(rec)


# ---------------------------------------------------------------------------
# RDAPLookup tests
# ---------------------------------------------------------------------------

class TestRDAPLookup(unittest.TestCase):
    def setUp(self):
        self.tmp = TemporaryDirectory()
        self.lu = asl.RDAPLookup(cache_dir=Path(self.tmp.name))

    def tearDown(self):
        self.tmp.cleanup()

    def test_rir_for_ip_aws(self):
        rir = asl._rir_for_ip("1.2.3.4")
        self.assertEqual(rir, "apnic")

    def test_rir_for_ip_defaults_to_arin_for_us_range(self):
        rir = asl._rir_for_ip("64.1.1.1")
        self.assertEqual(rir, "arin")

    def test_parse_rdap_response(self):
        rec = asl.RDAPLookup._parse_rdap_response("1.2.3.4", "arin", RDAP_RESPONSE)
        self.assertIsNotNone(rec)
        self.assertEqual(rec.name, "AMAZON-EC2-US")
        self.assertEqual(rec.organization, "Amazon Technologies Inc.")
        self.assertEqual(rec.country, "US")
        self.assertEqual(rec.abuse_email, "abuse@amazonaws.com")
        self.assertEqual(rec.rir, "arin")

    def test_parse_rdap_empty_entities(self):
        minimal = {"name": "TEST-NET", "country": "FR", "entities": []}
        rec = asl.RDAPLookup._parse_rdap_response("5.1.2.3", "ripe", minimal)
        self.assertIsNotNone(rec)
        self.assertEqual(rec.name, "TEST-NET")
        self.assertIsNone(rec.organization)

    def test_lookup_uses_cache_on_second_call(self):
        with patch.object(self.lu, "_http_get_json", return_value=RDAP_RESPONSE) as mock_http:
            rec1 = self.lu.lookup("1.2.3.4")
            rec2 = self.lu.lookup("1.2.3.4")
        self.assertEqual(mock_http.call_count, 1)
        self.assertEqual(rec1.name, rec2.name)

    def test_lookup_returns_none_on_http_error(self):
        import urllib.error
        with patch.object(self.lu, "_http_get_json", side_effect=urllib.error.URLError("timeout")):
            rec = self.lu.lookup("1.2.3.4")
        self.assertIsNone(rec)

    def test_lookup_falls_back_to_next_rir_on_404(self):
        import urllib.error
        call_count = [0]
        responses = [
            urllib.error.URLError("404"),
            RDAP_RESPONSE,
        ]

        def fake_get(url):
            r = responses[call_count[0]]
            call_count[0] += 1
            if isinstance(r, Exception):
                raise r
            return r

        with patch.object(self.lu, "_http_get_json", side_effect=fake_get):
            rec = self.lu.lookup("1.2.3.4")
        self.assertIsNotNone(rec)
        self.assertEqual(call_count[0], 2)


# ---------------------------------------------------------------------------
# PeeringDBLookup tests
# ---------------------------------------------------------------------------

class TestPeeringDBLookup(unittest.TestCase):
    def setUp(self):
        self.tmp = TemporaryDirectory()
        self.lu = asl.PeeringDBLookup(cache_dir=Path(self.tmp.name))

    def tearDown(self):
        self.tmp.cleanup()

    def test_parse_full_response(self):
        rec = asl.PeeringDBLookup._parse_peeringdb_response(16509, PEERINGDB_RESPONSE)
        self.assertIsNotNone(rec)
        self.assertEqual(rec.asn, 16509)
        self.assertEqual(rec.name, "AMAZON-02")
        self.assertEqual(rec.org_name, "Amazon Web Services")
        self.assertEqual(rec.info_type, "Content")

    def test_parse_empty_data_returns_none(self):
        rec = asl.PeeringDBLookup._parse_peeringdb_response(99999, PEERINGDB_EMPTY)
        self.assertIsNone(rec)

    def test_license_attribution_present(self):
        rec = asl.PeeringDBLookup._parse_peeringdb_response(16509, PEERINGDB_RESPONSE)
        self.assertIn("CC-BY-4.0", rec.license_attribution)
        self.assertIn("peeringdb.com", rec.license_attribution)

    def test_lookup_uses_cache_on_second_call(self):
        mock_body = json.dumps(PEERINGDB_RESPONSE).encode()
        mock_resp = MagicMock()
        mock_resp.__enter__ = lambda s: s
        mock_resp.__exit__ = MagicMock(return_value=False)
        mock_resp.read.return_value = mock_body
        with patch("urllib.request.urlopen", return_value=mock_resp) as mock_open:
            self.lu.lookup(16509)
            self.lu.lookup(16509)
        self.assertEqual(mock_open.call_count, 1)

    def test_lookup_returns_none_on_http_error(self):
        import urllib.error
        with patch("urllib.request.urlopen", side_effect=urllib.error.URLError("down")):
            rec = self.lu.lookup(16509)
        self.assertIsNone(rec)

    def test_normalize_pdb_type_hosting(self):
        self.assertEqual(asl._normalize_pdb_type("Hosting"), "hosting")

    def test_normalize_pdb_type_content(self):
        self.assertEqual(asl._normalize_pdb_type("Content"), "content")

    def test_normalize_pdb_type_none(self):
        self.assertIsNone(asl._normalize_pdb_type(None))


# ---------------------------------------------------------------------------
# MaxMindGeoReader tests
# ---------------------------------------------------------------------------

class TestMaxMindGeoReader(unittest.TestCase):
    def test_not_available_when_no_path(self):
        reader = asl.MaxMindGeoReader(db_path=None)
        self.assertFalse(reader.available)
        self.assertIsNone(reader.lookup("1.2.3.4"))

    def test_not_available_when_path_missing(self):
        reader = asl.MaxMindGeoReader(db_path="/nonexistent/GeoLite2.mmdb")
        self.assertFalse(reader.available)

    def test_not_available_when_maxminddb_not_installed(self):
        tmp = TemporaryDirectory()
        db_file = Path(tmp.name) / "fake.mmdb"
        db_file.write_bytes(b"fake")
        with patch.dict("sys.modules", {"maxminddb": None}):
            reader = asl.MaxMindGeoReader(db_path=db_file)
        self.assertFalse(reader.available)
        tmp.cleanup()

    def test_available_with_mock_db(self):
        tmp = TemporaryDirectory()
        db_file = Path(tmp.name) / "fake.mmdb"
        db_file.write_bytes(b"fake")
        mock_mm = MagicMock()
        mock_mm.open_database.return_value = MagicMock()
        with patch.dict("sys.modules", {"maxminddb": mock_mm}):
            reader = asl.MaxMindGeoReader(db_path=db_file)
        # open_database was called
        mock_mm.open_database.assert_called_once()
        tmp.cleanup()

    def test_parse_record_full(self):
        rec_data = {
            "country": {"iso_code": "DE", "names": {"en": "Germany"}},
            "city": {"names": {"en": "Berlin"}},
            "subdivisions": [{"names": {"en": "Berlin"}}],
            "location": {"latitude": 52.5, "longitude": 13.4},
        }
        rec = asl.MaxMindGeoReader._parse_record("5.1.2.3", rec_data)
        self.assertEqual(rec.country_iso, "DE")
        self.assertEqual(rec.city_name, "Berlin")
        self.assertAlmostEqual(rec.latitude, 52.5)
        self.assertAlmostEqual(rec.longitude, 13.4)

    def test_parse_record_empty(self):
        rec = asl.MaxMindGeoReader._parse_record("1.1.1.1", {})
        self.assertIsNone(rec.country_iso)
        self.assertIsNone(rec.city_name)

    def test_license_attribution_in_record(self):
        rec_data = {"country": {"iso_code": "US", "names": {"en": "United States"}}}
        rec = asl.MaxMindGeoReader._parse_record("8.8.8.8", rec_data)
        self.assertIn("MaxMind", rec.license_attribution)
        self.assertIn("CC-BY-SA-4.0", rec.license_attribution)


# ---------------------------------------------------------------------------
# LiveASNChain tests
# ---------------------------------------------------------------------------

class TestLiveASNChain(unittest.TestCase):
    def setUp(self):
        self.tmp = TemporaryDirectory()
        self.cache_dir = Path(self.tmp.name)

    def tearDown(self):
        self.tmp.cleanup()

    def _make_chain(
        self,
        cymru_return=None,
        rdap_return=None,
        pdb_return=None,
        geo_return=None,
    ):
        cymru = MagicMock(spec=asl.TeamCymruASNLookup)
        cymru.lookup.return_value = cymru_return
        rdap = MagicMock(spec=asl.RDAPLookup)
        rdap.lookup.return_value = rdap_return
        peeringdb = MagicMock(spec=asl.PeeringDBLookup)
        peeringdb.lookup.return_value = pdb_return
        geo = MagicMock(spec=asl.MaxMindGeoReader)
        geo.available = geo_return is not None
        geo.lookup.return_value = geo_return
        return asl.LiveASNChain(
            cache_dir=self.cache_dir,
            cymru=cymru,
            rdap=rdap,
            peeringdb=peeringdb,
            geo=geo,
        )

    def test_full_chain_merges_fields(self):
        cymru_rec = asl.CymruRecord(
            ip="1.2.3.4", asn=16509, prefix="1.2.0.0/16",
            country="US", rir="arin", alloc_date="1992-12-01",
        )
        rdap_rec = asl.RDAPRecord(
            ip="1.2.3.4", name="AMAZON-EC2-US",
            organization="Amazon Technologies Inc.", country="US",
            cidr="1.2.0.0/16", abuse_email="abuse@amazonaws.com", rir="arin",
        )
        pdb_rec = asl.PeeringDBRecord(
            asn=16509, name="AMAZON-02", org_name="Amazon Web Services",
            info_type="Content", country="US", website="https://aws.amazon.com",
        )
        chain = self._make_chain(cymru_return=cymru_rec, rdap_return=rdap_rec, pdb_return=pdb_rec)
        result = chain.resolve("1.2.3.4")
        self.assertEqual(result.asn, 16509)
        self.assertEqual(result.country, "US")
        self.assertEqual(result.organization, "Amazon Technologies Inc.")
        self.assertEqual(result.as_type, "content")
        self.assertEqual(result.abuse_email, "abuse@amazonaws.com")
        # Provenance should have entries from cymru, rdap, peeringdb
        sources = [p["source"] for p in result.source_provenance]
        self.assertIn("cymru_dns", sources)
        self.assertIn("rdap", sources)
        self.assertIn("peeringdb", sources)

    def test_cymru_only_partial_fill(self):
        cymru_rec = asl.CymruRecord(
            ip="1.2.3.4", asn=16509, prefix=None,
            country="US", rir="arin", alloc_date=None,
        )
        chain = self._make_chain(cymru_return=cymru_rec)
        result = chain.resolve("1.2.3.4")
        self.assertEqual(result.asn, 16509)
        self.assertEqual(result.country, "US")
        self.assertIsNone(result.organization)

    def test_all_sources_fail_returns_empty_result(self):
        chain = self._make_chain()
        result = chain.resolve("1.2.3.4")
        self.assertIsNone(result.asn)
        self.assertIsNone(result.organization)
        self.assertIsNone(result.country)
        self.assertEqual(result.source_provenance, [])

    def test_geo_fields_merged(self):
        cymru_rec = asl.CymruRecord(
            ip="1.2.3.4", asn=16509, prefix=None,
            country="US", rir="arin", alloc_date=None,
        )
        geo_rec = asl.GeoRecord(
            ip="1.2.3.4", country_iso="US", country_name="United States",
            city_name="Ashburn", subdivision="Virginia",
            latitude=39.04, longitude=-77.48, asn=16509, asn_org="Amazon",
        )
        chain = self._make_chain(cymru_return=cymru_rec, geo_return=geo_rec)
        result = chain.resolve("1.2.3.4")
        self.assertEqual(result.city, "Ashburn")
        self.assertAlmostEqual(result.latitude, 39.04)
        sources = [p["source"] for p in result.source_provenance]
        self.assertIn("maxmind_geolite2", sources)

    def test_provenance_peeringdb_has_license(self):
        cymru_rec = asl.CymruRecord(
            ip="1.2.3.4", asn=13335, prefix=None,
            country="US", rir="arin", alloc_date=None,
        )
        pdb_rec = asl.PeeringDBRecord(
            asn=13335, name="CLOUDFLARENET", org_name="Cloudflare",
            info_type="Content", country="US", website=None,
        )
        chain = self._make_chain(cymru_return=cymru_rec, pdb_return=pdb_rec)
        result = chain.resolve("1.2.3.4")
        pdb_prov = next(p for p in result.source_provenance if p["source"] == "peeringdb")
        self.assertEqual(pdb_prov["license"], "CC-BY-4.0")
        self.assertIn("peeringdb.com", pdb_prov["attribution"])


# ---------------------------------------------------------------------------
# classify_target live=True integration tests
# ---------------------------------------------------------------------------

class TestClassifyTargetLive(unittest.TestCase):
    def setUp(self):
        self.tmp = TemporaryDirectory()
        self.master_path = _write_master(Path(self.tmp.name))
        self.cache_dir = Path(self.tmp.name) / "cache"
        self.cache_dir.mkdir()

    def tearDown(self):
        self.tmp.cleanup()

    def _make_live_result(self, asn=99999, org="TestOrg", as_type="isp", country="FR"):
        r = asl.LiveASNResult(
            ip="203.0.113.1",
            asn=asn,
            organization=org,
            as_type=as_type,
            country=country,
        )
        r.source_provenance.append({
            "field": "asn",
            "source": "cymru_dns",
            "source_url": "dig TXT 1.113.0.203.origin.asn.cymru.com",
            "source_sha256": "n/a",
        })
        return r

    def test_live_false_does_not_call_chain(self):
        with patch("target_context_classifier._live_enrich") as mock_enrich:
            tcc.classify_target("203.0.113.1", master_path=self.master_path, live=False)
        mock_enrich.assert_not_called()

    def test_live_true_called_for_unknown_ip(self):
        live_result = self._make_live_result()
        with patch("target_context_classifier._live_enrich", return_value=live_result):
            ctx = tcc.classify_target(
                "203.0.113.1",
                master_path=self.master_path,
                live=True,
                cache_dir=self.cache_dir,
            )
        self.assertTrue(ctx["live_enriched"])
        self.assertEqual(ctx["asn"], 99999)
        self.assertEqual(ctx["as_organization"], "TestOrg")
        self.assertEqual(ctx["country"], "FR")

    def test_live_not_called_for_bogon(self):
        with patch("target_context_classifier._live_enrich") as mock_enrich:
            ctx = tcc.classify_target(
                "10.0.5.1",
                master_path=self.master_path,
                live=True,
                cache_dir=self.cache_dir,
            )
        mock_enrich.assert_not_called()
        self.assertFalse(ctx["live_enriched"])

    def test_live_returns_none_sets_not_enriched(self):
        with patch("target_context_classifier._live_enrich", return_value=None):
            ctx = tcc.classify_target(
                "203.0.113.1",
                master_path=self.master_path,
                live=True,
                cache_dir=self.cache_dir,
            )
        self.assertFalse(ctx["live_enriched"])

    def test_live_resolves_asn_then_static_lookup_used(self):
        # Live chain resolves ASN=16509 (AWS) -> static seed should fill cloud type
        live_result = self._make_live_result(asn=16509, org=None, as_type=None, country=None)
        live_result.source_provenance = [
            {"field": "asn", "source": "cymru_dns", "source_url": "dig ...", "source_sha256": "n/a"}
        ]
        with patch("target_context_classifier._live_enrich", return_value=live_result):
            ctx = tcc.classify_target(
                "1.2.3.4",
                master_path=self.master_path,
                live=True,
                cache_dir=self.cache_dir,
            )
        self.assertTrue(ctx["live_enriched"])
        # Static seed has 16509 -> cloud
        self.assertEqual(ctx["as_type"], "cloud")
        self.assertTrue(ctx["is_cloud"])

    def test_live_false_present_in_non_live_call(self):
        ctx = tcc.classify_target("8.8.8.8", master_path=self.master_path, live=False)
        self.assertFalse(ctx["live_enriched"])

    def test_live_cdn_redetected_after_asn_resolved(self):
        # Cloudflare ASN resolved by live chain -> CDN re-detection fires
        live_result = asl.LiveASNResult(ip="1.2.3.4", asn=13335, organization="Cloudflare")
        live_result.source_provenance = []
        with patch("target_context_classifier._live_enrich", return_value=live_result):
            ctx = tcc.classify_target(
                "1.2.3.4",
                server_header="cloudflare",
                master_path=self.master_path,
                live=True,
                cache_dir=self.cache_dir,
            )
        self.assertTrue(ctx["live_enriched"])
        self.assertTrue(ctx["is_cdn"])
        self.assertEqual(ctx["cdn_provider"], "cloudflare")


# ---------------------------------------------------------------------------
# Cache atomic write test
# ---------------------------------------------------------------------------

class TestCacheAtomicWrite(unittest.TestCase):
    def test_atomic_write_and_read(self):
        tmp = TemporaryDirectory()
        cache = asl.ASNCacheMixin(cache_dir=Path(tmp.name))
        data = {"asn": 16509, "country": "US"}
        cache._cache_write("1.2.3.4", data)
        result = cache._cache_read("1.2.3.4")
        self.assertEqual(result["asn"], 16509)
        self.assertEqual(result["country"], "US")
        tmp.cleanup()

    def test_cache_invalidate(self):
        tmp = TemporaryDirectory()
        cache = asl.ASNCacheMixin(cache_dir=Path(tmp.name))
        cache._cache_write("9.9.9.9", {"asn": 1})
        self.assertIsNotNone(cache._cache_read("9.9.9.9"))
        cache._cache_invalidate("9.9.9.9")
        self.assertIsNone(cache._cache_read("9.9.9.9"))
        tmp.cleanup()

    def test_no_tmp_file_remains_after_write(self):
        tmp = TemporaryDirectory()
        cache = asl.ASNCacheMixin(cache_dir=Path(tmp.name))
        cache._cache_write("5.5.5.5", {"x": 1})
        tmp_files = list(Path(tmp.name).glob("*.tmp"))
        self.assertEqual(tmp_files, [])
        tmp.cleanup()


# ---------------------------------------------------------------------------
# DNS wire-format parser tests
# ---------------------------------------------------------------------------

class TestDNSParser(unittest.TestCase):
    def test_parse_txt_rdata_simple(self):
        # "16509 | 1.2.0.0/16" is 18 bytes, so length prefix is \x12
        payload = b"16509 | 1.2.0.0/16"
        data = bytes([len(payload)]) + payload
        result = asl.TeamCymruASNLookup._parse_txt_rdata(data)
        self.assertEqual(result, "16509 | 1.2.0.0/16")

    def test_parse_txt_rdata_multi_string(self):
        # Two character-string segments concatenated
        s1 = b"hello "
        s2 = b"world"
        rdata = bytes([len(s1)]) + s1 + bytes([len(s2)]) + s2
        result = asl.TeamCymruASNLookup._parse_txt_rdata(rdata)
        self.assertEqual(result, "hello world")

    def test_parse_txt_rdata_empty(self):
        result = asl.TeamCymruASNLookup._parse_txt_rdata(b"")
        self.assertEqual(result, "")

    def test_recv_exactly_returns_none_on_empty(self):
        mock_sock = MagicMock()
        mock_sock.recv.return_value = b""
        result = asl.TeamCymruASNLookup._recv_exactly(mock_sock, 4)
        self.assertIsNone(result)


if __name__ == "__main__":
    unittest.main(verbosity=2)
