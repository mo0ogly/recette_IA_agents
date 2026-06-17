"""Core LLM types shared by every wire backend (Lane B, LB1).

A Lane B agent asks an LlmBackend to decide the next step given a system prompt,
the conversation history, and the tools it may call. The backend returns an
LlmDecision: either a tool call or a final answer. This module holds the neutral
types plus the offline scripted backends (StubLlm/ReplayLlm); the live providers
live in the per-wire modules (anthropic_wire, openai_wire, gemini_wire,
bedrock_wire) and are assembled by the registry.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Protocol, runtime_checkable


@dataclass(frozen=True)
class ToolSpec:
    """A tool the agent may call -- one canonical action, with a JSON-Schema arg shape."""

    name: str
    description: str
    parameters: dict


@dataclass(frozen=True)
class Message:
    role: str  # "user" | "assistant" | "tool"
    content: str
    tool_name: str | None = None  # set when role == "tool" or an assistant tool call
    # Structured tool-call round-trip (OpenAI/Groq wire): an assistant turn that
    # called a tool carries its args + a deterministic call id; the matching tool
    # result turn carries the same id. Free-text history confuses tool-calling
    # models (they imitate it and emit malformed function names), so the wire
    # format MUST send real tool_calls/tool messages, not prose.
    tool_args: dict | None = None
    tool_call_id: str | None = None


@dataclass(frozen=True)
class LlmDecision:
    kind: str  # "tool_call" | "final"
    text: str = ""
    tool_name: str | None = None
    tool_args: dict = field(default_factory=dict)
    raw: dict = field(default_factory=dict)  # provider raw response, captured for recording

    @property
    def is_tool_call(self) -> bool:
        return self.kind == "tool_call"


@runtime_checkable
class LlmBackend(Protocol):
    def decide(
        self, *, system: str, history: list[Message], tools: list[ToolSpec]
    ) -> LlmDecision: ...


# --- HTTP transport shape (matches recette._http_client.StdlibHttpClient) ---------------


class _Response(Protocol):
    def raise_for_status(self) -> None: ...
    def json(self) -> Any: ...


class _PostClient(Protocol):
    def post(self, path: str, json: dict | None = ...) -> _Response: ...


# --- offline scripted backend -----------------------------------------------------------


class StubLlm:
    """Returns pre-set decisions in order; a final no-op once exhausted. Deterministic."""

    def __init__(self, decisions: list[LlmDecision]) -> None:
        self._decisions = list(decisions)
        self._i = 0

    def decide(self, *, system: str, history: list[Message], tools: list[ToolSpec]) -> LlmDecision:
        if self._i >= len(self._decisions):
            return LlmDecision(kind="final", text="(no more scripted steps)")
        decision = self._decisions[self._i]
        self._i += 1
        return decision


class ReplayLlm(StubLlm):
    """Deterministic replay of decisions recorded from a previous run (LB4)."""
