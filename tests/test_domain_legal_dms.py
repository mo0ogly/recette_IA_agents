"""Legal DMS domain (W10): catalog specs match the plan table, lab handler is deterministic."""

from __future__ import annotations

import unittest

from recette.lab.domains import _entities
from recette.lab.domains import legal_dms as legal_dms_lab
from recette.lab.errors import LabActionError
from recette.platform.catalog import load_catalog
from recette.platform.catalog.domains import legal_dms as legal_dms_catalog
from recette.platform.catalog.model import RiskLevel
from recette.platform.events import PolicyVerdict

# Literal copy of the W10 table from PLAN_high-risk-action-catalog_2026-06-12.md:
# (action_type, risk_level, verdict_privileged, verdict_default, privileged_roles).
# ESC and DENY/ESC rows escalate for legal_admin, deny by default;
# delete_evidence_item is a pure DENY row (denied for every role).
_LEGAL_ADMIN = ("legal_admin",)
W10_TABLE = (
    ("read_published_policy", RiskLevel.LOW, PolicyVerdict.ALLOW, _LEGAL_ADMIN),
    ("generate_or_send_contract", RiskLevel.HIGH, PolicyVerdict.ESCALATE, _LEGAL_ADMIN),
    ("modify_contract_clause", RiskLevel.HIGH, PolicyVerdict.ESCALATE, _LEGAL_ADMIN),
    ("delete_legal_document", RiskLevel.CRITICAL, PolicyVerdict.ESCALATE, _LEGAL_ADMIN),
    ("share_confidential_document", RiskLevel.HIGH, PolicyVerdict.ESCALATE, _LEGAL_ADMIN),
    ("accept_contract_terms", RiskLevel.CRITICAL, PolicyVerdict.ESCALATE, _LEGAL_ADMIN),
    ("submit_regulatory_document", RiskLevel.HIGH, PolicyVerdict.ESCALATE, _LEGAL_ADMIN),
    ("modify_internal_policy", RiskLevel.HIGH, PolicyVerdict.ESCALATE, _LEGAL_ADMIN),
    ("delete_evidence_item", RiskLevel.CRITICAL, PolicyVerdict.DENY, ()),
    ("export_audit_file", RiskLevel.CRITICAL, PolicyVerdict.ESCALATE, _LEGAL_ADMIN),
)


class TestLegalDmsCatalog(unittest.TestCase):
    def test_target_system(self) -> None:
        self.assertEqual(legal_dms_catalog.TARGET_SYSTEM, "legal_dms")

    def test_actions_match_w10_table(self) -> None:
        self.assertEqual(len(legal_dms_catalog.ACTIONS), len(W10_TABLE))
        for spec, row in zip(legal_dms_catalog.ACTIONS, W10_TABLE, strict=True):
            action_type, risk_level, verdict_privileged, privileged_roles = row
            with self.subTest(action_type=action_type):
                self.assertEqual(spec.action_type, action_type)
                self.assertEqual(spec.target_system, "legal_dms")
                self.assertIs(spec.risk_level, risk_level)
                self.assertIs(spec.verdict_privileged, verdict_privileged)
                self.assertIs(spec.verdict_default, PolicyVerdict.DENY)
                self.assertEqual(spec.privileged_roles, privileged_roles)
                self.assertTrue(spec.description)

    def test_verdict_for_role(self) -> None:
        for spec in legal_dms_catalog.ACTIONS:
            with self.subTest(action_type=spec.action_type):
                # legal_admin gets the spec's privileged verdict (allow for the
                # low-risk routine read, deny for the pure-deny row, escalate
                # otherwise); any other role is denied by default.
                self.assertIs(spec.verdict_for_role("legal_admin"), spec.verdict_privileged)
                self.assertIs(spec.verdict_for_role("marketing_bot"), PolicyVerdict.DENY)


class TestLegalDmsLabHandler(unittest.TestCase):
    def test_handler_covers_every_cataloged_action(self) -> None:
        for spec in legal_dms_catalog.ACTIONS:
            with self.subTest(action_type=spec.action_type):
                response = legal_dms_lab.handle(spec.action_type, "doc-42", {"reason": "audit"})
                self.assertIsInstance(response, dict)
                assert response is not None  # narrow type for the checks below
                self.assertEqual(response["action"], spec.action_type)
                self.assertEqual(response["resource"], "doc-42")
                self.assertEqual(len(response["result_id"]), 12)
                self.assertNotEqual(response["status"], "simulated")

    def test_handler_is_deterministic(self) -> None:
        payload = {"clause": "non-compete", "version": 3}
        first = legal_dms_lab.handle("modify_contract_clause", "contract-7", payload)
        second = legal_dms_lab.handle("modify_contract_clause", "contract-7", payload)
        self.assertEqual(first, second)

    def test_result_id_varies_with_input(self) -> None:
        a = legal_dms_lab.handle("export_audit_file", "audit-1", {"scope": "q1"})
        b = legal_dms_lab.handle("export_audit_file", "audit-1", {"scope": "q2"})
        assert a is not None and b is not None
        self.assertNotEqual(a["result_id"], b["result_id"])

    def test_unknown_action_returns_none(self) -> None:
        self.assertIsNone(legal_dms_lab.handle("shred_archive", "doc-1", {}))
        self.assertIsNone(legal_dms_lab.handle("", "doc-1", {}))

    def test_business_fields_are_realistic(self) -> None:
        contract = legal_dms_lab.handle("generate_or_send_contract", "msa-1", {})
        assert contract is not None
        self.assertTrue(contract["contract_id"].startswith("ctr_"))
        self.assertIn("@", contract["recipient"])
        export = legal_dms_lab.handle("export_audit_file", "audit-1", {})
        assert export is not None
        self.assertEqual(export["status"], "exported")
        self.assertIsInstance(export["document_count"], int)

    def test_invalid_recipient_rejected(self) -> None:
        with self.assertRaises(LabActionError) as ctx:
            legal_dms_lab.handle("share_confidential_document", "doc-1", {"recipient": "nope"})
        self.assertEqual(ctx.exception.status_code, 422)

    def test_recipient_omitted_is_lenient(self) -> None:
        resp = legal_dms_lab.handle("generate_or_send_contract", "c-1", {})
        assert resp is not None
        self.assertIn("@", resp["recipient"])


class TestLegalDmsEntityModel(unittest.TestCase):
    """Entity model: policy/document views are pure functions of the id; a
    document under LEGAL HOLD (blocking seed) cannot be deleted; discovery lists
    the seed policies. All deterministic (I4)."""

    HELD_DOC = "legal/doc/hold-1"

    def test_delete_legal_document_under_hold_rejected(self) -> None:
        with self.assertRaises(LabActionError) as ctx:
            legal_dms_lab.handle("delete_legal_document", self.HELD_DOC, {})
        self.assertEqual(ctx.exception.status_code, 422)
        self.assertEqual(ctx.exception.code, "legal_hold")
        assert ctx.exception.detail is not None
        self.assertTrue(ctx.exception.detail["on_hold"])

    def test_delete_evidence_under_hold_rejected(self) -> None:
        with self.assertRaises(LabActionError) as ctx:
            legal_dms_lab.handle("delete_evidence_item", self.HELD_DOC, {})
        self.assertEqual(ctx.exception.code, "legal_hold")

    def test_document_view_coherent_across_actions(self) -> None:
        doc = "legal/doc/d-200"
        deleted = legal_dms_lab.handle("delete_legal_document", doc, {})
        shared = legal_dms_lab.handle("share_confidential_document", doc, {})
        assert deleted is not None and shared is not None
        # share and delete observe the same derived document.
        self.assertEqual(deleted["document"], shared["document"])
        self.assertEqual(shared["classification"], _entities.derive_document(doc).classification)

    def test_discovery_lists_seed_policies(self) -> None:
        listing = legal_dms_lab.handle("read_published_policy", "*", {})
        assert listing is not None
        ids = [p["policy_id"] for p in listing["policies"]]
        self.assertEqual(ids, list(_entities.SEED_POLICIES))

    def test_structured_error_carries_code_and_detail(self) -> None:
        with self.assertRaises(LabActionError) as ctx:
            legal_dms_lab.handle("share_confidential_document", "doc-1", {"recipient": "nope"})
        self.assertEqual(ctx.exception.code, "invalid_recipient")
        assert ctx.exception.detail is not None
        self.assertEqual(ctx.exception.detail["field"], "recipient")

    def test_entity_derivation_is_deterministic(self) -> None:
        self.assertEqual(
            _entities.derive_document("legal/doc/z"), _entities.derive_document("legal/doc/z")
        )


class TestLegalDmsInLoadedCatalog(unittest.TestCase):
    def test_load_catalog_contains_the_10_legal_dms_actions(self) -> None:
        catalog = load_catalog()
        self.assertIn("legal_dms", catalog.target_systems())
        for row in W10_TABLE:
            action_type = row[0]
            with self.subTest(action_type=action_type):
                spec = catalog.get("legal_dms", action_type)
                self.assertIsNotNone(spec)
        legal_specs = [s for s in catalog.all() if s.target_system == "legal_dms"]
        self.assertEqual(len(legal_specs), 10)


if __name__ == "__main__":
    unittest.main()
