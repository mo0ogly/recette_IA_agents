"""Gap #2: the multi-agent interaction graph + metrics are pure + deterministic."""

from __future__ import annotations

import unittest

from recette.maf_orchestration import HandoffHop, OrchestrationRun, ToolCall
from recette.orchestration_graph import interaction_graph


def _call(agent: str) -> ToolCall:
    return ToolCall(seq=0, agent_id=agent, provider="p", model="m", target="t")


_RUN = OrchestrationRun(
    hops=[
        HandoffHop(seq=1, source="triage", target="enrich"),
        HandoffHop(seq=2, source="enrich", target="notify"),
        HandoffHop(seq=3, source="triage", target="enrich"),  # repeated edge -> weight 2
    ],
    calls=[_call("triage"), _call("enrich"), _call("enrich")],
    order=["triage", "enrich", "notify"],
)


class TestInteractionGraph(unittest.TestCase):
    def test_nodes_edges_degrees(self) -> None:
        g = interaction_graph(_RUN)
        ids = [n["id"] for n in g["nodes"]]
        self.assertEqual(ids, ["enrich", "notify", "triage"])  # sorted
        triage = next(n for n in g["nodes"] if n["id"] == "triage")
        enrich = next(n for n in g["nodes"] if n["id"] == "enrich")
        self.assertEqual(triage["out_degree"], 2)  # triage->enrich twice
        self.assertEqual(triage["in_degree"], 0)
        self.assertEqual(enrich["in_degree"], 2)
        self.assertEqual(enrich["tool_calls"], 2)
        # The weighted triage->enrich edge carries weight 2.
        edge = next(e for e in g["edges"] if e["source"] == "triage")
        self.assertEqual(edge["weight"], 2)

    def test_pagerank_sums_to_one_and_sink_dominates(self) -> None:
        g = interaction_graph(_RUN)
        total = sum(n["pagerank"] for n in g["nodes"])
        self.assertAlmostEqual(total, 1.0, places=2)
        pr = {n["id"]: n["pagerank"] for n in g["nodes"]}
        # notify is the sink (everything flows toward it) -> highest rank.
        self.assertEqual(max(pr, key=lambda k: pr[k]), "notify")

    def test_deterministic(self) -> None:
        self.assertEqual(interaction_graph(_RUN), interaction_graph(_RUN))

    def test_empty_run(self) -> None:
        g = interaction_graph(OrchestrationRun())
        self.assertEqual(g["nodes"], [])
        self.assertEqual(g["edges"], [])


if __name__ == "__main__":
    unittest.main()
