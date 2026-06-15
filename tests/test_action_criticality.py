"""Ground-truth test for the Annex C criticality of every governed action.

Annex C of the AgentRail specification fixes a default governance posture
(criticality C1-C4) for each sensitive action. This test IS that ground truth:
the catalog must match EXPECTED exactly, no action may lack a criticality, and
no action may carry one absent from the table. A drift (new action, changed
posture) turns this red instead of being discovered by hand.

Legend (catalog/model.py::Criticality):
- C1 refuse by default          - C3 conditional authorization
- C2 systematic escalation      - C4 authorization with logging

Rows present in Annex C's 118-action referential keep its exact level. The
read-only "allow" rows, the knowledge_base index actions and the mcp tool
governance are NOT in Annex C; their level mirrors the implemented posture
(documented in each domain module) and is asserted here all the same.
"""

from __future__ import annotations

import unittest

from recette.platform.catalog import Criticality, load_catalog

# (target_system, action_type) -> Annex C criticality. Full, literal, frozen.
EXPECTED: dict[tuple[str, str], Criticality] = {
    # --- okta (Identity / Access) ---
    ("okta", "read_user_profile"): Criticality.C4,
    ("okta", "suspend_user"): Criticality.C3,
    ("okta", "delete_user"): Criticality.C1,
    ("okta", "reset_password"): Criticality.C3,
    ("okta", "modify_user_roles"): Criticality.C2,
    ("okta", "add_user_to_admin_group"): Criticality.C2,
    ("okta", "create_api_key"): Criticality.C3,
    ("okta", "revoke_api_key"): Criticality.C3,
    ("okta", "revoke_token"): Criticality.C3,
    ("okta", "generate_long_lived_token"): Criticality.C2,
    ("okta", "modify_mfa_policy"): Criticality.C1,
    ("okta", "disable_sso"): Criticality.C1,
    ("okta", "add_oauth_app"): Criticality.C2,
    ("okta", "modify_oauth_scopes"): Criticality.C2,
    ("okta", "invite_external_user"): Criticality.C3,
    ("okta", "revoke_long_lived_token"): Criticality.C2,
    ("okta", "assume_delegation"): Criticality.C1,
    # --- github (GitHub / DevOps) ---
    ("github", "read_repo_metadata"): Criticality.C4,
    ("github", "delete_repository"): Criticality.C1,
    ("github", "make_repo_public"): Criticality.C1,
    ("github", "modify_cicd_secrets"): Criticality.C2,
    ("github", "deploy_production"): Criticality.C2,
    ("github", "modify_protected_branch"): Criticality.C2,
    ("github", "disable_branch_protection"): Criticality.C1,
    ("github", "merge_pr_without_review"): Criticality.C1,
    ("github", "create_github_token"): Criticality.C3,
    ("github", "add_deploy_key"): Criticality.C2,
    ("github", "modify_gh_actions_workflow"): Criticality.C2,
    ("github", "delete_prod_environment"): Criticality.C1,
    ("github", "modify_org_permissions"): Criticality.C2,
    ("github", "add_external_collaborator"): Criticality.C3,
    ("github", "read_cicd_secrets"): Criticality.C2,
    ("github", "read_secret"): Criticality.C2,
    # --- crm (CRM / Sales) ---
    ("crm", "read_contact_record"): Criticality.C4,
    ("crm", "bulk_modify_contacts"): Criticality.C2,
    ("crm", "delete_contacts"): Criticality.C2,
    ("crm", "export_customer_base"): Criticality.C1,
    ("crm", "bulk_modify_deals"): Criticality.C2,
    ("crm", "change_strategic_account_owner"): Criticality.C2,
    ("crm", "modify_sales_pipeline"): Criticality.C3,
    ("crm", "send_mass_email"): Criticality.C2,
    ("crm", "change_opportunity_amounts"): Criticality.C3,
    ("crm", "modify_sensitive_fields"): Criticality.C2,
    ("crm", "sync_crm_to_external"): Criticality.C2,
    # --- finance (Finance / payments) ---
    ("finance", "read_invoice_status"): Criticality.C4,
    ("finance", "trigger_refund"): Criticality.C3,
    ("finance", "create_payment"): Criticality.C2,
    ("finance", "modify_iban"): Criticality.C1,
    ("finance", "add_payee"): Criticality.C2,
    ("finance", "validate_invoice"): Criticality.C3,
    ("finance", "modify_supplier_bank_details"): Criticality.C1,
    ("finance", "create_credit_note"): Criticality.C3,
    ("finance", "modify_price"): Criticality.C3,
    ("finance", "apply_mass_discount"): Criticality.C2,
    ("finance", "export_financial_data"): Criticality.C2,
    ("finance", "launch_wire_transfer"): Criticality.C1,
    ("finance", "modify_billing_rule"): Criticality.C2,
    ("finance", "freeze_operation"): Criticality.C3,
    # --- data_platform (Data / confidentiality) ---
    ("data_platform", "query_curated_dataset"): Criticality.C4,
    ("data_platform", "export_customer_data"): Criticality.C2,
    ("data_platform", "download_full_database"): Criticality.C1,
    ("data_platform", "share_pii_file"): Criticality.C2,
    ("data_platform", "send_data_to_external_domain"): Criticality.C1,
    ("data_platform", "modify_retention_policy"): Criticality.C2,
    ("data_platform", "delete_logs"): Criticality.C1,
    ("data_platform", "delete_audit_evidence"): Criticality.C1,
    ("data_platform", "access_hr_data"): Criticality.C2,
    ("data_platform", "access_medical_data"): Criticality.C1,
    ("data_platform", "access_sensitive_financial_data"): Criticality.C2,
    ("data_platform", "extract_data_to_external_llm"): Criticality.C1,
    # --- slack (Communication) ---
    ("slack", "read_public_channel"): Criticality.C4,
    ("slack", "send_message_external_channel"): Criticality.C3,
    ("slack", "invite_external_user"): Criticality.C3,
    ("slack", "share_sensitive_file"): Criticality.C2,
    ("slack", "create_public_channel"): Criticality.C3,
    ("slack", "modify_workspace_permissions"): Criticality.C2,
    ("slack", "delete_channel"): Criticality.C2,
    ("slack", "publish_company_announcement"): Criticality.C2,
    ("slack", "send_message_as_executive"): Criticality.C1,
    ("slack", "access_confidential_channel"): Criticality.C2,
    ("slack", "export_slack_history"): Criticality.C1,
    # --- support_desk (Support / customer ops) ---
    ("support_desk", "read_ticket"): Criticality.C4,
    ("support_desk", "bulk_close_tickets"): Criticality.C2,
    ("support_desk", "modify_critical_ticket_status"): Criticality.C3,
    ("support_desk", "send_auto_customer_reply"): Criticality.C4,
    ("support_desk", "grant_goodwill_credit"): Criticality.C3,
    ("support_desk", "delete_ticket"): Criticality.C2,
    ("support_desk", "export_customer_conversations"): Criticality.C2,
    ("support_desk", "modify_sla"): Criticality.C2,
    ("support_desk", "reassign_ticket_volume"): Criticality.C3,
    ("support_desk", "access_vip_tickets"): Criticality.C3,
    ("support_desk", "share_support_data_external"): Criticality.C2,
    # --- cloud (Cloud / infrastructure) ---
    ("cloud", "read_resource_inventory"): Criticality.C4,
    ("cloud", "delete_database"): Criticality.C1,
    ("cloud", "delete_s3_bucket"): Criticality.C1,
    ("cloud", "make_bucket_public"): Criticality.C1,
    ("cloud", "modify_security_group"): Criticality.C2,
    ("cloud", "open_sensitive_port"): Criticality.C1,
    ("cloud", "delete_backups"): Criticality.C1,
    ("cloud", "modify_k8s_config"): Criticality.C2,
    ("cloud", "delete_critical_pod"): Criticality.C2,
    ("cloud", "deploy_unvalidated_image"): Criticality.C1,
    ("cloud", "modify_env_variable"): Criticality.C3,
    ("cloud", "delete_kms_key"): Criticality.C1,
    ("cloud", "modify_cloud_iam"): Criticality.C2,
    ("cloud", "isolate_host"): Criticality.C2,
    # --- hris (HR) ---
    ("hris", "read_org_directory"): Criticality.C4,
    ("hris", "modify_salary"): Criticality.C1,
    ("hris", "delete_employee"): Criticality.C1,
    ("hris", "change_contract_status"): Criticality.C2,
    ("hris", "access_sensitive_hr_records"): Criticality.C2,
    ("hris", "export_employee_data"): Criticality.C2,
    ("hris", "modify_leave"): Criticality.C3,
    ("hris", "create_employee_record"): Criticality.C3,
    ("hris", "send_official_hr_comm"): Criticality.C2,
    ("hris", "modify_employee_access_rights"): Criticality.C2,
    # --- legal_dms (Legal / compliance) ---
    ("legal_dms", "read_published_policy"): Criticality.C4,
    ("legal_dms", "generate_or_send_contract"): Criticality.C2,
    ("legal_dms", "modify_contract_clause"): Criticality.C1,
    ("legal_dms", "delete_legal_document"): Criticality.C1,
    ("legal_dms", "share_confidential_document"): Criticality.C2,
    ("legal_dms", "accept_contract_terms"): Criticality.C1,
    ("legal_dms", "submit_regulatory_document"): Criticality.C1,
    ("legal_dms", "modify_internal_policy"): Criticality.C2,
    ("legal_dms", "delete_evidence_item"): Criticality.C1,
    ("legal_dms", "export_audit_file"): Criticality.C2,
    # --- product_cms (Product / content) ---
    ("product_cms", "read_content_draft"): Criticality.C4,
    ("product_cms", "publish_production"): Criticality.C2,
    ("product_cms", "modify_public_page"): Criticality.C3,
    ("product_cms", "send_marketing_campaign"): Criticality.C2,
    ("product_cms", "modify_pricing"): Criticality.C2,
    ("product_cms", "delete_content"): Criticality.C3,
    ("product_cms", "change_product_config"): Criticality.C3,
    ("product_cms", "enable_feature_all_customers"): Criticality.C2,
    ("product_cms", "disable_critical_feature"): Criticality.C1,
    ("product_cms", "modify_user_onboarding"): Criticality.C3,
    # --- knowledge_base (not in Annex C; posture-mirrored) ---
    ("knowledge_base", "query_knowledge_base"): Criticality.C4,
    ("knowledge_base", "ingest_document"): Criticality.C2,
    ("knowledge_base", "update_retrieval_config"): Criticality.C2,
    ("knowledge_base", "export_knowledge_base"): Criticality.C2,
    ("knowledge_base", "delete_document"): Criticality.C2,
    ("knowledge_base", "purge_index"): Criticality.C1,
    # --- mcp (not in Annex C; posture-mirrored) ---
    ("mcp", "invoke_tool"): Criticality.C3,
    ("mcp", "handoff"): Criticality.C2,
    # --- comms / compliance / gitlab (promoted scenario extras, not in Annex C) ---
    ("comms", "notify_customer"): Criticality.C3,
    ("compliance", "open_kyc_review"): Criticality.C3,
    ("gitlab", "read_repo"): Criticality.C4,
    ("gitlab", "list_repos"): Criticality.C4,
}


class TestActionCriticality(unittest.TestCase):
    def setUp(self) -> None:
        self.catalog = load_catalog()

    def test_every_action_matches_annex_c(self) -> None:
        """Each catalog action carries exactly its Annex C criticality."""
        for spec in self.catalog.all():
            key = (spec.target_system, spec.action_type)
            self.assertIn(key, EXPECTED, f"{key} has no Annex C criticality in the ground truth")
            self.assertIs(
                spec.criticality,
                EXPECTED[key],
                f"{key}: criticality {spec.criticality} != expected {EXPECTED[key]}",
            )

    def test_ground_truth_covers_catalog_exactly(self) -> None:
        """No catalog action missing a criticality, no stale EXPECTED entry."""
        catalog_keys = {(s.target_system, s.action_type) for s in self.catalog.all()}
        expected_keys = set(EXPECTED)
        self.assertEqual(
            catalog_keys,
            expected_keys,
            f"missing in EXPECTED: {catalog_keys - expected_keys}; "
            f"stale in EXPECTED: {expected_keys - catalog_keys}",
        )

    def test_to_dict_exposes_criticality(self) -> None:
        """Serialization carries criticality + its human label (API/console contract)."""
        from recette.platform.catalog.model import CRITICALITY_LABEL

        for spec in self.catalog.all():
            payload = spec.to_dict()
            self.assertEqual(payload["criticality"], spec.criticality)
            self.assertEqual(payload["criticality_label"], CRITICALITY_LABEL[spec.criticality])

    def test_every_level_is_used(self) -> None:
        """All four Annex C levels appear in the catalog (none is dead)."""
        used = {s.criticality for s in self.catalog.all()}
        self.assertEqual(used, set(Criticality))

    def test_v45_governed_actions_posture(self) -> None:
        """The six v4.5 Annex C additions carry the exact criticality + verdict."""
        from recette.platform.events import PolicyVerdict

        kyc = self.catalog.get("compliance", "open_kyc_review")
        assert kyc is not None
        self.assertIs(kyc.criticality, Criticality.C3)
        self.assertIs(kyc.verdict_privileged, PolicyVerdict.ESCALATE)
        self.assertIs(kyc.verdict_default, PolicyVerdict.DENY)

        revoke_token = self.catalog.get("okta", "revoke_token")
        assert revoke_token is not None
        self.assertIs(revoke_token.criticality, Criticality.C3)
        self.assertIs(revoke_token.verdict_privileged, PolicyVerdict.ESCALATE)
        self.assertIs(revoke_token.verdict_default, PolicyVerdict.DENY)

        delegation = self.catalog.get("okta", "assume_delegation")
        assert delegation is not None
        self.assertIs(delegation.criticality, Criticality.C1)
        self.assertIs(delegation.verdict_privileged, PolicyVerdict.DENY)
        self.assertIs(delegation.verdict_default, PolicyVerdict.DENY)
        self.assertEqual(delegation.privileged_roles, ())

        read_secret = self.catalog.get("github", "read_secret")
        assert read_secret is not None
        self.assertIs(read_secret.criticality, Criticality.C2)
        self.assertIs(read_secret.verdict_privileged, PolicyVerdict.ESCALATE)
        self.assertIs(read_secret.verdict_default, PolicyVerdict.DENY)

        isolate_host = self.catalog.get("cloud", "isolate_host")
        assert isolate_host is not None
        self.assertIs(isolate_host.criticality, Criticality.C2)
        self.assertIs(isolate_host.verdict_privileged, PolicyVerdict.ESCALATE)
        self.assertIs(isolate_host.verdict_default, PolicyVerdict.DENY)

        invoke_tool = self.catalog.get("mcp", "invoke_tool")
        assert invoke_tool is not None
        self.assertIs(invoke_tool.criticality, Criticality.C3)
        self.assertIs(invoke_tool.verdict_privileged, PolicyVerdict.ESCALATE)
        self.assertIs(invoke_tool.verdict_default, PolicyVerdict.DENY)


if __name__ == "__main__":
    unittest.main()
