"""v1 named-wire enrichment: map a captured connect endpoint to the declared
server, flag an undeclared host. Pure (I4) -- no clock, byte-stable on replay."""

from __future__ import annotations

import unittest

from recette.surface.netmap import (
    annotate_connect,
    annotate_recording,
    build_endpoint_map,
)

SERVERS: list[dict] = [
    {"id": "gh-mock", "system": "github", "mode": "mock_local", "port": 9101},
    {"id": "okta-mock", "system": "okta", "mode": "mock_local", "port": 9102},
    {"id": "real-oai", "system": "openai", "mode": "declared_url", "url": "https://api.openai.com"},
]


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


class AnnotateSmokeTest(unittest.TestCase):
    """Minimal smoke coverage for the annotate_* exports; the full
    behavior matrix lives in Task 2's tests."""

    def test_annotate_connect_resolves_declared_and_flags_undeclared(self) -> None:
        m = build_endpoint_map(SERVERS)
        known = annotate_connect("connect:127.0.0.1:9101", m)
        self.assertEqual(known["name"], "gh-mock")
        self.assertFalse(known["undeclared"])
        ghost = annotate_connect("connect:10.0.0.5:8443", m)
        self.assertIsNone(ghost["name"])
        self.assertTrue(ghost["undeclared"])

    def test_annotate_recording_collects_undeclared_hosts(self) -> None:
        recording = {
            "recordings": [
                {
                    "agent_id": "a1",
                    "surfaces": {
                        "ebpf_wire": [
                            "connect:127.0.0.1:9101",
                            "connect:10.0.0.5:8443",
                        ]
                    },
                }
            ]
        }
        out = annotate_recording(recording, SERVERS)
        self.assertEqual(out["undeclared_hosts"], ["10.0.0.5:8443"])
        self.assertEqual(len(out["wire_named"]["a1"]), 2)
