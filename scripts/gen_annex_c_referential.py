"""Generate the Annex C governed-action referential in repo schema.

Annex C of the AgentRail spec lists 118 sensitive actions with a dotted
`domain.object.verb` action_type and a default criticality C1-C4. The repo
models an action as a (target_system, action_type) pair (snake_case verb-object)
in the governed-action catalog (recette/platform/catalog). This script is the
bridge: it holds Annex C's source columns (category, French label, the original
dotted action_type) mapped to the repo pair, and ENRICHES each row from the
committed catalog (criticality, risk, verdict) so the referential cannot drift
from the catalog -- every row is cross-checked, a mismatch aborts generation.

Output: corpus/referentials/annex-c-governed-actions.json (machine-readable,
consumable by tools/tests). Regenerate + verify with tests/test_annex_c_referential.py.

Run: python -m scripts.gen_annex_c_referential   (or: python scripts/gen_annex_c_referential.py)
"""

from __future__ import annotations

import json
from pathlib import Path

from recette.platform.catalog import load_catalog
from recette.platform.catalog.model import CRITICALITY_LABEL, RISK_SCORE, Criticality

OUTPUT = Path("corpus/referentials/annex-c-governed-actions.json")

# Annex C source, in spec order. Columns:
#   (category, french_label, annex_c_action_type, target_system, action_type)
# The repo (target_system, action_type) MUST exist in the catalog; criticality
# and the rest are pulled from the catalog at build time (not duplicated here).
ANNEX_C_SOURCE: tuple[tuple[str, str, str, str, str], ...] = (
    # --- Identite / acces ---
    (
        "Identite / acces",
        "Suspendre un utilisateur Okta",
        "identity.user.suspend",
        "okta",
        "suspend_user",
    ),
    ("Identite / acces", "Supprimer un utilisateur", "identity.user.delete", "okta", "delete_user"),
    (
        "Identite / acces",
        "Reinitialiser un mot de passe",
        "identity.credential.reset",
        "okta",
        "reset_password",
    ),
    (
        "Identite / acces",
        "Modifier les roles d'un utilisateur",
        "identity.role.update",
        "okta",
        "modify_user_roles",
    ),
    (
        "Identite / acces",
        "Ajouter un utilisateur a un groupe admin",
        "identity.group.admin_add",
        "okta",
        "add_user_to_admin_group",
    ),
    ("Identite / acces", "Creer une cle API", "identity.apikey.create", "okta", "create_api_key"),
    (
        "Identite / acces",
        "Revoquer une cle API",
        "identity.apikey.revoke",
        "okta",
        "revoke_api_key",
    ),
    (
        "Identite / acces",
        "Generer un token longue duree",
        "identity.token.longlived_create",
        "okta",
        "generate_long_lived_token",
    ),
    (
        "Identite / acces",
        "Modifier une politique MFA",
        "identity.mfa.policy_update",
        "okta",
        "modify_mfa_policy",
    ),
    ("Identite / acces", "Desactiver le SSO", "identity.sso.disable", "okta", "disable_sso"),
    (
        "Identite / acces",
        "Ajouter une application OAuth",
        "identity.oauth.app_create",
        "okta",
        "add_oauth_app",
    ),
    (
        "Identite / acces",
        "Modifier les scopes OAuth",
        "identity.oauth.scope_update",
        "okta",
        "modify_oauth_scopes",
    ),
    (
        "Identite / acces",
        "Inviter un utilisateur externe",
        "identity.user.invite_external",
        "okta",
        "invite_external_user",
    ),
    # --- GitHub / DevOps ---
    (
        "GitHub / DevOps",
        "Supprimer un repository",
        "scm.repo.delete",
        "github",
        "delete_repository",
    ),
    (
        "GitHub / DevOps",
        "Rendre un repository public",
        "scm.repo.visibility_public",
        "github",
        "make_repo_public",
    ),
    (
        "GitHub / DevOps",
        "Modifier les secrets CI/CD",
        "scm.secret.update",
        "github",
        "modify_cicd_secrets",
    ),
    (
        "GitHub / DevOps",
        "Deployer en production",
        "scm.deploy.production",
        "github",
        "deploy_production",
    ),
    (
        "GitHub / DevOps",
        "Modifier une branche protegee",
        "scm.branch.protected_update",
        "github",
        "modify_protected_branch",
    ),
    (
        "GitHub / DevOps",
        "Desactiver les branch protection rules",
        "scm.branch.protection_disable",
        "github",
        "disable_branch_protection",
    ),
    (
        "GitHub / DevOps",
        "Merger une PR sans review",
        "scm.pr.merge_unreviewed",
        "github",
        "merge_pr_without_review",
    ),
    (
        "GitHub / DevOps",
        "Creer un token GitHub",
        "scm.token.create",
        "github",
        "create_github_token",
    ),
    ("GitHub / DevOps", "Ajouter un deploy key", "scm.deploykey.add", "github", "add_deploy_key"),
    (
        "GitHub / DevOps",
        "Modifier un workflow GitHub Actions",
        "scm.workflow.update",
        "github",
        "modify_gh_actions_workflow",
    ),
    (
        "GitHub / DevOps",
        "Supprimer un environnement de production",
        "scm.env.production_delete",
        "github",
        "delete_prod_environment",
    ),
    (
        "GitHub / DevOps",
        "Modifier les permissions d'une organisation",
        "scm.org.permission_update",
        "github",
        "modify_org_permissions",
    ),
    (
        "GitHub / DevOps",
        "Ajouter un collaborateur externe",
        "scm.collaborator.external_add",
        "github",
        "add_external_collaborator",
    ),
    # --- CRM / Sales ---
    (
        "CRM / Sales",
        "Modifier massivement des contacts",
        "crm.contact.bulk_update",
        "crm",
        "bulk_modify_contacts",
    ),
    ("CRM / Sales", "Supprimer des contacts", "crm.contact.delete", "crm", "delete_contacts"),
    ("CRM / Sales", "Exporter une base clients", "crm.data.export", "crm", "export_customer_base"),
    (
        "CRM / Sales",
        "Modifier des deals en masse",
        "crm.deal.bulk_update",
        "crm",
        "bulk_modify_deals",
    ),
    (
        "CRM / Sales",
        "Changer le proprietaire de comptes strategiques",
        "crm.account.owner_change_strategic",
        "crm",
        "change_strategic_account_owner",
    ),
    (
        "CRM / Sales",
        "Modifier un pipeline commercial",
        "crm.pipeline.update",
        "crm",
        "modify_sales_pipeline",
    ),
    ("CRM / Sales", "Envoyer un email massif", "crm.email.bulk_send", "crm", "send_mass_email"),
    (
        "CRM / Sales",
        "Changer les montants d'opportunites",
        "crm.opportunity.amount_update",
        "crm",
        "change_opportunity_amounts",
    ),
    (
        "CRM / Sales",
        "Modifier des champs sensibles",
        "crm.field.sensitive_update",
        "crm",
        "modify_sensitive_fields",
    ),
    (
        "CRM / Sales",
        "Synchroniser des donnees CRM vers un outil externe",
        "crm.sync.external",
        "crm",
        "sync_crm_to_external",
    ),
    # --- Finance / paiements ---
    (
        "Finance / paiements",
        "Declencher un remboursement Stripe",
        "finance.refund.create",
        "finance",
        "trigger_refund",
    ),
    (
        "Finance / paiements",
        "Creer un paiement",
        "finance.payment.create",
        "finance",
        "create_payment",
    ),
    ("Finance / paiements", "Modifier un IBAN", "finance.iban.update", "finance", "modify_iban"),
    (
        "Finance / paiements",
        "Ajouter un beneficiaire",
        "finance.beneficiary.add",
        "finance",
        "add_payee",
    ),
    (
        "Finance / paiements",
        "Valider une facture",
        "finance.invoice.approve",
        "finance",
        "validate_invoice",
    ),
    (
        "Finance / paiements",
        "Modifier les coordonnees bancaires d'un fournisseur",
        "finance.vendor.bank_update",
        "finance",
        "modify_supplier_bank_details",
    ),
    (
        "Finance / paiements",
        "Creer une note de credit",
        "finance.creditnote.create",
        "finance",
        "create_credit_note",
    ),
    ("Finance / paiements", "Modifier un prix", "finance.price.update", "finance", "modify_price"),
    (
        "Finance / paiements",
        "Appliquer une remise massive",
        "finance.discount.bulk_apply",
        "finance",
        "apply_mass_discount",
    ),
    (
        "Finance / paiements",
        "Exporter des donnees financieres",
        "finance.data.export",
        "finance",
        "export_financial_data",
    ),
    (
        "Finance / paiements",
        "Lancer un virement",
        "finance.transfer.execute",
        "finance",
        "launch_wire_transfer",
    ),
    (
        "Finance / paiements",
        "Modifier une regle de facturation",
        "finance.billing.rule_update",
        "finance",
        "modify_billing_rule",
    ),
    # --- Donnees / confidentialite ---
    (
        "Donnees / confidentialite",
        "Exporter des donnees clients",
        "data.customer.export",
        "data_platform",
        "export_customer_data",
    ),
    (
        "Donnees / confidentialite",
        "Telecharger une base complete",
        "data.database.full_download",
        "data_platform",
        "download_full_database",
    ),
    (
        "Donnees / confidentialite",
        "Partager un fichier contenant des donnees personnelles",
        "data.file.share_pii",
        "data_platform",
        "share_pii_file",
    ),
    (
        "Donnees / confidentialite",
        "Envoyer des donnees vers un domaine externe",
        "data.transfer.external_domain",
        "data_platform",
        "send_data_to_external_domain",
    ),
    (
        "Donnees / confidentialite",
        "Modifier une politique de retention",
        "data.retention.policy_update",
        "data_platform",
        "modify_retention_policy",
    ),
    (
        "Donnees / confidentialite",
        "Supprimer des logs",
        "data.logs.delete",
        "data_platform",
        "delete_logs",
    ),
    (
        "Donnees / confidentialite",
        "Supprimer des preuves d'audit",
        "data.audit.evidence_delete",
        "data_platform",
        "delete_audit_evidence",
    ),
    (
        "Donnees / confidentialite",
        "Acceder a des donnees RH",
        "data.hr.access",
        "data_platform",
        "access_hr_data",
    ),
    (
        "Donnees / confidentialite",
        "Acceder a des donnees medicales",
        "data.medical.access",
        "data_platform",
        "access_medical_data",
    ),
    (
        "Donnees / confidentialite",
        "Acceder a des donnees financieres sensibles",
        "data.financial.access",
        "data_platform",
        "access_sensitive_financial_data",
    ),
    (
        "Donnees / confidentialite",
        "Extraire des donnees vers un LLM externe",
        "data.llm.external_extract",
        "data_platform",
        "extract_data_to_external_llm",
    ),
    # --- Slack / communication ---
    (
        "Slack / communication",
        "Envoyer un message dans un canal externe",
        "comms.message.external_channel",
        "slack",
        "send_message_external_channel",
    ),
    (
        "Slack / communication",
        "Inviter un utilisateur externe",
        "comms.user.invite_external",
        "slack",
        "invite_external_user",
    ),
    (
        "Slack / communication",
        "Partager un fichier sensible",
        "comms.file.share_sensitive",
        "slack",
        "share_sensitive_file",
    ),
    (
        "Slack / communication",
        "Creer un canal public",
        "comms.channel.create_public",
        "slack",
        "create_public_channel",
    ),
    (
        "Slack / communication",
        "Modifier les permissions d'un workspace",
        "comms.workspace.permission_update",
        "slack",
        "modify_workspace_permissions",
    ),
    (
        "Slack / communication",
        "Supprimer un canal",
        "comms.channel.delete",
        "slack",
        "delete_channel",
    ),
    (
        "Slack / communication",
        "Publier une annonce entreprise",
        "comms.announcement.publish",
        "slack",
        "publish_company_announcement",
    ),
    (
        "Slack / communication",
        "Envoyer un message au nom d'un dirigeant",
        "comms.message.impersonate_executive",
        "slack",
        "send_message_as_executive",
    ),
    (
        "Slack / communication",
        "Acceder a un canal confidentiel",
        "comms.channel.confidential_access",
        "slack",
        "access_confidential_channel",
    ),
    (
        "Slack / communication",
        "Exporter l'historique Slack",
        "comms.history.export",
        "slack",
        "export_slack_history",
    ),
    # --- Support / customer operations ---
    (
        "Support / customer operations",
        "Fermer massivement des tickets",
        "support.ticket.bulk_close",
        "support_desk",
        "bulk_close_tickets",
    ),
    (
        "Support / customer operations",
        "Modifier le statut de tickets critiques",
        "support.ticket.critical_update",
        "support_desk",
        "modify_critical_ticket_status",
    ),
    (
        "Support / customer operations",
        "Envoyer une reponse client automatique",
        "support.reply.auto_send",
        "support_desk",
        "send_auto_customer_reply",
    ),
    (
        "Support / customer operations",
        "Accorder un geste commercial",
        "support.gesture.grant",
        "support_desk",
        "grant_goodwill_credit",
    ),
    (
        "Support / customer operations",
        "Supprimer un ticket",
        "support.ticket.delete",
        "support_desk",
        "delete_ticket",
    ),
    (
        "Support / customer operations",
        "Exporter les conversations client",
        "support.conversation.export",
        "support_desk",
        "export_customer_conversations",
    ),
    (
        "Support / customer operations",
        "Modifier les SLA",
        "support.sla.update",
        "support_desk",
        "modify_sla",
    ),
    (
        "Support / customer operations",
        "Reassigner un volume important de tickets",
        "support.ticket.bulk_reassign",
        "support_desk",
        "reassign_ticket_volume",
    ),
    (
        "Support / customer operations",
        "Acceder a des tickets VIP",
        "support.ticket.vip_access",
        "support_desk",
        "access_vip_tickets",
    ),
    (
        "Support / customer operations",
        "Partager des donnees support vers un outil externe",
        "support.data.external_share",
        "support_desk",
        "share_support_data_external",
    ),
    # --- Cloud / infrastructure ---
    (
        "Cloud / infrastructure",
        "Supprimer une base de donnees",
        "cloud.database.delete",
        "cloud",
        "delete_database",
    ),
    (
        "Cloud / infrastructure",
        "Supprimer un bucket S3",
        "cloud.bucket.delete",
        "cloud",
        "delete_s3_bucket",
    ),
    (
        "Cloud / infrastructure",
        "Rendre un bucket public",
        "cloud.bucket.public",
        "cloud",
        "make_bucket_public",
    ),
    (
        "Cloud / infrastructure",
        "Modifier une security group",
        "cloud.sg.update",
        "cloud",
        "modify_security_group",
    ),
    (
        "Cloud / infrastructure",
        "Ouvrir un port reseau sensible",
        "cloud.network.port_open_sensitive",
        "cloud",
        "open_sensitive_port",
    ),
    (
        "Cloud / infrastructure",
        "Supprimer des backups",
        "cloud.backup.delete",
        "cloud",
        "delete_backups",
    ),
    (
        "Cloud / infrastructure",
        "Modifier une configuration Kubernetes",
        "cloud.k8s.config_update",
        "cloud",
        "modify_k8s_config",
    ),
    (
        "Cloud / infrastructure",
        "Supprimer un pod critique",
        "cloud.k8s.pod_delete_critical",
        "cloud",
        "delete_critical_pod",
    ),
    (
        "Cloud / infrastructure",
        "Deployer une image non validee",
        "cloud.deploy.unverified_image",
        "cloud",
        "deploy_unvalidated_image",
    ),
    (
        "Cloud / infrastructure",
        "Modifier une variable d'environnement",
        "cloud.env.var_update",
        "cloud",
        "modify_env_variable",
    ),
    (
        "Cloud / infrastructure",
        "Supprimer une cle KMS",
        "cloud.kms.key_delete",
        "cloud",
        "delete_kms_key",
    ),
    (
        "Cloud / infrastructure",
        "Modifier les permissions IAM cloud",
        "cloud.iam.permission_update",
        "cloud",
        "modify_cloud_iam",
    ),
    # --- RH ---
    ("RH", "Modifier un salaire", "hr.salary.update", "hris", "modify_salary"),
    ("RH", "Supprimer un employe", "hr.employee.delete", "hris", "delete_employee"),
    (
        "RH",
        "Changer un statut contractuel",
        "hr.contract.status_update",
        "hris",
        "change_contract_status",
    ),
    (
        "RH",
        "Acceder a des dossiers RH sensibles",
        "hr.record.sensitive_access",
        "hris",
        "access_sensitive_hr_records",
    ),
    ("RH", "Exporter des donnees collaborateurs", "hr.data.export", "hris", "export_employee_data"),
    ("RH", "Modifier des conges", "hr.leave.update", "hris", "modify_leave"),
    ("RH", "Creer une fiche employe", "hr.employee.create", "hris", "create_employee_record"),
    (
        "RH",
        "Envoyer une communication RH officielle",
        "hr.communication.official_send",
        "hris",
        "send_official_hr_comm",
    ),
    (
        "RH",
        "Modifier des droits d'acces a un employe",
        "hr.access.update",
        "hris",
        "modify_employee_access_rights",
    ),
    # --- Juridique / conformite ---
    (
        "Juridique / conformite",
        "Generer ou envoyer un contrat",
        "legal.contract.send",
        "legal_dms",
        "generate_or_send_contract",
    ),
    (
        "Juridique / conformite",
        "Modifier une clause contractuelle",
        "legal.clause.update",
        "legal_dms",
        "modify_contract_clause",
    ),
    (
        "Juridique / conformite",
        "Supprimer un document legal",
        "legal.document.delete",
        "legal_dms",
        "delete_legal_document",
    ),
    (
        "Juridique / conformite",
        "Partager un document confidentiel",
        "legal.document.confidential_share",
        "legal_dms",
        "share_confidential_document",
    ),
    (
        "Juridique / conformite",
        "Accepter des conditions contractuelles",
        "legal.terms.accept",
        "legal_dms",
        "accept_contract_terms",
    ),
    (
        "Juridique / conformite",
        "Soumettre un document reglementaire",
        "legal.regulatory.submit",
        "legal_dms",
        "submit_regulatory_document",
    ),
    (
        "Juridique / conformite",
        "Modifier une politique interne",
        "legal.policy.internal_update",
        "legal_dms",
        "modify_internal_policy",
    ),
    (
        "Juridique / conformite",
        "Supprimer un element de preuve",
        "legal.evidence.delete",
        "legal_dms",
        "delete_evidence_item",
    ),
    (
        "Juridique / conformite",
        "Exporter un dossier d'audit",
        "legal.audit.export",
        "legal_dms",
        "export_audit_file",
    ),
    # --- Produit / contenu ---
    (
        "Produit / contenu",
        "Publier en production",
        "product.release.publish",
        "product_cms",
        "publish_production",
    ),
    (
        "Produit / contenu",
        "Modifier une page publique",
        "product.page.public_update",
        "product_cms",
        "modify_public_page",
    ),
    (
        "Produit / contenu",
        "Envoyer une campagne marketing",
        "product.campaign.send",
        "product_cms",
        "send_marketing_campaign",
    ),
    (
        "Produit / contenu",
        "Modifier un pricing",
        "product.pricing.update",
        "product_cms",
        "modify_pricing",
    ),
    (
        "Produit / contenu",
        "Supprimer du contenu",
        "product.content.delete",
        "product_cms",
        "delete_content",
    ),
    (
        "Produit / contenu",
        "Changer une configuration produit",
        "product.config.update",
        "product_cms",
        "change_product_config",
    ),
    (
        "Produit / contenu",
        "Activer une fonctionnalite pour tous les clients",
        "product.feature.enable_all",
        "product_cms",
        "enable_feature_all_customers",
    ),
    (
        "Produit / contenu",
        "Desactiver une fonctionnalite critique",
        "product.feature.critical_disable",
        "product_cms",
        "disable_critical_feature",
    ),
    (
        "Produit / contenu",
        "Modifier un onboarding utilisateur",
        "product.onboarding.update",
        "product_cms",
        "modify_user_onboarding",
    ),
)


def build() -> dict:
    """Build the referential dict, enriching each Annex C row from the catalog.

    Aborts (ValueError) if a row points at an action absent from the catalog --
    the referential may never reference an action the platform does not govern.
    """
    catalog = load_catalog()
    actions: list[dict] = []
    for category, label, annex_type, target_system, action_type in ANNEX_C_SOURCE:
        spec = catalog.get(target_system, action_type)
        if spec is None:
            raise ValueError(
                f"Annex C row '{annex_type}' maps to {target_system}/{action_type} "
                f"which is absent from the catalog"
            )
        actions.append(
            {
                "category": category,
                "label": label,
                "annex_c_action_type": annex_type,
                "target_system": spec.target_system,
                "action_type": spec.action_type,
                "criticality": spec.criticality.value,
                "criticality_label": CRITICALITY_LABEL[spec.criticality],
                "risk_level": spec.risk_level.value,
                "risk_score": RISK_SCORE[spec.risk_level],
                "verdict_privileged": spec.verdict_privileged.value,
                "verdict_default": spec.verdict_default.value,
                "privileged_roles": list(spec.privileged_roles),
            }
        )
    return {
        "source": "AgentRail spec Annex C -- governed-action referential",
        "schema": "repo (target_system, action_type); criticality C1-C4 per catalog/model.py",
        "criticality_legend": {k.value: CRITICALITY_LABEL[k] for k in Criticality},
        "count": len(actions),
        "actions": actions,
    }


def render(data: dict) -> str:
    """Stable, deterministic JSON text (2-space indent, trailing newline)."""
    return json.dumps(data, ensure_ascii=False, indent=2) + "\n"


def main() -> int:
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT.write_text(render(build()), encoding="utf-8")
    print(f"wrote {OUTPUT} ({build()['count']} actions)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
