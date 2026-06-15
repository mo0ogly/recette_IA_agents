"""Pace must not change the judged output (I4) and must stay out of lane_b."""

import json
import pathlib
import unittest

from recette.api import runners
from tests.test_runners import READ_THEN_FINAL, _mock_agent


def _run_collect_result(pace_ms: int) -> str:
    """Run the StubLlm-driven dashboard runner with the given pace and return the
    "result" frame's data as a byte-stable JSON string.

    Reuses the exact construction style from tests/test_runners.py: an in-memory
    LabForge agent (no server binding, no HTTP), a deterministic StubLlm, and the
    make_lane_b_runner(runner(params, emit, should_stop)) contract. ``pace_ms`` is
    supplied directly on the agent cfg, where resolve_pace reads it first.
    """
    agent = _mock_agent("a1", pace_ms=pace_ms)
    frames: list[tuple[str, dict]] = []
    runner = runners.make_lane_b_runner(agent, runners.build_stub_llm(READ_THEN_FINAL))
    runner({}, lambda kind, data: frames.append((kind, data)), lambda: False)
    result_data = next(data for kind, data in frames if kind == "result")
    return json.dumps(result_data, sort_keys=True)


class PaceDeterminismTest(unittest.TestCase):
    def test_lane_b_module_has_no_time_import(self):
        src = pathlib.Path("recette/lane_b.py").read_text()
        self.assertNotIn("import time", src)
        self.assertNotIn("time.sleep", src)

    def test_action_log_byte_identical_regardless_of_pace(self):
        original = runners.time.sleep
        runners.time.sleep = lambda s: None
        try:
            fast = _run_collect_result(pace_ms=0)
            slow = _run_collect_result(pace_ms=500)
        finally:
            runners.time.sleep = original
        self.assertEqual(fast, slow)


if __name__ == "__main__":
    unittest.main()
