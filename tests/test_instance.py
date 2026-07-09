"""Per-instance autonomy + strict context isolation (I4).

An instance decides on its OWN projection only; it can never see a peer's system
prompt or an utterance directed between two other instances.
"""

from __future__ import annotations

import unittest

from recette.instance import BROADCAST, AgentInstance, Conversation
from recette.llm import LlmDecision, StubLlm


class TestAgentInstance(unittest.TestCase):
    def test_decide_uses_own_system_and_backend(self) -> None:
        seen: dict = {}

        class SpyLlm(StubLlm):
            def decide(self, *, system, history, tools):
                seen["system"] = system
                return LlmDecision(kind="final", text="ok")

        inst = AgentInstance(
            instance_id="a", role="attacker", system="PRIVATE-A", backend=SpyLlm([])
        )
        inst.decide(history=[], tools=[])
        self.assertEqual(seen["system"], "PRIVATE-A")


class TestConversationIsolation(unittest.TestCase):
    def test_projection_excludes_peer_and_never_carries_system(self) -> None:
        convo = Conversation("s1")
        convo.append(sender="a", recipient="b", content="a->b")
        convo.append(sender="b", recipient="a", content="b->a")
        convo.append(sender="c", recipient="d", content="c->d private")  # not for a/b

        view_a = convo.project("a")
        contents = [m.content for m in view_a]
        self.assertIn("a->b", contents)
        self.assertIn("b->a", contents)
        self.assertNotIn("c->d private", contents)  # A cannot see C<->D
        # A's own line is 'assistant', the peer's is 'user'; no system anywhere.
        roles = {m.content: m.role for m in view_a}
        self.assertEqual(roles["a->b"], "assistant")
        self.assertEqual(roles["b->a"], "user")

    def test_broadcast_is_visible_to_all(self) -> None:
        convo = Conversation("s1")
        convo.append(sender="a", recipient=BROADCAST, content="hello all")
        self.assertIn("hello all", [m.content for m in convo.project("z")])

    def test_two_instances_share_no_state(self) -> None:
        # Distinct backends -> distinct decision streams: no common instance.
        a = AgentInstance("a", "r", "sys-a", StubLlm([LlmDecision(kind="final", text="from-a")]))
        b = AgentInstance("b", "r", "sys-b", StubLlm([LlmDecision(kind="final", text="from-b")]))
        self.assertEqual(a.decide([]).text, "from-a")
        self.assertEqual(b.decide([]).text, "from-b")
        self.assertIsNot(a.backend, b.backend)

    def test_empty_session_id_rejected(self) -> None:
        with self.assertRaises(ValueError):
            Conversation("")


if __name__ == "__main__":
    unittest.main()
