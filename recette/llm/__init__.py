"""LB1 -- LLM backends for Lane B agents (multi-provider, offline-testable).

A Lane B agent asks an LlmBackend to decide the next step given a system prompt, the
conversation history, and the tools it is allowed to call. The backend returns an
LlmDecision: either a tool call or a final answer.

This package was split by wire format from a single module; the public surface is
re-exported here verbatim, so ``from recette.llm import build_llm, StubLlm, ...``
and every ``recette.llm.<Backend>`` reference keeps working unchanged.

Backends:
- StubLlm   -- offline scripted decisions (deterministic; tests, fixtures, CI).
- ReplayLlm -- deterministic replay of a recorded run (LB4).
- AnthropicLlm / MinimaxLlm / MinimaxCnLlm -- Anthropic Messages wire.
- OpenAiLlm / OpenAiCompatLlm + cloud vendors -- OpenAI chat-completions wire.
- GeminiLlm -- Google Gemini generateContent wire.
- BedrockLlm -- AWS Bedrock Converse wire (bearer key, no SDK / SigV4).

Keys come from env (R8); the HTTP transport is injectable, so every live provider
is unit-tested with a stub client -- no API key, no network.
"""

from __future__ import annotations

from ._core import (
    LlmBackend,
    LlmDecision,
    Message,
    ReplayLlm,
    StubLlm,
    ToolSpec,
    _PostClient,
    _Response,
)
from ._models import provider_models
from ._registry import (
    _BASE_URL_DRIVEN_PROVIDERS,
    _PROVIDER_CLASSES,
    _PROVIDERS,
    build_llm,
    provider_host,
)
from .anthropic_wire import AnthropicLlm, MinimaxCnLlm, MinimaxLlm
from .bedrock_wire import BedrockLlm
from .gemini_wire import GeminiLlm
from .openai_wire import (
    AlibabaCodingPlanLlm,
    ArceeLlm,
    CerebrasLlm,
    DashscopeLlm,
    DeepSeekLlm,
    FireworksLlm,
    GmiLlm,
    GroqLlm,
    HuggingFaceLlm,
    KilocodeLlm,
    MistralLlm,
    MoonshotLlm,
    NousLlm,
    NovitaLlm,
    NvidiaLlm,
    OllamaCloudLlm,
    OpenAiCompatLlm,
    OpenAiLlm,
    OpencodeZenLlm,
    OpenRouterLlm,
    QwenLlm,
    SkynetLlm,
    StepfunLlm,
    TogetherLlm,
    XaiLlm,
    XiaomiLlm,
    ZaiCodingLlm,
    ZaiLlm,
)

__all__ = [
    # core
    "ToolSpec",
    "Message",
    "LlmDecision",
    "LlmBackend",
    "StubLlm",
    "ReplayLlm",
    "_Response",
    "_PostClient",
    # anthropic wire
    "AnthropicLlm",
    "MinimaxLlm",
    "MinimaxCnLlm",
    # openai wire
    "OpenAiLlm",
    "OpenAiCompatLlm",
    "GroqLlm",
    "MistralLlm",
    "DeepSeekLlm",
    "XaiLlm",
    "OpenRouterLlm",
    "TogetherLlm",
    "FireworksLlm",
    "MoonshotLlm",
    "ZaiLlm",
    "ZaiCodingLlm",
    "DashscopeLlm",
    "NvidiaLlm",
    "NousLlm",
    "OllamaCloudLlm",
    "NovitaLlm",
    "StepfunLlm",
    "ArceeLlm",
    "XiaomiLlm",
    "GmiLlm",
    "HuggingFaceLlm",
    "OpencodeZenLlm",
    "KilocodeLlm",
    "AlibabaCodingPlanLlm",
    "QwenLlm",
    "CerebrasLlm",
    "SkynetLlm",
    # gemini wire
    "GeminiLlm",
    # bedrock wire
    "BedrockLlm",
    # registry / factory
    "build_llm",
    "provider_host",
    "provider_models",
    "_PROVIDERS",
    "_PROVIDER_CLASSES",
    "_BASE_URL_DRIVEN_PROVIDERS",
]
