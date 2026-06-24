"""Tests the discovery's job: per-agent PLANNED vs SAID vs DONE coherence + the
logging recommendations (recette/surface/agent_analysis.py). Pure (I4).
"""

from __future__ import annotations

import json
import unittest

from recette.surface.agent_analysis import analyze_agent, analyze_recording


def _wire(*tokens: tuple[str, str, str | None, bool, str | None]) -> list[dict]:
    return [
        {"raw": raw, "kind": kind, "name": name, "undeclared": undeclared, "category": cat}
        for raw, kind, name, undeclared, cat in tokens
    ]


class TestAnalyzeAgent(unittest.TestCase):
    def test_coherent_agent(self) -> None:
        wire = _wire(("connect:127.0.0.1:9101", "connect", "github", False, None))
        r = analyze_agent(
            "good-bot",
            declared_scope=["read_repo"],
            declared_systems=["github"],
            wire_annotations=wire,
            decided_actions=["read_repo"],
        )
        self.assertTrue(r["identified"])
        self.assertTrue(r["coherent"])
        # one info rec for the legitimate wire
        self.assertTrue(all(rec["severity"] == "info" for rec in r["logging_recommendations"]))

    def test_undeclared_egress_is_alert(self) -> None:
        wire = _wire(("connect:8.8.8.8:443", "connect", None, True, None))
        r = analyze_agent(
            "leak", declared_scope=[], declared_systems=["github"], wire_annotations=wire
        )
        self.assertFalse(r["coherent"])
        top = r["logging_recommendations"][0]
        self.assertEqual(top["severity"], "alert")
        self.assertIn("8.8.8.8:443", top["log"])

    def test_undeclared_dns_is_alert(self) -> None:
        wire = _wire(("dns:evil.com", "dns", None, True, None))
        r = analyze_agent("x", declared_scope=[], declared_systems=[], wire_annotations=wire)
        self.assertEqual(r["logging_recommendations"][0]["severity"], "alert")
        self.assertEqual(r["done"]["undeclared_dns"], ["evil.com"])

    def test_said_out_of_scope_flagged(self) -> None:
        wire = _wire(("connect:127.0.0.1:9101", "connect", "github", False, None))
        r = analyze_agent(
            "drifter",
            declared_scope=["read_repo"],
            declared_systems=["github"],
            wire_annotations=wire,
            decided_actions=["read_repo", "push"],
        )
        self.assertFalse(r["coherent"])
        warns = [rec for rec in r["logging_recommendations"] if "push" in rec["log"]]
        self.assertEqual(len(warns), 1)
        self.assertEqual(warns[0]["severity"], "warn")

    def test_process_spawn_recommended(self) -> None:
        wire = _wire(("fork:99", "fork", None, False, "process"))
        r = analyze_agent("forker", declared_scope=[], declared_systems=[], wire_annotations=wire)
        self.assertTrue(r["done"]["process_spawned"])
        self.assertTrue(any("child process" in rec["log"] for rec in r["logging_recommendations"]))

    def test_credential_file_access_is_alert_and_breaks_coherence(self) -> None:
        wire = _wire(
            ("connect:127.0.0.1:9101", "connect", "gh-mock", False, None),
            ("open:/home/bot/.aws/credentials", "open", None, False, "other"),
        )
        r = analyze_agent(
            "creds",
            declared_scope=["read_repo"],
            declared_systems=["gh-mock"],
            wire_annotations=wire,
            decided_actions=["read_repo"],
        )
        self.assertFalse(r["coherent"])  # secret-material read is always anomalous
        self.assertEqual(r["done"]["credential_opens"], ["/home/bot/.aws/credentials"])
        top = r["logging_recommendations"][0]
        self.assertEqual(top["severity"], "alert")
        self.assertIn("AML.T0055", top["why"])

    def test_routine_open_stays_info(self) -> None:
        wire = _wire(("open:/etc/ssl/certs/ca.pem", "open", None, False, "etc"))
        r = analyze_agent("tls", declared_scope=[], declared_systems=[], wire_annotations=wire)
        self.assertEqual(r["done"]["credential_opens"], [])
        self.assertEqual(r["done"]["sensitive_opens"], ["/etc/ssl/certs/ca.pem"])
        self.assertTrue(all(rec["severity"] == "info" for rec in r["logging_recommendations"]))

    def test_doh_resolver_egress_is_distinct_alert(self) -> None:
        wire = _wire(("connect:8.8.8.8:443", "connect", None, True, None))
        r = analyze_agent("tunnel", declared_scope=[], declared_systems=[], wire_annotations=wire)
        self.assertEqual(r["done"]["doh_egress"], ["8.8.8.8"])
        top = r["logging_recommendations"][0]
        self.assertEqual(top["severity"], "alert")
        self.assertIn("DNS-over-HTTPS", top["why"])
        # the generic ghost-host alert is NOT also emitted for the resolver
        logs = [rec["log"] for rec in r["logging_recommendations"]]
        self.assertFalse(any("UNDECLARED host 8.8.8.8" in log for log in logs))

    def test_not_identified_when_no_surface(self) -> None:
        r = analyze_agent("ghost", declared_scope=[], declared_systems=[], wire_annotations=[])
        self.assertFalse(r["identified"])

    def test_deterministic(self) -> None:
        wire = _wire(("connect:8.8.8.8:443", "connect", None, True, None))
        a = analyze_agent("x", declared_scope=[], declared_systems=[], wire_annotations=wire)
        b = analyze_agent("x", declared_scope=[], declared_systems=[], wire_annotations=wire)
        self.assertEqual(json.dumps(a, sort_keys=True), json.dumps(b, sort_keys=True))


class TestAnalyzeRecording(unittest.TestCase):
    def test_runs_per_agent_sorted(self) -> None:
        annotated = {
            "wire_named": {
                "z-bot": _wire(("connect:127.0.0.1:9101", "connect", "github", False, None)),
                "a-bot": _wire(("connect:8.8.8.8:443", "connect", None, True, None)),
            }
        }
        declared = {
            "z-bot": {"scope": ["read_repo"], "systems": ["github"]},
            "a-bot": {"scope": [], "systems": ["github"]},
        }
        out = analyze_recording(annotated, declared_by_agent=declared)
        self.assertEqual([r["agent_id"] for r in out], ["a-bot", "z-bot"])
        self.assertFalse(out[0]["coherent"])  # a-bot leaked
        self.assertTrue(out[1]["coherent"])  # z-bot ok


class TestSaidCabling(unittest.TestCase):
    """SAID (decided actions) is cabled from a mock agent's scenario -- the
    deterministic decision script -- via declared_view (pure, no router import).
    Proves the middle column fills and that a said-out-of-scope action is caught."""

    def test_decided_from_scenario(self) -> None:
        from recette.surface.agent_analysis import decided_from_scenario

        scenario = [
            {"kind": "tool_call", "tool_name": "open_pr", "tool_args": {}},
            {"kind": "tool_call", "tool_name": "read_repo", "tool_args": {}},
            {"kind": "final", "text": "done"},
        ]
        self.assertEqual(decided_from_scenario(scenario), ["open_pr", "read_repo"])
        self.assertIsNone(decided_from_scenario(None))
        self.assertIsNone(decided_from_scenario([]))

    def test_declared_view_uses_bound_server_and_scenario(self) -> None:
        from recette.surface.agent_analysis import declared_view

        view = declared_view(
            {
                "id": "gh-bot",
                "server": "gh-mock",  # bound server id, not target_system
                "capability_scope": ["read_repo", "open_pr"],
                "scenario": [{"kind": "tool_call", "tool_name": "read_repo", "tool_args": {}}],
            }
        )
        self.assertEqual(view["systems"], ["gh-mock"])
        self.assertEqual(sorted(view["scope"]), ["open_pr", "read_repo"])
        self.assertEqual(view["decided"], ["read_repo"])

    def test_scenario_fills_said_in_scope(self) -> None:
        from recette.surface.agent_analysis import declared_view

        view = declared_view(
            {
                "id": "gh-bot",
                "server": "gh-mock",
                "capability_scope": ["read_repo", "open_pr"],
                "scenario": [
                    {"kind": "tool_call", "tool_name": "read_repo", "tool_args": {}},
                    {"kind": "tool_call", "tool_name": "open_pr", "tool_args": {}},
                ],
            }
        )
        wire = _wire(("connect:127.0.0.1:9101", "connect", "gh-mock", False, None))
        a = analyze_agent(
            "gh-bot",
            declared_scope=view["scope"],
            declared_systems=view["systems"],
            wire_annotations=wire,
            decided_actions=view["decided"],
        )
        self.assertEqual(a["said"]["actions"], ["open_pr", "read_repo"])
        self.assertTrue(a["coherent"])  # said in scope, dialed declared server

    def test_scenario_said_out_of_scope_is_divergent(self) -> None:
        from recette.surface.agent_analysis import declared_view

        view = declared_view(
            {
                "id": "rogue",
                "server": "okta-mock",
                "capability_scope": [],  # declares nothing
                "scenario": [{"kind": "tool_call", "tool_name": "delete_user", "tool_args": {}}],
            }
        )
        wire = _wire(("connect:127.0.0.1:9201", "connect", "okta-mock", False, None))
        a = analyze_agent(
            "rogue",
            declared_scope=view["scope"],
            declared_systems=view["systems"],
            wire_annotations=wire,
            decided_actions=view["decided"],
        )
        self.assertEqual(a["said"]["actions"], ["delete_user"])
        self.assertFalse(a["coherent"])  # said delete_user, scope empty
        warns = [r for r in a["logging_recommendations"] if "delete_user" in r["log"]]
        self.assertEqual(warns[0]["severity"], "warn")


if __name__ == "__main__":
    unittest.main()
