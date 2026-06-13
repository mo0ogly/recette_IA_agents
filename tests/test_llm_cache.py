"""Content-addressed LLM cache: a live call is paid once, then reproduces free (I4).

Dependency-free analog of langwatch/scenario's joblib cache: keyed by the call
inputs (namespace, system, history, tools), persisted to JSON.
"""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from recette.llm import LlmDecision, Message, ToolSpec
from recette.llm_cache import CachingLlm, LlmCache, call_key


class _CountingLlm:
    """Returns a fixed decision; counts how many times it was actually called."""

    def __init__(self, decision: LlmDecision) -> None:
        self.decision = decision
        self.calls = 0

    def decide(self, *, system, history, tools):  # type: ignore[no-untyped-def]
        self.calls += 1
        return self.decision


_TOOLS = [ToolSpec(name="t", description="d", parameters={"type": "object"})]
_DECISION = LlmDecision(kind="tool_call", tool_name="t", tool_args={"x": 1})


class TestCallKey(unittest.TestCase):
    def test_key_is_stable_and_input_sensitive(self) -> None:
        k1 = call_key("ns", "sys", [Message("user", "hi")], _TOOLS)
        k2 = call_key("ns", "sys", [Message("user", "hi")], _TOOLS)
        self.assertEqual(k1, k2)
        self.assertNotEqual(k1, call_key("ns", "sys", [Message("user", "bye")], _TOOLS))
        self.assertNotEqual(k1, call_key("other", "sys", [Message("user", "hi")], _TOOLS))


class TestCachingLlm(unittest.TestCase):
    def test_hit_does_not_call_inner_again(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            inner = _CountingLlm(_DECISION)
            llm = CachingLlm(inner, cache=LlmCache(Path(tmp) / "c.json"))
            a = llm.decide(system="s", history=[Message("user", "go")], tools=_TOOLS)
            b = llm.decide(system="s", history=[Message("user", "go")], tools=_TOOLS)
            self.assertEqual(a, b)
            self.assertEqual(inner.calls, 1)  # second was a cache hit
            self.assertEqual((llm.hits, llm.misses), (1, 1))

    def test_persists_across_instances(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "c.json"
            warm = _CountingLlm(_DECISION)
            CachingLlm(warm, cache=LlmCache(path)).decide(
                system="s", history=[Message("user", "go")], tools=_TOOLS
            )
            # A fresh process (new cache + new inner) reads the file and hits.
            cold = _CountingLlm(LlmDecision(kind="final", text="should-not-be-used"))
            llm = CachingLlm(cold, cache=LlmCache(path))
            d = llm.decide(system="s", history=[Message("user", "go")], tools=_TOOLS)
            self.assertEqual(d, _DECISION)
            self.assertEqual(cold.calls, 0)

    def test_miss_on_different_input(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            inner = _CountingLlm(_DECISION)
            llm = CachingLlm(inner, cache=LlmCache(Path(tmp) / "c.json"))
            llm.decide(system="s", history=[Message("user", "a")], tools=_TOOLS)
            llm.decide(system="s", history=[Message("user", "b")], tools=_TOOLS)
            self.assertEqual(inner.calls, 2)


if __name__ == "__main__":
    unittest.main()
