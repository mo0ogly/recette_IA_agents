"""v1 named-wire enrichment: map a captured connect endpoint to the declared
server, flag an undeclared host. Pure (I4) -- no clock, byte-stable on replay."""

from __future__ import annotations

import json
import unittest

from recette.surface.netmap import (
    annotate_connect,
    annotate_recording,
    annotate_token,
    build_endpoint_map,
)

SERVERS: list[dict] = [
    {"id": "gh-mock", "system": "github", "mode": "mock_local", "port": 9101},
    {"id": "okta-mock", "system": "okta", "mode": "mock_local", "port": 9102},
    {"id": "real-oai", "system": "openai", "mode": "declared_url", "url": "https://api.openai.com"},
]


class AnnotateTokenKindsTest(unittest.TestCase):
    """#4: all surface kinds are classified, not just connect."""

    EM = {"127.0.0.1:9102": "okta-mock"}
    DNS = {"okta.acme.internal"}

    def test_connect_declared_and_undeclared(self) -> None:
        a = annotate_token("connect:127.0.0.1:9102", self.EM, self.DNS)
        self.assertEqual((a["kind"], a["name"], a["undeclared"]), ("connect", "okta-mock", False))
        b = annotate_token("connect:8.8.8.8:443", self.EM, self.DNS)
        self.assertEqual((b["kind"], b["undeclared"]), ("connect", True))

    def test_dns_known_and_exfil(self) -> None:
        ok = annotate_token("dns:okta.acme.internal", self.EM, self.DNS)
        self.assertEqual((ok["kind"], ok["undeclared"]), ("dns", False))
        # a subdomain of a declared name is allowed
        sub = annotate_token("dns:api.okta.acme.internal", self.EM, self.DNS)
        self.assertFalse(sub["undeclared"])
        bad = annotate_token("dns:evil.attacker.com", self.EM, self.DNS)
        self.assertEqual((bad["kind"], bad["undeclared"]), ("dns", True))

    def test_open_category(self) -> None:
        self.assertEqual(annotate_token("open:/usr/lib/x.so", {}, set())["category"], "sys-lib")
        self.assertEqual(
            annotate_token("open:/a/site-packages/m.py", {}, set())["category"], "venv"
        )
        self.assertEqual(annotate_token("open:/x/recette/y.py", {}, set())["category"], "repo")
        self.assertEqual(annotate_token("open:/etc/hosts", {}, set())["category"], "etc")

    def test_fork_is_process_signal(self) -> None:
        a = annotate_token("fork:1234", {}, set())
        self.assertEqual((a["kind"], a["category"]), ("fork", "process"))

    def test_unknown_kind_passes_through(self) -> None:
        a = annotate_token("weird:thing", {}, set())
        self.assertEqual((a["kind"], a["undeclared"]), ("other", False))


class AnnotateRecordingSurfacesTest(unittest.TestCase):
    """#4: recording-level signals across surfaces (dns exfil, fork, summary)."""

    def test_dns_exfil_and_fork_and_summary(self) -> None:
        servers = [
            {"id": "okta-mock", "mode": "mock_local", "port": 9102, "fqdn": "okta.acme.internal"}
        ]
        recording = {
            "recordings": [
                {
                    "agent_id": "bot",
                    "surfaces": {
                        "ebpf_wire": [
                            "connect:127.0.0.1:9102",
                            "dns:okta.acme.internal",
                            "dns:exfil.evil.com",
                            "open:/usr/lib/x.so",
                            "fork:99",
                        ]
                    },
                }
            ]
        }
        out = annotate_recording(recording, servers)
        self.assertEqual(out["undeclared_dns"], ["exfil.evil.com"])
        self.assertEqual(out["process_signals"], {"bot": 1})
        self.assertEqual(out["surface_summary"], {"connect": 1, "dns": 2, "fork": 1, "open": 1})
        # v1 contract preserved
        self.assertIn("bot", out["wire_named"])
        self.assertEqual(out["undeclared_hosts"], [])


class BuildEndpointMapTest(unittest.TestCase):
    def test_mock_local_maps_loopback_port_to_id(self) -> None:
        m = build_endpoint_map(SERVERS)
        self.assertEqual(m["127.0.0.1:9101"], "gh-mock")
        self.assertEqual(m["127.0.0.1:9102"], "okta-mock")

    def test_declared_url_maps_host_default_https_port(self) -> None:
        m = build_endpoint_map(SERVERS)
        self.assertEqual(m["api.openai.com:443"], "real-oai")

    def test_empty_registry_is_empty_map(self) -> None:
        self.assertEqual(build_endpoint_map([]), {})

    def test_mock_local_without_port_is_skipped(self) -> None:
        self.assertEqual(build_endpoint_map([{"id": "x", "mode": "mock_local"}]), {})

    def test_declared_url_with_explicit_port(self) -> None:
        servers: list[dict] = [
            {"id": "x", "mode": "declared_url", "url": "https://api.example.com:8443"}
        ]
        self.assertEqual(build_endpoint_map(servers)["api.example.com:8443"], "x")

    def test_declared_url_without_url_is_skipped(self) -> None:
        self.assertEqual(build_endpoint_map([{"id": "x", "mode": "declared_url"}]), {})

    def test_server_without_id_is_skipped(self) -> None:
        self.assertEqual(build_endpoint_map([{"mode": "mock_local", "port": 9101}]), {})


class AnnotateConnectTest(unittest.TestCase):
    def test_known_endpoint_resolves_to_declared_name(self) -> None:
        m = build_endpoint_map(SERVERS)
        self.assertEqual(
            annotate_connect("connect:127.0.0.1:9101", m),
            {"raw": "connect:127.0.0.1:9101", "name": "gh-mock", "undeclared": False},
        )

    def test_unknown_endpoint_is_flagged_undeclared(self) -> None:
        m = build_endpoint_map(SERVERS)
        self.assertEqual(
            annotate_connect("connect:203.0.113.7:443", m),
            {"raw": "connect:203.0.113.7:443", "name": None, "undeclared": True},
        )

    def test_non_connect_token_passes_through_unflagged(self) -> None:
        m = build_endpoint_map(SERVERS)
        self.assertEqual(
            annotate_connect("exec:dx-live-bot:42", m),
            {"raw": "exec:dx-live-bot:42", "name": None, "undeclared": False},
        )


class AnnotateRecordingTest(unittest.TestCase):
    def _recording(self) -> dict:
        # Two agents in non-sorted order to also exercise stable output (I4).
        return {
            "recordings": [
                {
                    "agent_id": "dx-live-bot",
                    "surfaces": {"ebpf_wire": ["connect:127.0.0.1:9101"]},
                },
                {
                    "agent_id": "leak-bot",
                    "surfaces": {"ebpf_wire": ["connect:203.0.113.7:443"]},
                },
            ]
        }

    def test_groups_named_endpoints_per_agent_and_lists_undeclared(self) -> None:
        out = annotate_recording(self._recording(), SERVERS)
        self.assertEqual(out["wire_named"]["dx-live-bot"][0]["name"], "gh-mock")
        self.assertIs(out["wire_named"]["leak-bot"][0]["undeclared"], True)
        self.assertEqual(out["undeclared_hosts"], ["203.0.113.7:443"])

    def test_replay_is_byte_stable(self) -> None:
        rec = self._recording()
        first = json.dumps(annotate_recording(rec, SERVERS), sort_keys=True)
        second = json.dumps(annotate_recording(rec, SERVERS), sort_keys=True)
        self.assertEqual(first, second)

    def test_skipped_recording_is_empty_annotation(self) -> None:
        # The v1 contract keys stay present + empty; the #4 additive keys
        # (undeclared_dns / process_signals / surface_summary) are empty too.
        self.assertEqual(
            annotate_recording({"status": "skipped", "recordings": []}, SERVERS),
            {
                "wire_named": {},
                "undeclared_hosts": [],
                "undeclared_dns": [],
                "process_signals": {},
                "surface_summary": {},
            },
        )
