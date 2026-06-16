"""Guard: the tracked config corpus carries ONLY corpus keys, never op-state.

Anti-recurrence gate for the containment session (R20 / no-silent-recette-gaps):
a UI toggle of an OPERATIONAL flag (containment, ...) must persist to the
gitignored ``<config>.runtime.json`` sidecar, NEVER the versioned
``config/inspect_ia_agents.config.json``. If ``set_containment`` (or any future
op-state setter) ever writes the corpus again, or someone bakes a runtime concept
into it, this test goes RED -- the leak is no longer something to find by hand.

Deterministic: a pure read of the committed corpus, no clock/network/order
dependence (I4).
"""

from __future__ import annotations

import json
import unittest

from recette.api.config_store import default_config_path

# The seed corpus is agents/servers/backends + the schema version. Anything else
# at the top level is either op-state (belongs in the sidecar) or junk.
ALLOWED_TOP_LEVEL_KEYS = {"schema_version", "agents", "ai_backends", "servers"}

# Operational keys that MUST live in the gitignored runtime sidecar, never the
# tracked corpus. Listed explicitly so the failure message names the offender.
FORBIDDEN_OP_STATE_KEYS = {"containment"}


class ConfigCorpusCleanTests(unittest.TestCase):
    def setUp(self) -> None:
        path = default_config_path()
        if not path.exists():
            self.skipTest(f"no tracked corpus at {path}")
        self.cfg = json.loads(path.read_text(encoding="utf-8"))
        self.keys = set(self.cfg)

    def test_no_operational_state_leaked_into_the_corpus(self) -> None:
        leaked = self.keys & FORBIDDEN_OP_STATE_KEYS
        self.assertEqual(
            leaked,
            set(),
            f"operational state {sorted(leaked)} leaked into the tracked corpus; "
            "it must persist to the gitignored <config>.runtime.json sidecar",
        )

    def test_only_corpus_keys_are_present(self) -> None:
        unexpected = self.keys - ALLOWED_TOP_LEVEL_KEYS
        self.assertEqual(
            unexpected,
            set(),
            f"unexpected top-level key(s) {sorted(unexpected)} in the tracked corpus; "
            f"allowed: {sorted(ALLOWED_TOP_LEVEL_KEYS)} (op-state goes in the sidecar)",
        )


if __name__ == "__main__":
    unittest.main()
