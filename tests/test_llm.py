"""LB1 tests: LLM backends. Offline -- providers driven by a stub HTTP client (no key/network)."""

from __future__ import annotations

import os
import unittest
from typing import Any

from recette.llm import (
    AlibabaCodingPlanLlm,
    AnthropicLlm,
    ArceeLlm,
    BedrockLlm,
    CerebrasLlm,
    DashscopeLlm,
    DeepSeekLlm,
    FireworksLlm,
    GeminiLlm,
    GmiLlm,
    GroqLlm,
    HuggingFaceLlm,
    KilocodeLlm,
    LlmDecision,
    Message,
    MinimaxCnLlm,
    MinimaxLlm,
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
    StubLlm,
    TogetherLlm,
    ToolSpec,
    XaiLlm,
    XiaomiLlm,
    ZaiLlm,
    build_llm,
)

TOOLS = [ToolSpec(name="read_repo", description="read a repo", parameters={"type": "object"})]


class _StubResponse:
    def __init__(self, payload: dict) -> None:
        self._payload = payload

    def raise_for_status(self) -> None:
        return None

    def json(self) -> Any:
        return self._payload


class _StubClient:
    """Captures the last POST and returns a canned response."""

    def __init__(self, payload: dict) -> None:
        self.payload = payload
        self.last_path: str | None = None
        self.last_body: dict | None = None

    def post(self, path: str, json: dict | None = None) -> _StubResponse:
        self.last_path = path
        self.last_body = json
        return _StubResponse(self.payload)


class TestStubLlm(unittest.TestCase):
    def test_returns_scripted_decisions_in_order(self):
        d1 = LlmDecision(kind="tool_call", tool_name="read_repo", tool_args={"repo": "a/b"})
        d2 = LlmDecision(kind="final", text="done")
        llm = StubLlm([d1, d2])
        self.assertEqual(llm.decide(system="s", history=[], tools=TOOLS), d1)
        self.assertEqual(llm.decide(system="s", history=[], tools=TOOLS), d2)

    def test_exhausted_returns_final(self):
        llm = StubLlm([])
        out = llm.decide(system="s", history=[], tools=TOOLS)
        self.assertEqual(out.kind, "final")
        self.assertFalse(out.is_tool_call)


class TestAnthropic(unittest.TestCase):
    def test_parses_tool_use(self):
        payload = {
            "content": [
                {"type": "text", "text": "let me read"},
                {"type": "tool_use", "name": "read_repo", "input": {"repo": "acme/x"}},
            ]
        }
        client = _StubClient(payload)
        llm = AnthropicLlm(model="claude-x", client=client)
        out = llm.decide(system="be an agent", history=[Message("user", "go")], tools=TOOLS)
        self.assertTrue(out.is_tool_call)
        self.assertEqual(out.tool_name, "read_repo")
        self.assertEqual(out.tool_args, {"repo": "acme/x"})
        # request shape
        self.assertEqual(client.last_path, "/v1/messages")
        assert client.last_body is not None
        self.assertEqual(client.last_body["system"], "be an agent")
        self.assertEqual(client.last_body["tools"][0]["name"], "read_repo")
        self.assertIn("input_schema", client.last_body["tools"][0])

    def test_parses_final_text(self):
        client = _StubClient({"content": [{"type": "text", "text": "all good"}]})
        out = AnthropicLlm(model="m", client=client).decide(system="s", history=[], tools=TOOLS)
        self.assertEqual(out.kind, "final")
        self.assertEqual(out.text, "all good")

    def test_missing_key_without_client_raises(self):
        old = os.environ.pop("ANTHROPIC_API_KEY", None)
        try:
            with self.assertRaises(RuntimeError):
                AnthropicLlm(model="m")
        finally:
            if old is not None:
                os.environ["ANTHROPIC_API_KEY"] = old


class TestMinimax(unittest.TestCase):
    """MiniMax speaks the Anthropic Messages wire but authenticates with bearer."""

    def test_uses_bearer_auth_not_x_api_key(self) -> None:
        llm = MinimaxLlm(model="MiniMax-M3", api_key="mk")
        headers = llm._client.headers  # type: ignore[attr-defined]
        self.assertEqual(headers["Authorization"], "Bearer mk")
        self.assertIn("anthropic-version", headers)
        self.assertNotIn("x-api-key", headers)

    def test_missing_key_without_client_raises_naming_env_var(self) -> None:
        old = os.environ.pop("MINIMAX_API_KEY", None)
        try:
            with self.assertRaises(RuntimeError) as ctx:
                MinimaxLlm(model="m")
            self.assertIn("MINIMAX_API_KEY", str(ctx.exception))
        finally:
            if old is not None:
                os.environ["MINIMAX_API_KEY"] = old

    def test_decide_posts_messages_and_parses_tool_use(self) -> None:
        payload = {"content": [{"type": "tool_use", "name": "open_pr", "input": {"r": 1}}]}
        client = _StubClient(payload)
        out = MinimaxLlm(model="m", client=client).decide(system="s", history=[], tools=TOOLS)
        self.assertEqual(client.last_path, "/v1/messages")
        self.assertTrue(out.is_tool_call)
        self.assertEqual(out.tool_name, "open_pr")
        self.assertEqual(out.tool_args, {"r": 1})

    def test_cn_variant_overrides_host_and_env_keeps_bearer(self) -> None:
        self.assertEqual(MinimaxCnLlm.BASE_URL, "https://api.minimaxi.com/anthropic")
        self.assertEqual(MinimaxCnLlm.ENV_KEY, "MINIMAX_CN_API_KEY")
        llm = MinimaxCnLlm(model="m", api_key="ck")
        self.assertEqual(llm._client.headers["Authorization"], "Bearer ck")  # type: ignore[attr-defined]
        self.assertNotIn("x-api-key", llm._client.headers)  # type: ignore[attr-defined]


class TestBedrock(unittest.TestCase):
    """AWS Bedrock over the Converse wire with a bearer Bedrock API key."""

    def test_missing_key_without_client_raises_naming_env_var(self) -> None:
        old = os.environ.pop("AWS_BEARER_TOKEN_BEDROCK", None)
        try:
            with self.assertRaises(RuntimeError) as ctx:
                BedrockLlm(model="m")
            self.assertIn("AWS_BEARER_TOKEN_BEDROCK", str(ctx.exception))
        finally:
            if old is not None:
                os.environ["AWS_BEARER_TOKEN_BEDROCK"] = old

    def test_uses_bearer_auth(self) -> None:
        llm = BedrockLlm(model="m", api_key="bk")
        self.assertEqual(llm._client.headers["Authorization"], "Bearer bk")  # type: ignore[attr-defined]

    def test_decide_posts_converse_path_and_parses_tool_use(self) -> None:
        payload = {
            "output": {
                "message": {
                    "content": [{"toolUse": {"name": "open_pr", "input": {"repo": "acme/x"}}}]
                }
            }
        }
        client = _StubClient(payload)
        model = "anthropic.claude-3-5-sonnet-20240620-v1:0"
        out = BedrockLlm(model=model, client=client).decide(system="s", history=[], tools=TOOLS)
        # The colon in the model id must be percent-encoded into the path.
        self.assertEqual(client.last_path, f"/model/{model.replace(':', '%3A')}/converse")
        self.assertTrue(out.is_tool_call)
        self.assertEqual(out.tool_name, "open_pr")
        self.assertEqual(out.tool_args, {"repo": "acme/x"})
        assert client.last_body is not None
        self.assertEqual(client.last_body["system"], [{"text": "s"}])
        self.assertIn("toolConfig", client.last_body)

    def test_base_url_overrides_region_host(self) -> None:
        host = "https://bedrock-runtime.eu-west-1.amazonaws.com"
        llm = BedrockLlm(model="m", base_url=host, api_key="bk")
        self.assertEqual(llm._client.base_url, host)  # type: ignore[attr-defined]


class TestOpenAi(unittest.TestCase):
    def test_parses_tool_call_with_json_args(self):
        payload = {
            "choices": [
                {
                    "message": {
                        "tool_calls": [
                            {"function": {"name": "open_pr", "arguments": '{"repo": "acme/x"}'}}
                        ]
                    }
                }
            ]
        }
        client = _StubClient(payload)
        llm = OpenAiLlm(model="gpt-x", client=client)
        out = llm.decide(system="s", history=[], tools=TOOLS)
        self.assertTrue(out.is_tool_call)
        self.assertEqual(out.tool_name, "open_pr")
        self.assertEqual(out.tool_args, {"repo": "acme/x"})
        self.assertEqual(client.last_path, "/v1/chat/completions")
        assert client.last_body is not None
        self.assertEqual(client.last_body["messages"][0]["role"], "system")

    def test_parses_final_content(self):
        client = _StubClient({"choices": [{"message": {"content": "no action needed"}}]})
        out = OpenAiLlm(model="m", client=client).decide(system="s", history=[], tools=TOOLS)
        self.assertEqual(out.kind, "final")
        self.assertEqual(out.text, "no action needed")

    def test_missing_key_without_client_raises(self):
        old = os.environ.pop("OPENAI_API_KEY", None)
        try:
            with self.assertRaises(RuntimeError):
                OpenAiLlm(model="m")
        finally:
            if old is not None:
                os.environ["OPENAI_API_KEY"] = old


class TestOpenAiCompat(unittest.TestCase):
    def test_tool_call_parsed_from_openai_wire_format(self) -> None:
        payload = {
            "choices": [
                {
                    "message": {
                        "tool_calls": [
                            {
                                "function": {
                                    "name": "read_repo",
                                    "arguments": '{"resource": "acme/x"}',
                                }
                            }
                        ]
                    }
                }
            ]
        }
        client = _StubClient(payload)
        llm = OpenAiCompatLlm(model="qwen2.5", base_url="http://localhost:11434/v1", client=client)
        decision = llm.decide(system="s", history=[Message(role="user", content="go")], tools=TOOLS)
        self.assertTrue(decision.is_tool_call)
        self.assertEqual(decision.tool_name, "read_repo")
        self.assertEqual(decision.tool_args, {"resource": "acme/x"})

    def test_empty_tools_omits_the_key(self) -> None:
        # A strict OpenAI-compatible gateway (SKYNET/vLLM) rejects "tools": [] with
        # HTTP 400. A toolless call must omit the key entirely, not send an empty array.
        client = _StubClient({"choices": [{"message": {"content": "done"}}]})
        llm = OpenAiCompatLlm(model="m", base_url="http://h/v1", client=client)
        llm.decide(system="s", history=[Message(role="user", content="go")], tools=[])
        assert client.last_body is not None
        self.assertNotIn("tools", client.last_body)

    def test_no_api_key_required(self) -> None:
        # Local OpenAI-compatible servers (Ollama) have no key; must construct keyless.
        old = os.environ.pop("OPENAI_API_KEY", None)
        try:
            llm = OpenAiCompatLlm(model="qwen2.5", base_url="http://localhost:11434/v1")
            self.assertIsNotNone(llm)
        finally:
            if old is not None:
                os.environ["OPENAI_API_KEY"] = old

    def test_normalize_base_url_strips_v1_suffix(self) -> None:
        # The "/v1" suffix is stripped: decide() paths already start with /v1.
        self.assertEqual(OpenAiCompatLlm._normalize_base_url("http://h"), "http://h")
        self.assertEqual(OpenAiCompatLlm._normalize_base_url("http://h/v1"), "http://h")
        self.assertEqual(OpenAiCompatLlm._normalize_base_url("http://h/v1/"), "http://h")


class TestSkynet(unittest.TestCase):
    """SKYNET internal gateway -- per-model base_url, SKYNET_API_KEY bearer."""

    def test_per_model_base_url_posts_to_chat_completions(self) -> None:
        # base_url .../gpt-oss-120b/v1 -> effective .../gpt-oss-120b/v1/chat/completions.
        client = _StubClient({"choices": [{"message": {"content": "ok"}}]})
        llm = SkynetLlm(
            model="openai/gpt-oss-120b",
            base_url="https://api.skynet.cossi.internet/gpt-oss-120b/v1",
            client=client,
        )
        out = llm.decide(system="s", history=[Message(role="user", content="go")], tools=TOOLS)
        self.assertEqual(client.last_path, "/v1/chat/completions")
        self.assertEqual(out.kind, "final")

    def test_resolves_key_from_skynet_env_var(self) -> None:
        old = os.environ.get("SKYNET_API_KEY")
        os.environ["SKYNET_API_KEY"] = "uuid-token"
        try:
            llm = SkynetLlm(
                model="openai/gpt-oss-120b",
                base_url="https://api.skynet.cossi.internet/gpt-oss-120b/v1",
            )
            self.assertEqual(llm._client.headers["Authorization"], "Bearer uuid-token")  # type: ignore[attr-defined]
            self.assertEqual(SkynetLlm.ENV_KEY, "SKYNET_API_KEY")
        finally:
            if old is None:
                os.environ.pop("SKYNET_API_KEY", None)
            else:
                os.environ["SKYNET_API_KEY"] = old

    def test_base_url_v1_suffix_normalized(self) -> None:
        # ".../v1" and bare base must both end up posting to /v1/chat/completions
        client = _StubClient({"choices": []})
        llm = OpenAiCompatLlm(model="m", base_url="http://h:1/v1", client=client)
        llm.decide(system="s", history=[], tools=[])
        self.assertEqual(client.last_path, "/v1/chat/completions")


class TestGroq(unittest.TestCase):
    def test_requires_key_when_no_client(self) -> None:
        old = os.environ.pop("GROQ_API_KEY", None)
        try:
            with self.assertRaises(RuntimeError):
                GroqLlm(model="llama-3.3-70b-versatile")
        finally:
            if old is not None:
                os.environ["GROQ_API_KEY"] = old

    def test_decide_uses_openai_wire_format(self) -> None:
        client = _StubClient({"choices": [{"message": {"content": "ok"}}]})
        llm = GroqLlm(model="llama-3.3-70b-versatile", client=client)
        out = llm.decide(system="s", history=[Message(role="user", content="go")], tools=TOOLS)
        self.assertEqual(out.kind, "final")
        self.assertEqual(out.text, "ok")
        self.assertEqual(client.last_path, "/v1/chat/completions")


class TestMistral(unittest.TestCase):
    def test_requires_key_when_no_client(self) -> None:
        old = os.environ.pop("MISTRAL_API_KEY", None)
        try:
            with self.assertRaises(RuntimeError) as ctx:
                MistralLlm(model="mistral-large-latest")
            self.assertIn("MISTRAL_API_KEY", str(ctx.exception))
        finally:
            if old is not None:
                os.environ["MISTRAL_API_KEY"] = old

    def test_decide_uses_openai_wire_format(self) -> None:
        client = _StubClient({"choices": [{"message": {"content": "ok"}}]})
        llm = MistralLlm(model="mistral-large-latest", client=client)
        out = llm.decide(system="s", history=[Message(role="user", content="go")], tools=TOOLS)
        self.assertEqual(out.kind, "final")
        self.assertEqual(out.text, "ok")
        self.assertEqual(client.last_path, "/v1/chat/completions")


class TestDeepSeek(unittest.TestCase):
    def test_requires_key_when_no_client(self) -> None:
        old = os.environ.pop("DEEPSEEK_API_KEY", None)
        try:
            with self.assertRaises(RuntimeError) as ctx:
                DeepSeekLlm(model="deepseek-chat")
            self.assertIn("DEEPSEEK_API_KEY", str(ctx.exception))
        finally:
            if old is not None:
                os.environ["DEEPSEEK_API_KEY"] = old

    def test_decide_uses_openai_wire_format(self) -> None:
        client = _StubClient({"choices": [{"message": {"content": "ok"}}]})
        llm = DeepSeekLlm(model="deepseek-chat", client=client)
        out = llm.decide(system="s", history=[Message(role="user", content="go")], tools=TOOLS)
        self.assertEqual(out.kind, "final")
        self.assertEqual(out.text, "ok")
        self.assertEqual(client.last_path, "/v1/chat/completions")


class TestXai(unittest.TestCase):
    def test_requires_key_when_no_client(self) -> None:
        old = os.environ.pop("XAI_API_KEY", None)
        try:
            with self.assertRaises(RuntimeError) as ctx:
                XaiLlm(model="grok-3")
            self.assertIn("XAI_API_KEY", str(ctx.exception))
        finally:
            if old is not None:
                os.environ["XAI_API_KEY"] = old

    def test_decide_uses_openai_wire_format(self) -> None:
        client = _StubClient({"choices": [{"message": {"content": "ok"}}]})
        llm = XaiLlm(model="grok-3", client=client)
        out = llm.decide(system="s", history=[Message(role="user", content="go")], tools=TOOLS)
        self.assertEqual(out.kind, "final")
        self.assertEqual(out.text, "ok")
        self.assertEqual(client.last_path, "/v1/chat/completions")


class TestGemini(unittest.TestCase):
    def test_parses_function_call(self) -> None:
        payload = {
            "candidates": [
                {
                    "content": {
                        "parts": [
                            {"functionCall": {"name": "read_repo", "args": {"resource": "acme/x"}}}
                        ]
                    }
                }
            ]
        }
        client = _StubClient(payload)
        llm = GeminiLlm(model="gemini-2.0-flash", client=client)
        out = llm.decide(
            system="be an agent",
            history=[Message(role="user", content="go")],
            tools=TOOLS,
        )
        self.assertTrue(out.is_tool_call)
        self.assertEqual(out.tool_name, "read_repo")
        self.assertEqual(out.tool_args, {"resource": "acme/x"})
        self.assertEqual(client.last_path, "/v1beta/models/gemini-2.0-flash:generateContent")
        assert client.last_body is not None
        self.assertEqual(
            client.last_body["system_instruction"], {"parts": [{"text": "be an agent"}]}
        )
        declarations = client.last_body["tools"][0]["functionDeclarations"]
        self.assertEqual(declarations[0]["name"], "read_repo")
        self.assertEqual(client.last_body["contents"][0]["role"], "user")

    def test_parses_text_answer(self) -> None:
        payload = {"candidates": [{"content": {"parts": [{"text": "done"}]}}]}
        client = _StubClient(payload)
        out = GeminiLlm(model="m", client=client).decide(system="s", history=[], tools=TOOLS)
        self.assertEqual(out.kind, "final")
        self.assertEqual(out.text, "done")

    def test_requires_key_when_no_client(self) -> None:
        old = os.environ.pop("GEMINI_API_KEY", None)
        try:
            with self.assertRaises(RuntimeError):
                GeminiLlm(model="gemini-2.0-flash")
        finally:
            if old is not None:
                os.environ["GEMINI_API_KEY"] = old

    def test_empty_candidates_yield_empty_final(self) -> None:
        client = _StubClient({"candidates": []})
        out = GeminiLlm(model="m", client=client).decide(system="s", history=[], tools=TOOLS)
        self.assertEqual(out.kind, "final")
        self.assertEqual(out.text, "")


class TestOpenAiWireVendors(unittest.TestCase):
    """OpenAI-wire vendors share one base; each declares BASE_URL + ENV_KEY.

    The versioned-base vendors (moonshot..huggingface) carry their API version in
    BASE_URL and post to /chat/completions; the table pins each one's exact
    endpoint and primary key env var.
    """

    _VENDORS = (
        (GroqLlm, "https://api.groq.com/openai", "GROQ_API_KEY"),
        (MistralLlm, "https://api.mistral.ai", "MISTRAL_API_KEY"),
        (DeepSeekLlm, "https://api.deepseek.com", "DEEPSEEK_API_KEY"),
        (XaiLlm, "https://api.x.ai", "XAI_API_KEY"),
        (OpenRouterLlm, "https://openrouter.ai/api", "OPENROUTER_API_KEY"),
        (TogetherLlm, "https://api.together.xyz", "TOGETHER_API_KEY"),
        (FireworksLlm, "https://api.fireworks.ai/inference", "FIREWORKS_API_KEY"),
        (MoonshotLlm, "https://api.moonshot.ai/v1", "KIMI_API_KEY"),
        (ZaiLlm, "https://api.z.ai/api/paas/v4", "GLM_API_KEY"),
        (
            DashscopeLlm,
            "https://dashscope-intl.aliyuncs.com/compatible-mode/v1",
            "DASHSCOPE_API_KEY",
        ),
        (NvidiaLlm, "https://integrate.api.nvidia.com/v1", "NVIDIA_API_KEY"),
        (NousLlm, "https://inference.nousresearch.com/v1", "NOUS_API_KEY"),
        (OllamaCloudLlm, "https://ollama.com/v1", "OLLAMA_API_KEY"),
        (NovitaLlm, "https://api.novita.ai/openai/v1", "NOVITA_API_KEY"),
        (StepfunLlm, "https://api.stepfun.ai/step_plan/v1", "STEPFUN_API_KEY"),
        (ArceeLlm, "https://api.arcee.ai/api/v1", "ARCEEAI_API_KEY"),
        (XiaomiLlm, "https://api.xiaomimimo.com/v1", "XIAOMI_API_KEY"),
        (GmiLlm, "https://api.gmi-serving.com/v1", "GMI_API_KEY"),
        (HuggingFaceLlm, "https://router.huggingface.co/v1", "HF_TOKEN"),
        (OpencodeZenLlm, "https://opencode.ai/zen/v1", "OPENCODE_ZEN_API_KEY"),
        (KilocodeLlm, "https://api.kilo.ai/api/gateway", "KILOCODE_API_KEY"),
        (
            AlibabaCodingPlanLlm,
            "https://coding-intl.dashscope.aliyuncs.com/v1",
            "ALIBABA_CODING_PLAN_API_KEY",
        ),
        (QwenLlm, "https://portal.qwen.ai/v1", "QWEN_API_KEY"),
        (CerebrasLlm, "https://api.cerebras.ai/v1", "CEREBRAS_API_KEY"),
    )

    def test_each_vendor_declares_base_url_and_env_key(self) -> None:
        for cls, base_url, env_key in self._VENDORS:
            with self.subTest(vendor=cls.__name__):
                self.assertEqual(cls.BASE_URL, base_url)
                self.assertEqual(cls.ENV_KEY, env_key)

    def test_chat_path_depends_on_base_url_version_segment(self) -> None:
        # Bare-host vendors append /v1/chat/completions; versioned-base vendors
        # (BASE_URL already ends in its version) append only /chat/completions.
        self.assertEqual(GroqLlm.CHAT_PATH, "/v1/chat/completions")
        self.assertEqual(MoonshotLlm.CHAT_PATH, "/chat/completions")
        self.assertEqual(NovitaLlm.CHAT_PATH, "/chat/completions")

    def test_versioned_vendor_posts_to_chat_completions(self) -> None:
        # MoonshotLlm BASE_URL ends in /v1, so the effective URL is
        # api.moonshot.ai/v1/chat/completions -- the path must not double /v1.
        client = _StubClient({"content": []})
        MoonshotLlm(model="m", client=client).decide(system="s", history=[], tools=[])
        self.assertEqual(client.last_path, "/chat/completions")

    def test_missing_key_raises_runtimeerror_naming_env_var(self) -> None:
        for cls, _base_url, env_key in self._VENDORS:
            with self.subTest(vendor=cls.__name__):
                old = os.environ.pop(env_key, None)
                try:
                    with self.assertRaises(RuntimeError) as ctx:
                        cls(model="m")
                    self.assertIn(env_key, str(ctx.exception))
                finally:
                    if old is not None:
                        os.environ[env_key] = old


class TestFactory(unittest.TestCase):
    def test_build_known_providers(self):
        client = _StubClient({"content": []})
        self.assertIsInstance(build_llm("anthropic", "m", client=client), AnthropicLlm)
        self.assertIsInstance(build_llm("openai", "m", client=client), OpenAiLlm)
        self.assertIsInstance(build_llm("gemini", "m", client=client), GeminiLlm)
        self.assertIsInstance(build_llm("groq", "m", client=client), GroqLlm)
        self.assertIsInstance(build_llm("mistral", "m", client=client), MistralLlm)
        self.assertIsInstance(build_llm("deepseek", "m", client=client), DeepSeekLlm)
        self.assertIsInstance(build_llm("xai", "m", client=client), XaiLlm)
        self.assertIsInstance(build_llm("openrouter", "m", client=client), OpenRouterLlm)
        self.assertIsInstance(build_llm("together", "m", client=client), TogetherLlm)
        self.assertIsInstance(build_llm("fireworks", "m", client=client), FireworksLlm)
        self.assertIsInstance(build_llm("moonshot", "m", client=client), MoonshotLlm)
        self.assertIsInstance(build_llm("zai", "m", client=client), ZaiLlm)
        self.assertIsInstance(build_llm("dashscope", "m", client=client), DashscopeLlm)
        self.assertIsInstance(build_llm("nvidia", "m", client=client), NvidiaLlm)
        self.assertIsInstance(build_llm("nous", "m", client=client), NousLlm)
        self.assertIsInstance(build_llm("ollama_cloud", "m", client=client), OllamaCloudLlm)
        self.assertIsInstance(build_llm("novita", "m", client=client), NovitaLlm)
        self.assertIsInstance(build_llm("stepfun", "m", client=client), StepfunLlm)
        self.assertIsInstance(build_llm("arcee", "m", client=client), ArceeLlm)
        self.assertIsInstance(build_llm("xiaomi", "m", client=client), XiaomiLlm)
        self.assertIsInstance(build_llm("gmi", "m", client=client), GmiLlm)
        self.assertIsInstance(build_llm("huggingface", "m", client=client), HuggingFaceLlm)
        self.assertIsInstance(build_llm("minimax", "m", client=client), MinimaxLlm)
        self.assertIsInstance(build_llm("minimax_cn", "m", client=client), MinimaxCnLlm)
        self.assertIsInstance(build_llm("opencode_zen", "m", client=client), OpencodeZenLlm)
        self.assertIsInstance(build_llm("kilocode", "m", client=client), KilocodeLlm)
        self.assertIsInstance(
            build_llm("alibaba_coding_plan", "m", client=client), AlibabaCodingPlanLlm
        )
        self.assertIsInstance(build_llm("qwen", "m", client=client), QwenLlm)
        self.assertIsInstance(build_llm("cerebras", "m", client=client), CerebrasLlm)
        self.assertIsInstance(build_llm("bedrock", "m", client=client), BedrockLlm)
        self.assertIsInstance(
            build_llm("openai_compat", "m", client=client, base_url="http://h:1/v1"),
            OpenAiCompatLlm,
        )

    def test_api_key_is_threaded_to_provider(self):
        # No client, no env: the key must reach the provider and become the
        # Authorization bearer header on its constructed client (R8 resolution).
        llm = build_llm("openai", "m", api_key="sk-threaded")
        self.assertEqual(llm._client.headers["Authorization"], "Bearer sk-threaded")
        vendor = build_llm("groq", "m", api_key="gk")
        self.assertEqual(vendor._client.headers["Authorization"], "Bearer gk")
        anthropic = build_llm("anthropic", "m", api_key="ak")
        self.assertEqual(anthropic._client.headers["x-api-key"], "ak")
        gemini = build_llm("gemini", "m", api_key="gemk")
        self.assertEqual(gemini._client.headers["x-goog-api-key"], "gemk")
        compat = build_llm("openai_compat", "m", base_url="http://h:1/v1", api_key="ck")
        self.assertEqual(compat._client.headers["Authorization"], "Bearer ck")

    def test_unknown_provider_raises(self):
        with self.assertRaises(ValueError) as ctx:
            build_llm("bogus", "m")
        for known in (
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
        ):
            self.assertIn(known, str(ctx.exception))

    def test_openai_compat_requires_base_url(self):
        with self.assertRaises(ValueError) as ctx:
            build_llm("openai_compat", "m")
        self.assertIn("openai_compat requires base_url", str(ctx.exception))


if __name__ == "__main__":
    unittest.main()
