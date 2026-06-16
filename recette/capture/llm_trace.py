"""The enriched LLM-call record (field set adapted from tensorstax/agenttrace).

One captured ``decide()`` call: the agent's INTENT (the tool it chose + resource)
plus operational metrics (tokens, latency, error). The ``intent`` derived field
matches ``recette/surface/surfaces.py::_hook_key`` (``{action_type}:{resource}``)
so a captured tool-call lines up with the hook surface key.

Determinism: tokens are read from the provider response (deterministic per
recording); ``latency_ms`` is wall-clock OPERATIONAL metadata and never enters
the detection/judge path (cf. ``maf-standard.md``).
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class LlmCallTrace:
    """One captured LLM decision: intent + operational metrics."""

    seq: int
    event_id: str
    agent_id: str
    model: str
    kind: str  # "tool_call" | "final"
    tool_name: str | None
    resource: str
    prompt_tokens: int
    completion_tokens: int
    latency_ms: int
    error: str | None

    @property
    def intent(self) -> str:
        """The hook-surface key: ``{tool_name}:{resource}`` (empty tool -> ``:``)."""
        return f"{self.tool_name or ''}:{self.resource}"

    @property
    def total_tokens(self) -> int:
        return self.prompt_tokens + self.completion_tokens

    def to_dict(self, pricing: dict[str, dict[str, float]] | None = None) -> dict:
        """Serialise the trace; add a ``cost`` field only when ``pricing`` is given.

        ``pricing`` is the config-driven table (model -> per-1k rates, see
        ``recette/capture/cost.py``). When ``None`` (the default) the output is
        byte-identical to the pre-cost shape: no ``cost`` key, so existing call
        sites are unaffected. When a table is supplied, ``cost`` is the priced
        value or ``None`` (model absent / no price known) -- never a guess.
        """
        out = {
            "seq": self.seq,
            "event_id": self.event_id,
            "agent_id": self.agent_id,
            "model": self.model,
            "kind": self.kind,
            "tool_name": self.tool_name,
            "resource": self.resource,
            "intent": self.intent,
            "prompt_tokens": self.prompt_tokens,
            "completion_tokens": self.completion_tokens,
            "total_tokens": self.total_tokens,
            "latency_ms": self.latency_ms,
            "error": self.error,
        }
        if pricing is not None:
            from .cost import cost_of

            out["cost"] = cost_of(self, pricing)
        return out
