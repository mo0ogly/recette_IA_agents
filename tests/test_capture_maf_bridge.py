"""hook_mcp / hook_sdk from a MAF run's tool invocations (deterministic)."""

from __future__ import annotations

import unittest

from recette.capture.maf_bridge import recording_from_maf_actions
from recette.maf_judge import MafAction
from recette.surface.surfaces import ObservationSurface


def _act(seq: int, action: str, target: str, tool_kind: str | None) -> MafAction:
    return MafAction(
        seq=seq,
        agent_id="m1",
        provider="groq",
        model="m",
        action=action,
        target=target,
        tool_kind=tool_kind,
    )


class TestMafBridge(unittest.TestCase):
    def test_mcp_tool_call_is_hook_mcp(self) -> None:
        rec = recording_from_maf_actions("m1", [_act(1, "invoke_tool", "weather", "mcp")])
        self.assertEqual(rec.surfaces[ObservationSurface.HOOK_MCP], ("mcp:weather",))
        self.assertNotIn(ObservationSurface.HOOK_SDK, rec.surfaces)

    def test_function_tool_call_is_hook_sdk(self) -> None:
        rec = recording_from_maf_actions("m1", [_act(1, "invoke_tool", "calc", "function")])
        self.assertEqual(rec.surfaces[ObservationSurface.HOOK_SDK], ("function:calc",))

    def test_handoff_is_not_a_hook_observation(self) -> None:
        rec = recording_from_maf_actions("m1", [_act(1, "handoff", "agent-b", None)])
        self.assertEqual(rec.surfaces, {})

    def test_sorted_and_deduped_per_surface(self) -> None:
        rec = recording_from_maf_actions(
            "m1",
            [
                _act(1, "invoke_tool", "weather", "mcp"),
                _act(2, "invoke_tool", "alerts", "mcp"),
                _act(3, "invoke_tool", "weather", "mcp"),
            ],
        )
        self.assertEqual(rec.surfaces[ObservationSurface.HOOK_MCP], ("mcp:alerts", "mcp:weather"))


if __name__ == "__main__":
    unittest.main()
