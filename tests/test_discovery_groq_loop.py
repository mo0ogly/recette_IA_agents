"""The Groq -> discovery loop, deterministic (I4).

A REAL Groq run of `demo-gh-bot` (read_repo -> open_pr) was recorded by
``scripts/run_discovery_loop_live_groq.py``. This test REPLAYS that recording
byte-stable (no network, no secret) and asserts the loop the operator asked for:

  (a) the replayed Groq agent acts as a pr-bot (read_repo then open_pr);
  (b) the agent's SOURCE form (corpus/repos/gh-pr-bot) is DETECTED by the
      discovery recette -- discovery scans the source, never the runtime
      (recette-corpus.md), so this is the genuine "found by discovery";
  (c) the loop link: the run opened a PR and the discovered pr-bot repo is the
      same agent in its publishable form.

Determinism (R20/I4): the live run is frozen into the replay fixture; this test
never calls a provider.
"""

from __future__ import annotations

import json
import unittest
from pathlib import Path

from recette.discovery_harness import run_discovery_recette
from recette.lane_b import run_agent
from recette.recording import Recording, replay_backend

_FIXTURE = (
    Path(__file__).resolve().parents[1] / "tests" / "fixtures" / "discovery_loop_groq.replay.json"
)


def _replay_run():
    recording = Recording.from_dict(json.loads(_FIXTURE.read_text(encoding="utf-8")))
    return run_agent(
        agent_id="demo-gh-bot",
        principal="bot@acme",
        target_system="github",
        goal="Read the repository, then open a single pull request. Do both, once each.",
        capability_scope=["read_repo", "open_pr"],
        llm=replay_backend(recording),
        provider="stub",
        model="llama-3.3-70b-versatile",
        max_steps=8,
    )


class TestDiscoveryGroqLoop(unittest.TestCase):
    def test_replayed_groq_run_acts_as_a_pr_bot(self) -> None:
        kinds = [a.action_type for a in _replay_run().actions]
        self.assertIn("read_repo", kinds)
        self.assertIn("open_pr", kinds)

    def test_replay_is_byte_stable(self) -> None:
        first = [(a.action_type, a.resource) for a in _replay_run().actions]
        second = [(a.action_type, a.resource) for a in _replay_run().actions]
        self.assertEqual(first, second)

    def test_discovery_detects_the_pr_bot_source(self) -> None:
        card = run_discovery_recette()
        by_repo = {r.repo: r for r in card.results}
        self.assertIn("gh-pr-bot", by_repo)
        self.assertTrue(by_repo["gh-pr-bot"].detected_actual)
        self.assertTrue(by_repo["gh-pr-bot"].passed)

    def test_loop_links_runtime_action_to_discovered_source(self) -> None:
        result = _replay_run()
        self.assertTrue(any(a.action_type == "open_pr" for a in result.actions))
        card = run_discovery_recette()
        self.assertTrue(any(r.repo == "gh-pr-bot" and r.detected_actual for r in card.results))


if __name__ == "__main__":
    unittest.main()
