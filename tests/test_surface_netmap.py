"""v1 named-wire enrichment: map a captured connect endpoint to the declared
server, flag an undeclared host. Pure (I4) -- no clock, byte-stable on replay."""

from __future__ import annotations

import json
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
        self.assertEqual(
            annotate_recording({"status": "skipped", "recordings": []}, SERVERS),
            {"wire_named": {}, "undeclared_hosts": []},
        )
