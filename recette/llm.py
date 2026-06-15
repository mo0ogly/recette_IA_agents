"""LB1 -- LLM backends for Lane B agents (multi-provider, offline-testable).

A Lane B agent asks an LlmBackend to decide the next step given a system prompt, the
conversation history, and the tools it is allowed to call. The backend returns an
LlmDecision: either a tool call or a final answer.

Backends:
- StubLlm   -- offline scripted decisions (deterministic; tests, fixtures, CI).
- MinimaxLlm -- Anthropic Messages wire (api.minimax.io/anthropic) with a bearer
  auth header. Key: MINIMAX_API_KEY.
- BedrockLlm -- AWS Bedrock Converse wire with a Bedrock API key (bearer), no SDK
  / SigV4. Key: AWS_BEARER_TOKEN_BEDROCK. Region via base_url (default us-east-1).
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
- MoonshotLlm / ZaiLlm / DashscopeLlm / NvidiaLlm / NousLlm / OllamaCloudLlm /
  NovitaLlm / StepfunLlm / ArceeLlm / XiaomiLlm / GmiLlm / HuggingFaceLlm --
  additional OpenAI-wire cloud vendors whose BASE_URL already carries the API
  version segment (see _VersionedWireVendor). Keys: KIMI_API_KEY, GLM_API_KEY,
  DASHSCOPE_API_KEY, NVIDIA_API_KEY, NOUS_API_KEY, OLLAMA_API_KEY, NOVITA_API_KEY,
  STEPFUN_API_KEY, ARCEEAI_API_KEY, XIAOMI_API_KEY, GMI_API_KEY, HF_TOKEN.

ReplayLlm (deterministic replay of a recorded run) lands with the recorder in LB4.
"""

from __future__ import annotations

import json
import os
import urllib.parse
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
    ENV_KEY = "ANTHROPIC_API_KEY"

    @classmethod
    def _auth_headers(cls, key: str) -> dict:
        """Anthropic native auth: x-api-key plus the dated anthropic-version.

        Subclasses targeting an Anthropic-compatible endpoint with a different
        auth scheme override this (e.g. a bearer Authorization header).
        """
        return {"x-api-key": key, "anthropic-version": cls.API_VERSION}

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
            env_key = type(self).ENV_KEY
            key = api_key or os.environ.get(env_key)
            if not key:
                raise RuntimeError(f"{env_key} not set (or pass client/api_key)")
            client = StdlibHttpClient(type(self).BASE_URL, headers=type(self)._auth_headers(key))
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


class MinimaxLlm(AnthropicLlm):
    """MiniMax -- Anthropic Messages wire at api.minimax.io/anthropic. Key: MINIMAX_API_KEY.

    MiniMax exposes an Anthropic-compatible endpoint (Messages API, dated
    anthropic-version), so it reuses the Anthropic request/response shape and the
    /v1/messages path (effective /anthropic/v1/messages). It differs in auth: the
    key travels in a bearer Authorization header, not Anthropic's x-api-key.
    """

    BASE_URL = "https://api.minimax.io/anthropic"
    ENV_KEY = "MINIMAX_API_KEY"

    @classmethod
    def _auth_headers(cls, key: str) -> dict:
        return {"Authorization": f"Bearer {key}", "anthropic-version": cls.API_VERSION}


class MinimaxCnLlm(MinimaxLlm):
    """MiniMax China -- Anthropic Messages wire at api.minimaxi.com. Key: MINIMAX_CN_API_KEY.

    Same bearer-auth Anthropic-compatible shape as MinimaxLlm, against the China
    host (api.minimaxi.com) with a distinct key.
    """

    BASE_URL = "https://api.minimaxi.com/anthropic"
    ENV_KEY = "MINIMAX_CN_API_KEY"


# --- OpenAI ------------------------------------------------------------------------------


def _to_openai_messages(system: str, history: list[Message]) -> list[dict]:
    out: list[dict] = [{"role": "system", "content": system}]
    for m in history:
        if m.role == "assistant" and m.tool_name:
            # Real assistant tool call: emit a structured tool_calls block so the
            # model sees its own prior call in the protocol shape, not as prose.
            out.append(
                {
                    "role": "assistant",
                    "content": m.content or None,
                    "tool_calls": [
                        {
                            "id": m.tool_call_id or "call_0",
                            "type": "function",
                            "function": {
                                "name": m.tool_name,
                                "arguments": json.dumps(m.tool_args or {}, sort_keys=True),
                            },
                        }
                    ],
                }
            )
        elif m.role == "assistant":
            out.append({"role": "assistant", "content": m.content})
        elif m.role == "tool":
            out.append(
                {
                    "role": "tool",
                    "tool_call_id": m.tool_call_id or "call_0",
                    "content": m.content,
                }
            )
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
    # Request path for chat completions. Most OpenAI-wire vendors expose it under
    # /v1; a few (Novita, Perplexity) drop the /v1 segment, so a vendor subclass
    # overrides this attribute instead of duplicating decide().
    CHAT_PATH = "/v1/chat/completions"

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
        resp = self._client.post(type(self).CHAT_PATH, json=body)
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


class _VersionedWireVendor(_OpenAiWireVendor):
    """OpenAI-wire vendor whose BASE_URL already carries the API version segment.

    Unlike the vendors above (BASE_URL is the bare host, request path appends
    /v1/chat/completions), these declare a BASE_URL that already ends in its
    version path (e.g. /v1, /api/paas/v4, /compatible-mode/v1, /openai/v1), so
    the request path is just /chat/completions. BASE_URL and ENV_KEY are the
    exact endpoint and primary key env var documented by each provider.
    """

    CHAT_PATH = "/chat/completions"


class MoonshotLlm(_VersionedWireVendor):
    """Moonshot / Kimi -- OpenAI wire at api.moonshot.ai/v1. Key: KIMI_API_KEY."""

    BASE_URL = "https://api.moonshot.ai/v1"
    ENV_KEY = "KIMI_API_KEY"


class ZaiLlm(_VersionedWireVendor):
    """Z.AI / GLM -- OpenAI wire at api.z.ai/api/paas/v4. Key: GLM_API_KEY."""

    BASE_URL = "https://api.z.ai/api/paas/v4"
    ENV_KEY = "GLM_API_KEY"


class DashscopeLlm(_VersionedWireVendor):
    """Alibaba DashScope / Qwen -- OpenAI compatible-mode. Key: DASHSCOPE_API_KEY."""

    BASE_URL = "https://dashscope-intl.aliyuncs.com/compatible-mode/v1"
    ENV_KEY = "DASHSCOPE_API_KEY"


class NvidiaLlm(_VersionedWireVendor):
    """NVIDIA NIM -- OpenAI wire at integrate.api.nvidia.com/v1. Key: NVIDIA_API_KEY."""

    BASE_URL = "https://integrate.api.nvidia.com/v1"
    ENV_KEY = "NVIDIA_API_KEY"


class NousLlm(_VersionedWireVendor):
    """Nous Portal inference -- OpenAI wire. Key: NOUS_API_KEY."""

    BASE_URL = "https://inference.nousresearch.com/v1"
    ENV_KEY = "NOUS_API_KEY"


class OllamaCloudLlm(_VersionedWireVendor):
    """Ollama Cloud -- OpenAI wire at ollama.com/v1. Key: OLLAMA_API_KEY.

    For a local keyless Ollama server, use the "openai_compat" provider with a
    base_url instead; this vendor targets the hosted cloud endpoint.
    """

    BASE_URL = "https://ollama.com/v1"
    ENV_KEY = "OLLAMA_API_KEY"


class NovitaLlm(_VersionedWireVendor):
    """Novita AI -- OpenAI wire at api.novita.ai/openai/v1. Key: NOVITA_API_KEY."""

    BASE_URL = "https://api.novita.ai/openai/v1"
    ENV_KEY = "NOVITA_API_KEY"


class StepfunLlm(_VersionedWireVendor):
    """StepFun -- OpenAI wire at api.stepfun.ai/step_plan/v1. Key: STEPFUN_API_KEY."""

    BASE_URL = "https://api.stepfun.ai/step_plan/v1"
    ENV_KEY = "STEPFUN_API_KEY"


class ArceeLlm(_VersionedWireVendor):
    """Arcee -- OpenAI wire at api.arcee.ai/api/v1. Key: ARCEEAI_API_KEY."""

    BASE_URL = "https://api.arcee.ai/api/v1"
    ENV_KEY = "ARCEEAI_API_KEY"


class XiaomiLlm(_VersionedWireVendor):
    """Xiaomi MiMo -- OpenAI wire at api.xiaomimimo.com/v1. Key: XIAOMI_API_KEY."""

    BASE_URL = "https://api.xiaomimimo.com/v1"
    ENV_KEY = "XIAOMI_API_KEY"


class GmiLlm(_VersionedWireVendor):
    """GMI Cloud -- OpenAI wire at api.gmi-serving.com/v1. Key: GMI_API_KEY."""

    BASE_URL = "https://api.gmi-serving.com/v1"
    ENV_KEY = "GMI_API_KEY"


class HuggingFaceLlm(_VersionedWireVendor):
    """Hugging Face inference router -- OpenAI wire at router.huggingface.co/v1. Key: HF_TOKEN."""

    BASE_URL = "https://router.huggingface.co/v1"
    ENV_KEY = "HF_TOKEN"


class OpencodeZenLlm(_VersionedWireVendor):
    """OpenCode Zen -- OpenAI wire at opencode.ai/zen/v1. Key: OPENCODE_ZEN_API_KEY.

    Zen routes by model: Claude models would use the Anthropic wire and GPT-5/Codex
    a Responses wire. This binding covers the chat_completions default (every other
    model); pin a non-Claude, non-Codex model on the backend.
    """

    BASE_URL = "https://opencode.ai/zen/v1"
    ENV_KEY = "OPENCODE_ZEN_API_KEY"


class KilocodeLlm(_VersionedWireVendor):
    """Kilo AI Gateway -- OpenAI wire at api.kilo.ai/api/gateway. Key: KILOCODE_API_KEY.

    The gateway exposes a standard OpenAI /chat/completions interface; the base_url
    carries no version segment, so the effective endpoint is
    api.kilo.ai/api/gateway/chat/completions. The optional X-KILOCODE-ORGANIZATIONID
    header is not set here; bearer auth alone is enough for a single-org key.
    """

    BASE_URL = "https://api.kilo.ai/api/gateway"
    ENV_KEY = "KILOCODE_API_KEY"


class AlibabaCodingPlanLlm(_VersionedWireVendor):
    """Alibaba Cloud Coding Plan -- OpenAI wire. Key: ALIBABA_CODING_PLAN_API_KEY."""

    BASE_URL = "https://coding-intl.dashscope.aliyuncs.com/v1"
    ENV_KEY = "ALIBABA_CODING_PLAN_API_KEY"


class QwenLlm(_VersionedWireVendor):
    """Qwen Portal -- OpenAI wire at portal.qwen.ai/v1. Key: QWEN_API_KEY.

    The portal authenticates with an OAuth access token; paste that token as the
    backend key (it travels as the bearer Authorization header, stored write-only
    in the per-backend secret store). The operator refreshes it when it expires.
    """

    BASE_URL = "https://portal.qwen.ai/v1"
    ENV_KEY = "QWEN_API_KEY"


class CerebrasLlm(_VersionedWireVendor):
    """Cerebras inference -- OpenAI wire at api.cerebras.ai/v1. Key: CEREBRAS_API_KEY."""

    BASE_URL = "https://api.cerebras.ai/v1"
    ENV_KEY = "CEREBRAS_API_KEY"


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


# --- AWS Bedrock (Converse) --------------------------------------------------------------


def _to_converse_messages(history: list[Message]) -> list[dict]:
    """Map the neutral history to Bedrock Converse message blocks.

    Tool results are folded into a text user turn (same simplification as the
    Anthropic mapping) so the wire stays free of toolUseId bookkeeping.
    """
    out: list[dict] = []
    for m in history:
        if m.role == "assistant":
            out.append({"role": "assistant", "content": [{"text": m.content}]})
        elif m.role == "tool":
            text = f"[tool {m.tool_name} result] {m.content}"
            out.append({"role": "user", "content": [{"text": text}]})
        else:
            out.append({"role": "user", "content": [{"text": m.content}]})
    return out


def _parse_converse(data: dict) -> LlmDecision:
    blocks = ((data.get("output") or {}).get("message") or {}).get("content") or []
    text_parts: list[str] = []
    for block in blocks:
        if not isinstance(block, dict):
            continue
        use = block.get("toolUse")
        if use:
            return LlmDecision(
                kind="tool_call",
                tool_name=use.get("name"),
                tool_args=use.get("input", {}) or {},
                text="".join(text_parts),
                raw=data,
            )
        if "text" in block:
            text_parts.append(block.get("text", ""))
    return LlmDecision(kind="final", text="".join(text_parts), raw=data)


class BedrockLlm:
    """AWS Bedrock backend over the Converse API. Key: AWS_BEARER_TOKEN_BEDROCK.

    Uses a Bedrock API key (bearer Authorization header) against the region
    runtime host, so no AWS SDK / SigV4 signing is needed. The default region is
    us-east-1; pass base_url to target another region's bedrock-runtime host. The
    model id is URL-encoded into the /model/{id}/converse path (model ids carry a
    colon, e.g. anthropic.claude-3-5-sonnet-20240620-v1:0).
    """

    BASE_URL = "https://bedrock-runtime.us-east-1.amazonaws.com"
    ENV_KEY = "AWS_BEARER_TOKEN_BEDROCK"

    def __init__(
        self,
        *,
        model: str,
        client: _PostClient | None = None,
        base_url: str | None = None,
        api_key: str | None = None,
        max_tokens: int = 1024,
    ) -> None:
        self._model = model
        self._max_tokens = max_tokens
        if client is None:
            key = api_key or os.environ.get(self.ENV_KEY)
            if not key:
                raise RuntimeError(f"{self.ENV_KEY} not set (or pass client/api_key)")
            client = StdlibHttpClient(
                base_url or self.BASE_URL, headers={"Authorization": f"Bearer {key}"}
            )
        self._client = client

    def decide(self, *, system: str, history: list[Message], tools: list[ToolSpec]) -> LlmDecision:
        body: dict = {
            "messages": _to_converse_messages(history),
            "inferenceConfig": {"maxTokens": self._max_tokens},
        }
        if system:
            body["system"] = [{"text": system}]
        if tools:
            body["toolConfig"] = {
                "tools": [
                    {
                        "toolSpec": {
                            "name": t.name,
                            "description": t.description,
                            "inputSchema": {"json": t.parameters},
                        }
                    }
                    for t in tools
                ]
            }
        path = f"/model/{urllib.parse.quote(self._model, safe='')}/converse"
        resp = self._client.post(path, json=body)
        resp.raise_for_status()
        return _parse_converse(resp.json())


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
    "moonshot",
    "zai",
    "dashscope",
    "nvidia",
    "nous",
    "ollama_cloud",
    "novita",
    "stepfun",
    "arcee",
    "xiaomi",
    "gmi",
    "huggingface",
    "minimax",
    "minimax_cn",
    "opencode_zen",
    "kilocode",
    "alibaba_coding_plan",
    "qwen",
    "cerebras",
    "bedrock",
    "openai_compat",
)

# Provider id -> backend class, so the target HOST of a provider can be derived
# from its class BASE_URL without instantiating it (used by the reconcile
# allowlist so a real-mode LLM call is not mistaken for an unmediated path). The
# drift guard test asserts this covers exactly _PROVIDERS.
_PROVIDER_CLASSES: dict[str, type] = {
    "anthropic": AnthropicLlm,
    "openai": OpenAiLlm,
    "gemini": GeminiLlm,
    "groq": GroqLlm,
    "mistral": MistralLlm,
    "deepseek": DeepSeekLlm,
    "xai": XaiLlm,
    "openrouter": OpenRouterLlm,
    "together": TogetherLlm,
    "fireworks": FireworksLlm,
    "moonshot": MoonshotLlm,
    "zai": ZaiLlm,
    "dashscope": DashscopeLlm,
    "nvidia": NvidiaLlm,
    "nous": NousLlm,
    "ollama_cloud": OllamaCloudLlm,
    "novita": NovitaLlm,
    "stepfun": StepfunLlm,
    "arcee": ArceeLlm,
    "xiaomi": XiaomiLlm,
    "gmi": GmiLlm,
    "huggingface": HuggingFaceLlm,
    "minimax": MinimaxLlm,
    "minimax_cn": MinimaxCnLlm,
    "opencode_zen": OpencodeZenLlm,
    "kilocode": KilocodeLlm,
    "alibaba_coding_plan": AlibabaCodingPlanLlm,
    "qwen": QwenLlm,
    "cerebras": CerebrasLlm,
    "bedrock": BedrockLlm,
    "openai_compat": OpenAiCompatLlm,
}


# Providers with NO canonical host: the target is whatever base_url the backend
# was configured with (the class default must not leak into the allowlist).
_BASE_URL_DRIVEN_PROVIDERS = frozenset({"openai_compat"})


def provider_host(provider: str, base_url: str | None = None) -> str | None:
    """The ``host:port`` an LLM call for ``provider`` targets, or None if unknown.

    Uses ``base_url`` when given (openai_compat / a bedrock region override),
    else the provider class ``BASE_URL``. openai_compat has no canonical host, so
    without a base_url it is None. https implies port 443. Pure: no network, no
    instantiation -- just URL parsing of a known constant."""
    if provider in _BASE_URL_DRIVEN_PROVIDERS:
        url = base_url
    else:
        cls = _PROVIDER_CLASSES.get(provider)
        url = base_url or (getattr(cls, "BASE_URL", None) if cls is not None else None)
    if not url:
        return None
    parsed = urllib.parse.urlparse(url)
    if not parsed.hostname:
        return None
    port = parsed.port or (443 if parsed.scheme == "https" else 80)
    return f"{parsed.hostname}:{port}"


# Provider id -> known model ids the console offers as a dropdown; first entry =
# default selected when that provider is picked. INTENTIONALLY PARTIAL: only
# providers whose model ids are grounded in this repo or an authoritative source
# are listed. An absent provider falls back to a free-text model field in the
# UI. Never invent a model id here (R13) -- a wrong suggestion is worse than
# none; the dropdown always keeps a "custom" path, so an unlisted model stays
# typeable. Add an entry only when a model id is verified, not guessed.
_PROVIDER_MODELS: dict[str, tuple[str, ...]] = {
    "anthropic": (
        "claude-opus-4-8",
        "claude-sonnet-4-6",
        "claude-haiku-4-5",
        "claude-fable-5",
    ),
    "openai": ("gpt-4o", "gpt-4o-mini"),
    "groq": ("llama-3.3-70b-versatile", "llama-3.1-8b-instant"),
    "mistral": ("mistral-large-latest", "mistral-small-latest"),
    "deepseek": ("deepseek-chat", "deepseek-reasoner"),
    # Nous Research inference models, frozen once from models.dev (no runtime
    # fetch -> I4). Bare model names as the vendor publishes them; the panel's
    # free-text field remains the fallback if the direct endpoint expects a
    # prefixed variant. First = default (smaller/faster than 405B).
    "nous": (
        "Hermes-4-70B",
        "Hermes-4-405B",
        "Hermes-3-Llama-3.1-70B",
        "Hermes-3-Llama-3.1-405B",
    ),
    # Other providers frozen ONCE from models.dev (no runtime fetch -> I4).
    # Ids are verbatim models.dev ids per vendor; order is models.dev's, NOT a
    # relevance ranking, so the first entry is a convenience default, not a
    # flagship -- the panel free-text field stays the way to pick anything else.
    # Capped to 12; pure aggregators stay a partial subset. Not verified live.
    "openrouter": (
        "inclusionai/ling-2.6-1t",
        "inclusionai/ring-2.6-1t",
        "inclusionai/ling-2.6-flash",
        "ibm-granite/granite-4.0-h-micro",
        "ibm-granite/granite-4.1-8b",
        "meta-llama/llama-3.1-8b-instruct",
        "meta-llama/llama-3-70b-instruct",
        "meta-llama/llama-3.1-70b-instruct",
        "meta-llama/llama-3.2-1b-instruct",
        "meta-llama/llama-4-maverick",
        "meta-llama/llama-3.2-11b-vision-instruct",
        "meta-llama/llama-3.3-70b-instruct:free",
    ),
    "fireworks": (
        "accounts/fireworks/routers/kimi-k2p6-turbo",
        "accounts/fireworks/routers/kimi-k2p7-code-fast",
        "accounts/fireworks/routers/glm-5p1-fast",
        "accounts/fireworks/routers/kimi-k2p6-fast",
        "accounts/fireworks/models/deepseek-v4-flash",
        "accounts/fireworks/models/deepseek-v4-pro",
        "accounts/fireworks/models/minimax-m2p7",
        "accounts/fireworks/models/minimax-m3",
        "accounts/fireworks/models/kimi-k2p6",
        "accounts/fireworks/models/qwen3p7-plus",
        "accounts/fireworks/models/glm-5p1",
        "accounts/fireworks/models/gpt-oss-120b",
    ),
    "moonshot": (
        "kimi-k2-0905-preview",
        "kimi-k2-thinking-turbo",
        "kimi-k2.7-code",
        "kimi-k2-thinking",
        "kimi-k2-0711-preview",
        "kimi-k2-turbo-preview",
        "kimi-k2.5",
        "kimi-k2.6",
    ),
    "zai": (
        "glm-4.7",
        "glm-4.5v",
        "glm-4.5",
        "glm-4.7-flashx",
        "glm-5.1",
        "glm-4.6",
        "glm-4.6v",
        "glm-5v-turbo",
        "glm-4.5-air",
        "glm-4.7-flash",
        "glm-4.5-flash",
        "glm-5",
    ),
    "dashscope": (
        "qwen3-omni-flash",
        "qwen3-coder-plus",
        "qwen-plus",
        "qwen3-coder-30b-a3b-instruct",
        "qwen3-omni-flash-realtime",
        "qwen3-32b",
        "qwen-omni-turbo-realtime",
        "qwen-plus-character-ja",
        "qwen3-next-80b-a3b-instruct",
        "qwen3.7-plus",
        "qwen3.6-35b-a3b",
        "qwen3.7-max",
    ),
    "nvidia": (
        "moonshotai/kimi-k2-instruct-0905",
        "moonshotai/kimi-k2.6",
        "minimaxai/minimax-m2.7",
        "stepfun-ai/step-3.7-flash",
        "stepfun-ai/step-3.5-flash",
        "google/gemma-3n-e4b-it",
        "google/gemma-3n-e2b-it",
        "google/google-paligemma",
        "google/gemma-4-31b-it",
        "google/gemma-2-2b-it",
        "microsoft/phi-4-mini-instruct",
        "microsoft/phi-4-multimodal-instruct",
    ),
    "ollama_cloud": (
        "deepseek-v4-flash",
        "minimax-m2.5",
        "devstral-small-2:24b",
        "glm-4.7",
        "cogito-2.1:671b",
        "minimax-m2.1",
        "gpt-oss:120b",
        "nemotron-3-nano:30b",
        "ministral-3:8b",
        "rnj-1:8b",
        "kimi-k2.7-code",
        "glm-5.1",
    ),
    "novita": (
        "inclusionai/ling-2.6-1t",
        "inclusionai/ring-2.6-1t",
        "inclusionai/ling-2.6-flash",
        "meta-llama/llama-3.1-8b-instruct",
        "meta-llama/llama-3-70b-instruct",
        "meta-llama/llama-4-scout-17b-16e-instruct",
        "meta-llama/llama-3.3-70b-instruct",
        "meta-llama/llama-3-8b-instruct",
        "meta-llama/llama-3.2-3b-instruct",
        "meta-llama/llama-4-maverick-17b-128e-instruct-fp8",
        "moonshotai/kimi-k2-instruct",
        "moonshotai/kimi-k2-thinking",
    ),
    "stepfun": (
        "step-3.5-flash",
        "step-3.5-flash-2603",
    ),
    "xiaomi": (
        "mimo-v2.5-pro-ultraspeed",
        "mimo-v2.5",
        "mimo-v2-omni",
        "mimo-v2-flash",
        "mimo-v2-pro",
        "mimo-v2.5-pro",
    ),
    "gmi": (
        "moonshotai/Kimi-K2.6",
        "anthropic/claude-opus-4.7",
        "anthropic/claude-sonnet-4.6",
        "anthropic/claude-opus-4.6",
        "zai-org/GLM-5.1-FP8",
        "zai-org/GLM-5-FP8",
        "deepseek-ai/DeepSeek-V4-Flash",
        "deepseek-ai/DeepSeek-V4-Pro",
    ),
    "huggingface": (
        "moonshotai/Kimi-K2-Thinking",
        "moonshotai/Kimi-K2-Instruct-0905",
        "moonshotai/Kimi-K2-Instruct",
        "moonshotai/Kimi-K2.6",
        "moonshotai/Kimi-K2.5",
        "Qwen/Qwen3-Coder-Next",
        "Qwen/Qwen3-Next-80B-A3B-Instruct",
        "Qwen/Qwen3.5-397B-A17B",
        "Qwen/Qwen3-235B-A22B-Thinking-2507",
        "Qwen/Qwen3-Coder-480B-A35B-Instruct",
        "Qwen/Qwen3-Next-80B-A3B-Thinking",
        "XiaomiMiMo/MiMo-V2-Flash",
    ),
    "minimax_cn": (
        "MiniMax-M2.1",
        "MiniMax-M2.5-highspeed",
        "MiniMax-M2.7-highspeed",
        "MiniMax-M2",
        "MiniMax-M2.5",
        "MiniMax-M3",
        "MiniMax-M2.7",
    ),
    "kilocode": (
        "inclusionai/ling-2.6-1t",
        "inclusionai/ring-2.6-1t",
        "inclusionai/ling-2.6-flash",
        "ibm-granite/granite-4.0-h-micro",
        "ibm-granite/granite-4.1-8b",
        "meta-llama/llama-3.1-8b-instruct",
        "meta-llama/llama-3-70b-instruct",
        "meta-llama/llama-3.1-70b-instruct",
        "meta-llama/llama-3.2-1b-instruct",
        "meta-llama/llama-4-maverick",
        "meta-llama/llama-3.2-11b-vision-instruct",
        "meta-llama/llama-3.3-70b-instruct",
    ),
    "alibaba_coding_plan": (
        "qwen3-coder-plus",
        "glm-4.7",
        "qwen3.7-plus",
        "qwen3.7-max",
        "qwen3.6-flash",
        "qwen3-max-2026-01-23",
        "qwen3.5-plus",
        "kimi-k2.5",
        "MiniMax-M2.5",
        "qwen3-coder-next",
        "glm-5",
        "qwen3.6-plus",
    ),
}


def provider_models(provider: str) -> tuple[str, ...]:
    """Known model ids for ``provider`` (first = default), or empty if none are
    declared. Pure lookup over the curated, intentionally partial map above."""
    return _PROVIDER_MODELS.get(provider, ())


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
    if provider == "moonshot":
        return MoonshotLlm(model=model, client=client, api_key=api_key)
    if provider == "zai":
        return ZaiLlm(model=model, client=client, api_key=api_key)
    if provider == "dashscope":
        return DashscopeLlm(model=model, client=client, api_key=api_key)
    if provider == "nvidia":
        return NvidiaLlm(model=model, client=client, api_key=api_key)
    if provider == "nous":
        return NousLlm(model=model, client=client, api_key=api_key)
    if provider == "ollama_cloud":
        return OllamaCloudLlm(model=model, client=client, api_key=api_key)
    if provider == "novita":
        return NovitaLlm(model=model, client=client, api_key=api_key)
    if provider == "stepfun":
        return StepfunLlm(model=model, client=client, api_key=api_key)
    if provider == "arcee":
        return ArceeLlm(model=model, client=client, api_key=api_key)
    if provider == "xiaomi":
        return XiaomiLlm(model=model, client=client, api_key=api_key)
    if provider == "gmi":
        return GmiLlm(model=model, client=client, api_key=api_key)
    if provider == "huggingface":
        return HuggingFaceLlm(model=model, client=client, api_key=api_key)
    if provider == "minimax":
        return MinimaxLlm(model=model, client=client, api_key=api_key)
    if provider == "minimax_cn":
        return MinimaxCnLlm(model=model, client=client, api_key=api_key)
    if provider == "opencode_zen":
        return OpencodeZenLlm(model=model, client=client, api_key=api_key)
    if provider == "kilocode":
        return KilocodeLlm(model=model, client=client, api_key=api_key)
    if provider == "alibaba_coding_plan":
        return AlibabaCodingPlanLlm(model=model, client=client, api_key=api_key)
    if provider == "qwen":
        return QwenLlm(model=model, client=client, api_key=api_key)
    if provider == "cerebras":
        return CerebrasLlm(model=model, client=client, api_key=api_key)
    if provider == "bedrock":
        # base_url optionally overrides the region host (default us-east-1).
        return BedrockLlm(model=model, client=client, base_url=base_url, api_key=api_key)
    if provider == "openai_compat":
        if not base_url and client is None:
            raise ValueError("openai_compat requires base_url")
        return OpenAiCompatLlm(model=model, base_url=base_url or "", client=client, api_key=api_key)
    raise ValueError(f"unknown provider {provider!r}; known: {', '.join(_PROVIDERS)}")
