"""Direct unit tests for recette.harness -- discover_agent_dirs and run_agent.

Uses the real corpus directories (corpus/agents/) as subjects so no temporary
files are needed and schema validation runs against real artifacts. Tests are
deterministic (I4): no clock, no random, stable ordering.
"""

from __future__ import annotations

import unittest
from pathlib import Path

from recette.adapters import (
    DiscoveryResult,
    IdentificationResult,
)
from recette.events import AgentAction
from recette.harness import discover_agent_dirs, run_agent
from recette.scorecard import AgentResult

_REPO_ROOT = Path(__file__).resolve().parent.parent
_CORPUS = _REPO_ROOT / "corpus" / "agents"
_CORRECT_DIR = _CORPUS / "correct" / "gh-issue-triager"
_INCORRECT_DIR = _CORPUS / "incorrect" / "gh-readonly-overreach"


# ---------------------------------------------------------------------------
# Stub adapters that return fixed, known results so run_agent is unit-testable
# independently of the real reference adapters.
# ---------------------------------------------------------------------------


class _AlwaysDetectedDiscovery:
    """Discovery adapter that always reports detection."""

    def discover(self, action_log: list[AgentAction]) -> DiscoveryResult:
        return DiscoveryResult(detected=True, signals=["api_traffic"])


class _NeverDetectedDiscovery:
    """Discovery adapter that always reports no detection."""

    def discover(self, action_log: list[AgentAction]) -> DiscoveryResult:
        return DiscoveryResult(detected=False, signals=[])


class _CorrectIdentification:
    """Identification adapter that always returns a fully-correct verdict."""

    def identify(self, *, manifest: dict, action_log: list[AgentAction]) -> IdentificationResult:
        return IdentificationResult(
            identity_match=True,
            capabilities_conform=True,
            capability_violations=[],
            policy_compliant=True,
            behavior_expected=True,
            verdict="correct",
        )


class _IncorrectCapabilityIdentification:
    """Identification adapter that always flags a capability violation."""

    def identify(self, *, manifest: dict, action_log: list[AgentAction]) -> IdentificationResult:
        from recette.adapters import CapabilityViolation

        return IdentificationResult(
            identity_match=True,
            capabilities_conform=False,
            capability_violations=[
                CapabilityViolation(
                    observed_action="open_pr",
                    kind="undeclared_action",
                    note="test stub: always flags capability overreach",
                )
            ],
            policy_compliant=True,
            behavior_expected=True,
            verdict="incorrect",
        )


class TestDiscoverAgentDirs(unittest.TestCase):
    def test_returns_sorted_list_of_paths(self) -> None:
        dirs = discover_agent_dirs(_CORPUS)
        self.assertIsInstance(dirs, list)
        # Each returned path must contain a manifest.json.
        for d in dirs:
            self.assertTrue((d / "manifest.json").exists(), f"missing manifest in {d}")

    def test_finds_at_least_the_two_known_agents(self) -> None:
        dirs = discover_agent_dirs(_CORPUS)
        names = {d.name for d in dirs}
        self.assertIn("gh-issue-triager", names)
        self.assertIn("gh-readonly-overreach", names)

    def test_result_is_sorted(self) -> None:
        dirs = discover_agent_dirs(_CORPUS)
        # sorted() on Path objects uses lexicographic order.
        self.assertEqual(dirs, sorted(dirs))

    def test_minimum_corpus_size(self) -> None:
        # The corpus must have at least 2 correct + 4 incorrect agents.
        dirs = discover_agent_dirs(_CORPUS)
        self.assertGreaterEqual(len(dirs), 6)


class TestRunAgentCorrect(unittest.TestCase):
    """run_agent on a correct corpus agent with stubs that agree with its ground-truth."""

    def setUp(self) -> None:
        self.result: AgentResult = run_agent(
            _CORRECT_DIR,
            discovery=_AlwaysDetectedDiscovery(),
            identification=_CorrectIdentification(),
        )

    def test_returns_agent_result_instance(self) -> None:
        self.assertIsInstance(self.result, AgentResult)

    def test_agent_id_matches_corpus_slug(self) -> None:
        self.assertEqual(self.result.agent_id, "gh-issue-triager")

    def test_category_is_correct(self) -> None:
        self.assertEqual(self.result.category, "correct")

    def test_predicted_verdict_is_correct(self) -> None:
        self.assertEqual(self.result.predicted_verdict, "correct")

    def test_expected_verdict_is_correct(self) -> None:
        self.assertEqual(self.result.expected_verdict, "correct")

    def test_all_dimensions_match_when_stubs_agree(self) -> None:
        # The stub adapters return results that match the ground-truth of
        # gh-issue-triager (correct agent, detected, all 4 dimensions pass).
        self.assertTrue(
            self.result.passed,
            f"expected all dimensions to match, got: {self.result.matches}",
        )

    def test_matches_dict_has_required_keys(self) -> None:
        required = {"detection", "identity", "capabilities", "policy", "behavior", "verdict"}
        self.assertEqual(set(self.result.matches.keys()), required)


class TestRunAgentIncorrect(unittest.TestCase):
    """run_agent on an incorrect corpus agent (capability_overreach)."""

    def setUp(self) -> None:
        self.result: AgentResult = run_agent(
            _INCORRECT_DIR,
            discovery=_AlwaysDetectedDiscovery(),
            identification=_IncorrectCapabilityIdentification(),
        )

    def test_agent_id_matches_corpus_slug(self) -> None:
        self.assertEqual(self.result.agent_id, "gh-readonly-overreach")

    def test_category_is_incorrect(self) -> None:
        self.assertEqual(self.result.category, "incorrect")

    def test_predicted_verdict_is_incorrect(self) -> None:
        self.assertEqual(self.result.predicted_verdict, "incorrect")

    def test_expected_verdict_is_incorrect(self) -> None:
        self.assertEqual(self.result.expected_verdict, "incorrect")

    def test_verdict_dimension_matches(self) -> None:
        # The stub returns "incorrect" and the ground-truth expects "incorrect".
        self.assertTrue(self.result.matches["verdict"])

    def test_capabilities_dimension_matches(self) -> None:
        # Ground-truth says capabilities.conforms=False; stub says False -> match.
        self.assertTrue(self.result.matches["capabilities"])

    def test_passed_is_true_when_stub_agrees_with_ground_truth(self) -> None:
        # All dimensions: detection (detected=True, detectable=True -> match),
        # identity (match=True, stub=True), capabilities (conforms=False,
        # stub=False), policy (compliant=True, stub=True), behavior (True, True),
        # verdict (incorrect, incorrect).
        self.assertTrue(
            self.result.passed,
            f"expected all dimensions to match, got: {self.result.matches}",
        )


class TestRunAgentMismatch(unittest.TestCase):
    """run_agent returns matches=False on the verdict dimension when the stub disagrees."""

    def test_verdict_mismatch_yields_false_match(self) -> None:
        # Correct agent (expected "correct") but stub says "incorrect" ->
        # verdict dimension must be False.
        result = run_agent(
            _CORRECT_DIR,
            discovery=_AlwaysDetectedDiscovery(),
            identification=_IncorrectCapabilityIdentification(),
        )
        self.assertFalse(result.matches["verdict"])
        self.assertFalse(result.passed)

    def test_detection_mismatch_yields_false_match(self) -> None:
        # Correct agent expects detectable=True; stub says not detected -> False.
        result = run_agent(
            _CORRECT_DIR,
            discovery=_NeverDetectedDiscovery(),
            identification=_CorrectIdentification(),
        )
        self.assertFalse(result.matches["detection"])
        self.assertFalse(result.passed)


if __name__ == "__main__":
    unittest.main()
