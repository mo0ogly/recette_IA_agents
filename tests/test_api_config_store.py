"""U1: versioned config store for Lane B agents + AI backends + servers."""

from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from recette.api.config_store import ConfigStore, UnknownAgentError, UnknownServerError


class TestConfigStore(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.path = Path(self.tmp.name) / "cfg.json"
        self.store = ConfigStore(self.path)

    def tearDown(self) -> None:
        self.tmp.cleanup()

    def test_missing_file_reads_empty_default(self) -> None:
        cfg = self.store.read()
        self.assertEqual(cfg["schema_version"], "1.0")
        self.assertEqual(cfg["agents"], [])
        self.assertEqual(cfg["ai_backends"], [])
        self.assertFalse(self.path.exists())  # read never creates

    def test_add_agent_persists_and_roundtrips(self) -> None:
        agent = {
            "id": "a1",
            "principal": "acme-bot@github",
            "target_system": "github",
            "goal": "bump deps",
            "capability_scope": ["read_repo", "open_pr"],
            "ai_backend_id": "b1",
            "runtime": "lab",
        }
        self.store.add_agent(agent)
        on_disk = json.loads(self.path.read_text())
        self.assertEqual(on_disk["agents"], [agent])
        # a fresh store over the same file sees it
        self.assertEqual(ConfigStore(self.path).get_agent("a1"), agent)

    def test_add_ai_backend_rejects_key_fields(self) -> None:
        with self.assertRaises(ValueError):
            self.store.add_ai_backend(
                {"id": "b1", "provider": "anthropic", "model": "x", "api_key": "sekret"}
            )

    def test_add_ai_backend_rejects_password_fields(self) -> None:
        for fname in ("password", "passwd"):
            with self.assertRaises(ValueError, msg=f"field {fname!r} must be rejected"):
                self.store.add_ai_backend(
                    {"id": "b1", "provider": "anthropic", "model": "x", fname: "sekret"}
                )

    def test_duplicate_id_rejected(self) -> None:
        self.store.add_ai_backend({"id": "b1", "provider": "openai", "model": "gpt"})
        with self.assertRaises(ValueError):
            self.store.add_ai_backend({"id": "b1", "provider": "openai", "model": "gpt"})

    def test_update_and_delete_agent(self) -> None:
        self.store.add_agent(
            {
                "id": "a1",
                "principal": "p",
                "target_system": "github",
                "goal": "g",
                "capability_scope": [],
                "ai_backend_id": "b1",
                "runtime": "lab",
            }
        )
        self.store.update_agent("a1", {"goal": "g2"})
        self.assertEqual(self.store.get_agent("a1")["goal"], "g2")
        self.store.delete_agent("a1")
        self.assertIsNone(self.store.get_agent("a1"))

    def test_update_unknown_agent_raises_unknown_agent_error(self) -> None:
        with self.assertRaises(UnknownAgentError):
            self.store.update_agent("nope", {"goal": "x"})

    def test_delete_unknown_agent_raises(self) -> None:
        # Strict 404 semantics, mirroring delete_server (no silent idempotency).
        with self.assertRaises(UnknownAgentError):
            self.store.delete_agent("nope")
        self.assertTrue(issubclass(UnknownAgentError, LookupError))

    def test_update_agent_rejects_bad_runtime_without_writing(self) -> None:
        self.store.add_agent(
            {
                "id": "a1",
                "principal": "p",
                "target_system": "github",
                "goal": "g",
                "capability_scope": [],
                "ai_backend_id": "b1",
                "runtime": "lab",
            }
        )
        with self.assertRaises(ValueError):
            self.store.update_agent("a1", {"runtime": "bogus"})
        # the bad patch must not have been persisted
        self.assertEqual(self.store.get_agent("a1")["runtime"], "lab")


class GroundTruthSectionTests(unittest.TestCase):
    """Optional ground_truth block on agents (used by the verdict judge)."""

    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.path = Path(self.tmp.name) / "cfg.json"
        self.store = ConfigStore(self.path)

    def tearDown(self) -> None:
        self.tmp.cleanup()

    def _agent(self, **extra: object) -> dict:
        return {
            "id": "a1",
            "principal": "bot@acme",
            "target_system": "github",
            "goal": "g",
            "capability_scope": [],
            "ai_backend_id": "b1",
            "runtime": "lab",
            **extra,
        }

    def test_full_ground_truth_block_accepted_and_roundtrips(self) -> None:
        ground_truth = {
            "detectable": True,
            "expected_identity": "bot@acme",
            "dimensions": {
                "identity": True,
                "capabilities": True,
                "policy": True,
                "behavior": True,
            },
            "expected_verdict": "correct",
        }
        self.store.add_agent(self._agent(ground_truth=ground_truth))
        self.assertEqual(self.store.get_agent("a1")["ground_truth"], ground_truth)
        # a fresh store over the same file sees the same block
        self.assertEqual(ConfigStore(self.path).get_agent("a1")["ground_truth"], ground_truth)

    def test_agent_without_ground_truth_still_fine(self) -> None:
        self.store.add_agent(self._agent())
        self.assertNotIn("ground_truth", self.store.get_agent("a1"))

    def test_empty_ground_truth_dict_allowed(self) -> None:
        self.store.add_agent(self._agent(ground_truth={}))
        self.assertEqual(self.store.get_agent("a1")["ground_truth"], {})

    def test_non_dict_ground_truth_rejected(self) -> None:
        with self.assertRaises(ValueError):
            self.store.add_agent(self._agent(ground_truth=["detectable"]))

    def test_bad_verdict_literal_rejected(self) -> None:
        with self.assertRaises(ValueError):
            self.store.add_agent(self._agent(ground_truth={"expected_verdict": "maybe"}))

    def test_non_bool_detectable_rejected(self) -> None:
        with self.assertRaises(ValueError):
            self.store.add_agent(self._agent(ground_truth={"detectable": "yes"}))

    def test_unknown_dimension_key_rejected(self) -> None:
        with self.assertRaises(ValueError):
            self.store.add_agent(self._agent(ground_truth={"dimensions": {"latency": True}}))

    def test_non_bool_dimension_rejected(self) -> None:
        with self.assertRaises(ValueError):
            self.store.add_agent(self._agent(ground_truth={"dimensions": {"identity": "ok"}}))

    def test_non_dict_dimensions_rejected(self) -> None:
        with self.assertRaises(ValueError):
            self.store.add_agent(self._agent(ground_truth={"dimensions": ["identity"]}))

    def test_unknown_top_level_key_rejected(self) -> None:
        with self.assertRaises(ValueError):
            self.store.add_agent(self._agent(ground_truth={"rationale": "because"}))

    def test_partial_ground_truth_allowed(self) -> None:
        self.store.add_agent(self._agent(ground_truth={"detectable": False}))
        self.assertEqual(self.store.get_agent("a1")["ground_truth"], {"detectable": False})

    def test_update_agent_validates_ground_truth_patch_without_writing(self) -> None:
        self.store.add_agent(self._agent(ground_truth={"detectable": True}))
        with self.assertRaises(ValueError):
            self.store.update_agent("a1", {"ground_truth": {"expected_verdict": "bogus"}})
        # the bad patch must not have been persisted
        self.assertEqual(self.store.get_agent("a1")["ground_truth"], {"detectable": True})

    def test_update_agent_accepts_valid_ground_truth_patch(self) -> None:
        self.store.add_agent(self._agent())
        self.store.update_agent("a1", {"ground_truth": {"expected_verdict": "incorrect"}})
        self.assertEqual(
            self.store.get_agent("a1")["ground_truth"], {"expected_verdict": "incorrect"}
        )


class ServerSectionTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.path = Path(self.tmp.name) / "cfg.json"
        self.store = ConfigStore(self.path)

    def tearDown(self) -> None:
        self.tmp.cleanup()

    def test_add_list_update_delete_server(self) -> None:
        self.store.add_server(
            {"id": "gh-mock", "system": "github", "mode": "mock_local", "port": 9101}
        )
        self.assertEqual(self.store.read()["servers"][0]["id"], "gh-mock")
        self.assertEqual(self.store.list_servers()[0]["id"], "gh-mock")
        self.assertEqual(self.store.get_server("gh-mock")["port"], 9101)
        self.store.update_server("gh-mock", {"port": 9102})
        self.assertEqual(self.store.read()["servers"][0]["port"], 9102)
        self.store.delete_server("gh-mock")
        self.assertEqual(self.store.read()["servers"], [])
        self.assertIsNone(self.store.get_server("gh-mock"))

    def test_duplicate_server_id_rejected(self) -> None:
        self.store.add_server(
            {"id": "gh-mock", "system": "github", "mode": "mock_local", "port": 9101}
        )
        with self.assertRaises(ValueError):
            self.store.add_server(
                {"id": "gh-mock", "system": "github", "mode": "mock_local", "port": 9102}
            )

    def test_unknown_mode_rejected(self) -> None:
        with self.assertRaises(ValueError):
            self.store.add_server({"id": "gh-ssh", "system": "github", "mode": "ssh"})

    def test_mode_specific_required_fields(self) -> None:
        with self.assertRaises(ValueError):
            self.store.add_server({"id": "s1", "system": "github", "mode": "mock_local"})
        with self.assertRaises(ValueError):
            self.store.add_server(
                {"id": "s1", "system": "github", "mode": "mock_local", "port": "9101"}
            )
        with self.assertRaises(ValueError):
            self.store.add_server({"id": "s2", "system": "github", "mode": "declared_url"})
        with self.assertRaises(ValueError):
            self.store.add_server({"id": "s3", "system": "github", "mode": "real_saas"})

    def test_honeypot_mode_accepted_with_int_port(self) -> None:
        # A honeypot is a sink server (a target an agent must NEVER reach
        # directly). It reuses the mock_local server shape (port-bound) but a
        # distinct mode so build_allowlist excludes it -> traffic to it is a
        # bypass signal, not a mediated path.
        self.store.add_server(
            {"id": "shadow-db-sink", "system": "shadow_db", "mode": "honeypot", "port": 9113}
        )
        self.assertEqual(self.store.get_server("shadow-db-sink")["mode"], "honeypot")

    def test_honeypot_mode_requires_int_port(self) -> None:
        with self.assertRaises(ValueError):
            self.store.add_server({"id": "hp", "system": "shadow_db", "mode": "honeypot"})
        with self.assertRaises(ValueError):
            self.store.add_server(
                {"id": "hp", "system": "shadow_db", "mode": "honeypot", "port": "9113"}
            )

    def test_secret_fields_rejected(self) -> None:
        with self.assertRaises(ValueError):
            self.store.add_server(
                {
                    "id": "gh-real",
                    "system": "github",
                    "mode": "declared_url",
                    "base_url": "https://gh.example",
                    "token": "sekret",
                }
            )

    def test_server_password_fields_rejected(self) -> None:
        for fname in ("password", "passwd"):
            with self.assertRaises(ValueError, msg=f"field {fname!r} must be rejected"):
                self.store.add_server(
                    {
                        "id": "gh-real",
                        "system": "github",
                        "mode": "declared_url",
                        "base_url": "https://gh.example",
                        fname: "sekret",
                    }
                )

    def test_update_unknown_server_raises(self) -> None:
        with self.assertRaises(UnknownServerError):
            self.store.update_server("nope", {"port": 9102})
        self.assertTrue(issubclass(UnknownServerError, LookupError))

    def test_delete_unknown_server_raises(self) -> None:
        with self.assertRaises(UnknownServerError):
            self.store.delete_server("nope")

    def test_update_rejects_invalid_merged_entry_without_writing(self) -> None:
        self.store.add_server(
            {"id": "gh-mock", "system": "github", "mode": "mock_local", "port": 9101}
        )
        # switching mode without supplying the new required field must fail
        with self.assertRaises(ValueError):
            self.store.update_server("gh-mock", {"mode": "declared_url"})
        # the bad patch must not have been persisted
        self.assertEqual(self.store.get_server("gh-mock")["mode"], "mock_local")

    def test_read_defaults_servers_to_empty_list(self) -> None:
        # a config file written before this change has no "servers" key
        self.path.write_text(
            json.dumps({"schema_version": "1.0", "agents": [], "ai_backends": []}),
            encoding="utf-8",
        )
        self.assertEqual(self.store.read()["servers"], [])
        self.assertEqual(self.store.list_servers(), [])

    def test_update_switching_mode_purges_old_mode_field(self) -> None:
        # mock_local carries a port; switching to declared_url must drop the
        # now-irrelevant port so the stored entry has no stale target field.
        self.store.add_server({"id": "s1", "system": "github", "mode": "mock_local", "port": 9101})
        merged = self.store.update_server("s1", {"mode": "declared_url", "base_url": "http://h"})
        self.assertNotIn("port", merged)
        self.assertNotIn("port", self.store.get_server("s1"))
        self.assertEqual(merged["base_url"], "http://h")

    def test_update_null_value_removes_key(self) -> None:
        # A JSON null in the patch clears the key rather than storing null.
        self.store.add_server(
            {
                "id": "s1",
                "system": "github",
                "mode": "declared_url",
                "base_url": "http://h",
                "auth_env": "GH_TOKEN",
            }
        )
        merged = self.store.update_server("s1", {"auth_env": None})
        self.assertNotIn("auth_env", merged)
        self.assertNotIn("auth_env", self.store.get_server("s1"))

    def test_update_null_cannot_remove_required_field(self) -> None:
        # Clearing the current mode's required field leaves an invalid entry.
        self.store.add_server({"id": "s1", "system": "github", "mode": "mock_local", "port": 9101})
        with self.assertRaises(ValueError):
            self.store.update_server("s1", {"port": None})
        # the bad patch must not have been persisted
        self.assertEqual(self.store.get_server("s1")["port"], 9101)

    def test_update_normal_field_does_not_drop_other_keys(self) -> None:
        # A plain field update must not remove unrelated keys.
        self.store.add_server(
            {
                "id": "s1",
                "system": "github",
                "mode": "mock_local",
                "port": 9101,
                "label": "primary",
            }
        )
        merged = self.store.update_server("s1", {"label": "secondary"})
        self.assertEqual(merged["port"], 9101)
        self.assertEqual(merged["label"], "secondary")

    def test_update_switching_mode_without_new_required_field_raises(self) -> None:
        self.store.add_server({"id": "s1", "system": "github", "mode": "mock_local", "port": 9101})
        with self.assertRaises(ValueError):
            self.store.update_server("s1", {"mode": "real_saas"})
        # the bad patch must not have been persisted
        self.assertEqual(self.store.get_server("s1")["mode"], "mock_local")
