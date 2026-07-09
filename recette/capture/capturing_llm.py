"""CapturingLlm -- the in-process hook, as an LlmBackend wrapper.

Mirrors the existing wrapper idiom (``recette/llm_cache.py::CachingLlm``): it
wraps ANY ``LlmBackend`` and is transparent to the decide->act loop. On each
``decide()`` it records one ``LlmCallTrace`` (the agent's intent + operational
metrics) to an injected sink. This is agentwatch's interception mechanism adapted
to this codebase's seam -- no global monkeypatch, so it stays deterministic and
unit-testable.

Fail-safe (failure-modes.md): a sink error NEVER breaks ``decide`` -- observation
must not block execution. ``event_id`` is sequence-derived (no clock, I4);
``latency_ms`` is the one wall-clock read, kept as OPERATIONAL metadata that never
enters the detection/judge path (cf. maf-standard.md).
"""

from __future__ import annotations

import time
from collections.abc import Callable

from ..llm import LlmBackend, LlmDecision, Message, ToolSpec
from .llm_trace import LlmCallTrace
from .usage import extract_usage


class CapturingLlm:
    """Wraps a backend; records one LlmCallTrace per decision, then returns it."""

    def __init__(
        self,
        inner: LlmBackend,
        *,
        agent_id: str,
        model: str,
        sink: Callable[[LlmCallTrace], None] | None = None,
    ) -> None:
        self._inner = inner
        self._agent_id = agent_id
        self._model = model
        self._sink = sink
        self._seq = 0

    def decide(self, *, system: str, history: list[Message], tools: list[ToolSpec]) -> LlmDecision:
        start = time.perf_counter()
        decision = self._inner.decide(system=system, history=history, tools=tools)
        latency_ms = int((time.perf_counter() - start) * 1000)

        self._seq += 1
        prompt_tokens, completion_tokens = extract_usage(decision.raw)
        trace = LlmCallTrace(
            seq=self._seq,
            event_id=f"LC{self._seq:06d}",
            agent_id=self._agent_id,
            model=self._model,
            kind=decision.kind,
            tool_name=decision.tool_name,
            resource=str(decision.tool_args.get("resource", "")),
            prompt_tokens=prompt_tokens,
            completion_tokens=completion_tokens,
            latency_ms=latency_ms,
            error=None,
            rationale=decision.text,
        )
        self._emit(trace)
        return decision

    def _emit(self, trace: LlmCallTrace) -> None:
        if self._sink is None:
            return
        try:
            self._sink(trace)
        except Exception:  # noqa: BLE001 -- observation must never break the run
            # A blind hook is tolerable (eBPF is the no-cooperation backstop);
            # a hook that crashes the agent is not. Swallow and continue.
            pass
