"""Schema tests for the discovery ground-truth artifact."""

from __future__ import annotations

import json
import unittest
from pathlib import Path

import jsonschema

REPO = Path(__file__).resolve().parent.parent
SCHEMA = REPO / "corpus" / "schemas" / "discovery-ground-truth.schema.json"


class TestDiscoverySchema(unittest.TestCase):
    def test_schema_is_valid_and_accepts_minimal_doc(self):
        schema = json.loads(SCHEMA.read_text(encoding="utf-8"))
        jsonschema.Draft202012Validator.check_schema(schema)
        doc = {
            "agent_repo": "gh-pr-bot",
            "target_system": "github",
            "detected": True,
            "agent_count": 1,
            "action_patterns": ["open_pr"],
            "risk_rank": 2,
            "policy_generated": True,
        }
        jsonschema.Draft202012Validator(schema).validate(doc)

    def test_schema_accepts_true_negative(self):
        schema = json.loads(SCHEMA.read_text(encoding="utf-8"))
        doc = {
            "agent_repo": "gh-no-agent",
            "target_system": "github",
            "detected": False,
            "agent_count": 0,
            "action_patterns": [],
            "risk_rank": 0,
            "policy_generated": False,
        }
        jsonschema.Draft202012Validator(schema).validate(doc)

    def test_schema_rejects_unknown_action(self):
        schema = json.loads(SCHEMA.read_text(encoding="utf-8"))
        doc = {
            "agent_repo": "bad",
            "target_system": "github",
            "detected": True,
            "action_patterns": ["delete_universe"],
        }
        with self.assertRaises(jsonschema.ValidationError):
            jsonschema.Draft202012Validator(schema).validate(doc)


if __name__ == "__main__":
    unittest.main()
