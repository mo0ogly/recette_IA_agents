"""A134 regression guard: the nightly authoring prompt must encode the
matcher.go field/value contract.

This test is NECESSARY but NOT SUFFICIENT (it asserts the prompt TEXT, not
that the LLM obeys it). Behavioral validation -- a gated, observed nightly
dry-run confirming the generated rules carry `field` for
cookie/js_global/json_field/header/attr and load+fire -- is A137, not this
test. This guard exists so the prompt contract cannot silently revert to the
pre-A134 inverted form ("field only for header, omit for all others") that
produced the entire A123-A130 structurally-dead corpus.
"""
import json
import unittest

import wave_ai
import wave_config


class TestWaveAIPromptContract(unittest.TestCase):
    def test_schema_example_parses(self):
        json.loads(wave_config.SCHEMA_EXAMPLE.replace("DATE", "2026-01-01"))

    def test_prompt_encodes_field_value_contract(self):
        _, usr = wave_ai.build_prompt(
            [{"taxonomy_code": "TESTPROD", "product": "Test",
              "vendor": "", "vendor_website": ""}],
            "2026-05-15",
        )
        required = [
            '"field" is MANDATORY',
            "does NOT pattern-match cookie names",
            'target="js_global": field =',
            "single most common authoring error",
            'match_type="exists"',
            'PREFER target="script_src"',
            "MATCHER SHAPES REFERENCE",
            '"json_field"',
            "CSS-attribute selector",
        ]
        missing = [s for s in required if s not in usr]
        self.assertEqual(missing, [], f"prompt contract missing: {missing}")

    def test_pre_a134_inverted_rule_is_gone(self):
        _, usr = wave_ai.build_prompt(
            [{"taxonomy_code": "TESTPROD", "product": "Test",
              "vendor": "", "vendor_website": ""}],
            "2026-05-15",
        )
        self.assertNotIn(
            'matchers "field": only valid for target="header"', usr,
            "the pre-A134 inverted field rule (root cause of the "
            "A123-A130 dead corpus) has reverted",
        )


if __name__ == "__main__":
    unittest.main()
