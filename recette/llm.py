"""LB1 -- LLM backends for Lane B agents (multi-provider, offline-testable).

A Lane B agent asks an LlmBackend to decide the next step given a system prompt, the
conversation history, and the tools it is allowed to call. The backend returns an
LlmDecision: either a tool call or a final answer.

Backends:
- StubLlm   -- offline scripted decisions (deterministic; tests, fixtures, CI).
- AnthropicLlm / OpenAiLlm -- live providers over plain HTTPS JSON (stdlib client, zero
  SDK dependency). The HTTP transport is injectable, so they are unit-tested with a stub
  client -- no API key, no network. Keys come from env (R8): ANTHROPIC_API_KEY / OPENAI_API_KEY.
- OpenAiCompatLlm -- OpenAI wire format against a configurable base_url (Ollama, vLLM,
  LiteLLM proxies); API key optional for local keyless servers.

ReplayLlm (deterministic replay of a recorded run) lands with the recorder in LB4.
"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass, field
from typing import Any, Protocol, runtime_checkable

from ._http_client import StdlibHttpClient


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
    tool_name: str | None = None  # set when role == "tool"


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


# --- Anthropic ---------------------------------------------------------------------------


def _to_anthropic_messages(history: list[Message]) -> list[dict]:
    out: list[dict] = []
    for m in history:
        if m.role == "assistant":
            out.append({"role": "assistant", "content": [{"type": "text", "text": m.content}]})
        elif m.role == "tool":
            text = f"[tool {m.tool_name} result] {m.content}"
            out.append({"role": "user", "content": [{"type": "text", "text": text}]})
        else:
            out.append({"role": "user", "content": [{"type": "text", "text": m.content}]})
    return out


def _parse_anthropic(data: dict) -> LlmDecision:
    text_parts: list[str] = []
    for block in data.get("content", []):
        if not isinstance(block, dict):
            continue
        if block.get("type") == "tool_use":
            return LlmDecision(
                kind="tool_call",
                tool_name=block.get("name"),
                tool_args=block.get("input", {}) or {},
                text="".join(text_parts),
                raw=data,
            )
        if block.get("type") == "text":
            text_parts.append(block.get("text", ""))
    return LlmDecision(kind="final", text="".join(text_parts), raw=data)


class AnthropicLlm:
    BASE_URL = "https://api.anthropic.com"
    API_VERSION = "2023-06-01"

    def __init__(
        self,
        *,
        model: str,
        client: _PostClient | None = None,
        api_key: str | None = None,
        max_tokens: int = 1024,
    ) -> None:
        self._model = model
        self._max_tokens = max_tokens
        if client is None:
            key = api_key or os.environ.get("ANTHROPIC_API_KEY")
            if not key:
                raise RuntimeError("ANTHROPIC_API_KEY not set (or pass client/api_key)")
            client = StdlibHttpClient(
                self.BASE_URL,
                headers={"x-api-key": key, "anthropic-version": self.API_VERSION},
            )
        self._client = client

    def decide(self, *, system: str, history: list[Message], tools: list[ToolSpec]) -> LlmDecision:
        body = {
            "model": self._model,
            "max_tokens": self._max_tokens,
            "system": system,
            "messages": _to_anthropic_messages(history),
            "tools": [
                {"name": t.name, "description": t.description, "input_schema": t.parameters}
                for t in tools
            ],
        }
        resp = self._client.post("/v1/messages", json=body)
        resp.raise_for_status()
        return _parse_anthropic(resp.json())


# --- OpenAI ------------------------------------------------------------------------------


def _to_openai_messages(system: str, history: list[Message]) -> list[dict]:
    out: list[dict] = [{"role": "system", "content": system}]
    for m in history:
        if m.role == "assistant":
            out.append({"role": "assistant", "content": m.content})
        elif m.role == "tool":
            out.append({"role": "user", "content": f"[tool {m.tool_name} result] {m.content}"})
        else:
            out.append({"role": "user", "content": m.content})
    return out


def _parse_openai(data: dict) -> LlmDecision:
    choices = data.get("choices", [])
    if not choices:
        return LlmDecision(kind="final", text="", raw=data)
    message = choices[0].get("message", {})
    tool_calls = message.get("tool_calls") or []
    if tool_calls:
        fn = tool_calls[0].get("function", {})
        raw_args = fn.get("arguments", "{}")
        try:
            args = json.loads(raw_args) if isinstance(raw_args, str) else dict(raw_args)
        except (ValueError, TypeError):
            args = {}
        return LlmDecision(kind="tool_call", tool_name=fn.get("name"), tool_args=args, raw=data)
    return LlmDecision(kind="final", text=message.get("content") or "", raw=data)


class OpenAiLlm:
    BASE_URL = "https://api.openai.com"

    def __init__(
        self,
        *,
        model: str,
        client: _PostClient | None = None,
        api_key: str | None = None,
    ) -> None:
        self._model = model
        if client is None:
            key = api_key or os.environ.get("OPENAI_API_KEY")
            if not key:
                raise RuntimeError("OPENAI_API_KEY not set (or pass client/api_key)")
            client = StdlibHttpClient(self.BASE_URL, headers={"Authorization": f"Bearer {key}"})
        self._client = client

    def decide(self, *, system: str, history: list[Message], tools: list[ToolSpec]) -> LlmDecision:
        body = {
            "model": self._model,
            "messages": _to_openai_messages(system, history),
            "tools": [
                {
                    "type": "function",
                    "function": {
                        "name": t.name,
                        "description": t.description,
                        "parameters": t.parameters,
                    },
                }
                for t in tools
            ],
        }
        resp = self._client.post("/v1/chat/completions", json=body)
        resp.raise_for_status()
        return _parse_openai(resp.json())


class OpenAiCompatLlm(OpenAiLlm):
    """OpenAI-wire-compatible backend with a configurable base URL.

    Covers Ollama, vLLM, LiteLLM proxies. The API key is optional:
    local servers run keyless; remote ones pass api_key explicitly.
    """

    def __init__(
        self,
        *,
        model: str,
        base_url: str,
        client: _PostClient | None = None,
        api_key: str | None = None,
    ) -> None:
        if client is None:
            headers = {"Authorization": f"Bearer {api_key}"} if api_key else None
            client = StdlibHttpClient(self._normalize_base_url(base_url), headers=headers)
        # Passing a non-None client makes the parent skip its env-key requirement.
        super().__init__(model=model, client=client)

    @staticmethod
    def _normalize_base_url(base_url: str) -> str:
        """Strip trailing slashes and a trailing "/v1": request paths already start with /v1."""
        base = base_url.rstrip("/")
        if base.endswith("/v1"):
            base = base[: -len("/v1")]
        return base


# --- provider factory --------------------------------------------------------------------

_PROVIDERS = ("anthropic", "openai")


def build_llm(provider: str, model: str, *, client: _PostClient | None = None) -> LlmBackend:
    """Construct a live provider backend by name. Keys come from env (R8)."""
    if provider == "anthropic":
        return AnthropicLlm(model=model, client=client)
    if provider == "openai":
        return OpenAiLlm(model=model, client=client)
    raise ValueError(f"unknown provider {provider!r}; known: {', '.join(_PROVIDERS)}")
