"""Assist copilot HTTP surface: prompts catalog, chat, session memory.

Exercises the /assist router through TestClient with a StubLlm injected via
``app.state.llm_factory`` (no key, no network), the same harness pattern as
tests/test_api_config_routes.py.
"""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

try:
    from fastapi.testclient import TestClient

    from recette.api.app import create_app
    from recette.api.config_store import ConfigStore
    from recette.api.prompt_store import PromptStore
    from recette.api.secret_store import BackendSecretStore
    from recette.llm import LlmDecision, StubLlm

    _HAS_FASTAPI = True
except ImportError:  # pragma: no cover
    _HAS_FASTAPI = False


@unittest.skipUnless(_HAS_FASTAPI, "requires the [api] extra (fastapi)")
class AssistRoutesBase(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        root = Path(self.tmp.name)
        self.config_store = ConfigStore(root / "cfg.json")
        self.secret_store = BackendSecretStore(root / "secrets.json")
        self.prompt_store = PromptStore(root / "overrides.json")
        self.app = create_app(
            config_store=self.config_store,
            secret_store=self.secret_store,
            prompt_store=self.prompt_store,
        )
        self.client = TestClient(self.app)

    def tearDown(self) -> None:
        self.tmp.cleanup()

    def _add_backend(self, backend_id: str = "b1") -> None:
        r = self.client.post(
            "/config/ai-backends",
            json={"id": backend_id, "provider": "groq", "model": "test-model"},
        )
        self.assertEqual(r.status_code, 201)

    def _stub_factory(self, replies: list[str], captured: dict | None = None):
        # ONE StubLlm shared across factory calls so scripted replies advance
        # from one chat exchange to the next.
        stub = StubLlm([LlmDecision(kind="final", text=text) for text in replies])

        def factory(provider, model, *, base_url=None, api_key=None):
            if captured is not None:
                captured["provider"] = provider
                captured["model"] = model
                captured["api_key"] = api_key

            if captured is None:
                return stub

            class CapturingStub:
                def decide(self, *, system, history, tools):
                    captured["system"] = system
                    captured["history"] = history
                    return stub.decide(system=system, history=history, tools=tools)

            return CapturingStub()

        return factory


class TestAssistPrompts(AssistRoutesBase):
    def test_catalog_lists_defaults(self) -> None:
        body = self.client.get("/assist/prompts").json()
        entries = {e["id"]: e for e in body["prompts"]}
        self.assertIn("chat.system", entries)
        self.assertIn("help.system", entries)
        for entry in body["prompts"]:
            self.assertIn(entry["kind"], ("text", "json"))
            self.assertFalse(entry["overridden"])
            self.assertEqual(entry["value"], entry["default"])
            for key in ("view", "trigger", "endpoint", "component", "loc"):
                self.assertIn(key, entry["localisation"])

    def test_override_lifecycle(self) -> None:
        r = self.client.put("/assist/prompts/chat.system", json={"value": "custom fr prompt"})
        self.assertEqual(r.status_code, 200)
        entry = r.json()
        self.assertTrue(entry["overridden"])
        self.assertEqual(entry["value"], "custom fr prompt")
        self.assertNotEqual(entry["default"], "custom fr prompt")
        # Reset restores the default.
        self.assertEqual(self.client.delete("/assist/prompts/chat.system").status_code, 204)
        body = self.client.get("/assist/prompts").json()
        entry = next(e for e in body["prompts"] if e["id"] == "chat.system")
        self.assertFalse(entry["overridden"])
        self.assertEqual(entry["value"], entry["default"])

    def test_put_validation(self) -> None:
        self.assertEqual(
            self.client.put("/assist/prompts/nope", json={"value": "x"}).status_code, 404
        )
        self.assertEqual(
            self.client.put("/assist/prompts/chat.system", json={"value": "  "}).status_code, 400
        )
        # kind json rejects a bare string; kind text rejects a dict.
        self.assertEqual(
            self.client.put("/assist/prompts/help.levels", json={"value": "text"}).status_code,
            400,
        )
        self.assertEqual(
            self.client.put("/assist/prompts/chat.system", json={"value": {"a": 1}}).status_code,
            400,
        )
        self.assertEqual(self.client.delete("/assist/prompts/nope").status_code, 404)

    def test_json_prompt_override(self) -> None:
        value = {"debutant": "custom", "expert": "custom expert"}
        r = self.client.put("/assist/prompts/help.levels", json={"value": value})
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.json()["value"], value)


class TestAssistChat(AssistRoutesBase):
    def test_chat_happy_path_appends_both_turns(self) -> None:
        self._add_backend()
        self.app.state.llm_factory = self._stub_factory(["bonjour, je suis le copilote"])
        r = self.client.post(
            "/assist/chat",
            json={"session_id": "s-1", "backend_id": "b1", "message": "salut"},
        )
        self.assertEqual(r.status_code, 200)
        body = r.json()
        self.assertEqual(body["source"], "llm")
        self.assertEqual(body["reply"], "bonjour, je suis le copilote")
        self.assertEqual(body["model"], "test-model")
        self.assertIsNone(body["error"])
        roles = [(m["role"], m["source"]) for m in body["thread"]]
        self.assertEqual(roles, [("user", "user"), ("assistant", "llm")])
        for message in body["thread"]:
            self.assertIn("id", message)
            self.assertIn("created_at", message)

    def test_chat_uses_prompt_override_and_secret(self) -> None:
        self._add_backend()
        self.secret_store.set_secret("b1", "sk-test-123")
        self.client.put("/assist/prompts/chat.system", json={"value": "OVERRIDE-SYSTEM"})
        captured: dict = {}
        self.app.state.llm_factory = self._stub_factory(["ok"], captured)
        self.client.post(
            "/assist/chat",
            json={"session_id": "s-1", "backend_id": "b1", "message": "salut"},
        )
        # Hot-reloaded override reaches the model; the per-backend secret is
        # resolved server-side (R8) and handed to the factory.
        self.assertTrue(captured["system"].startswith("OVERRIDE-SYSTEM"))
        self.assertEqual(captured["api_key"], "sk-test-123")
        self.assertEqual(captured["provider"], "groq")

    def test_chat_multi_turn_history_replayed(self) -> None:
        self._add_backend()
        captured: dict = {}
        self.app.state.llm_factory = self._stub_factory(["r1", "r2"], captured)
        self.client.post(
            "/assist/chat", json={"session_id": "s-1", "backend_id": "b1", "message": "q1"}
        )
        self.client.post(
            "/assist/chat", json={"session_id": "s-1", "backend_id": "b1", "message": "q2"}
        )
        # Second call sees q1 + r1 + q2 (bounded replay window).
        contents = [(m.role, m.content) for m in captured["history"]]
        self.assertEqual(contents, [("user", "q1"), ("assistant", "r1"), ("user", "q2")])

    def test_chat_thread_is_bounded(self) -> None:
        from recette.api.assist_sessions import MAX_THREAD_MESSAGES

        self._add_backend()
        self.app.state.llm_factory = self._stub_factory([f"r{i}" for i in range(30)])
        for i in range(30):
            self.client.post(
                "/assist/chat",
                json={"session_id": "s-1", "backend_id": "b1", "message": f"q{i}"},
            )
        thread = self.client.get("/assist/sessions/s-1").json()["thread"]
        self.assertEqual(len(thread), MAX_THREAD_MESSAGES)
        # Oldest turns evicted; the newest exchange is last.
        self.assertEqual(thread[-2]["content"], "q29")
        self.assertEqual(thread[-1]["content"], "r29")

    def test_chat_validation_errors(self) -> None:
        self._add_backend()
        r = self.client.post(
            "/assist/chat", json={"session_id": "s-1", "backend_id": "b1", "message": "  "}
        )
        self.assertEqual(r.status_code, 400)
        r = self.client.post(
            "/assist/chat", json={"session_id": " ", "backend_id": "b1", "message": "x"}
        )
        self.assertEqual(r.status_code, 400)
        r = self.client.post(
            "/assist/chat", json={"session_id": "s-1", "backend_id": "nope", "message": "x"}
        )
        self.assertEqual(r.status_code, 404)

    def test_llm_failure_maps_to_source_error_never_500(self) -> None:
        self._add_backend()

        def raising_factory(provider, model, *, base_url=None, api_key=None):
            raise RuntimeError("provider unreachable")

        self.app.state.llm_factory = raising_factory
        r = self.client.post(
            "/assist/chat",
            json={"session_id": "s-1", "backend_id": "b1", "message": "salut"},
        )
        self.assertEqual(r.status_code, 200)
        body = r.json()
        self.assertEqual(body["source"], "error")
        self.assertIn("provider unreachable", body["error"])
        self.assertIsNone(body["model"])
        # The failed turn is visible in the thread but flagged as error...
        self.assertEqual(body["thread"][-1]["source"], "error")
        # ...and a later successful call does NOT replay it to the model.
        captured: dict = {}
        self.app.state.llm_factory = self._stub_factory(["ok"], captured)
        self.client.post(
            "/assist/chat", json={"session_id": "s-1", "backend_id": "b1", "message": "retry"}
        )
        replayed = [(m.role, m.content) for m in captured["history"]]
        self.assertEqual(replayed, [("user", "salut"), ("user", "retry")])


class TestAssistSessions(AssistRoutesBase):
    def test_unknown_session_reads_empty(self) -> None:
        body = self.client.get("/assist/sessions/ghost").json()
        self.assertEqual(body, {"thread": [], "insights": []})

    def test_clear_session(self) -> None:
        self._add_backend()
        self.app.state.llm_factory = self._stub_factory(["ok"])
        self.client.post(
            "/assist/chat", json={"session_id": "s-1", "backend_id": "b1", "message": "salut"}
        )
        self.assertEqual(len(self.client.get("/assist/sessions/s-1").json()["thread"]), 2)
        self.assertEqual(self.client.delete("/assist/sessions/s-1").status_code, 204)
        self.assertEqual(self.client.get("/assist/sessions/s-1").json()["thread"], [])
        # Idempotent.
        self.assertEqual(self.client.delete("/assist/sessions/s-1").status_code, 204)

    def test_sessions_are_isolated(self) -> None:
        self._add_backend()
        self.app.state.llm_factory = self._stub_factory(["a", "b"])
        self.client.post(
            "/assist/chat", json={"session_id": "s-1", "backend_id": "b1", "message": "un"}
        )
        self.client.post(
            "/assist/chat", json={"session_id": "s-2", "backend_id": "b1", "message": "deux"}
        )
        t1 = self.client.get("/assist/sessions/s-1").json()["thread"]
        t2 = self.client.get("/assist/sessions/s-2").json()["thread"]
        self.assertEqual(t1[0]["content"], "un")
        self.assertEqual(t2[0]["content"], "deux")

    def test_topics_stub_empty(self) -> None:
        self.assertEqual(self.client.get("/assist/topics").json(), {"topics": []})


class TestAssistSessionStoreBounds(unittest.TestCase):
    def test_lru_eviction_cap(self) -> None:
        from recette.api.assist_sessions import AssistSessionStore

        store = AssistSessionStore(max_sessions=3)
        for n in range(4):
            store.get_or_create(f"s-{n}")
        self.assertEqual(store.count(), 3)
        self.assertIsNone(store.get("s-0"))
        self.assertIsNotNone(store.get("s-3"))

    def test_lru_touch_on_access(self) -> None:
        from recette.api.assist_sessions import AssistSessionStore

        store = AssistSessionStore(max_sessions=2)
        store.get_or_create("s-a")
        store.get_or_create("s-b")
        store.get_or_create("s-a")  # touch: s-b becomes the eviction candidate
        store.get_or_create("s-c")
        self.assertIsNotNone(store.get("s-a"))
        self.assertIsNone(store.get("s-b"))


class TestAssistPromptHelpers(unittest.TestCase):
    def test_wrap_untrusted_fences_and_truncates(self) -> None:
        from recette.api.assist_prompts import MAX_UNTRUSTED_CHARS, wrap_untrusted

        wrapped = wrap_untrusted("payload", "journal")
        self.assertTrue(wrapped.startswith("<<<journal>>>\n"))
        self.assertTrue(wrapped.endswith("\n<<<fin_journal>>>"))
        big = wrap_untrusted("x" * (MAX_UNTRUSTED_CHARS + 500), "journal")
        inner = big.split("\n")[1]
        self.assertEqual(len(inner), MAX_UNTRUSTED_CHARS)

    def test_journal_summary_shape(self) -> None:
        from recette.api.assist_prompts import journal_summary

        self.assertEqual(journal_summary([]), "")
        insights = [
            {"topic": "t1", "label": "Agents", "answer": "reponse un"},
            {"topic": "t2", "label": "Verdicts", "answer": "x" * 300},
        ]
        recap = journal_summary(insights)
        self.assertIn("JOURNAL D'ANALYSE", recap)
        self.assertIn("- Agents: reponse un", recap)
        # Long answers truncated per line.
        self.assertIn("...", recap)
        self.assertNotIn("x" * 250, recap)


if __name__ == "__main__":
    unittest.main()
