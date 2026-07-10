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
    ZaiCodingLlm,
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
    "zai_coding",
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
    # Neutral display name for the same internal vLLM gateway (same class/host/
    # key). Kept as a first-class provider so it appears in the console catalog;
    # resolves via the gateway backend class. The prior id is unaffected.
    "internal",
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
    "zai_coding": ZaiCodingLlm,
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
    "internal": SkynetLlm,  # neutral alias -> same class (drift guard: keys == _PROVIDERS)
    "bedrock": BedrockLlm,
    "openai_compat": OpenAiCompatLlm,
}


# Providers with NO canonical host: the target is whatever base_url the backend
# was configured with (the class default must not leak into the allowlist).
_BASE_URL_DRIVEN_PROVIDERS = frozenset({"openai_compat", "skynet", "internal"})


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
    proxy_url: str | None = None,
) -> LlmBackend:
    """Construct a live provider backend by name.

    Key resolution (R8): an explicit api_key wins (per-backend secret store);
    otherwise the provider reads its env var fallback. The key is never logged.
    base_url is required for (and only used by) the "openai_compat" provider.
    ``proxy_url`` (optional) routes the provider's HTTP client through an explicit
    proxy -- the seam the mitmproxy wire overlay uses so an orchestration run's
    LLM bytes are captured on the wire. Explicit input (never ambient env), so a
    run stays reproducible (I4). Ignored when a client is injected (tests)."""
    if provider == "anthropic":
        return AnthropicLlm(model=model, client=client, api_key=api_key, proxy_url=proxy_url)
    if provider == "openai":
        return OpenAiLlm(model=model, client=client, api_key=api_key, proxy_url=proxy_url)
    if provider == "gemini":
        return GeminiLlm(model=model, client=client, api_key=api_key, proxy_url=proxy_url)
    if provider == "groq":
        return GroqLlm(model=model, client=client, api_key=api_key, proxy_url=proxy_url)
    if provider == "mistral":
        return MistralLlm(model=model, client=client, api_key=api_key, proxy_url=proxy_url)
    if provider == "deepseek":
        return DeepSeekLlm(model=model, client=client, api_key=api_key, proxy_url=proxy_url)
    if provider == "xai":
        return XaiLlm(model=model, client=client, api_key=api_key, proxy_url=proxy_url)
    if provider == "openrouter":
        return OpenRouterLlm(model=model, client=client, api_key=api_key, proxy_url=proxy_url)
    if provider == "together":
        return TogetherLlm(model=model, client=client, api_key=api_key, proxy_url=proxy_url)
    if provider == "fireworks":
        return FireworksLlm(model=model, client=client, api_key=api_key, proxy_url=proxy_url)
    if provider == "moonshot":
        return MoonshotLlm(model=model, client=client, api_key=api_key, proxy_url=proxy_url)
    if provider == "zai":
        return ZaiLlm(model=model, client=client, api_key=api_key, proxy_url=proxy_url)
    if provider == "zai_coding":
        return ZaiCodingLlm(model=model, client=client, api_key=api_key, proxy_url=proxy_url)
    if provider == "dashscope":
        return DashscopeLlm(model=model, client=client, api_key=api_key, proxy_url=proxy_url)
    if provider == "nvidia":
        return NvidiaLlm(model=model, client=client, api_key=api_key, proxy_url=proxy_url)
    if provider == "nous":
        return NousLlm(model=model, client=client, api_key=api_key, proxy_url=proxy_url)
    if provider == "ollama_cloud":
        return OllamaCloudLlm(model=model, client=client, api_key=api_key, proxy_url=proxy_url)
    if provider == "novita":
        return NovitaLlm(model=model, client=client, api_key=api_key, proxy_url=proxy_url)
    if provider == "stepfun":
        return StepfunLlm(model=model, client=client, api_key=api_key, proxy_url=proxy_url)
    if provider == "arcee":
        return ArceeLlm(model=model, client=client, api_key=api_key, proxy_url=proxy_url)
    if provider == "xiaomi":
        return XiaomiLlm(model=model, client=client, api_key=api_key, proxy_url=proxy_url)
    if provider == "gmi":
        return GmiLlm(model=model, client=client, api_key=api_key, proxy_url=proxy_url)
    if provider == "huggingface":
        return HuggingFaceLlm(model=model, client=client, api_key=api_key, proxy_url=proxy_url)
    if provider == "minimax":
        return MinimaxLlm(model=model, client=client, api_key=api_key, proxy_url=proxy_url)
    if provider == "minimax_cn":
        return MinimaxCnLlm(model=model, client=client, api_key=api_key, proxy_url=proxy_url)
    if provider == "opencode_zen":
        return OpencodeZenLlm(model=model, client=client, api_key=api_key, proxy_url=proxy_url)
    if provider == "kilocode":
        return KilocodeLlm(model=model, client=client, api_key=api_key, proxy_url=proxy_url)
    if provider == "alibaba_coding_plan":
        return AlibabaCodingPlanLlm(
            model=model, client=client, api_key=api_key, proxy_url=proxy_url
        )
    if provider == "qwen":
        return QwenLlm(model=model, client=client, api_key=api_key, proxy_url=proxy_url)
    if provider == "cerebras":
        return CerebrasLlm(model=model, client=client, api_key=api_key, proxy_url=proxy_url)
    if provider in ("skynet", "internal"):  # neutral alias shares this branch
        if not base_url and client is None:
            raise ValueError(
                f"{provider} requires base_url (https://api.skynet.cossi.internet/<model>/v1)"
            )
        return SkynetLlm(
            model=model,
            base_url=base_url or "",
            client=client,
            api_key=api_key,
            proxy_url=proxy_url,
        )
    if provider == "bedrock":
        # base_url optionally overrides the region host (default us-east-1).
        return BedrockLlm(
            model=model, client=client, base_url=base_url, api_key=api_key, proxy_url=proxy_url
        )
    if provider == "openai_compat":
        if not base_url and client is None:
            raise ValueError("openai_compat requires base_url")
        return OpenAiCompatLlm(
            model=model,
            base_url=base_url or "",
            client=client,
            api_key=api_key,
            proxy_url=proxy_url,
        )
    raise ValueError(f"unknown provider {provider!r}; known: {', '.join(_PROVIDERS)}")
