"""Gap #3: the generated agent registry projects subject metadata (pure row)."""

from __future__ import annotations

import unittest

from recette.registry import registry_row


class TestRegistryRow(unittest.TestCase):
    def test_projects_core_and_metadata_fields(self) -> None:
        manifest = {
            "agent_id": "gl-release-bot",
            "name": "GitLab Release Bot",
            "version": "1.0.0",
            "target_systems": ["gitlab"],
            "capability_scope": [{"action": "read_repo"}, {"action": "open_pr"}],
            "source": {"standard": "microsoft-agent-framework"},
            "metadata": {
                "publisher": {"name": "acme-platform", "contact": "p@acme.test"},
                "compliance": ["soc2"],
                "party": "1p",
                "tags": ["gitlab", "release"],
            },
        }
        row = registry_row(manifest, "git")
        self.assertEqual(row["agent_id"], "gl-release-bot")
        self.assertEqual(row["family"], "git")
        self.assertEqual(row["capabilities"], 2)
        self.assertEqual(row["publisher"], "acme-platform")
        self.assertEqual(row["compliance"], ["soc2"])
        self.assertEqual(row["party"], "1p")
        self.assertEqual(row["standard"], "microsoft-agent-framework")

    def test_absent_metadata_is_none_or_empty_never_invented(self) -> None:
        row = registry_row({"agent_id": "x", "name": "X"}, "git")
        self.assertIsNone(row["publisher"])
        self.assertIsNone(row["party"])
        self.assertEqual(row["compliance"], [])
        self.assertEqual(row["tags"], [])
        self.assertEqual(row["kind"], "git_agent")


try:
    from fastapi.testclient import TestClient

    from recette.api.app import create_app

    _HAVE_FASTAPI = True
except ImportError:  # pragma: no cover
    _HAVE_FASTAPI = False


@unittest.skipUnless(_HAVE_FASTAPI, "fastapi not installed")
class TestRegistryRoute(unittest.TestCase):
    def test_generated_registry_includes_seeded_metadata(self) -> None:
        body = TestClient(create_app()).get("/registry/agents").json()
        self.assertTrue(body["generated"])
        self.assertGreater(body["count"], 0)
        # The seeded exemplar carries its registry metadata through the aggregate.
        rel = next((r for r in body["agents"] if r["agent_id"] == "gl-release-bot"), None)
        self.assertIsNotNone(rel)
        assert rel is not None
        self.assertEqual(rel["party"], "1p")
        self.assertIn("soc2", rel["compliance"])


if __name__ == "__main__":
    unittest.main()
