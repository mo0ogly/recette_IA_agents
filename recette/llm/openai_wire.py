"""OpenAI chat-completions wire backends (OpenAI + every OpenAI-wire vendor)."""

from __future__ import annotations

import json
import os

from .._http_client import StdlibHttpClient
from ._core import LlmDecision, Message, ToolSpec, _PostClient


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
        # Keep the assistant text accompanying the tool call (the model's stated
        # rationale): dropping it silences the "why" the observability surfaces
        # (recording, LlmCallTrace) rely on. The other wires (Anthropic, Bedrock,
        # Gemini) already preserve it.
        return LlmDecision(
            kind="tool_call",
            tool_name=fn.get("name"),
            tool_args=args,
            text=message.get("content") or "",
            raw=data,
        )
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
        proxy_url: str | None = None,
    ) -> None:
        self._model = model
        if client is None:
            key = api_key or os.environ.get("OPENAI_API_KEY")
            if not key:
                raise RuntimeError("OPENAI_API_KEY not set (or pass client/api_key)")
            client = StdlibHttpClient(
                self.BASE_URL,
                headers={"Authorization": f"Bearer {key}"},
                proxy_url=proxy_url,
            )
        self._client = client

    def decide(self, *, system: str, history: list[Message], tools: list[ToolSpec]) -> LlmDecision:
        body: dict = {
            "model": self._model,
            "messages": _to_openai_messages(system, history),
        }
        # Only send `tools` when there is at least one. A strict OpenAI-compatible
        # gateway (SKYNET/vLLM) rejects an empty `tools: []` with HTTP 400
        # ("tools must not be an empty array"); omitting the key is valid on every
        # provider, so this is the portable shape (a toolless agent/team member).
        if tools:
            body["tools"] = [
                {
                    "type": "function",
                    "function": {
                        "name": t.name,
                        "description": t.description,
                        "parameters": t.parameters,
                    },
                }
                for t in tools
            ]
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
        proxy_url: str | None = None,
    ) -> None:
        if client is None:
            headers = {"Authorization": f"Bearer {api_key}"} if api_key else None
            client = StdlibHttpClient(
                self._normalize_base_url(base_url), headers=headers, proxy_url=proxy_url
            )
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
        self,
        *,
        model: str,
        client: _PostClient | None = None,
        api_key: str | None = None,
        proxy_url: str | None = None,
    ) -> None:
        if client is None:
            env_key = type(self).ENV_KEY
            key = api_key or os.environ.get(env_key)
            if not key:
                raise RuntimeError(f"{env_key} not set (or pass client/api_key)")
            client = StdlibHttpClient(
                type(self).BASE_URL,
                headers={"Authorization": f"Bearer {key}"},
                proxy_url=proxy_url,
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
    """Z.AI / GLM -- OpenAI wire at api.z.ai/api/paas/v4. Key: GLM_API_KEY.

    This is the pay-as-you-go standard API (billed by account balance). A GLM
    *Coding Plan* subscription is metered by a separate quota that only the
    coding endpoint draws from -- use ``ZaiCodingLlm`` for that."""

    BASE_URL = "https://api.z.ai/api/paas/v4"
    ENV_KEY = "GLM_API_KEY"


class ZaiCodingLlm(_VersionedWireVendor):
    """Z.AI / GLM Coding Plan -- OpenAI wire at api.z.ai/api/coding/paas/v4.

    Same GLM models and key (GLM_API_KEY) as ``ZaiLlm``, but the coding endpoint:
    a GLM Coding Plan subscription is metered by its 5-hour/weekly quota here,
    NOT by the pay-as-you-go balance the standard ``/api/paas/v4`` endpoint uses
    (which returns 429 code 1113 "insufficient balance" for a Coding-Plan-only
    account). Mirrors the AlibabaCodingPlanLlm split."""

    BASE_URL = "https://api.z.ai/api/coding/paas/v4"
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


class SkynetLlm(OpenAiCompatLlm):
    """SKYNET internal vLLM gateway -- OpenAI wire, per-model base_url.

    Each model is served at its own route ``https://api.skynet.cossi.internet/
    <model>/v1`` (e.g. gpt-oss-120b, glm46v, qwen3.6), so the backend supplies
    the per-model ``base_url`` like openai_compat -- there is no single canonical
    host. The body ``model`` is the id reported by ``/v1/models`` (e.g.
    ``openai/gpt-oss-120b``). The key SKYNET_API_KEY (a UUID token) travels as the
    bearer Authorization header, stored write-only in the per-backend secret
    store. Surfaces as the first-class ``skynet`` provider on /ai-backends.
    """

    ENV_KEY = "SKYNET_API_KEY"

    def __init__(
        self,
        *,
        model: str,
        base_url: str,
        client: _PostClient | None = None,
        api_key: str | None = None,
        proxy_url: str | None = None,
    ) -> None:
        key = api_key or os.environ.get(self.ENV_KEY)
        super().__init__(
            model=model, base_url=base_url, client=client, api_key=key, proxy_url=proxy_url
        )
