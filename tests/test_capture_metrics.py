"""Gap #1: operational metrics aggregation is pure + deterministic (I4)."""

from __future__ import annotations

import unittest

from recette.capture.llm_trace import LlmCallTrace
from recette.capture.metrics import _percentile, summarize_metrics


def _t(
    agent: str, tool: str | None, lat: int, pt: int, ct: int, err: str | None = None
) -> LlmCallTrace:
    return LlmCallTrace(
        seq=0,
        event_id="e",
        agent_id=agent,
        model="m",
        kind="tool_call" if tool else "final",
        tool_name=tool,
        resource="r",
        prompt_tokens=pt,
        completion_tokens=ct,
        latency_ms=lat,
        error=err,
    )


class TestPercentile(unittest.TestCase):
    def test_nearest_rank(self) -> None:
        vals = [10, 20, 30, 40, 50]
        self.assertEqual(_percentile(vals, 50), 30)
        self.assertEqual(_percentile(vals, 95), 50)
        self.assertEqual(_percentile([], 50), 0)


class TestSummarize(unittest.TestCase):
    def test_groups_by_agent_and_tool_with_metrics(self) -> None:
        traces = [
            _t("bot", "read_repo", 100, 10, 5),
            _t("bot", "read_repo", 300, 20, 5, err="boom"),
            _t("bot", "open_pr", 200, 8, 2),
        ]
        s = summarize_metrics(traces)
        self.assertEqual(s["totals"]["calls"], 3)
        self.assertEqual(s["totals"]["errors"], 1)
        self.assertEqual(s["totals"]["total_tokens"], 10 + 5 + 20 + 5 + 8 + 2)
        self.assertEqual(s["agents"]["bot"]["calls"], 3)
        self.assertEqual(s["tools"]["read_repo"]["calls"], 2)
        self.assertEqual(s["tools"]["read_repo"]["errors"], 1)
        self.assertEqual(s["tools"]["read_repo"]["error_rate"], 0.5)
        # cost None without a pricing table (never a guessed zero).
        self.assertIsNone(s["totals"]["cost_usd"])
        # Anomaly flag: read_repo at 50% errors is degraded; open_pr is ok.
        self.assertEqual(s["tools"]["read_repo"]["health"], "degraded")
        self.assertEqual(s["tools"]["open_pr"]["health"], "ok")

    def test_error_threshold_is_configurable(self) -> None:
        traces = [_t("a", "x", 5, 1, 1, err="e"), _t("a", "x", 5, 1, 1)]  # 50% errors
        self.assertEqual(summarize_metrics(traces, error_threshold=0.6)["totals"]["health"], "ok")
        self.assertEqual(
            summarize_metrics(traces, error_threshold=0.4)["totals"]["health"], "degraded"
        )

    def test_deterministic(self) -> None:
        traces = [_t("a", "x", 5, 1, 1), _t("a", "y", 9, 2, 2)]
        self.assertEqual(summarize_metrics(traces), summarize_metrics(traces))

    def test_empty(self) -> None:
        s = summarize_metrics([])
        self.assertEqual(s["totals"]["calls"], 0)
        self.assertEqual(s["agents"], {})


try:
    from fastapi.testclient import TestClient

    from recette.api.app import create_app

    _HAVE_FASTAPI = True
except ImportError:  # pragma: no cover
    _HAVE_FASTAPI = False


@unittest.skipUnless(_HAVE_FASTAPI, "fastapi not installed")
class TestMetricsRoute(unittest.TestCase):
    def test_summary_shape(self) -> None:
        body = TestClient(create_app()).get("/metrics/summary").json()
        self.assertIn("totals", body)
        self.assertIn("agents", body)
        self.assertIn("tools", body)
        self.assertEqual(body["totals"]["calls"], 0)


if __name__ == "__main__":
    unittest.main()
