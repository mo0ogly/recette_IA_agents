"""Integrity recette for the predefined campaign templates.

Every template must stay launchable in one click: ids unique, profiles
known, every action a real catalog action of its target system, and the
seeded mock agent must run its scenario end-to-end through the Lane B
engine (deterministic, LabForge -- no side effect).
"""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from recette.api.campaign_store import CampaignStore
from recette.api.campaign_templates import TEMPLATES, get_template, instantiate, list_templates
from recette.api.config_store import ConfigStore
from recette.api.runners import build_stub_llm
from recette.lane_b import run_agent
from recette.tools import agent_action_catalog

VALID_PROFILES = {"legit", "suspect", "destructive"}

CATALOG_ACTIONS = {(row["target_system"], row["action"]) for row in agent_action_catalog()}
CATALOG_SYSTEMS = {row["target_system"] for row in agent_action_catalog()}


class TestTemplateIntegrity(unittest.TestCase):
    def test_ids_are_unique(self) -> None:
        ids = [t["id"] for t in TEMPLATES]
        self.assertEqual(len(ids), len(set(ids)))

    def test_every_template_has_the_required_fields(self) -> None:
        for t in TEMPLATES:
            with self.subTest(template=t.get("id")):
                for key in ("id", "title", "profile", "target_system", "principal", "goal"):
                    self.assertTrue(t.get(key), f"missing or empty {key!r}")
                self.assertTrue(t["actions"], "template without actions")

    def test_profiles_are_known(self) -> None:
        for t in TEMPLATES:
            with self.subTest(template=t["id"]):
                self.assertIn(t["profile"], VALID_PROFILES)

    def test_target_systems_exist_in_the_catalog(self) -> None:
        for t in TEMPLATES:
            with self.subTest(template=t["id"]):
                self.assertIn(t["target_system"], CATALOG_SYSTEMS)

    def test_every_action_is_a_catalog_action_of_its_target_system(self) -> None:
        for t in TEMPLATES:
            for action in t["actions"]:
                with self.subTest(template=t["id"], action=action):
                    self.assertIn(
                        (t["target_system"], action),
                        CATALOG_ACTIONS,
                        f"{action!r} is not a catalog action of {t['target_system']!r}",
                    )

    def test_profile_coverage_includes_all_three(self) -> None:
        self.assertEqual({t["profile"] for t in TEMPLATES}, VALID_PROFILES)


class TestTemplateAccessors(unittest.TestCase):
    def test_list_templates_exposes_one_entry_per_template(self) -> None:
        listed = list_templates()
        self.assertEqual(len(listed), len(TEMPLATES))
        for entry, t in zip(listed, TEMPLATES, strict=True):
            self.assertEqual(entry["id"], t["id"])
            self.assertEqual(entry["agent_id"], f"{t['id']}-agent")
            self.assertEqual(entry["actions"], list(t["actions"]))

    def test_get_template_round_trip_and_unknown(self) -> None:
        first = TEMPLATES[0]
        self.assertEqual(get_template(first["id"]), first)
        self.assertIsNone(get_template("no-such-template"))


class TestInstantiate(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        tmp = Path(self._tmp.name)
        self.config_store = ConfigStore(tmp / "config.json")
        self.campaign_store = CampaignStore(tmp / "campaigns.json")

    def test_instantiate_seeds_agent_and_campaign(self) -> None:
        template = TEMPLATES[0]
        campaign = instantiate(template, self.config_store, self.campaign_store)
        agent = self.config_store.get_agent(f"{template['id']}-agent")
        assert agent is not None
        self.assertEqual(agent["ai_mode"], "mock")
        self.assertEqual(agent["runtime"], "lab")
        self.assertEqual(agent["capability_scope"], list(template["actions"]))
        scenario = agent["scenario"]
        self.assertEqual(scenario[-1]["kind"], "final")
        tool_calls = [s["tool_name"] for s in scenario if s["kind"] == "tool_call"]
        self.assertEqual(tool_calls, list(template["actions"]))
        self.assertEqual(campaign["id"], template["id"])
        self.assertEqual(campaign["steps"], [{"agent_id": f"{template['id']}-agent"}])
        self.assertIsNotNone(self.campaign_store.get(template["id"]))

    def test_instantiate_missing_id_raises_key_error(self) -> None:
        # A template dict without the required "id" key must raise KeyError
        # immediately -- instantiate builds agent_id from template["id"] and
        # campaign["id"] from template["id"], so a missing key is caught early.
        bad_template = {
            "principal": "x@acme",
            "target_system": "okta",
            "goal": "test",
            "actions": ["suspend_user"],
            "title": "bad",
            "profile": "legit",
        }
        with self.assertRaises(KeyError):
            instantiate(bad_template, self.config_store, self.campaign_store)

    def test_instantiate_missing_principal_raises_key_error(self) -> None:
        # A template without "principal" raises KeyError when building the agent dict.
        bad_template = {
            "id": "missing-principal",
            "target_system": "okta",
            "goal": "test",
            "actions": ["suspend_user"],
            "title": "bad",
            "profile": "legit",
        }
        with self.assertRaises(KeyError):
            instantiate(bad_template, self.config_store, self.campaign_store)

    def test_instantiate_is_idempotent(self) -> None:
        template = TEMPLATES[0]
        instantiate(template, self.config_store, self.campaign_store)
        instantiate(template, self.config_store, self.campaign_store)
        self.assertEqual(len(self.campaign_store.list()), 1)
        agents = [
            a for a in self.config_store.read()["agents"] if a["id"] == f"{template['id']}-agent"
        ]
        self.assertEqual(len(agents), 1)


class TestTemplatesRunEndToEnd(unittest.TestCase):
    """Each template's seeded scenario must run through the Lane B engine."""

    def test_every_template_scenario_executes_all_its_actions(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            config_store = ConfigStore(Path(tmp) / "config.json")
            campaign_store = CampaignStore(Path(tmp) / "campaigns.json")
            for template in TEMPLATES:
                with self.subTest(template=template["id"]):
                    instantiate(template, config_store, campaign_store)
                    agent = config_store.get_agent(f"{template['id']}-agent")
                    assert agent is not None
                    result = run_agent(
                        agent_id=agent["id"],
                        principal=agent["principal"],
                        target_system=agent["target_system"],
                        goal=agent["goal"],
                        capability_scope=agent["capability_scope"],
                        llm=build_stub_llm(agent["scenario"]),
                    )
                    executed = [a.action_type for a in result.actions]
                    self.assertEqual(executed, list(template["actions"]))


if __name__ == "__main__":
    unittest.main()
