"""LB1 tests: LLM backends. Offline -- providers driven by a stub HTTP client (no key/network)."""

from __future__ import annotations

import os
import unittest
from typing import Any

from recette.llm import (
    AnthropicLlm,
    GroqLlm,
    LlmDecision,
    Message,
    OpenAiCompatLlm,
    OpenAiLlm,
    StubLlm,
    ToolSpec,
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


class TestFactory(unittest.TestCase):
    def test_build_known_providers(self):
        client = _StubClient({"content": []})
        self.assertIsInstance(build_llm("anthropic", "m", client=client), AnthropicLlm)
        self.assertIsInstance(build_llm("openai", "m", client=client), OpenAiLlm)

    def test_unknown_provider_raises(self):
        with self.assertRaises(ValueError):
            build_llm("ollama", "m")


if __name__ == "__main__":
    unittest.main()
