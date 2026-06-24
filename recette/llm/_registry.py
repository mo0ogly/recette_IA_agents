"""Provider registry + factory: name -> backend class, host derivation, build_llm."""

from __future__ import annotations

import urllib.parse

from ._core import LlmBackend, _PostClient
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
    ZaiLlm,
)

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
    "skynet",
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
    "skynet": SkynetLlm,
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
    if provider == "skynet":
        return SkynetLlm(model=model, client=client, api_key=api_key)
    if provider == "bedrock":
        # base_url optionally overrides the region host (default us-east-1).
        return BedrockLlm(model=model, client=client, base_url=base_url, api_key=api_key)
    if provider == "openai_compat":
        if not base_url and client is None:
            raise ValueError("openai_compat requires base_url")
        return OpenAiCompatLlm(model=model, base_url=base_url or "", client=client, api_key=api_key)
    raise ValueError(f"unknown provider {provider!r}; known: {', '.join(_PROVIDERS)}")
