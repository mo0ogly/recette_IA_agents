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
- GroqLlm -- Groq cloud, OpenAI wire format at api.groq.com. Key: GROQ_API_KEY.
- MistralLlm -- Mistral cloud, OpenAI wire format at api.mistral.ai. Key: MISTRAL_API_KEY.
- DeepSeekLlm -- DeepSeek cloud, OpenAI wire format at api.deepseek.com. Key: DEEPSEEK_API_KEY.
- XaiLlm -- xAI cloud, OpenAI wire format at api.x.ai. Key: XAI_API_KEY.
- GeminiLlm -- Google Gemini generateContent wire format. Key: GEMINI_API_KEY.

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


# --- OpenAI-wire cloud vendors -----------------------------------------------------------


class _OpenAiWireVendor(OpenAiLlm):
    """Shared base for cloud vendors that speak the OpenAI wire format verbatim.

    A concrete vendor only declares two class attributes:
    - BASE_URL: the vendor host (request paths already start with /v1).
    - ENV_KEY: the environment variable holding the bearer key (R8).

    The shared __init__ reads the key from api_key or that env var (unless a client is
    injected, e.g. in tests), builds an Authorization-Bearer client, and defers wire
    handling to OpenAiLlm. Any other OpenAI-compatible vendor is covered by the
    "openai_compat" provider + base_url instead.
    """

    BASE_URL: str
    ENV_KEY: str

    def __init__(
        self, *, model: str, client: _PostClient | None = None, api_key: str | None = None
    ) -> None:
        if client is None:
            env_key = type(self).ENV_KEY
            key = api_key or os.environ.get(env_key)
            if not key:
                raise RuntimeError(f"{env_key} not set (or pass client/api_key)")
            client = StdlibHttpClient(
                type(self).BASE_URL, headers={"Authorization": f"Bearer {key}"}
            )
        # Passing a non-None client makes the parent skip its env-key requirement.
        super().__init__(model=model, client=client)


class GroqLlm(_OpenAiWireVendor):
    """Groq cloud backend -- OpenAI wire format at api.groq.com. Key: GROQ_API_KEY."""

    BASE_URL = "https://api.groq.com/openai"
    ENV_KEY = "GROQ_API_KEY"


class MistralLlm(_OpenAiWireVendor):
    """Mistral cloud backend -- OpenAI wire format at api.mistral.ai. Key: MISTRAL_API_KEY."""

    BASE_URL = "https://api.mistral.ai"
    ENV_KEY = "MISTRAL_API_KEY"


class DeepSeekLlm(_OpenAiWireVendor):
    """DeepSeek cloud backend -- OpenAI wire at api.deepseek.com. Key: DEEPSEEK_API_KEY."""

    BASE_URL = "https://api.deepseek.com"
    ENV_KEY = "DEEPSEEK_API_KEY"


class XaiLlm(_OpenAiWireVendor):
    """xAI cloud backend -- OpenAI wire format at api.x.ai. Key: XAI_API_KEY."""

    BASE_URL = "https://api.x.ai"
    ENV_KEY = "XAI_API_KEY"


class OpenRouterLlm(_OpenAiWireVendor):
    """OpenRouter aggregator -- OpenAI wire at openrouter.ai/api. Key: OPENROUTER_API_KEY.

    BASE_URL has no trailing /v1: request paths already start with /v1, so the
    effective endpoint is /api/v1/chat/completions.
    """

    BASE_URL = "https://openrouter.ai/api"
    ENV_KEY = "OPENROUTER_API_KEY"


class TogetherLlm(_OpenAiWireVendor):
    """Together AI -- OpenAI wire at api.together.xyz. Key: TOGETHER_API_KEY."""

    BASE_URL = "https://api.together.xyz"
    ENV_KEY = "TOGETHER_API_KEY"


class FireworksLlm(_OpenAiWireVendor):
    """Fireworks AI -- OpenAI wire at api.fireworks.ai/inference. Key: FIREWORKS_API_KEY.

    The /v1 in request paths yields the effective /inference/v1/chat/completions.
    """

    BASE_URL = "https://api.fireworks.ai/inference"
    ENV_KEY = "FIREWORKS_API_KEY"


# --- Gemini ------------------------------------------------------------------------------


def _to_gemini_contents(history: list[Message]) -> list[dict]:
    out: list[dict] = []
    for m in history:
        if m.role == "assistant":
            out.append({"role": "model", "parts": [{"text": m.content}]})
        elif m.role == "tool":
            text = f"[tool {m.tool_name} result] {m.content}"
            out.append({"role": "user", "parts": [{"text": text}]})
        else:
            out.append({"role": "user", "parts": [{"text": m.content}]})
    return out


def _parse_gemini(data: dict) -> LlmDecision:
    candidates = data.get("candidates") or []
    if not candidates:
        return LlmDecision(kind="final", text="", raw=data)
    parts = (candidates[0].get("content") or {}).get("parts") or []
    text_parts: list[str] = []
    for part in parts:
        if not isinstance(part, dict):
            continue
        call = part.get("functionCall")
        if call:
            return LlmDecision(
                kind="tool_call",
                tool_name=call.get("name"),
                tool_args=call.get("args", {}) or {},
                text="".join(text_parts),
                raw=data,
            )
        if "text" in part:
            text_parts.append(part.get("text", ""))
    return LlmDecision(kind="final", text="".join(text_parts), raw=data)


class GeminiLlm:
    """Google Gemini backend -- generateContent wire format. Key: GEMINI_API_KEY."""

    BASE_URL = "https://generativelanguage.googleapis.com"

    def __init__(
        self, *, model: str, client: _PostClient | None = None, api_key: str | None = None
    ) -> None:
        self._model = model
        if client is None:
            key = api_key or os.environ.get("GEMINI_API_KEY")
            if not key:
                raise RuntimeError("GEMINI_API_KEY not set (or pass client/api_key)")
            client = StdlibHttpClient(self.BASE_URL, headers={"x-goog-api-key": key})
        self._client = client

    def decide(self, *, system: str, history: list[Message], tools: list[ToolSpec]) -> LlmDecision:
        body: dict = {
            "system_instruction": {"parts": [{"text": system}]},
            "contents": _to_gemini_contents(history),
        }
        if tools:
            body["tools"] = [
                {
                    "functionDeclarations": [
                        {"name": t.name, "description": t.description, "parameters": t.parameters}
                        for t in tools
                    ]
                }
            ]
        resp = self._client.post(f"/v1beta/models/{self._model}:generateContent", json=body)
        resp.raise_for_status()
        return _parse_gemini(resp.json())


# --- provider factory --------------------------------------------------------------------

_PROVIDERS = (
    "anthropic",
    "openai",
    "gemini",
    "groq",
    "mistral",
    "deepseek",
    "xai",
    "openrouter",
    "together",
    "fireworks",
    "openai_compat",
)


def build_llm(
    provider: str,
    model: str,
    *,
    client: _PostClient | None = None,
    base_url: str | None = None,
    api_key: str | None = None,
) -> LlmBackend:
    """Construct a live provider backend by name.

    Key resolution (R8): an explicit api_key wins (per-backend secret store);
    otherwise the provider reads its env var fallback. The key is never logged.
    base_url is required for (and only used by) the "openai_compat" provider.
    """
    if provider == "anthropic":
        return AnthropicLlm(model=model, client=client, api_key=api_key)
    if provider == "openai":
        return OpenAiLlm(model=model, client=client, api_key=api_key)
    if provider == "gemini":
        return GeminiLlm(model=model, client=client, api_key=api_key)
    if provider == "groq":
        return GroqLlm(model=model, client=client, api_key=api_key)
    if provider == "mistral":
        return MistralLlm(model=model, client=client, api_key=api_key)
    if provider == "deepseek":
        return DeepSeekLlm(model=model, client=client, api_key=api_key)
    if provider == "xai":
        return XaiLlm(model=model, client=client, api_key=api_key)
    if provider == "openrouter":
        return OpenRouterLlm(model=model, client=client, api_key=api_key)
    if provider == "together":
        return TogetherLlm(model=model, client=client, api_key=api_key)
    if provider == "fireworks":
        return FireworksLlm(model=model, client=client, api_key=api_key)
    if provider == "openai_compat":
        if not base_url and client is None:
            raise ValueError("openai_compat requires base_url")
        return OpenAiCompatLlm(
            model=model, base_url=base_url or "", client=client, api_key=api_key
        )
    raise ValueError(f"unknown provider {provider!r}; known: {', '.join(_PROVIDERS)}")
