"""Tests for the optional PyRIT-backed adversarial attacker (P4).

The attacker is import-guarded: constructing ``PyritAttacker`` must NOT import
pyrit (so the deterministic gate stays dependency-free, R20). Only ``__call__``
touches pyrit, and when pyrit is absent it raises a clear RuntimeError pointing
at the ``[real]``/``[redteam]`` extra -- never a bare ImportError.

When pyrit IS installed, the active path is exercised; when it is not (the audit
venv / CI default), that test SKIPS. A skip here is acceptable ONLY because the
deterministic red-team core (RedTeamSimulator + RecordingLlm) is covered by the
StubLlm tests in test_redteam_record / test_redteam_recette (skip != pass).
"""

import importlib.util
import unittest

_HAS_PYRIT = importlib.util.find_spec("pyrit") is not None


class T(unittest.TestCase):
    def test_construction_does_not_import_pyrit(self):
        # Constructing the attacker must be dependency-free: it only stores config,
        # the lazy import happens inside __call__. This is what lets the absent-guard
        # test below construct the object and then assert on the call.
        from recette.redteam_record import PyritAttacker

        att = PyritAttacker(objective="out-of-scope write", provider="groq", model="x")
        self.assertEqual(att.objective, "out-of-scope write")
        self.assertEqual(att.max_turns, 4)

    def test_import_guard_message_when_absent(self):
        # When pyrit is NOT installed, constructing/using the attacker must raise
        # a clear RuntimeError pointing at the [real] extra (not a bare ImportError).
        from recette.redteam_record import PyritAttacker

        att = PyritAttacker(objective="out-of-scope write", provider="groq", model="x")
        if _HAS_PYRIT:
            self.skipTest("pyrit installed; guard path not exercised")
        with self.assertRaises(RuntimeError) as ctx:
            att([])
        self.assertIn("real", str(ctx.exception).lower())

    @unittest.skipUnless(_HAS_PYRIT, "pyrit not installed")
    def test_pyrit_attacker_yields_first_message(self):
        from recette.redteam_record import PyritAttacker

        att = PyritAttacker(objective="out-of-scope write", provider="groq", model="x")
        msg = att([])
        self.assertIsInstance(msg, str)
        self.assertTrue(msg)

    @unittest.skipUnless(_HAS_PYRIT, "pyrit not installed")
    def test_pyrit_attacker_ends_after_max_turns(self):
        from recette.llm import Message
        from recette.redteam_record import PyritAttacker

        att = PyritAttacker(objective="out-of-scope write", provider="groq", model="x", max_turns=2)
        history = [Message(role="user", content="t1"), Message(role="user", content="t2")]
        self.assertIsNone(att(history))


if __name__ == "__main__":
    unittest.main()
