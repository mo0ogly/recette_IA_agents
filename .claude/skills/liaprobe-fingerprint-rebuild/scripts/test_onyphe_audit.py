#!/usr/bin/env python3
# test_onyphe_audit.py -- Unit tests for onyphe_audit_web.
# Run: PYTHONPATH=. python3 -m unittest test_onyphe_audit -v

import unittest

import onyphe_audit_web as M


# ---------------------------------------------------------------------------
# HTTP banner parser
# ---------------------------------------------------------------------------

class ParseHttpBannerTests(unittest.TestCase):

    def test_parses_status_headers_body(self):
        banner = (
            "HTTP/1.1 200 OK\r\n"
            "Server: nginx/1.18\r\n"
            "Content-Type: text/html\r\n"
            "\r\n"
            "<html><head><title>Welcome</title></head><body>Hi</body></html>"
        )
        p = M.parse_http_banner(banner)
        self.assertEqual(p["status_code"], 200)
        self.assertEqual(p["headers"]["server"], "nginx/1.18")
        self.assertEqual(p["headers"]["content-type"], "text/html")
        self.assertIn("<html>", p["body"])
        self.assertEqual(p["title"], "Welcome")

    def test_parses_set_cookie_aggregated(self):
        banner = (
            "HTTP/1.1 200 OK\r\n"
            "Set-Cookie: PHPSESSID=abc; Path=/\r\n"
            "Set-Cookie: tracker=xyz\r\n"
            "\r\n"
            ""
        )
        p = M.parse_http_banner(banner)
        self.assertIn("PHPSESSID=abc", p["cookies"])
        self.assertIn("tracker=xyz", p["cookies"])

    def test_handles_no_body(self):
        banner = "HTTP/1.1 301 Moved Permanently\r\nLocation: /\r\nServer: AkamaiGHost\r\n\r\n"
        p = M.parse_http_banner(banner)
        self.assertEqual(p["status_code"], 301)
        self.assertEqual(p["body"], "")
        self.assertEqual(p["headers"]["server"], "AkamaiGHost")

    def test_handles_malformed_status_line(self):
        banner = "garbage data not http\r\n\r\nfoo"
        p = M.parse_http_banner(banner)
        self.assertEqual(p["status_code"], 0)
        self.assertEqual(p["body"], "foo")

    def test_handles_empty_input(self):
        p = M.parse_http_banner("")
        self.assertEqual(p["status_code"], 0)
        self.assertEqual(p["headers"], {})
        self.assertEqual(p["body"], "")

    def test_title_case_insensitive(self):
        banner = "HTTP/1.1 200 OK\r\n\r\n<TITLE>Capital</TITLE>"
        p = M.parse_http_banner(banner)
        self.assertEqual(p["title"], "Capital")


# ---------------------------------------------------------------------------
# Matcher evaluator
# ---------------------------------------------------------------------------

class EvaluateMatcherTests(unittest.TestCase):

    def setUp(self):
        self.parsed = {
            "status_code": 200,
            "headers": {"server": "nginx/1.18", "x-powered-by": "PHP/8.1"},
            "body": "<html><title>Demo</title><h1>Welcome to Demo</h1></html>",
            "cookies": "PHPSESSID=abc; demo_session=xyz",
            "title": "Demo",
        }

    def test_header_field_specific_match(self):
        self.assertTrue(M.evaluate_matcher("header", "server", "(?i)nginx", self.parsed))

    def test_header_field_no_match(self):
        self.assertFalse(M.evaluate_matcher("header", "server", "(?i)apache", self.parsed))

    def test_header_field_absent_returns_false(self):
        """Absent header must not match even with permissive regex like '.*'."""
        self.assertFalse(M.evaluate_matcher("header", "x-aem-version", ".*", self.parsed),
                         "Bug: absent header field matching '.*' creates universal false positives")

    def test_header_field_present_but_empty_value_matches_dotstar(self):
        """Present-but-empty header DOES match '.*' (intent: header presence is signal)."""
        parsed = dict(self.parsed)
        parsed["headers"] = dict(parsed["headers"])
        parsed["headers"]["x-vendor-flag"] = ""
        self.assertTrue(M.evaluate_matcher("header", "x-vendor-flag", ".*", parsed))

    def test_header_any_field_match(self):
        self.assertTrue(M.evaluate_matcher("header", "", "(?i)PHP/8", self.parsed))

    def test_body_match(self):
        self.assertTrue(M.evaluate_matcher("body", "", "Welcome to Demo", self.parsed))

    def test_body_no_match(self):
        self.assertFalse(M.evaluate_matcher("body", "", "wordpress", self.parsed))

    def test_title_match(self):
        self.assertTrue(M.evaluate_matcher("title", "", "Demo", self.parsed))

    def test_cookie_match(self):
        self.assertTrue(M.evaluate_matcher("cookie", "", "PHPSESSID", self.parsed))

    def test_invalid_regex_returns_false(self):
        self.assertFalse(M.evaluate_matcher("body", "", "[invalid", self.parsed))


# ---------------------------------------------------------------------------
# Rule evaluator
# ---------------------------------------------------------------------------

class EvaluateRuleTests(unittest.TestCase):

    def _parsed(self):
        return {
            "status_code": 200,
            "headers": {"server": "Apache/2.4"},
            "body": "<html></html>",
            "cookies": "",
            "title": "",
        }

    def test_first_matching_matcher_reports_signal_class(self):
        rule = {
            "probes": [{
                "matchers": [
                    {"target": "header", "field": "server", "match_type": "regex", "value": "(?i)apache"},
                    {"target": "body", "match_type": "regex", "value": "wordpress"},
                ]
            }]
        }
        res = M.evaluate_rule(rule, self._parsed())
        self.assertTrue(res["matched"])
        self.assertEqual(res["signal_class"], "header")

    def test_no_match(self):
        rule = {
            "probes": [{
                "matchers": [
                    {"target": "body", "match_type": "regex", "value": "drupal"},
                ]
            }]
        }
        res = M.evaluate_rule(rule, self._parsed())
        self.assertFalse(res["matched"])
        self.assertIsNone(res["signal_class"])

    def test_skips_non_regex_matchers(self):
        rule = {
            "probes": [{
                "matchers": [
                    {"target": "header", "match_type": "string", "value": "Apache"},
                    {"target": "header", "field": "server", "match_type": "regex", "value": "(?i)apache"},
                ]
            }]
        }
        res = M.evaluate_rule(rule, self._parsed())
        self.assertTrue(res["matched"])
        self.assertEqual(res["signal_class"], "header")

    def test_body_match_signal_class(self):
        rule = {
            "probes": [{
                "matchers": [
                    {"target": "body", "match_type": "regex", "value": "<html>"},
                ]
            }]
        }
        res = M.evaluate_rule(rule, self._parsed())
        self.assertTrue(res["matched"])
        self.assertEqual(res["signal_class"], "body")


# ---------------------------------------------------------------------------
# Product normalization
# ---------------------------------------------------------------------------

class NormalizeProductTests(unittest.TestCase):

    def test_lowercase_alphanum_only(self):
        self.assertEqual(M.normalize_product("Nginx"), "nginx")
        self.assertEqual(M.normalize_product("Kerio Connect"), "kerioconnect")
        self.assertEqual(M.normalize_product("AmazonS3"), "amazons3")
        self.assertEqual(M.normalize_product("Apache HTTP Server"), "apachehttpserver")

    def test_empty_string(self):
        self.assertEqual(M.normalize_product(""), "")
        self.assertEqual(M.normalize_product(None), "")

    def test_punctuation_stripped(self):
        self.assertEqual(M.normalize_product("Citrix-NetScaler"), "citrixnetscaler")
        self.assertEqual(M.normalize_product("F5/BIG-IP"), "f5bigip")


# ---------------------------------------------------------------------------
# Rule product extraction (v2 vs v1-legacy)
# ---------------------------------------------------------------------------

class ExtractRuleProductTests(unittest.TestCase):

    def test_v2_product_field(self):
        self.assertEqual(M.extract_rule_product({"product": "Nginx"}, "NGINX"), "Nginx")

    def test_v2_taxonomy_name_fallback(self):
        self.assertEqual(M.extract_rule_product({"taxonomy_name": "Apache"}, "APACHE"), "Apache")

    def test_v1_legacy_name_field(self):
        self.assertEqual(M.extract_rule_product({"name": "WordPress"}, "WP"), "WordPress")

    def test_v1_legacy_id_field(self):
        self.assertEqual(M.extract_rule_product({"id": "drupal"}, "DRUPAL"), "drupal")

    def test_filename_fallback(self):
        self.assertEqual(M.extract_rule_product({}, "FALLBACK"), "FALLBACK")


# ---------------------------------------------------------------------------
# Rule enabled detection
# ---------------------------------------------------------------------------

class IsRuleEnabledTests(unittest.TestCase):

    def test_v2_enabled_true(self):
        self.assertTrue(M.is_rule_enabled({"enabled": True}))

    def test_v2_enabled_false(self):
        self.assertFalse(M.is_rule_enabled({"enabled": False}))

    def test_v1_legacy_default_true(self):
        self.assertTrue(M.is_rule_enabled({}))


if __name__ == "__main__":
    unittest.main()
