"""Bridge captured tool-calls to the hook_sdk surface (deterministic detection)."""

from __future__ import annotations

import unittest

from recette.capture.llm_trace import LlmCallTrace
from recette.capture.surface_bridge import recording_from_traces
from recette.surface.surfaces import ObservationSurface


def _trace(kind: str, tool_name: str | None, resource: str, seq: int = 1) -> LlmCallTrace:
    return LlmCallTrace(
        seq=seq,
        event_id=f"LC{seq:06d}",
        agent_id="a1",
        model="m",
        kind=kind,
        tool_name=tool_name,
        resource=resource,
        prompt_tokens=0,
        completion_tokens=0,
        latency_ms=9,
        error=None,
    )


class TestSurfaceBridge(unittest.TestCase):
    def test_tool_calls_become_hook_sdk_visible(self) -> None:
        rec = recording_from_traces("a1", [_trace("tool_call", "read_repo", "acme/x")])
        self.assertEqual(rec.surfaces[ObservationSurface.HOOK_SDK], ("read_repo:acme/x",))

    def test_final_only_run_is_blind_on_hook(self) -> None:
        rec = recording_from_traces("ghost", [_trace("final", None, "")])
        self.assertNotIn(ObservationSurface.HOOK_SDK, rec.surfaces)

    def test_intents_sorted_and_deduped(self) -> None:
        rec = recording_from_traces(
            "a1",
            [
                _trace("tool_call", "open_pr", "acme/x", 1),
                _trace("tool_call", "read_repo", "acme/x", 2),
                _trace("tool_call", "open_pr", "acme/x", 3),
            ],
        )
        self.assertEqual(
            rec.surfaces[ObservationSurface.HOOK_SDK],
            ("open_pr:acme/x", "read_repo:acme/x"),
        )


if __name__ == "__main__":
    unittest.main()
