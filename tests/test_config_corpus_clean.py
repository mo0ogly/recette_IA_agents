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
import os
import unittest
from pathlib import Path

from recette.api.config_store import default_config_path

# Audit the REPO's tracked corpus directly (not default_config_path(), which the
# suite redirects to a throwaway copy): this gate must always read the committed
# artifact so a leak in version control fails the build.
TRACKED_CORPUS = Path(__file__).resolve().parents[1] / "config" / "inspect_ia_agents.config.json"

# The seed corpus is agents/servers/backends + the schema version. Anything else
# at the top level is either op-state (belongs in the sidecar) or junk.
ALLOWED_TOP_LEVEL_KEYS = {"schema_version", "agents", "ai_backends", "servers"}

# Operational keys that MUST live in the gitignored runtime sidecar, never the
# tracked corpus. Listed explicitly so the failure message names the offender.
FORBIDDEN_OP_STATE_KEYS = {"containment"}


class ConfigCorpusCleanTests(unittest.TestCase):
    def setUp(self) -> None:
        if not TRACKED_CORPUS.exists():
            self.skipTest(f"no tracked corpus at {TRACKED_CORPUS}")
        self.cfg = json.loads(TRACKED_CORPUS.read_text(encoding="utf-8"))
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


class SuiteConfigIsolationTests(unittest.TestCase):
    """When the suite runs via ./recette.sh test, the config path is redirected
    to a throwaway COPY so no test can write the tracked corpus. This asserts the
    isolation is actually in effect (it is a no-op skip when run ad hoc without
    the wrapper, e.g. a bare `python -m unittest`)."""

    def test_suite_config_path_is_not_the_tracked_corpus(self) -> None:
        env_path = os.environ.get("INSPECT_IA_AGENTS_CONFIG_PATH")
        if not env_path:
            self.skipTest("ad-hoc run: INSPECT_IA_AGENTS_CONFIG_PATH not set by the wrapper")
        self.assertNotEqual(
            Path(env_path).resolve(),
            TRACKED_CORPUS.resolve(),
            "the test suite is pointed at the TRACKED corpus; a writing test would "
            "pollute it -- the recette.sh wrapper must redirect to a throwaway copy",
        )
        # And default_config_path() honours that redirection.
        self.assertEqual(default_config_path().resolve(), Path(env_path).resolve())


if __name__ == "__main__":
    unittest.main()
