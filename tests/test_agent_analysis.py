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


if __name__ == "__main__":
    unittest.main()
