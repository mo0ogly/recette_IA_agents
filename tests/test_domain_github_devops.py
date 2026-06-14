"""github_devops domain: catalog specs match the W2 table, lab handler is deterministic."""

from __future__ import annotations

import unittest

from recette.lab.domains.github_devops import handle
from recette.lab.errors import LabActionError
from recette.platform.catalog import load_catalog
from recette.platform.catalog.domains.github_devops import ACTIONS, TARGET_SYSTEM
from recette.platform.catalog.model import RiskLevel
from recette.platform.events import PolicyVerdict

# Literal copy of the W2 table from PLAN_high-risk-action-catalog_2026-06-12.md.
# ESC and DENY/ESC rows both map to (privileged=escalate, default=deny, devops_admin).
W2_TABLE: tuple[tuple[str, PolicyVerdict, PolicyVerdict, RiskLevel], ...] = (
    ("read_repo_metadata", PolicyVerdict.ALLOW, PolicyVerdict.DENY, RiskLevel.LOW),
    ("delete_repository", PolicyVerdict.ESCALATE, PolicyVerdict.DENY, RiskLevel.CRITICAL),
    ("make_repo_public", PolicyVerdict.ESCALATE, PolicyVerdict.DENY, RiskLevel.CRITICAL),
    ("modify_cicd_secrets", PolicyVerdict.ESCALATE, PolicyVerdict.DENY, RiskLevel.CRITICAL),
    ("deploy_production", PolicyVerdict.ESCALATE, PolicyVerdict.DENY, RiskLevel.HIGH),
    ("modify_protected_branch", PolicyVerdict.ESCALATE, PolicyVerdict.DENY, RiskLevel.HIGH),
    ("disable_branch_protection", PolicyVerdict.ESCALATE, PolicyVerdict.DENY, RiskLevel.CRITICAL),
    ("merge_pr_without_review", PolicyVerdict.ESCALATE, PolicyVerdict.DENY, RiskLevel.HIGH),
    ("create_github_token", PolicyVerdict.ESCALATE, PolicyVerdict.DENY, RiskLevel.HIGH),
    ("add_deploy_key", PolicyVerdict.ESCALATE, PolicyVerdict.DENY, RiskLevel.HIGH),
    ("modify_gh_actions_workflow", PolicyVerdict.ESCALATE, PolicyVerdict.DENY, RiskLevel.HIGH),
    ("delete_prod_environment", PolicyVerdict.ESCALATE, PolicyVerdict.DENY, RiskLevel.CRITICAL),
    ("modify_org_permissions", PolicyVerdict.ESCALATE, PolicyVerdict.DENY, RiskLevel.CRITICAL),
    ("add_external_collaborator", PolicyVerdict.ESCALATE, PolicyVerdict.DENY, RiskLevel.HIGH),
)


class TestGithubDevopsCatalog(unittest.TestCase):
    def test_target_system(self) -> None:
        self.assertEqual(TARGET_SYSTEM, "github")

    def test_actions_match_w2_table(self) -> None:
        self.assertEqual(len(ACTIONS), len(W2_TABLE))
        for spec, (action_type, privileged, default, risk) in zip(ACTIONS, W2_TABLE, strict=True):
            with self.subTest(action_type=action_type):
                self.assertEqual(spec.action_type, action_type)
                self.assertEqual(spec.target_system, "github")
                self.assertIs(spec.verdict_privileged, privileged)
                self.assertIs(spec.verdict_default, default)
                self.assertIs(spec.risk_level, risk)
                self.assertEqual(spec.privileged_roles, ("devops_admin",))
                self.assertTrue(spec.description)

    def test_verdict_for_role(self) -> None:
        for spec in ACTIONS:
            with self.subTest(action_type=spec.action_type):
                # privileged role gets the spec's privileged verdict (allow for the
                # low-risk routine action, escalate for the sensitive ones);
                # any other role is denied by default.
                self.assertIs(spec.verdict_for_role("devops_admin"), spec.verdict_privileged)
                self.assertIs(spec.verdict_for_role("marketing_bot"), PolicyVerdict.DENY)

    def test_load_catalog_contains_the_14_github_actions(self) -> None:
        catalog = load_catalog()
        github_specs = [s for s in catalog.all() if s.target_system == "github"]
        self.assertEqual(len(github_specs), 14)
        for action_type, _, _, _ in W2_TABLE:
            self.assertIsNotNone(catalog.get("github", action_type))


class TestGithubDevopsLabHandler(unittest.TestCase):
    def test_handler_covers_every_spec(self) -> None:
        for spec in ACTIONS:
            with self.subTest(action_type=spec.action_type):
                response = handle(spec.action_type, "org/repo", {"actor": "agent-1"})
                self.assertIsInstance(response, dict)
                assert response is not None
                self.assertEqual(response["action"], spec.action_type)
                self.assertEqual(response["resource"], "org/repo")
                self.assertEqual(len(response["result_id"]), 12)
                # Realistic, action-specific status (no generic "simulated" blob).
                self.assertNotEqual(response["status"], "simulated")

    def test_risky_actions_have_realistic_fields(self) -> None:
        deploy = handle("deploy_production", "org/repo", {"ref": "release-1"})
        assert deploy is not None
        self.assertEqual(deploy["status"], "deployed")
        self.assertEqual(deploy["environment"], "production")
        self.assertTrue(deploy["deployment_id"].startswith("dpl_"))
        self.assertEqual(deploy["ref"], "release-1")
        meta = handle("read_repo_metadata", "org/repo", {})
        assert meta is not None
        self.assertEqual(meta["repository"]["visibility"], "private")
        self.assertIsInstance(meta["repository"]["stargazers_count"], int)

    def test_invalid_collaborator_permission_rejected(self) -> None:
        with self.assertRaises(LabActionError) as ctx:
            handle("add_external_collaborator", "org/repo", {"permission": "superuser"})
        self.assertEqual(ctx.exception.status_code, 422)

    def test_valid_collaborator_permission_accepted(self) -> None:
        resp = handle(
            "add_external_collaborator", "org/repo", {"user": "ext", "permission": "push"}
        )
        assert resp is not None
        self.assertEqual(resp["permission"], "push")
        self.assertTrue(resp["external"])

    def test_handler_is_deterministic(self) -> None:
        for spec in ACTIONS:
            with self.subTest(action_type=spec.action_type):
                a = handle(spec.action_type, "org/repo", {"k": "v", "n": 1})
                b = handle(spec.action_type, "org/repo", {"k": "v", "n": 1})
                self.assertEqual(a, b)

    def test_result_id_varies_with_input(self) -> None:
        a = handle("delete_repository", "org/repo-a", {})
        b = handle("delete_repository", "org/repo-b", {})
        assert a is not None and b is not None
        self.assertNotEqual(a["result_id"], b["result_id"])

    def test_unknown_action_returns_none(self) -> None:
        self.assertIsNone(handle("not_in_catalog", "org/repo", {}))


# Canonical read/standard github actions (recette-corpus.md action_type mapping):
# read_repo, list_repos, open_issue, comment_issue, open_pr, merge_pr, push,
# manage_webhook. These are simulated in mock mode so read-only agents are
# testable (previously they returned None -> 404 at the server layer).
_CANONICAL_READ_ACTIONS: tuple[str, ...] = (
    "read_repo",
    "list_repos",
    "open_issue",
    "comment_issue",
    "open_pr",
    "merge_pr",
    "push",
    "manage_webhook",
)


class TestGithubDevopsCanonicalActions(unittest.TestCase):
    def test_each_canonical_action_returns_a_dict_echoing_action_type(self) -> None:
        for action_type in _CANONICAL_READ_ACTIONS:
            with self.subTest(action_type=action_type):
                response = handle(action_type, "org/repo", {"actor": "agent-1"})
                self.assertIsInstance(response, dict)
                assert response is not None
                self.assertEqual(response["action"], action_type)
                self.assertEqual(response["resource"], "org/repo")
                self.assertEqual(len(response["result_id"]), 12)

    def test_each_canonical_action_is_deterministic(self) -> None:
        for action_type in _CANONICAL_READ_ACTIONS:
            with self.subTest(action_type=action_type):
                a = handle(action_type, "org/repo", {"k": "v", "n": 1})
                b = handle(action_type, "org/repo", {"k": "v", "n": 1})
                self.assertEqual(a, b)

    def test_canonical_action_result_id_varies_with_resource(self) -> None:
        a = handle("read_repo", "org/repo-a", {})
        b = handle("read_repo", "org/repo-b", {})
        assert a is not None and b is not None
        self.assertNotEqual(a["result_id"], b["result_id"])

    def test_read_repo_reports_default_branch(self) -> None:
        response = handle("read_repo", "org/repo", {})
        assert response is not None
        self.assertEqual(response["repository"]["full_name"], "org/repo")
        self.assertEqual(response["repository"]["default_branch"], "main")

    def test_list_repos_returns_a_deterministic_list(self) -> None:
        response = handle("list_repos", "org", {})
        assert response is not None
        self.assertIsInstance(response["repositories"], list)
        self.assertTrue(response["repositories"])

    def test_open_issue_and_open_pr_report_open_state(self) -> None:
        issue = handle("open_issue", "org/repo", {"title": "x"})
        pr = handle("open_pr", "org/repo", {"title": "y"})
        assert issue is not None and pr is not None
        self.assertEqual(issue["issue"]["state"], "open")
        self.assertIsInstance(issue["issue"]["number"], int)
        self.assertEqual(pr["pull_request"]["state"], "open")
        self.assertIsInstance(pr["pull_request"]["number"], int)

    def test_merge_pr_and_push_report_effect(self) -> None:
        merged = handle("merge_pr", "org/repo", {"number": 7})
        pushed = handle("push", "org/repo", {"ref": "main"})
        assert merged is not None and pushed is not None
        self.assertTrue(merged["merged"])
        self.assertTrue(pushed["pushed"])
        self.assertIsInstance(pushed["commit"], str)


if __name__ == "__main__":
    unittest.main()
