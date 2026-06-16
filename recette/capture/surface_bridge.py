"""Bridge captured LLM traces -> the hook_sdk surface recording.

Turns a run's ``LlmCallTrace`` list into the same ``CaptureRecording`` the surface
judge consumes (``recette/surface/recording.py``), so a HOOK capture is scored by
the exact same deterministic detector as an eBPF capture -- one judge, one model.

Only tool-call intents are observable on the hook surface: a pure thought / final
answer reveals no ACTION, so an agent that only ``final``s is seen nowhere on the
hook (it may still be caught on ``ebpf_wire`` -- the ghost case). Operational
metrics (tokens, latency) are intentionally NOT in the recording: detection is a
pure function of the intents (I4); the metrics live only on the trace.
"""

from __future__ import annotations

from collections.abc import Iterable

from ..surface.recording import CaptureRecording
from ..surface.surfaces import ObservationSurface
from .llm_trace import LlmCallTrace


def recording_from_traces(agent_id: str, traces: Iterable[LlmCallTrace]) -> CaptureRecording:
    """Build a hook_sdk CaptureRecording from captured tool-call intents."""
    surfaces: dict[ObservationSurface, tuple[str, ...]] = {}
    keys = sorted({t.intent for t in traces if t.kind == "tool_call" and t.tool_name})
    if keys:
        surfaces[ObservationSurface.HOOK_SDK] = tuple(keys)
    return CaptureRecording(agent_id=agent_id, surfaces=surfaces)
