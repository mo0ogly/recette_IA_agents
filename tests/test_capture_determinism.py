"""I4: the hook capture detection is byte-stable; ghost crosses surfaces.

The hook recording is a pure function of the captured intents (latency excluded),
so two identical captured runs yield identical surfaces. And an agent observed
only on ebpf_wire is caught there while blind on hook -- the cross-surface ghost
the multi-surface thesis must surface.
"""

from __future__ import annotations

import json
import unittest

from recette.capture.capturing_llm import CapturingLlm
from recette.capture.llm_trace import LlmCallTrace
from recette.capture.surface_bridge import recording_from_traces
from recette.llm import LlmDecision, StubLlm
from recette.surface.recording import score_recording

_SCRIPT = [
    LlmDecision(kind="tool_call", tool_name="read_repo", tool_args={"resource": "acme/x"}),
    LlmDecision(kind="tool_call", tool_name="open_pr", tool_args={"resource": "acme/x"}),
    LlmDecision(kind="final", text="done"),
]


def _capture_run() -> list[LlmCallTrace]:
    traces: list[LlmCallTrace] = []
    llm = CapturingLlm(StubLlm(list(_SCRIPT)), agent_id="a1", model="m", sink=traces.append)
    for _ in _SCRIPT:
        llm.decide(system="s", history=[], tools=[])
    return traces


class TestCaptureDeterminism(unittest.TestCase):
    def test_hook_recording_is_byte_stable(self) -> None:
        first = recording_from_traces("a1", _capture_run())
        second = recording_from_traces("a1", _capture_run())
        self.assertEqual(first.surfaces, second.surfaces)

    def test_ghost_is_caught_on_ebpf_blind_on_hook(self) -> None:
        payload = {
            "status": "ok",
            "recordings": [
                {"agent_id": "ghost", "surfaces": {"ebpf_wire": ["exec:ghost:7"]}},
            ],
        }
        card = score_recording(json.dumps(payload))
        self.assertTrue(card.ok)  # caught somewhere (eBPF backstop)
        self.assertEqual(card.detected_per_surface.get("hook_sdk", 0), 0)  # blind on hook


if __name__ == "__main__":
    unittest.main()
