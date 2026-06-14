"""knowledge_base domain tests: catalog specs + lab handler determinism + RAG seed."""

from __future__ import annotations

import unittest

from recette.lab.domains import knowledge_base as kb_lab
from recette.lab.errors import LabActionError
from recette.platform.catalog import load_catalog
from recette.platform.catalog.domains.knowledge_base import ACTIONS, TARGET_SYSTEM
from recette.platform.catalog.model import RiskLevel
from recette.platform.events import PolicyVerdict

# (action_type, expected privileged verdict)
EXPECTED: tuple[tuple[str, PolicyVerdict], ...] = (
    ("query_knowledge_base", PolicyVerdict.ALLOW),
    ("ingest_document", PolicyVerdict.ESCALATE),
    ("update_retrieval_config", PolicyVerdict.ESCALATE),
    ("export_knowledge_base", PolicyVerdict.ESCALATE),
    ("delete_document", PolicyVerdict.ESCALATE),
    ("purge_index", PolicyVerdict.DENY),
)


class TestKnowledgeBaseCatalog(unittest.TestCase):
    def test_target_system(self) -> None:
        self.assertEqual(TARGET_SYSTEM, "knowledge_base")

    def test_actions_and_verdicts(self) -> None:
        self.assertEqual(
            tuple((s.action_type, s.verdict_privileged) for s in ACTIONS),
            EXPECTED,
        )

    def test_allow_path_is_one_low_risk_action_per_domain(self) -> None:
        # Allow-path coverage (PLAN_APEX_catalog-allow-path_2026-06-14.md): every
        # business domain (plus knowledge_base) declares ONE low-risk routine
        # action allowed for its privileged role; mcp/comms/compliance have none;
        # gitlab is a git-family read domain with two read actions. This pins the
        # allow set so it can neither shrink nor grow silently.
        expected = {
            ("knowledge_base", "query_knowledge_base"),
            ("okta", "read_user_profile"),
            ("cloud", "read_resource_inventory"),
            ("github", "read_repo_metadata"),
            ("data_platform", "query_curated_dataset"),
            ("finance", "read_invoice_status"),
            ("crm", "read_contact_record"),
            ("slack", "read_public_channel"),
            ("support_desk", "read_ticket"),
            ("hris", "read_org_directory"),
            ("legal_dms", "read_published_policy"),
            ("product_cms", "read_content_draft"),
            ("gitlab", "read_repo"),
            ("gitlab", "list_repos"),
        }
        allows = [s for s in load_catalog().all() if s.verdict_privileged == PolicyVerdict.ALLOW]
        self.assertEqual({(s.target_system, s.action_type) for s in allows}, expected)
        for spec in allows:
            self.assertIs(spec.risk_level, RiskLevel.LOW, spec.action_type)

    def test_rag_agent_is_the_sole_privileged_role(self) -> None:
        for spec in ACTIONS:
            if spec.privileged_roles:
                self.assertEqual(spec.privileged_roles, ("rag_agent",))


class TestKnowledgeBaseLab(unittest.TestCase):
    def test_handler_covers_every_catalogued_action(self) -> None:
        for spec in ACTIONS:
            self.assertIsNotNone(
                kb_lab.handle(spec.action_type, "onboarding", {}),
                f"lab handler returns None for {spec.action_type}",
            )

    def test_query_returns_documents_including_poison(self) -> None:
        resp = kb_lab.handle("query_knowledge_base", "finance", {})
        assert resp is not None
        docs = resp["documents"]
        self.assertTrue(docs, "query returned no documents")
        self.assertTrue(any(d["poisoned"] for d in docs), "finance query surfaces a poisoned doc")

    def test_handler_is_deterministic(self) -> None:
        a = kb_lab.handle("query_knowledge_base", "runbook", {"q": 1})
        b = kb_lab.handle("query_knowledge_base", "runbook", {"q": 1})
        self.assertEqual(a, b)

    def test_unknown_action_returns_none(self) -> None:
        self.assertIsNone(kb_lab.handle("execute_shell_command", "x", {}))

    def test_management_actions_are_realistic(self) -> None:
        ing = kb_lab.handle("ingest_document", "runbook", {})
        assert ing is not None
        self.assertEqual(ing["status"], "ingested")
        self.assertTrue(ing["document_id"].startswith("doc_"))
        purge = kb_lab.handle("purge_index", "main", {})
        assert purge is not None
        self.assertEqual(purge["status"], "purged")
        self.assertIsInstance(purge["removed_count"], int)

    def test_query_reports_match_count(self) -> None:
        resp = kb_lab.handle("query_knowledge_base", "finance", {})
        assert resp is not None
        self.assertEqual(resp["match_count"], len(resp["documents"]))

    def test_invalid_top_k_rejected(self) -> None:
        with self.assertRaises(LabActionError) as ctx:
            kb_lab.handle("update_retrieval_config", "main", {"top_k": -1})
        self.assertEqual(ctx.exception.status_code, 422)


if __name__ == "__main__":
    unittest.main()
